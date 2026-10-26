"""What the parser finds: definitions, modules, dependencies, and the
commands a project adds."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum

from hol_language_server_core.text import Location, Position, Range, location


class Dependency:
    def __init__(self, name: str, hol_light_relative: bool, name_range: Range) -> None:
        self.name = name
        # Resolve relative to the HOL Light base directory, not the
        # workspace roots, when the loader is `loads`.
        self.hol_light_relative = hol_light_relative
        # The quoted file name in the source.
        self.range = name_range


class DefinitionType(IntEnum):
    theorem = 0
    definition = 1
    term = 2
    other = 3
    # A HOL constant, introduced by a definition's term.
    constant = 4


DEFINITION_TYPE_NAMES = {
    DefinitionType.theorem: "theorem",
    DefinitionType.definition: "definition",
    DefinitionType.term: "term",
    DefinitionType.other: "value",
    DefinitionType.constant: "constant",
}


class Definition:
    def __init__(self, name: str, def_type: DefinitionType, content: str, module: Module | None,
                 offset: int, file_path: str, position: Position) -> None:
        self.name = name
        self.def_type = def_type
        self.content = content
        self.module = module
        # Offset of the name token in the file text.
        self.offset = offset
        self.position = position
        # The whole item which defines this name (`let ... ;;`), shared by
        # the bindings of `let ... and ...`.
        self.source_start: int | None = None
        self.source_end: int | None = None
        # Constants only: the OCaml name of the definition introducing it.
        self.defined_by: str | None = None
        self._file_path = file_path

    def get_file_path(self) -> str:
        return self._file_path

    def get_location(self) -> Location:
        return location(self._file_path, self.position)

    @property
    def full_name(self) -> str:
        if self.module is not None:
            return self.module.full_name + "." + self.name
        return self.name

    def to_string(self) -> str:
        if self.def_type == DefinitionType.theorem:
            return f"Theorem `{self.name}`\n```\n`|- {self.content}`\n```"
        if self.def_type == DefinitionType.definition:
            return f"Definition `{self.name}`\n```\n`|- {self.content}`\n```"
        if self.def_type == DefinitionType.term:
            return "```\n`" + self.content + "`\n```"
        if self.def_type == DefinitionType.constant:
            return f"Constant `{self.name}`, defined by `{self.defined_by}`\n```\n`|- {self.content}`\n```"
        text = f"*{self.name}*"
        if self.content:
            # content represents type
            text += f" : {self.content}"
        return text


@dataclass
class OpenDecl:
    name: str
    # Offsets of the `open`/`include` statement and of the end of the name.
    start: int
    end: int


class Module:
    def __init__(self, name: str, parent: Module | None, start: int, file_path: str,
                 position: Position) -> None:
        self.parent = parent
        self.name = name
        self.full_name = (
            parent.full_name + "." + name if parent is not None else name
        )
        # Offset of the module name token in the file text.
        self.start = start
        self.end: int | None = None
        self.position = position
        self.end_position: Position | None = None
        self._file_path = file_path
        self.modules: list[Module] = []
        self.open_decls: list[OpenDecl] = []
        self.include_decls: list[OpenDecl] = []

    def get_file_path(self) -> str:
        return self._file_path

    def get_location(self) -> Location:
        return location(self._file_path, self.position)

    def to_string(self) -> str:
        return f"Module `{self.full_name}`"


@dataclass
class ParseResult:
    definitions: list[Definition]
    # Modules sorted by their start position.
    modules: list[Module]
    dependencies: list[Dependency]
    # Tracks all open and include statements. Holds no definitions or modules.
    global_module: Module
    # HOL constants the definitions introduce, found in their terms.
    constants: list[Definition] = field(default_factory=list[Definition])


@dataclass
class CustomCommands:
    # A project's own command names, read like the built-in ones they stand for.
    # Import commands (like `needs`)
    imports: list[str] = field(default_factory=list)
    # Theorem commands (like `prove`)
    theorems: list[str] = field(default_factory=list)
    # Constant definition commands (like `new_definition`)
    definitions: list[str] = field(default_factory=list)
