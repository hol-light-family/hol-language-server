"""Where a position is inside a backquoted HOL term, and the HOL name there."""

from hol_language_server_core.parser import HOL_TOKEN_RE, skip_comments
from hol_language_server_core.service.tokens import REFERENCE_RE


def in_term(text: str, start: int, offset: int) -> bool:
    """Whether the offset is inside a backquoted HOL term. Scans text from
    start, which is outside comments, strings, and terms."""
    pos = start
    while True:
        m = REFERENCE_RE.search(text, pos)
        if m is None or m.start() >= offset:
            return False
        if m.group(0) == "(*":
            pos = skip_comments(text, m.start())
            if pos > offset:
                return False
            continue
        if m.end() > offset:
            return m.group(0).startswith("`")
        pos = m.end()


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
