"""Semantics records: parsing, label matching, ranking and the compact tree."""

from __future__ import annotations

import pytest

from flutter_web_drive import semantics
from flutter_web_drive.errors import DriveError
from flutter_web_drive.tests.fakes import node

TAB = node(4, "Library\nTab 1 of 4", rect=(0, 8, 80, 67), flags=("current",))
HEADING = node(12, "Library", role="", tag="h2", tappable=False, rect=(16, 13, 72, 30))
CONTAINER = node(1, "", role="", tappable=False, rect=(0, 0, 1400, 900))
FIELD = node(
    20, "Email", role="textbox", value="me@x", tappable=False, flags=("focused",)
)


def test_parse_nodes_builds_typed_records() -> None:
    (parsed,) = semantics.parse_nodes([TAB])
    assert parsed.id == 4
    assert parsed.lines == ("Library", "Tab 1 of 4")
    assert parsed.center == (40.0, 41.5)
    assert parsed.flags == ("current",)


def test_parse_nodes_rejects_non_list() -> None:
    with pytest.raises(DriveError, match="semantics"):
        semantics.parse_nodes("nope")


def test_exact_match_hits_whole_label_or_any_line() -> None:
    tab = semantics.parse_nodes([TAB])[0]
    assert semantics.matches(tab, "Library")
    assert semantics.matches(tab, "Library\nTab 1 of 4")
    assert semantics.matches(tab, "Library | Tab 1 of 4")  # as `tree` prints it
    assert not semantics.matches(tab, "Lib")
    assert semantics.matches(tab, "lib", contains=True)
    assert not semantics.matches(tab, "Browse", contains=True)


def test_find_prefers_tappable_and_keeps_document_order() -> None:
    nodes = semantics.parse_nodes(
        [HEADING, TAB, node(9, "Library", rect=(0, 300, 10, 10))]
    )
    hits = semantics.find(nodes, "Library")
    assert [h.id for h in hits] == [4, 9, 12]


def test_describe_is_one_line_with_tags_and_value() -> None:
    tab, field = semantics.parse_nodes([TAB, FIELD])
    assert (
        semantics.describe(tab)
        == '#4 button "Library | Tab 1 of 4" [tap,current] @0,8 80x67'
    )
    assert (
        semantics.describe(field) == '#20 textbox "Email" = "me@x" [focused] @0,0 80x40'
    )
    heading = semantics.parse_nodes([HEADING])[0]
    assert semantics.describe(heading) == '#12 h2 "Library" @16,13 72x30'


def test_format_tree_hides_empty_containers_unless_all() -> None:
    nodes = semantics.parse_nodes([CONTAINER, TAB, FIELD])
    compact = semantics.format_tree(nodes)
    assert "#1 " not in compact
    assert "#4 " in compact
    assert "#1 " in semantics.format_tree(nodes, show_all=True)


def test_format_tree_filter_matches_label_role_or_value() -> None:
    nodes = semantics.parse_nodes([TAB, FIELD])
    assert semantics.format_tree(nodes, filt="textbox").count("\n") == 0
    assert "#20" in semantics.format_tree(nodes, filt="ME@X")
    assert semantics.format_tree(nodes, filt="zzz") == "(no matching semantics nodes)"
    assert semantics.format_tree([]) == "(no semantics nodes)"


def test_hint_lists_tappable_labels_capped() -> None:
    many = [node(i, f"b{i}") for i in range(15)] + [HEADING, node(99, "")]
    hint = semantics.hint(semantics.parse_nodes(many))
    assert hint.startswith('"b0", "b1"')
    assert "b12" not in hint
    assert hint.endswith("...")
    assert semantics.hint(semantics.parse_nodes([HEADING])) == "(no tappable nodes)"
    assert semantics.hint(semantics.parse_nodes([TAB])) == '"Library | Tab 1 of 4"'


def test_js_snippets_never_read_password_values() -> None:
    assert "password" in semantics.COLLECT_JS
    assert semantics.IMAGE_STATS_FN.startswith("(async")


def test_in_row_keeps_nodes_vertically_inside_the_anchor_row() -> None:
    rows = semantics.parse_nodes(
        [
            node(1, "Chapter 2\n2024-01-02", rect=(0, 100, 1000, 60)),
            node(2, "Mark unread", rect=(900, 110, 40, 40)),
            node(3, "Chapter 1\n2024-01-01", rect=(0, 160, 1000, 60)),
            node(4, "Mark read", rect=(900, 170, 40, 40)),
        ]
    )
    assert [n.id for n in semantics.in_row(rows, "Chapter 2")] == [2]
    assert [n.id for n in semantics.in_row(rows, "chapter 1", contains=True)] == [4]
    assert semantics.in_row(rows, "Chapter 9") == []
