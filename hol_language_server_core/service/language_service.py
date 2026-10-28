"""Static lookup over HOL Light sources. The servers are thin layers over it."""

import os
import re
from collections.abc import Callable

from hol_language_server_core import util
from hol_language_server_core.config import Settings, expand_root_paths
from hol_language_server_core.database import Database, Dependency
from hol_language_server_core.parser import OCAML_KEYWORDS, Definition, Module, skip_comments
from hol_language_server_core.service.results import (DefinitionTarget, MissingLoad, Reference, SourceInfo,
                                                      SymbolInfo, definition_symbol, module_symbol)
from hol_language_server_core.service.scope import bound_names, local_binding
from hol_language_server_core.service.terms import bound_in_term, hol_word_at, term_start
from hol_language_server_core.service.tokens import REFERENCE_RE, is_name_start
from hol_language_server_core.text import Position, Range, TextDoc, location


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
        if word_range is None or "." in word or not is_name_start(word) or word in OCAML_KEYWORDS:
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

    def term_constants(self, doc: TextDoc, position: Position) -> tuple[list[Definition], Range | None] | None:
        """Inside a backquoted term, the HOL constants the name at the
        position names, and the name's range. None outside terms and in an
        `^` antiquotation, which names an OCaml value."""
        if position.line < 0 or position.line >= doc.line_count:
            return None
        offset = doc.offset_at(position)
        file = self.database.get_file_index(doc.path)
        # Top-level items start outside terms: scan from the last one.
        start = max((d.source_start for d in file.definitions
                     if d.source_start is not None and d.source_start <= offset), default=0) if file else 0
        term = term_start(doc.text, start, offset)
        if term is None:
            return None
        line = doc.line_at(position.line)
        span = hol_word_at(line, position.character)
        if span is None:
            return [], None
        begin, end = span
        # `^x`, but not the `^` of a type such as `real^N`.
        if line[begin - 1:begin] == "^" and not re.match(r"[\w']", line[begin - 2:begin - 1]):
            return None
        word_range = Range(position.with_(character=begin), position.with_(character=end))
        word = line[begin:end]
        # A variable the term binds hides a constant of its name.
        if bound_in_term(doc.text, term, offset - position.character + begin, word):
            return [], word_range
        return self.database.find_constants(word, doc.path), word_range

    def hover(self, doc: TextDoc, position: Position) -> tuple[str, Range | None] | None:
        """The statement of the definition at the position, else None.
        None for local names: they have no statement. Inside a term, the
        statement of the definition of the HOL constant."""
        constants = self.term_constants(doc, position)
        if constants is not None:
            found, word_range = constants
            return (found[0].to_string(), word_range) if found else None
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
        """Go to Definition: the file named by a `needs` string; inside a term,
        the HOL constants the name names; else the definitions and modules
        the word at the position names."""
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
        constants = self.term_constants(doc, position)
        if constants is not None:
            return [DefinitionTarget(loc.path, loc.range) for loc in (c.get_location() for c in constants[0])]
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
            m = REFERENCE_RE.search(text, pos)
            if m is None or m.start() >= end:
                break
            word = m.group(0)
            pos = m.end()
            if word == "(*":
                pos = skip_comments(text, m.start())
                continue
            if not is_name_start(word):
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
