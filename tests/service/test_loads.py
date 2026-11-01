"""Tests of finding what files load: the load path, workspace indexing, custom
imports, and missing loads."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from hol_server_paths import EXAMPLES, HOL, PROJECT, example_service
from lookups import check_lookup_comments
from hol_language_server_core.config import (default_settings, expand_root_paths, parse_settings,
                                              settings_from_options, split_load_path)
from hol_language_server_core.parser import CustomCommands
from hol_language_server_core.service import HolLanguageService
from hol_language_server_core.text import Position, TextDoc


# ================================ Load path. =================================
def load_path_service(workspace: str, hol: str = HOL) -> HolLanguageService:
    settings = default_settings()
    settings.hol_path = hol
    settings.workspace = workspace
    settings.root_paths = [".", "{workspace}"]
    return HolLanguageService(settings)


def test_load_path_updates_find_what_the_comments_say():
    workspace = os.path.join(EXAMPLES, "load_path")
    service = load_path_service(workspace)
    path = os.path.join(workspace, "main.ml")
    service.index(path, True)
    check_lookup_comments(service, service.get_document(path), EXAMPLES)
    [missing] = service.missing_loads(path)[path]
    assert missing.name == "too_early.ml"


def test_load_path_expands_the_hol_directory(tmp_path: Path):
    hol = tmp_path / "hol"
    (hol / "extra").mkdir(parents=True)
    (hol / "hol.ml").write_text("")
    (hol / "extra" / "in_hol.ml").write_text("let in_hol = 1;;\n")
    (tmp_path / "$odd").mkdir()
    (tmp_path / "$odd" / "in_odd.ml").write_text("let in_odd = 1;;\n")
    (tmp_path / "absolute").mkdir()
    (tmp_path / "absolute" / "in_absolute.ml").write_text("let in_absolute = 1;;\n")
    service = load_path_service(str(tmp_path), str(hol))
    path = str(tmp_path / "t.ml")
    service.open_document(path, (
        'load_path := ["$/extra"; "$$odd"; "%s"] @ !load_path;;\n'
        'needs "in_hol.ml";;\nneeds "in_odd.ml";;\nneeds "in_absolute.ml";;\n' % (tmp_path / "absolute")))
    service.index(path, True)
    file = service.database.get_file_index(path)
    assert file is not None
    assert [dep.path for dep in file.dependencies] == [
        str(hol / "extra" / "in_hol.ml"),
        str(tmp_path / "$odd" / "in_odd.ml"),
        str(tmp_path / "absolute" / "in_absolute.ml"),
    ]


@pytest.mark.parametrize(("value", "paths"), [
    ("", []),
    ("a", ["a"]),
    ("a:b", ["a", "b"]),
    (":a::b:", ["a", "b"]),
    # As hol_loader.ml: these do not split, and the characters stay.
    ("a\\:b:c", ["a\\:b", "c"]),
    ("'a:b':c", ["'a:b'", "c"]),
    ('"a:b":c', ['"a:b"', "c"]),
])
def test_split_load_path_follows_hol_light(value: str, paths: list[str]):
    assert split_load_path(value) == paths


def test_load_path_flag_replaces_the_environment(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HOLLIGHT_LOAD_PATH", "/from/env:$/in_hol")
    settings, _ = parse_settings(["--hol-path", "/hol", "--root", "."], None)
    assert expand_root_paths(settings) == [".", "/from/env", "/hol/in_hol"]
    settings, _ = parse_settings(["--hol-path", "/hol", "--root", ".", "--load-path", "/a", "--load-path", "$$b"], None)
    assert expand_root_paths(settings) == [".", "/a", "$b"]
    # Editor settings keep it: they have no load path of their own.
    assert settings_from_options({"rootPaths": ["/r"]}, settings).load_path == ["/a", "$$b"]


def test_load_path_setting_finds_and_completes_after_the_roots(tmp_path: Path):
    (tmp_path / "extra").mkdir()
    (tmp_path / "extra" / "in_extra.ml").write_text("let in_extra = 1;;\n")
    (tmp_path / "extra" / "both.ml").write_text("let extra_both = 1;;\n")
    (tmp_path / "both.ml").write_text("let top_both = 1;;\n")
    settings = default_settings()
    settings.hol_path = HOL
    settings.workspace = str(tmp_path)
    settings.root_paths = ["."]
    settings.load_path = [str(tmp_path / "extra")]
    service = HolLanguageService(settings)
    path = str(tmp_path / "t.ml")
    doc = service.open_document(path, 'needs "in_extra.ml";;\nneeds "both.ml";;\n')
    service.index(path, True)
    file = service.database.get_file_index(path)
    assert file is not None
    assert [dep.path for dep in file.dependencies] == [
        str(tmp_path / "extra" / "in_extra.ml"), str(tmp_path / "both.ml")]
    [item] = service.completion(doc, Position(0, len('needs "in_e')))
    assert (item.label, item.kind) == ("in_extra.ml", "file")


def test_load_path_does_not_change_loads(tmp_path: Path):
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "v.ml").write_text("let v = 1;;\n")
    service = load_path_service(str(tmp_path))
    path = str(tmp_path / "t.ml")
    doc = service.open_document(path, 'load_path := "vendor" :: !load_path;;\nloads "v.ml";;\n')
    service.index(path, True)
    [missing] = service.missing_loads(path)[path]
    assert missing.name == "v.ml"
    assert service.completion(doc, Position(1, len('loads "v'))) == []


# ============================= Workspace indexing. ===========================
def workspace_service(workspace: Path) -> HolLanguageService:
    settings = default_settings()
    settings.hol_path = HOL
    settings.workspace = str(workspace)
    return HolLanguageService(settings)


def indexed_paths(service: HolLanguageService, name: str) -> list[str]:
    return [symbol.path for symbol in service.find_symbols(name)]


@pytest.fixture
def locked(tmp_path: Path) -> Iterator[Path]:
    """A directory of tmp_path, under which nothing can be read till the test ends."""
    if os.geteuid() == 0:
        pytest.skip("root reads every file")
    path = tmp_path / "locked"
    path.mkdir()
    yield path
    path.chmod(0o700)


def test_workspace_indexing_skips_an_unreadable_directory(
        tmp_path: Path, locked: Path, caplog: pytest.LogCaptureFixture):
    (tmp_path / "good.ml").write_text("let found_me = 1;;\n")
    (locked / "hidden.ml").write_text("let not_found = 1;;\n")
    locked.chmod(0o000)
    service = workspace_service(tmp_path)
    service.index_workspace()
    assert indexed_paths(service, "found_me") == [str(tmp_path / "good.ml")]
    assert indexed_paths(service, "not_found") == []
    assert f"Skipping directory {locked}" in caplog.text


def test_workspace_indexing_skips_an_unreadable_file(
        tmp_path: Path, locked: Path, caplog: pytest.LogCaptureFixture):
    (tmp_path / "good.ml").write_text("let found_me = 1;;\n")
    (tmp_path / "zz_last.ml").write_text("let found_last = 1;;\n")
    unreadable = locked / "unreadable.ml"
    unreadable.write_text("let not_found = 1;;\n")
    unreadable.chmod(0o000)
    service = workspace_service(tmp_path)
    service.index_workspace()
    # Files after it are read too.
    assert indexed_paths(service, "found_me") == [str(tmp_path / "good.ml")]
    assert indexed_paths(service, "found_last") == [str(tmp_path / "zz_last.ml")]
    assert f"Skipping file {unreadable}" in caplog.text


def test_workspace_indexing_ends_on_symlink_cycles(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    (tmp_path / "good.ml").write_text("let found_me = 1;;\n")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "inner.ml").write_text("let found_inner = 1;;\n")
    (tmp_path / "sub" / "loop").symlink_to(tmp_path, target_is_directory=True)
    (tmp_path / "self").symlink_to(tmp_path / "self")
    (tmp_path / "broken.ml").symlink_to(tmp_path / "missing.ml")
    service = workspace_service(tmp_path)
    service.index_workspace()
    assert indexed_paths(service, "found_me") == [str(tmp_path / "good.ml")]
    assert indexed_paths(service, "found_inner") == [str(tmp_path / "sub" / "inner.ml")]
    assert f"Skipping {tmp_path / 'self'}" in caplog.text


def test_workspace_indexing_reads_a_directory_once_under_its_real_path(tmp_path: Path):
    workspace = tmp_path / "workspace"
    (workspace / "z_real").mkdir(parents=True)
    (workspace / "z_real" / "real.ml").write_text("let in_real = 1;;\n")
    # Sorted before its target, and walked after it.
    (workspace / "a_link").symlink_to(workspace / "z_real", target_is_directory=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "linked.ml").write_text("let in_linked = 1;;\n")
    (workspace / "m_link").symlink_to(outside, target_is_directory=True)
    (workspace / "n_link").symlink_to(outside, target_is_directory=True)
    service = workspace_service(workspace)
    service.index_workspace()
    assert indexed_paths(service, "in_real") == [str(workspace / "z_real" / "real.ml")]
    # A linked source tree is still read, by the first link to it.
    assert indexed_paths(service, "in_linked") == [str(workspace / "m_link" / "linked.ml")]


# =============== Loads: custom imports, missing-load coverage. ===============
def test_indexing_parses_unchanged_text_once(monkeypatch: pytest.MonkeyPatch):
    import hol_language_server_core.database as database
    from hol_language_server_core.parser import ParseResult

    service = example_service()
    path = os.path.join(PROJECT, "completion.ml")
    with open(path, encoding="utf-8") as handle:
        doc = service.open_document(path, handle.read())
    service.index(path, True)
    parsed: list[str] = []
    real_parse = database.parse_text

    def counting_parse(text: str, file_path: str, custom: CustomCommands,
                       infixes: frozenset[str]) -> ParseResult:
        parsed.append(file_path)
        return real_parse(text, file_path, custom, infixes)

    monkeypatch.setattr(database, "parse_text", counting_parse)
    # Requests on the same document: no parse, full or not.
    service.index(path, True)
    service.index(path, False)
    assert path not in parsed
    # The same text in a new document object: still no parse.
    same = service.open_document(path, doc.text)
    service.index(path, True)
    assert path not in parsed
    # Changed text, even on the same object: parsed once.
    same.text += "\n"
    service.index(path, False)
    assert parsed.count(path) == 1


def test_definition_jumps_through_a_custom_import(tmp_path: Path):
    # tmp_path: the helper name and custom settings must not leak into the shared workspace.
    (tmp_path / "lib.ml").write_text("let helper = 1;;\n")
    (tmp_path / "main.ml").write_text('my_needs "lib.ml";;\nlet x = helper;;\n')
    settings = default_settings()
    settings.hol_path = HOL
    settings.workspace = str(tmp_path)
    settings.custom_commands = CustomCommands(imports=["my_needs"])
    service = HolLanguageService(settings)
    path = str(tmp_path / "main.ml")
    assert service.index(path, True) == []
    doc = service.get_document(path)
    [target] = service.definition(doc, Position(0, 11))
    assert target.path == str(tmp_path / "lib.ml")
    [target] = service.definition(doc, Position(1, 9))
    assert target.path == str(tmp_path / "lib.ml")


def test_missing_loads_cover_the_files_it_loads(tmp_path: Path):
    # tmp_path: deliberately broken files would pollute the shared workspace's pinned missing list.
    (tmp_path / "a.ml").write_text('needs "gone.ml";;\n')
    (tmp_path / "main.ml").write_text('needs "a.ml";;\nneeds "nope.ml";;\n')
    settings = default_settings()
    settings.hol_path = HOL
    settings.workspace = str(tmp_path)
    service = HolLanguageService(settings)
    path = str(tmp_path / "main.ml")
    service.index(path, True)
    missing = {p: [(m.name, m.range.start.line, m.range.start.character) for m in loads]
               for p, loads in service.missing_loads(path).items() if loads}
    assert missing == {path: [("nope.ml", 1, 6)], str(tmp_path / "a.ml"): [("gone.ml", 0, 6)]}


def test_imports_past_the_line_start_are_found(tmp_path: Path):
    (tmp_path / "u.ml").write_text("let u = 1;;\n")
    text = 'if true\nthen needs "u.ml"\nelse loads "u.ml";;\nlet _ = (needs "u.ml");;\n'
    settings = default_settings()
    settings.hol_path = HOL
    settings.workspace = str(tmp_path)
    settings.root_paths = ["."]
    service = HolLanguageService(settings)
    path = str(tmp_path / "t.ml")
    doc = service.open_document(path, text)
    service.index(path, True)
    file = service.database.get_file_index(path)
    assert file is not None
    assert [dep.name for dep in file.dependencies] == ["u.ml", "u.ml", "u.ml"]
    [missing] = service.missing_loads(path)[path]
    assert (missing.name, missing.range.start.line) == ("u.ml", 2)
    [target] = service.definition(doc, Position(3, 17))
    assert target.path == str(tmp_path / "u.ml")
    items = service.completion(TextDoc(path, '(needs "u'), Position(0, len('(needs "u')))
    assert [(item.label, item.kind) for item in items] == [("u.ml", "file")]
