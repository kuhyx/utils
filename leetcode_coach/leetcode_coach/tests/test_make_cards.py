"""Tests for the /leetcode card builder CLI: delivery paths and its output."""

from __future__ import annotations

import io
import json
import runpy
from typing import Any

import pytest

from leetcode_coach import anki_connect, make_cards


def _card(front: str, back: str = "x") -> dict[str, str]:
    return {"front": front, "back": back}


def test_guid_ignores_escaping() -> None:
    raw = make_cards.card_note("n & m?", "b", "slug")
    esc = make_cards.card_note("n &amp; m?", "b", "slug")
    assert raw.guid == esc.guid
    assert raw.fields == ["n & m?", "b", "slug"]
    assert raw.tags == ["leetcode", "slug"]


def _run(monkeypatch: pytest.MonkeyPatch, argv: list[str], spec: dict[str, Any]) -> int:
    monkeypatch.setattr("sys.argv", ["make_cards.py", *argv])
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(spec)))
    return make_cards.main()


GOOD = {
    "slug": "s",
    "cards": [_card("JS: cancel a pending setTimeout?", "clearTimeout(id)")],
}


def test_dry_run_prints_without_logging(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Any
) -> None:
    monkeypatch.setattr(make_cards, "OUT_DIR", tmp_path)
    assert _run(monkeypatch, ["--dry-run", "-"], GOOD) == 0
    assert capsys.readouterr().out == (
        "| Front | Back |\n|---|---|\n"
        "| JS: cancel a pending setTimeout? | clearTimeout(id) |\n"
    )
    assert not (tmp_path / "cards.tsv").exists()


def test_reads_a_file_argument(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Any
) -> None:
    spec = tmp_path / "cards.json"
    spec.write_text(json.dumps(GOOD), encoding="utf-8")
    assert _run(monkeypatch, ["--dry-run", str(spec)], {}) == 0
    assert "clearTimeout(id)" in capsys.readouterr().out


def test_replace_offline_fails_closed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Any
) -> None:
    monkeypatch.setattr(make_cards, "OUT_DIR", tmp_path)
    monkeypatch.setattr(anki_connect, "available", lambda: False)
    assert _run(monkeypatch, ["--replace", "-"], GOOD) == 1
    assert "needs Anki open" in capsys.readouterr().err
    assert not (tmp_path / "cards.tsv").exists()


def test_offline_writes_apkg_and_prints_bare_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Any
) -> None:
    monkeypatch.setattr(make_cards, "OUT_DIR", tmp_path)
    monkeypatch.setattr(anki_connect, "available", lambda: False)
    assert _run(monkeypatch, ["-"], GOOD) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[-1].startswith("anki ")
    assert lines[-1].endswith(".apkg")
    assert "(Anki desktop not open). Import with:" in lines[-2]
    assert list((tmp_path / "anki").glob("*-s.apkg"))
    tsv = (tmp_path / "cards.tsv").read_text(encoding="utf-8")
    assert tsv.endswith("\ts\tJS: cancel a pending setTimeout?\tclearTimeout(id)\n")


def test_bad_arguments_and_rejected_cards(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(monkeypatch, ["--dry-run", "--replace", "-"], GOOD) == 1
    usage = (
        "Usage: make_cards.py [--dry-run | --replace] <cards.json | ->   (- = stdin)"
    )
    assert capsys.readouterr().err.strip() == usage
    assert _run(monkeypatch, [], GOOD) == 1
    assert capsys.readouterr().err.strip() == usage
    bad = {"slug": "s", "cards": [_card("JS: nest or separate?", "Nest.")]}
    assert _run(monkeypatch, ["--dry-run", "-"], bad) == 1
    err = capsys.readouterr().err
    assert err.startswith("cards rejected:\n  card 1: either/or front")


def test_online_path_pushes_and_reports(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Any
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(make_cards, "OUT_DIR", tmp_path)
    monkeypatch.setattr(anki_connect, "available", lambda: True)
    monkeypatch.setattr(anki_connect, "ensure_model", lambda *a: calls.append("model"))
    monkeypatch.setattr(anki_connect, "sync", lambda: calls.append("sync"))
    monkeypatch.setattr(
        anki_connect, "sync_notes", lambda *a, replace: (1, 0, 2 if replace else 0)
    )
    assert _run(monkeypatch, ["--replace", "-"], GOOD) == 0
    out = capsys.readouterr().out
    assert "1 cards -> Anki desktop: 1 added, 0 updated, 2 deleted in 'LeetCode'" in out
    assert "AnkiWeb sync requested" in out
    assert calls == ["model", "sync"]


def test_script_entry_point(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.argv", ["make_cards.py"])
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_path(make_cards.__file__, run_name="__main__")
    assert exit_info.value.code == 1
    assert capsys.readouterr().err.startswith("Usage: make_cards.py")
