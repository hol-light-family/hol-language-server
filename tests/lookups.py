"""Go to Definition and hover results written in an example file as comments.

The format is in tests/README.md, "Looked-up names in the example file".
"""

import os
import re
from dataclasses import dataclass

from hol_language_server_core.service import HolLanguageService
from hol_language_server_core.text import TextDoc

_DIRECTIVE_RE = re.compile(r"\(\* (goto|hover): (.*?) =>\s+(.*?)\s+\*\)", re.DOTALL)


@dataclass
class _Use:
    snippet: str
    skip: int


@dataclass
class _GotoTarget:
    snippet: str
    skip: int
    # Relative to the examples directory; None is the file holding the comment.
    relpath: str | None


def _parse_use(raw: str) -> _Use:
    text, plus, skip = raw.strip().rpartition(" +")
    if plus and skip.isdigit():
        return _Use(text, int(skip))
    return _Use(raw.strip(), 0)


def _parse_goto(raw: str) -> _GotoTarget | None:
    text, at, relpath = raw.strip().rpartition(" @")
    if at:
        use = _parse_use(text)
        return _GotoTarget(use.snippet, use.skip, relpath)
    if raw.strip() == "nowhere":
        return None
    use = _parse_use(raw)
    return _GotoTarget(use.snippet, use.skip, None)


def check_lookup_comments(service: HolLanguageService, doc: TextDoc, examples: str) -> None:
    """Every goto and hover comment in the document holds for the service."""
    for match in _DIRECTIVE_RE.finditer(doc.text):
        kind, use_raw, payload_raw = match.group(1), match.group(2), match.group(3)
        use = _parse_use(use_raw)
        offset = doc.text.index(use.snippet) + use.skip
        assert offset < match.start(), f"{use.snippet!r} first occurs inside or after its comment"
        position = doc.position_at(offset)
        if kind == "goto":
            target = _parse_goto(payload_raw)
            if target is None:
                assert service.definition(doc, position) == []
            else:
                path = doc.path if target.relpath is None else os.path.join(examples, target.relpath)
                target_doc = service.get_document(path)
                expected = target_doc.position_at(target_doc.text.index(target.snippet) + target.skip)
                [found] = service.definition(doc, position)
                assert (found.path, found.range.start) == (path, expected)
        elif payload_raw.strip() == "none":
            assert service.hover(doc, position) is None
        else:
            found = service.hover(doc, position)
            assert found is not None
            assert found[0] == payload_raw.strip()
