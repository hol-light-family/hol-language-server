"""Static lookup over HOL Light sources. The MCP server is a thin layer over it."""

import os
import re
from collections.abc import Callable
from dataclasses import dataclass

from hol_language_server_core import util
from hol_language_server_core.config import Settings, expand_root_paths
from hol_language_server_core.database import Database, Dependency
from hol_language_server_core.parser import DEFINITION_TYPE_NAMES, OCAML_KEYWORDS, Definition, Module, skip_comments
from hol_language_server_core.text import CHAR_LITERAL, Position, Range, TextDoc, location


@dataclass
class SymbolInfo:
    name: str
    # Qualified with module names.
    full_name: str
    kind: str  # theorem, definition, term, value, or module
    path: str
    # Offset of the name in the file text.
    offset: int
    position: Position
    # The term of a theorem, definition, or term; the type of a value.
    content: str | None = None
    # Definitions only: offsets of the whole item defining the name.
    source_start: int | None = None
    source_end: int | None = None
    # Modules only.
    end_position: Position | None = None
    # The full name of the enclosing module.
    container: str | None = None


@dataclass
class DefinitionTarget:
    path: str
    range: Range


@dataclass
class MissingLoad:
    # The file name as written, and where it is written.
    name: str
    range: Range


@dataclass
class SourceInfo:
    doc: TextDoc
    start: int
    end: int


@dataclass
class Reference:
    # The name as written in the source.
    name: str
    # What the name refers to there (as Go to Definition).
    symbols: list[SymbolInfo]


# Comments match by their opening only (they nest).
_REFERENCE_RE = re.compile(
    r"\(\*"
    + r'|"(?:[^"\\]|\\[\s\S])*"'
    + r"|`[^`]*`"
    + r"|" + CHAR_LITERAL
    + r"|\d[\w'.]*"
    + r"|[A-Za-z_][\w']*(?:\.[A-Za-z_][\w']*)*"
)

# Tokens for binding positions: REFERENCE_RE plus pattern punctuation.
_BINDER_RE = re.compile(_REFERENCE_RE.pattern + r"|->|\|\||[|=()[\]{};]")

# Where each binding construct's patterns end.
_BINDER_ENDS = {
    "let": "=", "and": "=", "for": "=",
    "fun": "->", "function": "->", "with": "->", "|": "->",
}
_BINDER_STOPS = {"in", "let", "then", "else", "do", ";", ";;"}
_MAX_BINDER_TOKENS = 40


def _is_name_start(word: str) -> bool:
    return word[:1] == "_" or "a" <= word[:1] <= "z" or "A" <= word[:1] <= "Z"


def bound_names(text: str, start: int, end: int) -> set[str]:
    """Names bound by `let`, `and`, `fun`, `function`, `for`, and match or
    try arms in text[start, end). A heuristic, not scope analysis: a name
    bound anywhere in the range counts as bound everywhere in it."""
    bound: set[str] = set()
    pending: list[str] | None = None
    terminator = ""
    depth = 0
    count = 0
    pos = start
    while True:
        m = _BINDER_RE.search(text, pos)
        if m is None or m.start() >= end:
            break
        tok = m.group(0)
        pos = m.end()
        if tok == "(*":
            pos = skip_comments(text, m.start())
            continue
        if pending is not None:
            if depth == 0 and tok == terminator:
                bound.update(pending)
                pending = None
                continue
            count += 1
            if (
                count > _MAX_BINDER_TOKENS
                or (depth == 0 and tok in _BINDER_STOPS)
                or (depth == 0 and tok == ")")
            ):
                pending = None
            else:
                if tok in ("(", "[", "{"):
                    depth += 1
                elif tok in (")", "]", "}"):
                    depth -= 1
                elif _is_name_start(tok) and tok not in OCAML_KEYWORDS:
                    pending.append(tok)
                continue
        if tok in _BINDER_ENDS:
            pending = []
            terminator = _BINDER_ENDS[tok]
            depth = 0
            count = 0
    return bound


# Tokens for scopes: REFERENCE_RE plus pattern and bracket punctuation.
_SCOPE_RE = re.compile(_REFERENCE_RE.pattern + r"|->|::|:=|\|\||[|=:()[\]{};]")
_SCOPE_OPEN = {"(", "[", "{", "begin", "do"}
_SCOPE_CLOSE = {")", "]", "}", "end", "done"}
# Where each binding construct's patterns end, and whether its names end at
# the next `|` (match and function arms).
_SCOPE_BINDERS = {
    "let": ("=", False), "and": ("=", False), "for": ("=", False),
    "fun": ("->", False), "function": ("->", True), "with": ("->", True), "|": ("->", True),
}


