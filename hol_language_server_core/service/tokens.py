"""Scanning OCaml source for names, skipping comments, strings, and terms."""

import re

from hol_language_server_core.parser import Lexer, Token, TokenType
from hol_language_server_core.text import CHAR_LITERAL, QUOTED_STRING


# Comments match by their opening only (they nest).
REFERENCE_RE = re.compile(
    r"\(\*"
    + r'|"(?:[^"\\]|\\[\s\S])*"'
    + r"|" + QUOTED_STRING
    + r"|`[^`]*`"
    + r"|" + CHAR_LITERAL
    + r"|\d[\w'.]*"
    + r"|[A-Za-z_][\w']*(?:\.[A-Za-z_][\w']*)*"
)


def is_name_start(word: str) -> bool:
    return word[:1] == "_" or "a" <= word[:1] <= "z" or "A" <= word[:1] <= "Z"


def enclosing_token(text: str, start: int, offset: int) -> Token | None:
    """The comment, string, or term holding the offset, lexed like the
    parser from start, which is outside all three. One the text ends
    inside holds the end of the text too."""
    lexer = Lexer(text)
    lexer.pos = start
    while True:
        token = lexer.next_token()
        if token.type == TokenType.eof or token.start_pos >= offset:
            return None
        if token.end_pos > offset or (token.end_pos == offset and not token.closed):
            return token if token.type in (TokenType.comment, TokenType.string, TokenType.term) else None
