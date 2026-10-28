"""OCaml-subset parser for HOL Light sources.

Finds `needs`/`loads`/`loadt` dependencies, `prove`-style theorems,
`new_definition`-style constant definitions, other `let` bindings, and
`module`/`open`/`include` structure. Everything else is skipped.

- `model`: what the parser finds.
- `lexer`: tokens of OCaml source.
- `statements`: the parser of top-level statements, bindings, and modules.
"""

from hol_language_server_core.parser.lexer import OCAML_KEYWORDS, ParserError, Token, TokenType, skip_comments
from hol_language_server_core.parser.model import (
    DEFINITION_TYPE_NAMES,
    CustomCommands,
    Definition,
    DefinitionType,
    Dependency,
    Module,
    OpenDecl,
    ParseResult,
)
from hol_language_server_core.parser.statements import Parser, parse_text

__all__ = [
    "DEFINITION_TYPE_NAMES",
    "OCAML_KEYWORDS",
    "CustomCommands",
    "Definition",
    "DefinitionType",
    "Dependency",
    "Module",
    "OpenDecl",
    "ParseResult",
    "Parser",
    "ParserError",
    "Token",
    "TokenType",
    "parse_text",
    "skip_comments",
]
