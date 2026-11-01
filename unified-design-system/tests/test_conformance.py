"""Tests for scripts/conformance.py (100 % branch coverage)."""

from __future__ import annotations

import json
import runpy
import sys
from typing import TYPE_CHECKING

import conformance
import pytest

if TYPE_CHECKING:
    from pathlib import Path


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_count_text_css_tokens_literals_and_skips() -> None:
    css = (
        "/* #123456 in a comment */\n"
        ":root { --brand: #b8862e; }\n"
        "@media (min-width: 600px) { a { color: red; } }\n"
        ".a { color: var(--brand); margin: 12px 0px; border: 1.5pt solid #fff; }\n"
    )
    assert conformance.count_text(css, ".css") == (1, 3)


def test_count_text_line_comments_and_urls_in_ts() -> None:
    ts = 'const u = "http://x.test"; // #abcdef\nconst c = "#a1b2c3";\n'
    assert conformance.count_text(ts, ".ts") == (0, 1)


def test_count_text_dart_tokens_and_literals() -> None:
    dart = (
        "final c = Color(0xFF112233);\n"
        "final d = AppPalette.accent;\n"
        "final e = Theme.of(context).colorScheme.primary;\n"
    )
    assert conformance.count_text(dart, ".dart") == (3, 1)


def test_conformance_percent_and_none() -> None:
    assert conformance.Surface("x").conformance is None
    assert conformance.Surface("x", 1, 3, 1).conformance == 75.0


def test_scan_groups_by_manifest_and_skips_generated(tmp_path: Path) -> None:
    write(tmp_path, "pubspec.yaml", "name: a")
    write(tmp_path, "lib/ui.dart", "final c = AppPalette.bg; final d = '#fff';")
    write(tmp_path, "lib/tokens.dart", "const c = Color(0xFF000000);")
    write(tmp_path, "lib/a.g.dart", "const c = '#ffffff';")
    write(tmp_path, "build/out.css", "a { color: #fff }")
    write(tmp_path, "test/x_test.dart", "const c = '#fff';")
    write(tmp_path, "web/package.json", "{}")
    write(tmp_path, "web/s.css", "a { margin: 8px; color: var(--x); }")
    write(tmp_path, "site/astro.config.mjs", "export default {}")
    write(tmp_path, "site/p.astro", "<p style='top: 4pt'>hi</p>")
    write(tmp_path, "loose/readme.txt", "#fff 3px")
    write(tmp_path, "root.tsx", "const a = 'var(--r)';")
    write(tmp_path, "big.css", "a{}" + " " * conformance.MAX_BYTES)
    surfaces = {s.name: s for s in conformance.scan(tmp_path)}
    assert sorted(surfaces) == [".", "site", "web"]
    assert (surfaces["."].token_usages, surfaces["."].raw_literals) == (2, 1)
    assert surfaces["."].files == 2
    assert (surfaces["web"].token_usages, surfaces["web"].raw_literals) == (1, 1)
    assert (surfaces["site"].token_usages, surfaces["site"].raw_literals) == (0, 1)


def test_scan_ignores_non_regular_file(tmp_path: Path) -> None:
    (tmp_path / "dangling.css").symlink_to(tmp_path / "missing.css")
    assert conformance.scan(tmp_path) == []


def test_totals_and_report(tmp_path: Path) -> None:
    write(tmp_path, "a.css", "a { margin: 8px; }")
    write(tmp_path, "web/package.json", "{}")
    write(tmp_path, "web/b.css", "b { color: var(--x); }")
    rep = conformance.report(tmp_path)
    assert rep["totals"]["token_usages"] == 1
    assert rep["totals"]["raw_literals"] == 1
    assert rep["totals"]["conformance"] == 50.0
    assert [s["name"] for s in rep["surfaces"]] == [".", "web"]


def test_main_table_json_and_delta(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = tmp_path / "repo"
    write(repo, "a.css", "a { margin: 8px; color: var(--x); }")
    assert conformance.main([str(repo)]) == 0
    assert "TOTAL" in capsys.readouterr().out
    assert conformance.main([str(repo), "--json"]) == 0
    first = capsys.readouterr().out
    assert "delta" not in json.loads(first)
    prev = tmp_path / "prev.json"
    prev.write_text(first, encoding="utf-8")
    write(repo, "b.css", "b { color: var(--y); }")
    assert conformance.main([str(repo), "--json", "--previous", str(prev)]) == 0
    assert json.loads(capsys.readouterr().out)["delta"]["rows"][-1]["token_usages"] == 1.0
    assert conformance.main([str(repo), "--previous", str(prev)]) == 0
    assert "d.tokens" in capsys.readouterr().out


def test_main_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert conformance.main([str(tmp_path / "nope")]) == 2
    assert "not a directory" in capsys.readouterr().err
    assert conformance.main([str(tmp_path), "--previous", str(tmp_path / "none.json")]) == 2
    assert "cannot read previous" in capsys.readouterr().err


def test_script_entry_point(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["conformance.py", str(tmp_path)])
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_path(conformance.__file__, run_name="__main__")
    assert exit_info.value.code == 0
