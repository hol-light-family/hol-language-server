"""Tests of the core lookup methods behind editor features: positions,
hover, go to definition, and document and workspace symbols."""

import os
from pathlib import Path

import pytest
from hol_server_paths import EXAMPLES, HOL, PROJECT
from lookups import check_lookup_comments
from hol_language_server_core.config import default_settings, expand_root_paths, parse_settings, settings_from_options
from hol_language_server_core.parser import CustomCommands
from hol_language_server_core.service import HolLanguageService
from hol_language_server_core.text import Position, TextDoc
from hol_language_server_core.util import get_word_at_position


def example_service() -> HolLanguageService:
    settings = default_settings()
    settings.hol_path = HOL
    settings.workspace = PROJECT
    return HolLanguageService(settings)


def tactics_doc(service: HolLanguageService) -> TextDoc:
    path = os.path.join(PROJECT, "tactics.ml")
    service.index(path, True)
    return service.get_document(path)


def locals_doc(service: HolLanguageService) -> TextDoc:
    path = os.path.join(PROJECT, "locals.ml")
    service.index(path, True)
    return service.get_document(path)


# ======== Positions and words: offset round-trips, operator fallback. ========
def test_positions_round_trip_through_offsets():
    doc = TextDoc("x.ml", "let A = 1;;\nlet BB =\n  2;;\n")
    assert doc.offset_at(Position(1, 4)) == len("let A = 1;;\nlet ")
    assert doc.position_at(doc.offset_at(Position(2, 2))) == Position(2, 2)
    assert doc.offset_at(Position(-1, 0)) == 0
    assert doc.offset_at(Position(99, 0)) == len(doc.text)


def test_word_at_position_falls_back_to_operators():
    doc = TextDoc("x.ml", "let x = f 1;;\n")
    assert get_word_at_position(doc, Position(0, 4))[0] == "x"
    word, span = get_word_at_position(doc, Position(0, 6))
    assert span is not None
    assert (word, (span.start.character, span.end.character)) == ("=", (6, 7))
    assert get_word_at_position(doc, Position(1, 0))[0] is None


# ===== Hover and definition: scope, shadowing, lets, needs, conversions. =====
def test_hover_shows_the_theorem_statement():
    service = example_service()
    doc = tactics_doc(service)
    # ADD_SYM_ALT in `REWRITE_TAC[th; ADD_SYM_ALT]` on line 12 (0-based).
    found = service.hover(doc, Position(12, 20))
    assert found is not None
    markdown, _ = found
    assert markdown == "Theorem `ADD_SYM_ALT`\n```\n`|- !m n. n + m = m + n`\n```"


def test_hover_shows_a_value_and_a_module():
    service = example_service()
    doc = tactics_doc(service)
    found = service.hover(doc, Position(11, 5))
    assert found is not None
    markdown, _ = found
    assert markdown == "*HELPER_TAC*"
    assert service.hover(doc, Position(6, 1)) is None


def test_definition_jumps_to_the_name():
    service = example_service()
    doc = tactics_doc(service)
    [target] = service.definition(doc, Position(11, 5))
    assert target.path == doc.path
    assert (target.range.start.line, target.range.start.character) == (11, 4)
    assert service.definition(doc, Position(6, 1)) == []
    assert service.definition(doc, Position(doc.line_count, 0)) == []
    assert service.definition(doc, Position(-1, 0)) == []


def test_definition_jumps_through_needs():
    service = example_service()
    path = os.path.join(PROJECT, "main.ml")
    service.index(path, True)
    doc = service.get_document(path)
    [target] = service.definition(doc, Position(6, 8))
    assert target.path == os.path.join(PROJECT, "lib", "util.ml")


def test_conversions_resolve_where_they_are_used():
    service = example_service()
    path = os.path.join(PROJECT, "conversions.ml")
    service.index(path, True)
    check_lookup_comments(service, service.get_document(path), EXAMPLES)


def test_definition_of_a_let_in_name_is_its_binding():
    service = example_service()
    doc = locals_doc(service)
    # The y on line 7 (0-based) is bound by `let y = 1 in` on line 6.
    [target] = service.definition(doc, Position(7, 2))
    assert (target.path, target.range.start.line, target.range.start.character) == (doc.path, 6, 6)


def test_definition_of_a_parameter_is_the_parameter():
    service = example_service()
    doc = locals_doc(service)
    # Uses on lines 10 and 13 (0-based), and the parameters they name.
    for use, binding in [((10, 2), (9, 18)), ((10, 6), (9, 20)),
                         ((13, 2), (12, 15)), ((13, 6), (12, 17))]:
        [target] = service.definition(doc, Position(*use))
        assert (target.path, target.range.start.line, target.range.start.character) == (doc.path, *binding)