@dataclass
class _Binding:
    name: str
    offset: int
    depth: int
    arm: bool


@dataclass
class _LetFrame:
    depth: int
    # Names the `let` binds for the code after its `in`.
    heads: list[tuple[str, int]]
    # Parameters of the binding being read, in scope up to `and` or `in`.
    params: list[_Binding]


@dataclass
class _Pattern:
    keyword: str
    terminator: str
    arm: bool
    names: list[tuple[str, int]]
    depth: int = 0
    tokens: int = 0
    rec: bool = False
    # The first token of a `let` pattern was a name: `let f x y = ...`.
    head_first: bool = False
    # Depth of a type annotation being skipped.
    type_depth: int | None = None
    guard: bool = False


def local_binding(text: str, start: int, offset: int, word: str) -> int | None:
    """Offset of the local binding of `word` in scope at `offset`, scanning
    text[start, offset) (start: the beginning of the top-level item): a name
    bound by `let ... in`, a parameter, or a match or try arm variable.
    `offset` itself when the word there is a binding. None when the word is
    not bound locally. A heuristic: it tracks brackets, `let ... in`, and
    arms, not the full OCaml grammar."""
    active: list[_Binding] = []
    frames: list[_LetFrame] = []
    pending: _Pattern | None = None
    depth = 0

    def activate(names: list[tuple[str, int]], arm: bool) -> list[_Binding]:
        new = [_Binding(name, off, depth, arm) for name, off in names]
        active.extend(new)
        return new

    def finish(p: _Pattern) -> None:
        if p.keyword in ("let", "and"):
            frame = next((f for f in reversed(frames) if f.depth == depth), None)
            if frame is None:
                return
            # `let f x y = ...`: f is bound after `in`, x and y in the body.
            if p.head_first and len(p.names) > 1:
                heads, params = p.names[:1], p.names[1:]
            else:
                heads, params = p.names, []
            frame.heads.extend(heads)
            frame.params = activate(params, False)
            if p.rec:
                activate(heads, False)
        else:
            activate(p.names, p.arm)

    pos = start
    while True:
        m = _SCOPE_RE.search(text, pos)
        if m is None or m.start() > offset:
            break
        tok = m.group(0)
        pos = m.end()
        if tok == "(*":
            pos = skip_comments(text, m.start())
            continue
        at_word = m.start() == offset
        if pending is not None:
            p = pending
            if p.depth == 0 and tok == p.terminator:
                if at_word:
                    break
                pending = None
                finish(p)
                continue
            p.tokens += 1
            if p.tokens > _MAX_BINDER_TOKENS or (p.depth == 0 and (tok in _BINDER_STOPS or tok in _SCOPE_CLOSE)):
                pending = None
            else:
                if tok in ("(", "[", "{"):
                    p.depth += 1
                elif tok in (")", "]", "}"):
                    p.depth -= 1
                    if p.type_depth is not None and p.depth < p.type_depth:
                        p.type_depth = None
                elif tok == ":":
                    if p.type_depth is None:
                        p.type_depth = p.depth
                elif tok == "when":
                    p.guard = True
                elif tok == "rec" and p.tokens == 1 and p.keyword == "let":
                    p.rec = True
                    p.tokens = 0
                elif (_is_name_start(tok) and tok not in OCAML_KEYWORDS
                      and p.type_depth is None and not p.guard):
                    if p.tokens == 1 and p.keyword in ("let", "and"):
                        p.head_first = True
                    if at_word and tok == word:
                        return offset
                    p.names.append((tok, m.start()))
                if at_word:
                    break
                continue
        if at_word:
            break
        if tok in _SCOPE_OPEN:
            depth += 1
        elif tok in _SCOPE_CLOSE:
            depth -= 1
            active = [b for b in active if b.depth <= depth]
            frames = [f for f in frames if f.depth <= depth]
        elif tok == "in":
            frame = next((f for f in reversed(frames) if f.depth == depth), None)
            if frame is not None:
                active = [b for b in active if b not in frame.params]
                activate([h for h in frame.heads if all(b.offset != h[1] for b in active)], False)
                frames.remove(frame)
        elif tok in _SCOPE_BINDERS:
            terminator, arm = _SCOPE_BINDERS[tok]
            if arm:
                active = [b for b in active if not (b.arm and b.depth == depth)]
            if tok == "let":
                frames.append(_LetFrame(depth, [], []))
            elif tok == "and":
                frame = next((f for f in reversed(frames) if f.depth == depth), None)
                if frame is None:
                    continue
                active = [b for b in active if b not in frame.params]
                frame.params = []
            pending = _Pattern(tok, terminator, arm, [])
    for b in reversed(active):
        if b.name == word:
            return b.offset
    return None


