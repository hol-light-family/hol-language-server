"""Which names are local: bound by `let ... in`, a parameter, or an arm.
Heuristics over brackets and keywords, not the full OCaml grammar."""

import re
from dataclasses import dataclass

from hol_language_server_core.parser import OCAML_KEYWORDS, skip_comments
from hol_language_server_core.service.tokens import REFERENCE_RE, is_name_start


# Tokens for binding positions: REFERENCE_RE plus pattern punctuation.
_BINDER_RE = re.compile(REFERENCE_RE.pattern + r"|->|\|\||[|=()[\]{};]")

# Where each binding construct's patterns end.
_BINDER_ENDS = {
    "let": "=", "and": "=", "for": "=",
    "fun": "->", "function": "->", "with": "->", "|": "->",
}
_BINDER_STOPS = {"in", "let", "then", "else", "do", ";", ";;"}
_MAX_BINDER_TOKENS = 40


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
                elif is_name_start(tok) and tok not in OCAML_KEYWORDS:
                    pending.append(tok)
                continue
        if tok in _BINDER_ENDS:
            pending = []
            terminator = _BINDER_ENDS[tok]
            depth = 0
            count = 0
    return bound


# Tokens for scopes: REFERENCE_RE plus pattern and bracket punctuation.
_SCOPE_RE = re.compile(REFERENCE_RE.pattern + r"|->|::|:=|\|\||[|=:()[\]{};]")
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
                elif (is_name_start(tok) and tok not in OCAML_KEYWORDS
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