def test_local_names_follow_scope():
    service = example_service()
    doc = locals_doc(service)
    check_lookup_comments(service, doc, EXAMPLES)


def test_a_parameter_named_like_a_global_is_the_parameter():
    service = example_service()
    doc = tactics_doc(service)
    # th in `REWRITE_TAC[th; ADD_SYM_ALT]` is HELPER_TAC's parameter, not the
    # top-level th above it.
    use = doc.text.index("th; ADD_SYM_ALT")
    [target] = service.definition(doc, doc.position_at(use))
    assert doc.offset_at(target.range.start) == doc.text.index("th =\n")


def test_constants_in_terms_go_to_their_definition():
    service = example_service()
    path = os.path.join(PROJECT, "constants.ml")
    service.index(path, True)
    check_lookup_comments(service, service.get_document(path), EXAMPLES)


def test_a_bound_variable_named_like_a_constant_goes_nowhere():
    service = example_service()
    path = os.path.join(PROJECT, "bound.ml")
    service.index(path, True)
    check_lookup_comments(service, service.get_document(path), EXAMPLES)


def test_a_comment_definition_is_not_a_definition():
    service = example_service()
    path = os.path.join(PROJECT, "comment_defs.ml")
    service.index(path, True)
    check_lookup_comments(service, service.get_document(path), EXAMPLES)


# ================= Completion: names, members, files. =================
def test_completion_offers_what_the_complete_comments_say():
    service = example_service()
    path = os.path.join(PROJECT, "completion.ml")
    service.index(path, True)
    check_lookup_comments(service, service.get_document(path), EXAMPLES)


def test_terms_offer_what_the_complete_comments_say():
    service = example_service()
    path = os.path.join(PROJECT, "constants.ml")
    service.index(path, True)
    check_lookup_comments(service, service.get_document(path), EXAMPLES)


def test_import_paths_offer_what_the_complete_comments_say():
    service = example_service()
    path = os.path.join(PROJECT, "completion_files.ml")
    service.index(path, True)
    check_lookup_comments(service, service.get_document(path), EXAMPLES)


def test_completion_carries_docs_ranges_and_commit_characters():
    service = example_service()
    path = os.path.join(PROJECT, "completion.ml")
    service.index(path, True)
    doc = service.get_document(path)
    offset = doc.text.index("let z = ADD_S") + len("let z = ADD_S")
    [sym, _alt] = service.completion(doc, doc.position_at(offset))
    assert sym.documentation == "Theorem `ADD_SYM`\n```\n`|- !m n. m + n = n + m`\n```"
    assert sym.edit_range is None
    offset = doc.text.index("let z = Inne") + len("let z = Inne")
    [inner] = service.completion(doc, doc.position_at(offset))
    assert (inner.documentation, inner.commit_characters, inner.edit_range) == (
        "Module `Gadget.Inner`", ["."], None)
    offset = doc.text.index("let q = Gadget.Inne") + len("let q = Gadget.Inne")
    [member] = service.completion(doc, doc.position_at(offset))
    assert (member.documentation, member.commit_characters) == ("Module `Gadget.Inner`", ["."])
    assert member.edit_range is not None
    assert (member.edit_range.start.character, member.edit_range.end.character) == (15, 19)
    offset = doc.text.index("let z = Kernel.kfun") + len("let z = Kernel.kfun")
    members = service.completion(doc, doc.position_at(offset))
    assert [(item.label, item.kind) for item in members] == [("kfun", "value"), ("kfun2", "value")]
    for item in members:
        assert item.edit_range is not None
        assert (item.edit_range.start.character, item.edit_range.end.character) == (15, 19)
    offset = doc.text.index("let w = Kernel.") + len("let w = Kernel.")
    members = service.completion(doc, doc.position_at(offset))
    assert [item.label for item in members] == ["kfun", "kfun2"]
    for item in members:
        assert item.edit_range is not None
        assert (item.edit_range.start.character, item.edit_range.end.character) == (15, 15)
    service = example_service()
    path = os.path.join(PROJECT, "constants.ml")
    service.index(path, True)
    doc = service.get_document(path)
    offset = doc.text.index("EVEN 4 /\\ fib") + len("EVEN 4 /\\ fib")
    members = service.completion(doc, doc.position_at(offset))
    assert [item.label for item in members] == ["fibonacci", "fib", "fib3"]
    fib = members[1]
    assert fib.documentation == "Constant `fib`, defined by `FIB_DEF`\n```\n`|- fib n = fibonacci n`\n```"
    assert fib.edit_range is not None
    assert (fib.edit_range.start.character, fib.edit_range.end.character) == (52, 55)


