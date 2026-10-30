"""Static lookup over HOL Light sources. The servers are thin layers over it.

- `language_service`: `HolLanguageService`, the lookups.
- `results`: what the lookups return.
- `scope`: which names are local.
- `terms`: positions inside backquoted HOL terms.
- `tokens`: scanning source for names.
"""

from hol_language_server_core.service.language_service import HolLanguageService, resolve_path
from hol_language_server_core.service.results import (
    Completion,
    DefinitionTarget,
    MissingLoad,
    Reference,
    SourceInfo,
    SymbolInfo,
    definition_symbol,
    module_symbol,
)
from hol_language_server_core.service.scope import bound_names, local_binding
from hol_language_server_core.service.terms import bound_in_term, hol_word_at, term_start

__all__ = [
    "Completion",
    "DefinitionTarget",
    "HolLanguageService",
    "MissingLoad",
    "Reference",
    "SourceInfo",
    "SymbolInfo",
    "bound_in_term",
    "bound_names",
    "definition_symbol",
    "hol_word_at",
    "local_binding",
    "module_symbol",
    "resolve_path",
    "term_start",
]
