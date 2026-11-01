"""Fixture checkouts for the hol-language-server tests, and a service over them."""

import os

from hol_language_server_core.config import default_settings
from hol_language_server_core.service import HolLanguageService
from hol_language_server_core.text import TextDoc

EXAMPLES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "examples")
HOL = os.path.join(EXAMPLES, "hol")
PROJECT = os.path.join(EXAMPLES, "project")


def example_service() -> HolLanguageService:
    settings = default_settings()
    settings.hol_path = HOL
    settings.workspace = PROJECT
    return HolLanguageService(settings)


def tactics_doc(service: HolLanguageService) -> TextDoc:
    path = os.path.join(PROJECT, "tactics.ml")
    service.index(path, True)
    return service.get_document(path)
