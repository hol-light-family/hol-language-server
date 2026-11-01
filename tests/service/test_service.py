"""Tests of the core lookup methods behind editor features: positions,
hover, go to definition, and document and workspace symbols."""

import os

import pytest
from hol_server_paths import EXAMPLES, PROJECT, example_service, tactics_doc
from lookups import check_lookup_comments
from hol_language_server_core.service import HolLanguageService
from hol_language_server_core.text import Position, TextDoc
from hol_language_server_core.util import get_word_at_position


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


def test_comments_and_strings_are_not_lookups():
    service = example_service()
    path = os.path.join(PROJECT, "no_lookups.ml")
    service.index(path, True)
    check_lookup_comments(service, service.get_document(path), EXAMPLES)


@pytest.mark.parametrize("text", ["(* lookup_target", '"lookup_target', "(* outer (* inner *) lookup_target",
                                  "{|lookup_target", "{id|x |} lookup_target"])
def test_text_the_file_ends_inside_is_not_a_lookup(text: str):
    service = example_service()
    path = os.path.join(PROJECT, "no_lookups.ml")
    with open(path, encoding="utf-8") as handle:
        doc = service.open_document(path, handle.read() + "\nlet z = " + text)
    service.index(path, True)
    position = Position(doc.line_count - 1, len("let z = " + text))
    assert service.hover(doc, position) is None
    assert service.definition(doc, position) == []


def test_lookups_out_of_range_find_nothing():
    service = example_service()
    doc = tactics_doc(service)
    for line in (-1, doc.line_count):
        assert service.hover(doc, Position(line, 0)) is None
        assert service.definition(doc, Position(line, 0)) == []


def test_a_comment_definition_is_not_a_definition():
    service = example_service()
    path = os.path.join(PROJECT, "comment_defs.ml")
    service.index(path, True)
    check_lookup_comments(service, service.get_document(path), EXAMPLES)


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
