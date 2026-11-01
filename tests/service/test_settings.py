"""Tests of settings from flags and editor options."""


import pytest
from hol_server_paths import PROJECT
from hol_language_server_core.config import (default_settings, expand_root_paths, parse_settings,
                                              settings_from_options)
from hol_language_server_core.parser import CustomCommands


# ======== Settings: options, rejections, root paths, custom commands. ========
def test_settings_from_options_reads_the_section():
    base = default_settings()
    settings = settings_from_options(
        {"path": "/hol", "rootPaths": ["."], "autoIndex": False, "indexWorkspace": True},
        base,
    )
    assert (settings.hol_path, settings.root_paths) == ("/hol", ["."])
    assert (settings.auto_index, settings.index_workspace) == (False, True)
    assert settings.workspace == base.workspace
    assert settings_from_options({}, base) == base


def test_settings_from_options_rejects_bad_settings():
    base = default_settings()
    for options, message in [
        (None, "must be an object"),
        ("/hol", "must be an object"),
        ({"holPath": "/hol"}, "Unknown hol-light settings: holPath"),
        ({"path": 5}, "path must be a str"),
        ({"autoIndex": "false"}, "autoIndex must be a bool"),
        ({"rootPaths": "."}, "rootPaths must be a list"),
        ({"rootPaths": [1]}, "rootPaths must hold strings"),
        ({"customImports": "my_needs"}, "customImports must be a list"),
        ({"customTheorems": ["my prove"]}, "is not an OCaml identifier"),
        ({"customDefinitions": [3]}, "is not an OCaml identifier"),
    ]:
        with pytest.raises(ValueError, match=message):
            settings_from_options(options, base)


def test_root_paths_reject_unknown_and_unset_placeholders():
    settings = default_settings()
    settings.workspace = PROJECT
    for root_paths, message in [
        (["{wrkspace}/lib"], "unknown placeholder"),
        (["{hol}"], "is not set"),
        ([""], "Empty root path"),
    ]:
        settings.root_paths = root_paths
        with pytest.raises(ValueError, match=message):
            expand_root_paths(settings)


def test_custom_commands_come_from_options_and_flags():
    base = default_settings()
    settings = settings_from_options(
        {"customImports": ["my_needs"], "customTheorems": ["my_prove"], "customDefinitions": []}, base
    )
    assert settings.custom_commands == CustomCommands(imports=["my_needs"], theorems=["my_prove"])
    settings, _ = parse_settings(["--custom-import", "my_needs", "--custom-import", "load_proof",
                                  "--custom-definition", "my_define"], None)
    assert settings.custom_commands == CustomCommands(imports=["my_needs", "load_proof"],
                                                      definitions=["my_define"])
    with pytest.raises(ValueError, match="--custom-theorem: 'a.b' is not an OCaml identifier"):
        parse_settings(["--custom-theorem", "a.b"], None)
