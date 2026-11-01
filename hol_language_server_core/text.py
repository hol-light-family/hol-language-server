"""A file read for lookup. Positions inside it are offsets into `text`.

Lines and characters are 0-based. Characters count Unicode code points;
LSP editors count UTF-16 code units, which agrees except for characters
outside the Basic Multilingual Plane.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cached_property

# An OCaml character literal (e.g., '"' or '\''), not a prime of an identifier.
CHAR_LITERAL = (
    r"(?<![\w'])'(?:\\(?:[\\'\"ntbr ]|\d{3}|x[0-9a-fA-F]{2}|o[0-7]{3})|[^\\'\n])'"
)

# The opening of an OCaml quoted string, such as `{|` or `{id|`.
QUOTED_STRING_OPEN = r"\{[a-z_]*\|"
# A whole one, up to the end of the text if it is not closed. Nothing escapes in it.
QUOTED_STRING = r"\{(?P<quote_id>[a-z_]*)\|[\s\S]*?(?:(?P<quote_close>\|(?P=quote_id)\})|\Z)"


@dataclass(frozen=True)
class Position:
    line: int
    character: int

    def translate(self, line_delta: int = 0, character_delta: int = 0) -> Position:
        return Position(self.line + line_delta, self.character + character_delta)

    def with_(self, line: int | None = None, character: int | None = None) -> Position:
        return Position(
            self.line if line is None else line,
            self.character if character is None else character,
        )


@dataclass(frozen=True)
class Range:
    start: Position
    end: Position


@dataclass(frozen=True)
class Location:
    path: str
    range: Range


def location(path: str, pos: Position) -> Location:
    return Location(path, Range(pos, pos))


# The `wordPattern` of vscode-hol-light/language-configuration.json.
WORD_PATTERN = re.compile(
    r"-?0[xX][0-9a-fA-F][0-9a-fA-F_]*(\.[0-9a-fA-F_]*)?([pP][+-]?\d[\d_]*)?"
    r"|-?0[oO][0-7][0-7_]*"
    r"|-?0[bB][01][01_]*"
    r"|-?\d[\d_]*(\.[\d_]*)?([eE][+-]?\d[\d_]*)?"
    r"|[A-Za-z_'][A-Za-z_'.0-9]*"
)


_ASTRAL_RE = re.compile("[\U00010000-\U0010FFFF]")


def astral_lines(text: str) -> dict[int, str]:
    """The lines holding a character outside the Basic Multilingual Plane,
    by line number: the only lines where code-point and UTF-16 columns differ."""
    if text.isascii() or _ASTRAL_RE.search(text) is None:
        return {}
    return {number: line for number, line in enumerate(text.split("\n")) if _ASTRAL_RE.search(line)}


class TextDoc:
    def __init__(self, path: str, text: str) -> None:
        self.path = path
        self.text = text
        self._line_starts: list[int] = []
        i = 0
        while True:
            self._line_starts.append(i)
            i = text.find("\n", i) + 1
            if i <= 0:
                break

    @cached_property
    def astral_lines(self) -> dict[int, str]:
        return astral_lines(self.text)

    @property
    def line_count(self) -> int:
        return len(self._line_starts)

    def line_at(self, line: int) -> str:
        start = self._line_starts[line]
        if line + 1 < len(self._line_starts):
            end = self._line_starts[line + 1] - 1
        else:
            end = len(self.text)
        return self.text[start:end].removesuffix("\r")

    def offset_at(self, pos: Position) -> int:
        if pos.line < 0:
            return 0
        if pos.line >= len(self._line_starts):
            return len(self.text)
        return min(
            self._line_starts[pos.line]
            + max(0, min(pos.character, len(self.line_at(pos.line)))),
            len(self.text),
        )

    def position_at(self, offset: int) -> Position:
        offset = max(0, min(offset, len(self.text)))
        starts = self._line_starts
        lo, hi = 0, len(starts)
        while lo < hi:
            mid = (lo + hi) >> 1
            if offset < starts[mid]:
                hi = mid
            else:
                lo = mid + 1
        line = lo - 1
        return Position(line, min(offset - starts[line], len(self.line_at(line))))

    def get_text(self, range: Range | None = None) -> str:
        if range is None:
            return self.text
        return self.text[self.offset_at(range.start):self.offset_at(range.end)]

    def get_word_range_at_position(self, pos: Position) -> Range | None:
        if pos.line < 0 or pos.line >= self.line_count:
            return None
        line = self.line_at(pos.line)
        at = 0
        while True:
            m = WORD_PATTERN.search(line, at)
            if m is None:
                return None
            start, end = m.start(), m.end()
            if start <= pos.character <= end:
                return Range(Position(pos.line, start), Position(pos.line, end))
            if start > pos.character:
                return None
            at = end
