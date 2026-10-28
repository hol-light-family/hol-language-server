"""Expected parser results written in an example file as `expect` comments.

The format is in tests/README.md, "Expected results in the example file".
"""

import re
from dataclasses import dataclass

from hol_language_server_core.parser import DefinitionType, ParseResult
from hol_language_server_core.text import Range

_EXPECT_RE = re.compile(r"\(\* expect( module)?: (.*?) \*\)")
_ITEM_RE = re.compile(r"([^\s:@]+)(?::(\w+))?(?:@(\d+):(\d+)-(\d+):(\d+))?$")


@dataclass
class Expected:
    full_name: str
    kind: DefinitionType
    # Lines and columns from 1, the end inclusive, as an editor shows them.
    source: tuple[int, int, int, int] | None
    # Offset of the comment that holds it.
    comment: int


def read_expectations(text: str) -> tuple[list[Expected], list[Expected]]:
    """The expected definitions and modules, in the order they are written."""
    definitions: list[Expected] = []
    modules: list[Expected] = []
    for comment in _EXPECT_RE.finditer(text):
        for item in comment.group(2).split():
            m = _ITEM_RE.match(item)
            if m is None:
                raise ValueError(f"Not an expected item: {item!r}")
            name, kind, *numbers = m.groups()
            source = None if numbers[0] is None else (
                int(numbers[0]), int(numbers[1]), int(numbers[2]), int(numbers[3]))
            expected = Expected(name, DefinitionType[kind or "other"], source, comment.start())
            (modules if comment.group(1) else definitions).append(expected)
    return definitions, modules


def _editor_range(source_range: Range) -> tuple[int, int, int, int]:
    start, end = source_range.start, source_range.end
    return start.line + 1, start.character + 1, end.line + 1, end.character


def _found_after(found: list[tuple[str, int]], expected: list[Expected]) -> list[str]:
    """Each found (name, offset) that does not lie between the comment of its
    expectation and the comment before that."""
    wrong: list[str] = []
    previous = current = -1
    for (name, offset), item in zip(found, expected, strict=True):
        if item.comment != current:
            previous, current = current, item.comment
        if not previous < offset < current:
            wrong.append(name)
    return wrong


def check_expectations(text: str, result: ParseResult) -> None:
    definitions, modules = read_expectations(text)
    assert definitions or modules, "The file has no expect comments"
    assert [(d.full_name, DefinitionType(d.def_type)) for d in result.definitions] == [
        (e.full_name, e.kind) for e in definitions]
    assert [m.full_name for m in result.modules] == [e.full_name for e in modules]
    assert _found_after([(d.full_name, d.offset) for d in result.definitions], definitions) == []
    assert _found_after([(m.full_name, m.start) for m in result.modules], modules) == []
    for found, expected in zip(result.definitions, definitions, strict=True):
        if expected.source is not None:
            assert found.source_range is not None
            assert (found.full_name, _editor_range(found.source_range)) == (
                expected.full_name, expected.source)
