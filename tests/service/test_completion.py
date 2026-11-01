"""Tests of completion: names, module members, HOL constants in terms, and
import paths."""

import os
from pathlib import Path

import pytest
from hol_server_paths import EXAMPLES, PROJECT, example_service, tactics_doc
from lookups import check_lookup_comments
from hol_language_server_core.config import default_settings
from hol_language_server_core.parser import CustomCommands
from hol_language_server_core.service import HolLanguageService
from hol_language_server_core.text import Position, TextDoc


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


def test_unclosed_terms_offer_what_the_complete_comments_say():
    service = example_service()
    path = os.path.join(PROJECT, "completion_unclosed_term.ml")
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
    assert sym.edit_range is not None
    assert (sym.edit_range.start.character, sym.edit_range.end.character) == (8, 13)
    offset = doc.text.index("let z = Inne") + len("let z = Inne")
    [inner] = service.completion(doc, doc.position_at(offset))
    assert (inner.documentation, inner.commit_characters) == ("Module `Gadget.Inner`", ["."])
    assert inner.edit_range is not None
    assert (inner.edit_range.start.character, inner.edit_range.end.character) == (8, 12)
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


def test_completion_covers_the_unqualified_segment():
    service = example_service()
    path = os.path.join(PROJECT, "completion.ml")
    service.index(path, True)
    doc = service.get_document(path)
    offset = doc.text.index("let m = Kernel.kfun") + len("let m = Ke")
    [kernel] = service.completion(doc, doc.position_at(offset))
    assert (kernel.label, kernel.kind) == ("Kernel", "module")
    assert kernel.edit_range is not None
    assert (kernel.edit_range.start.character, kernel.edit_range.end.character) == (8, 14)
    offset = doc.text.index("let z = probe_tac.foo") + len("let z = probe_t")
    [tac] = service.completion(doc, doc.position_at(offset))
    assert (tac.label, tac.kind) == ("probe_tac", "value")
    assert tac.edit_range is not None
    assert (tac.edit_range.start.character, tac.edit_range.end.character) == (8, 17)


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


def test_completion_is_empty_in_an_unclosed_comment_string_or_term_import():
    service = example_service()
    path = os.path.join(PROJECT, "completion.ml")
    service.index(path, True)
    doc = service.get_document(path)
    # lib/util.ml exists, so the last two would list it were they imports.
    probes = ["(* Gadget widg", 'let s = "hello Gad', "(* outer (* x *) Gadget widg",
              "let s = {|hello Gad", "let s = {id|x |} Gad", "needs {|lib/u",
              '(* needs "lib/u', 'let t = `needs "lib/u']
    for probe in probes:
        changed = service.open_document(path, doc.text + "\n" + probe)
        position = Position(changed.line_count - 1, len(probe))
        assert service.completion(changed, position) == []


def test_word_binders_read_like_symbol_ones():
    service = example_service()
    path = os.path.join(PROJECT, "word_binders.ml")
    service.index(path, True)
    check_lookup_comments(service, service.get_document(path), EXAMPLES)


@pytest.mark.parametrize(("term", "labels"), [
    ("`!fi", []),
    ("`?fi", []),
    ("`?!fi", []),
    ("`\\fi", []),
    ("`@fi", []),
    ("`!x fi", []),
    ("`!x:num fi", []),
    ("`!x. !fi", []),
    ("`forall fi", []),
    ("`exists fi", []),
    ("`existsunique fi", []),
    ("`lambda fi", []),
    ("`forall x fi", []),
    ("`forall x:num fi", []),
    ("`forall x. exists fi", []),
    # After the dot, and after the connectives holding a backslash, names are uses.
    ("`!x. fi", ["fibonacci", "fib", "fib3"]),
    ("`x /\\ fi", ["fibonacci", "fib", "fib3"]),
    ("`x \\/ fi", ["fibonacci", "fib", "fib3"]),
    ("`forall x. fi", ["fibonacci", "fib", "fib3"]),
    ("`forall_thm fi", ["fibonacci", "fib", "fib3"]),
    ("`my_exists fi", ["fibonacci", "fib", "fib3"]),
])
def test_a_variable_being_named_completes_to_nothing(term: str, labels: list[str]):
    service = example_service()
    path = os.path.join(PROJECT, "constants.ml")
    service.index(path, True)
    doc = service.get_document(path)
    # Unclosed, so the term runs to the end of the text.
    changed = service.open_document(path, doc.text + "\nlet t = " + term)
    service.index(path, True)
    position = Position(changed.line_count - 1, len("let t = " + term))
    assert [item.label for item in service.completion(changed, position)] == labels
