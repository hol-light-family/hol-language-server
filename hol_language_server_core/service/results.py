"""What the service returns: symbols, Go to Definition targets, missing
loads, source ranges, and references."""

from dataclasses import dataclass

from hol_language_server_core.parser import DEFINITION_TYPE_NAMES, Definition, Module
from hol_language_server_core.text import Position, Range, TextDoc


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
    # The same item as lines and characters; the end is exclusive.
    source_range: Range | None = None
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


@dataclass
class Completion:
    label: str
    # theorem, definition, term, value, module, file, or folder.
    kind: str
    # Markdown shown beside the item, if any.
    documentation: str | None = None
    # Sort key. Files carry ' ' plus the label, so they sort first.
    sort_text: str | None = None
    # Characters that accept the item.
    commit_characters: list[str] | None = None
    # The span the label replaces. None replaces the word at the cursor.
    edit_range: Range | None = None


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
        source_range=defn.source_range,
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