def test_completion_covers_the_qualified_segment():
    service = example_service()
    path = os.path.join(PROJECT, "completion.ml")
    service.index(path, True)
    doc = service.get_document(path)
    changed = service.open_document(path, doc.text + "\nlet q2 = Gadget.Inner")
    [member] = service.completion(changed, Position(changed.line_count - 1, len("let q2 = Gadget.Inne")))
    assert member.label == "Inner"
    assert member.edit_range is not None
    assert (member.edit_range.start.character, member.edit_range.end.character) == (16, 21)


def test_completion_lists_import_paths(tmp_path: Path):
    # tmp_path: the directory entries completed here must not leak into the shared workspace.
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "util.ml").write_text("let u = 1;;\n")
    (tmp_path / "lib" / ".hidden.ml").write_text("let h = 1;;\n")
    (tmp_path / "lib" / "notes.txt").write_text("no\n")
    (tmp_path / "lib" / "sub").mkdir()
    (tmp_path / "linked").symlink_to(tmp_path / "lib", target_is_directory=True)
    (tmp_path / "hol").mkdir()
    (tmp_path / "hol" / "marker.ml").write_text("let m = 1;;\n")
    settings = default_settings()
    settings.hol_path = str(tmp_path / "hol")
    settings.workspace = str(tmp_path)
    settings.root_paths = ["."]
    settings.custom_commands = CustomCommands(imports=["my_needs"])
    service = HolLanguageService(settings)
    path = str(tmp_path / "main.ml")
    doc = TextDoc(path, 'needs "lib/u')
    [found] = service.completion(doc, Position(0, len('needs "lib/u')))
    assert (found.label, found.kind, found.sort_text) == ("util.ml", "file", " util.ml")
    assert found.edit_range is not None
    assert (found.edit_range.start.character, found.edit_range.end.character) == (11, 12)
    doc = TextDoc(path, 'needs "lib/')
    items = service.completion(doc, Position(0, len('needs "lib/')))
    assert {(item.label, item.kind) for item in items} == {("util.ml", "file"), ("sub", "folder")}
    [folder] = [item for item in items if item.kind == "folder"]
    assert folder.commit_characters == ["/"]
    doc = TextDoc(path, 'needs "l')
    items = service.completion(doc, Position(0, len('needs "l')))
    assert {(item.label, item.kind) for item in items} == {("lib", "folder"), ("linked", "folder")}
    doc = TextDoc(path, 'loads "m')
    [found] = service.completion(doc, Position(0, len('loads "m')))
    assert (found.label, found.kind) == ("marker.ml", "file")
    doc = TextDoc(path, 'loads "l')
    assert service.completion(doc, Position(0, len('loads "l'))) == []
    doc = TextDoc(path, 'needs "lib/util.ml')
    items = service.completion(doc, Position(0, len('needs "li')))
    [folder] = [item for item in items if item.label == "lib"]
    assert folder.edit_range is not None
    assert (folder.edit_range.start.character, folder.edit_range.end.character) == (7, 10)
    doc = TextDoc(path, 'my_needs "lib/u')
    [found] = service.completion(doc, Position(0, len('my_needs "lib/u')))
    assert found.label == "util.ml"
    doc = TextDoc(path, 'needs "gone/')
    assert service.completion(doc, Position(0, len('needs "gone/'))) == []
    doc = TextDoc(path, 'needs "lib/util.ml"')
    assert service.completion(doc, Position(0, len(doc.text))) == []


def test_completion_is_empty_without_a_word():
    service = example_service()
    doc = tactics_doc(service)
    assert service.completion(doc, Position(0, 0)) == []
    assert service.completion(doc, Position(doc.line_count, 0)) == []
    assert service.completion(doc, Position(-1, 0)) == []


def test_completion_is_empty_in_an_unclosed_comment_or_string():
    service = example_service()
    path = os.path.join(PROJECT, "completion.ml")
    service.index(path, True)
    doc = service.get_document(path)
    probes = ["(* Gadget widg", 'let s = "hello Gad', "(* outer (* x *) Gadget widg"]
    for probe in probes:
        changed = service.open_document(path, doc.text + "\n" + probe)
        position = Position(changed.line_count - 1, len(probe))
        assert service.completion(changed, position) == []


# ================ Symbols: document order, predicate search. =================
def test_document_symbols_are_position_ordered():
    service = example_service()
    path = os.path.join(PROJECT, "main.ml")
    service.index(path, True)
    symbols = service.document_symbols(path)
    assert [s.name for s in symbols] == ["MY_THM", "x"]
    lines = [(s.position.line, s.position.character) for s in symbols]
    assert lines == sorted(lines)
    assert service.document_symbols(os.path.join(PROJECT, "nope.ml")) == []


def test_search_symbols_matches_by_predicate():
    service = example_service()
    service.index_workspace()
    names = {s.full_name for s in service.search_symbols(lambda n: "TAC" in n)}
    assert {"HELPER_TAC", "MY_TAC", "OTHER_TAC"} <= names


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


# =============== Loads: custom imports, missing-load coverage. ===============
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
