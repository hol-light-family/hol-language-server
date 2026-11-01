"""OCaml-subset parser for HOL Light sources.

Finds `needs`/`loads`/`loadt` dependencies, simple `load_path` updates, `prove`-style theorems,
`new_definition`-style constant definitions and the HOL constants their terms
introduce, other `let` bindings, and `module`/`open`/`include` structure.
Everything else is skipped.

- `model`: what the parser finds.
- `lexer`: tokens of OCaml source.
- `statements`: the parser of top-level statements, bindings, and modules.
- `terms`: the constants a definition's term introduces.
"""

from hol_language_server_core.parser.lexer import OCAML_KEYWORDS, Lexer, ParserError, Token, TokenType, skip_comments
from hol_language_server_core.parser.model import (
    DEFINITION_TYPE_NAMES,
    CustomCommands,
    Definition,
    DefinitionType,
    Dependency,
    LoadPath,
    Module,
    OpenDecl,
    ParseResult,
)
from hol_language_server_core.parser.statements import Parser, parse_text
from hol_language_server_core.parser.terms import HOL_TOKEN_RE, declared_infixes, term_constants

__all__ = [
    "DEFINITION_TYPE_NAMES",
    "HOL_TOKEN_RE",
    "OCAML_KEYWORDS",
    "CustomCommands",
    "Definition",
    "DefinitionType",
    "Dependency",
    "Lexer",
    "LoadPath",
    "Module",
    "OpenDecl",
    "ParseResult",
    "Parser",
    "ParserError",
    "Token",
    "TokenType",
    "declared_infixes",
    "parse_text",
    "skip_comments",
    "term_constants",
]
