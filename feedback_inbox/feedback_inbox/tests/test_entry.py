# Copyright (c) 2026 Krzysztof Rudnicki
"""Finding a bundle's markdown entry and reading its report."""

from __future__ import annotations

from typing import TYPE_CHECKING

from feedback_inbox._entry import (
    find_entry,
    game_and_combo,
    note_from_entry,
    read_report,
)
from feedback_inbox.tests.test_support import make_bundle

if TYPE_CHECKING:
    from pathlib import Path

    from feedback_inbox._paths import Paths


def test_find_entry_picks_the_matching_section(paths: Paths) -> None:
    first = make_bundle(paths.data_root, stamp="2026-11-11T13-52-33-162", note="alpha")
    second = make_bundle(paths.data_root, stamp="2026-11-11T13-53-19-124", note="beta")
    entry = find_entry(first.parent, second)
    assert entry is not None
    assert "beta" in entry
    assert "alpha" not in entry
    assert find_entry(first.parent, first) is not None


def test_find_entry_missing(paths: Paths) -> None:
    bundle = make_bundle(paths.data_root, entry=False)
    assert find_entry(bundle.parent, bundle) is None
    (bundle.parent / "feedback-2026-11-11.md").write_bytes(b"\xff\xfe")
    assert find_entry(bundle.parent, bundle) is None


def test_read_report(paths: Paths) -> None:
    bundle = make_bundle(paths.data_root, note="  hello  \nworld")
    report = read_report(bundle / "report.json")
    assert report is not None
    assert report.note == "  hello  \nworld"
    assert (report.game, report.combo) == ("museum", "loop=P2")


def test_read_report_corrupt_forms(tmp_path: Path) -> None:
    path = tmp_path / "report.json"
    for bad in ("{broken", "[1]", '{"note": 3, "game": null}'):
        path.write_text(bad, encoding="utf-8")
        report = read_report(path)
        if bad == '{"note": 3, "game": null}':
            assert report is not None
            assert (report.note, report.game, report.combo) == ("", "", "")
        else:
            assert report is None
    path.write_bytes(b"\xff\xfe")
    assert read_report(path) is None


def test_entry_fallbacks(paths: Paths) -> None:
    bundle = make_bundle(paths.data_root, note="line one\nline two")
    entry = find_entry(bundle.parent, bundle)
    assert entry is not None
    assert note_from_entry(entry) == "line one\nline two"
    assert game_and_combo(entry) == ("museum", "loop=P2,carry=d,id=c")
    assert note_from_entry("## head only") == ""
    assert game_and_combo("nothing here") == ("", "")
