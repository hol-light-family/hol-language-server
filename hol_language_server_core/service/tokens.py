"""Scanning OCaml source for names, skipping comments, strings, and terms."""

import re

from hol_language_server_core.text import CHAR_LITERAL


# Comments match by their opening only (they nest).
REFERENCE_RE = re.compile(
    r"\(\*"
    + r'|"(?:[^"\\]|\\[\s\S])*"'
    + r"|`[^`]*`"
    + r"|" + CHAR_LITERAL
    + r"|\d[\w'.]*"
    + r"|[A-Za-z_][\w']*(?:\.[A-Za-z_][\w']*)*"
)


def is_name_start(word: str) -> bool:
    return word[:1] == "_" or "a" <= word[:1] <= "z" or "A" <= word[:1] <= "Z"
