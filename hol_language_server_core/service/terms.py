"""Where a position is inside a backquoted HOL term, the HOL name there, and
whether the term binds it."""

import re

from hol_language_server_core.parser import HOL_TOKEN_RE, skip_comments
from hol_language_server_core.service.tokens import REFERENCE_RE

# A binder and the names before its dot: `!x y.`, `?x.`, `?!x.`, `\x.`,
# `@x.`. Not the `\` of `/\` or `\/`. The names may carry types, which may
# hold spaces (`x:24 word`), `->`, `^` and commas.
_BINDER_RE = re.compile(r"(?<![/\\])(?:\?!|[!?\\@])(?!/)([\w'\s():^\->,]*?)\.")


def term_start(text: str, start: int, offset: int) -> int | None:
    """Offset of the backquote opening the HOL term the offset is inside,
    else None. Scans text from start, which is outside comments, strings,
    and terms."""
    pos = start
    while True:
        m = REFERENCE_RE.search(text, pos)
        if m is None or m.start() >= offset:
            return None
        if m.group(0) == "(*":
            pos = skip_comments(text, m.start())
            if pos > offset:
                return None
            continue
        if m.end() > offset:
            return m.start() if m.group(0).startswith("`") else None
        pos = m.end()


def _binder_names(group: str) -> list[str]:
    """The names of a binder group such as ` a (x:num) y:24 word`: a type
    after `:` runs to the closing parenthesis, or to the end."""
    names: list[str] = []
    depth = 0
    type_depth: int | None = None
    for token in re.findall(r"[\w']+|[():]", group):
        if token == "(":
            depth += 1
        elif token == ")":
            if type_depth == depth:
                type_depth = None
            depth -= 1
        elif token == ":":
            if type_depth is None:
                type_depth = depth
        elif type_depth is None:
            names.append(token)
    return names


def _in_scope(text: str, start: int, offset: int) -> bool:
    """Whether a binder body starting at start still runs at offset: it
    ends at the bracket that closes around the binder, or at a `;` of a
    list it is an element of."""
    depth = 0
    for char in text[start:offset]:
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
            if depth < 0:
                return False
        elif char == ";" and depth == 0:
            return False
    return True


def bound_in_term(text: str, start: int, offset: int, word: str) -> bool:
    """Whether a binder of the term opening at start binds the word at
    offset: the word is one of the binder's names, or in its body."""
    # Binders before the offset lie in the same term: the pattern holds no backquote.
    for m in _BINDER_RE.finditer(text, start + 1):
        if m.start() >= offset:
            break
        if word not in _binder_names(m.group(1)):
            continue
        if offset < m.end() or _in_scope(text, m.end(), offset):
            return True
    return False


def hol_word_at(line: str, character: int) -> tuple[int, int] | None:
    """Start and end of the HOL name or symbol at the character in a term,
    or just before it."""
    before: tuple[int, int] | None = None
    for m in HOL_TOKEN_RE.finditer(line):
        if m.start() > character:
            break
        if character < m.end():
            before = m.start(), m.end()
            break
        if m.end() == character:
            before = m.start(), m.end()
    if before is None or line[before[0]] in "()[]{},;.":
        return None
    return before
