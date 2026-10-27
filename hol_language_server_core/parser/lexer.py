"""Tokens of OCaml source. A HOL term, a string, or a comment is one token."""

from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass
from enum import IntEnum

from hol_language_server_core.text import CHAR_LITERAL, Position


def line_number(line_starts: list[int], pos: int) -> int:
    return bisect_right(line_starts, pos) - 1


def end_position(line_starts: list[int], end: int) -> Position:
    # The end of text[:end], on the line of its last character.
    line = line_number(line_starts, end - 1)
    return Position(line, end - line_starts[line])


def skip_comments(text: str, pos: int) -> int:
    """End offset of the comment starting at pos. Assumes pos is at `(*`."""
    n = len(text)
    level = 1
    i = pos + 1
    while i < n:
        i = text.find("*", i + 1)
        if i < 0:
            return n
        if text[i - 1] == "(":
            level += 1
        elif i + 1 < n and text[i + 1] == ")":
            level -= 1
            if level <= 0:
                return i + 2
            i += 1
    return n


class TokenType(IntEnum):
    eof = 0
    comment = 1
    string = 2
    term = 3
    statement_separator = 4
    operator = 5
    identifier = 6
    other = 7


_TOKEN_RE = re.compile(
    CHAR_LITERAL
    + r"|\(\*"
    + r"|[" + '"' + r"`'()\],{}]"
    + r"|\[\|?|\|\]"
    + r"|[-+*/#><=!?~%&$^@:.|]+"
    + r"|;+"
    + r"|[_a-zA-Z][\w'.]*"
    + r"|\d[\w'.]*"
)

_OPERATOR_CHARS = set("-+*/#><=!?~%&$^@:.|")


OCAML_KEYWORDS = set(
    "and as assert asr begin class constraint do done downto else end "
    "exception external false for fun function functor if in include inherit "
    "initializer land lazy let lor lsl lsr lxor match method mod module mutable "
    "new nonrec object of open or private rec sig struct then to true try type "
    "val virtual when while with".split()
)


class Token:
    def __init__(self, token_type: TokenType, start: int, end: int, value: str | None = None) -> None:
        self.type = token_type
        self.value = value
        self.start_pos = start
        self.end_pos = end
        self._start_position: Position | None = None
        self._end_position: Position | None = None

    def get_value(self, text: str) -> str:
        return self.value if self.value is not None else text[self.start_pos:self.end_pos]

    def get_start_position(self, line_starts: list[int]) -> Position:
        if self._start_position is None:
            line = line_number(line_starts, self.start_pos)
            self._start_position = Position(line, self.start_pos - line_starts[line])
        return self._start_position

    def get_end_position(self, line_starts: list[int]) -> Position:
        if self._end_position is None:
            self._end_position = end_position(line_starts, self.end_pos)
        return self._end_position


class ParserError(Exception):
    def __init__(self, message: str, token: Token | None = None) -> None:
        super().__init__(message)
        self.token = token


@dataclass
class LexerState:
    pos: int
    cur_token: Token | None = None


class Lexer:
    """A stream of tokens over the text, with one token of lookahead."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.eof_token = Token(TokenType.eof, len(text), len(text), "")
        self._line_starts: list[int] = []
        i = 0
        while True:
            self._line_starts.append(i)
            i = text.find("\n", i) + 1
            if i <= 0:
                break
        self.pos = 0
        self._cur: Token | None = None

    def reset_state(self, state: LexerState) -> None:
        self.pos = state.pos
        self._cur = state.cur_token

    def save_state(self) -> LexerState:
        return LexerState(self.pos, self._cur)

    def peek(self) -> Token:
        if self._cur is None:
            self._cur = self.next_token()
        return self._cur

    def next_token(self) -> Token:
        if self._cur is not None:
            res = self._cur
            self._cur = None
            return res
        m = _TOKEN_RE.search(self.text, self.pos)
        if m is None:
            self.pos = len(self.text)
            return self.eof_token
        tok = m.group(0)
        if tok == "(*":
            return self._parse_comment(m.start())
        if tok == '"':
            return self._parse_string(m.start())
        if tok == "`":
            return self._parse_term(m.start())
        self.pos = m.end()
        if tok.startswith(";;"):
            kind = TokenType.statement_separator
        elif tok[0] == "_" or "a" <= tok[0] <= "z" or "A" <= tok[0] <= "Z":
            kind = TokenType.identifier
        elif tok != "|]" and tok[0] in _OPERATOR_CHARS:
            kind = TokenType.operator
        else:
            kind = TokenType.other
        return Token(kind, m.start(), self.pos, tok)

    def _parse_comment(self, pos: int) -> Token:
        pattern = re.compile(r"\(\*|\*\)")
        p = pos + 2
        level = 1
        while True:
            m = pattern.search(self.text, p)
            if m is None:
                break
            if m.group(0) == "(*":
                level += 1
            elif level - 1 <= 0:
                level = 0
                self.pos = m.end()
                return Token(TokenType.comment, pos, self.pos)
            else:
                level -= 1
            p = m.end()
        self.pos = len(self.text)
        return Token(TokenType.comment, pos, self.pos)

    def _parse_string(self, pos: int) -> Token:
        pattern = re.compile(r'"|\\.')
        p = pos + 1
        while True:
            m = pattern.search(self.text, p)
            if m is None:
                break
            if m.group(0) == '"':
                self.pos = m.end()
                return Token(TokenType.string, pos, self.pos)
            p = m.end()
        self.pos = len(self.text)
        return Token(TokenType.string, pos, self.pos)

    def _parse_term(self, pos: int) -> Token:
        end = self.text.find("`", pos + 1)
        self.pos = len(self.text) if end < 0 else end + 1
        return Token(TokenType.term, pos, self.pos)

    def skip_comments(self) -> None:
        while self.peek().type == TokenType.comment:
            self.next_token()

    def peek_skip_comments(self) -> Token:
        self.skip_comments()
        return self.peek()

    def next_skip_comments(self) -> Token:
        self.skip_comments()
        return self.next_token()

    def expect(self, value: str | TokenType) -> Token:
        token = self.next_skip_comments()
        if isinstance(value, str):
            ok = token.value == value
        else:
            ok = token.type == value
        if not ok:
            raise ParserError(f"{value if isinstance(value, str) else value.name} expected", token)
        return token

    def match1(self, value: str | TokenType) -> Token | None:
        """Consume the next non-comment token when it matches; else None."""
        token = self.peek_skip_comments()
        if isinstance(value, str):
            ok = token.value == value
        else:
            ok = token.type == value
        if ok:
            return self.next_token()
        return None

    def _skip_while_eq(self, value: str) -> None:
        while self.peek_skip_comments().value == value:
            self.next_token()