def definition_symbol(defn: Definition) -> SymbolInfo:
    return SymbolInfo(
        name=defn.name,
        full_name=defn.full_name,
        kind=DEFINITION_TYPE_NAMES[defn.def_type],
        path=defn.get_file_path(),
        offset=defn.offset,
        content=defn.content or None,
        source_start=defn.source_start,
        source_end=defn.source_end,
        position=defn.position,
        container=defn.module.full_name if defn.module is not None else None,
    )


def module_symbol(mod: Module) -> SymbolInfo:
    return SymbolInfo(
        name=mod.name,
        full_name=mod.full_name,
        kind="module",
        path=mod.get_file_path(),
        offset=mod.start,
        position=mod.position,
        end_position=mod.end_position,
        container=mod.parent.full_name if mod.parent is not None else None,
    )


class HolLanguageService:
    def __init__(self, settings: Settings) -> None:
        self.database = Database()
        self._settings = settings
        # Contents of documents open in an editor (they may differ from disk).
        self._overlays: dict[str, TextDoc] = {}

    @property
    def root_paths(self) -> list[str]:
        return expand_root_paths(self._settings)

    def open_document(self, file_path: str, text: str) -> TextDoc:
        doc = TextDoc(file_path, text)
        self._overlays[file_path] = doc
        return doc

    def close_document(self, file_path: str) -> None:
        self._overlays.pop(file_path, None)

    def get_document(self, file_path: str) -> TextDoc:
        if file_path in self._overlays:
            return self._overlays[file_path]
        return TextDoc(file_path, util.read_text(file_path))

    def index(self, file_path: str, full: bool) -> list[Dependency]:
        """Index the file and its dependencies. Returns unresolved ones."""
        doc = self.get_document(file_path)
        return self.database.index_document_with_dependencies(
            doc, self._settings.hol_path, self.root_paths, full, self._settings.custom_commands
        )

    def index_workspace(self) -> list[Dependency]:
        """Index every .ml and .hl file under the workspace root, except
        hidden directories and node_modules. Returns the unresolved dependencies."""
        files: list[str] = []

        def walk(directory: str) -> None:
            for entry in util.read_dir(directory):
                if entry.name.startswith(".") or entry.name == "node_modules":
                    continue
                path = os.path.join(directory, entry.name)
                if entry.is_dir(follow_symlinks=True):
                    walk(path)
                elif entry.is_file(follow_symlinks=True) and re.search(
                    r"\.(?:ml|hl)$", entry.name
                ):
                    files.append(path)

        walk(self._settings.workspace)
        files.sort()
        unresolved: list[Dependency] = []
        for file in files:
            unresolved.extend(self.index(file, False))
        return unresolved

    def find_symbols(self, name: str, deps: set[str] | None = None) -> list[SymbolInfo]:
        """Definitions and modules of the name in all indexed files (or the
        given files only). The name may carry module qualifiers. Exact
        full-name matches come first, suffix matches after."""
        names = name.split(".")
        last = names[-1]
        defs, mods = self.database.find_all_by_name(last, deps)

        def qualified(item: Definition | Module) -> bool:
            return (
                len(names) == 1
                or item.full_name == name
                or item.full_name.endswith("." + name)
            )

        symbols = [module_symbol(m) for m in mods if qualified(m)] + [
            definition_symbol(d) for d in defs if qualified(d)
        ]
        if len(names) > 1:
            # Stable: index order within each rank.
            symbols.sort(key=lambda s: s.full_name != name)
        return symbols

    def local_binding(self, doc: TextDoc, word: str, word_range: Range | None) -> int | None:
        """Offset of the local binding (`let ... in`, a parameter, an arm
        variable) that the word at word_range names, else None. Names that
        are top-level definitions are left to the index."""
        if word_range is None or "." in word or not _is_name_start(word) or word in OCAML_KEYWORDS:
            return None
        file = self.database.get_file_index(doc.path)
        if file is None:
            return None
        offset = doc.offset_at(word_range.start)
        item = next((d for d in file.definitions
                     if d.source_start is not None and d.source_end is not None
                     and d.source_start <= offset < d.source_end), None)
        if item is None or item.source_start is None:
            return None
        found = local_binding(doc.text, item.source_start, offset, word)
        if found is None or any(d.offset == found for d in file.definitions):
            return None
        return found

    def hover(self, doc: TextDoc, position: Position) -> tuple[str, Range | None] | None:
        """The statement of the definition at the position, else None.
        None for local names: they have no statement."""
        word, word_range = util.get_word_at_position(doc, position)
        if not word:
            return None
        if self.local_binding(doc, word, word_range) is not None:
            return None
        defs, mods = self.database.find_definitions_and_modules(
            word, doc.path, doc.offset_at(position)
        )
        if defs:
            return defs[0].to_string(), word_range
        mod = next(iter(mods), None)
        if mod is not None:
            return mod.to_string(), word_range
        return None

    def definition(self, doc: TextDoc, position: Position) -> list[DefinitionTarget]:
        """Go to Definition: the file named by a `needs` string, else the
        definitions and modules the word at the position names."""
        if position.line < 0 or position.line >= doc.line_count:
            return []
        imports = ["needs", "loads", "loadt", *self._settings.custom_commands.imports]
        m = re.match(r'^\s*(?:' + "|".join(imports) + r')\s*"(.*?)"', doc.line_at(position.line))
        if m:
            text = m.group(0)
            if text.find('"') <= position.character <= text.rfind('"'):
                dep = self.database.find_dependency(doc.path, m.group(1))
                loc = dep.get_location() if dep is not None else None
                if loc is None:
                    return []
                return [DefinitionTarget(loc.path, loc.range)]
        word, word_range = util.get_word_at_position(doc, position)
        if not word:
            return []
        local = self.local_binding(doc, word, word_range)
        if local is not None:
            loc = location(doc.path, doc.position_at(local))
            return [DefinitionTarget(loc.path, loc.range)]
        defs, mods = self.database.find_definitions_and_modules(
            word, doc.path, doc.offset_at(position)
        )
        return [
            DefinitionTarget(loc.path, loc.range)
            for loc in (found.get_location() for found in [*defs, *mods])
        ]

    def missing_loads(self, file_path: str) -> dict[str, list[MissingLoad]]:
        """For the file and every file it sees, the loads in it that cannot be
        found (an empty list when there are none)."""
        missing: dict[str, list[MissingLoad]] = {}
        for path in sorted({file_path} | self.database.all_dependencies(file_path)):
            file = self.database.get_file_index(path)
            if file is not None:
                missing[path] = [MissingLoad(dep.name, dep.range)
                                 for dep in file.dependencies if not dep.is_resolved]
        return missing

    def document_symbols(self, file_path: str) -> list[SymbolInfo]:
        """Definitions and modules of the file, in position order."""
        file = self.database.get_file_index(file_path)
        if file is None:
            return []
        symbols = [module_symbol(m) for m in file.modules] + [
            definition_symbol(d) for d in file.definitions
        ]
        return sorted(symbols, key=lambda s: (s.position.line, s.position.character))

    def search_symbols(self, predicate: Callable[[str], bool],
                       deps: set[str] | None = None) -> list[SymbolInfo]:
        """Definitions and modules whose names satisfy the predicate."""
        defs, mods = self.database.filter_by_name(predicate, deps)
        return [module_symbol(m) for m in mods] + [definition_symbol(d) for d in defs]

    def source(self, symbol: SymbolInfo) -> SourceInfo | None:
        """Document and offsets of the item defining the symbol. The document
        is read once; callers slice what they show from it."""
        if symbol.source_start is None or symbol.source_end is None:
            return None
        return SourceInfo(self.get_document(symbol.path), symbol.source_start, symbol.source_end)

    def references(self, doc: TextDoc, start: int, end: int,
                   exclude: SymbolInfo | None = None) -> list[Reference]:
        """Names used in text[start, end) of the document (outside comments,
        strings, and HOL terms) which name indexed definitions, in order of
        first use. Names bound in the range itself (parameters, `let ... in`,
        `fun`, match patterns) are left out."""
        text = doc.text
        seen = bound_names(text, start, end)
        result: list[Reference] = []

        def is_excluded(symbol: SymbolInfo) -> bool:
            return (
                exclude is not None
                and symbol.path == exclude.path
                and symbol.offset == exclude.offset
            )

        pos = start
        while True:
            m = _REFERENCE_RE.search(text, pos)
            if m is None or m.start() >= end:
                break
            word = m.group(0)
            pos = m.end()
            if word == "(*":
                pos = skip_comments(text, m.start())
                continue
            if not _is_name_start(word):
                continue
            if word in OCAML_KEYWORDS or word in seen:
                continue
            seen.add(word)
            defs, _ = self.database.find_definitions_and_modules(word, doc.path, m.start())
            symbols = [s for s in (definition_symbol(d) for d in defs) if not is_excluded(s)]
            if symbols:
                result.append(Reference(word, symbols))
        return result


def resolve_path(file_path: str, workspace: str) -> str:
    if os.path.isabs(file_path):
        return os.path.normpath(file_path)
    return os.path.normpath(os.path.join(workspace or os.getcwd(), file_path))
