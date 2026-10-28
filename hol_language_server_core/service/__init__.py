"""Static lookup over HOL Light sources. The servers are thin layers over it.

- `language_service`: `HolLanguageService`, the lookups.
- `results`: what the lookups return.
- `scope`: which names are local.
- `terms`: positions inside backquoted HOL terms.
- `tokens`: scanning source for names.
"""

from hol_language_server_core.service.language_service import HolLanguageService, resolve_path
from hol_language_server_core.service.results import (
    DefinitionTarget,
    MissingLoad,
    Reference,
    SourceInfo,
    SymbolInfo,
    definition_symbol,
    module_symbol,
)
from hol_language_server_core.service.scope import bound_names, local_binding
from hol_language_server_core.service.terms import hol_word_at, in_term

__all__ = [
    "DefinitionTarget",
    "HolLanguageService",
    "MissingLoad",
    "Reference",
    "SourceInfo",
    "SymbolInfo",
    "bound_names",
    "definition_symbol",
    "hol_word_at",
    "in_term",
    "local_binding",
    "module_symbol",
    "resolve_path",
]
