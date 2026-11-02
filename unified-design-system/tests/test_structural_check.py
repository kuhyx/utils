"""Tests for scripts/structural_check.py: both directions of the checker."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import structural_check
import structural_map

REAL_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """A scratch copy of the five source files, mutable per test."""
    for rel in structural_check.SOURCE_FILES.values():
        dest = tmp_path / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REAL_ROOT / rel, dest)
    return tmp_path


def edit(root: Path, stack: str, old: str, new: str) -> None:
    path = root / structural_check.SOURCE_FILES[stack]
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not in {path}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def failures(root: Path) -> list[str]:
    return [r.detail for r in structural_check.run(root) if not r.ok]


def test_real_tree_is_green() -> None:
    assert failures(REAL_ROOT) == []
    assert structural_check.main(REAL_ROOT) == 0


@pytest.mark.parametrize(
    ("stack", "old", "new", "token"),
    [
        ("css", "--space-2: 8px", "--space-2: 9px", "space.sm"),
        ("dart", "double sm = 8;", "double sm = 9;", "space.sm"),
        ("tk", "sm: int = 8", "sm: int = 9", "space.sm"),
        ("css", "--duration-fast: 120ms;", "--duration-fast: 130ms;", "duration.fast"),
        ("dart", "milliseconds: 200", "milliseconds: 210", "duration.base"),
        ("css", "cubic-bezier(0.3, 0, 1, 1)", "cubic-bezier(0.4, 0, 1, 1)", "ease.accelerate"),
        ("dart", "Cubic(0, 0, 0, 1)", "Cubic(0, 0, 0, 2)", "ease.decelerate"),
        ("css", "--radius-md: 12px", "--radius-md: 13px", "radius.md"),
        ("tk", "title: int = 24", "title: int = 25", "text.title"),
        ("css", "0 4px 8px rgba", "0 5px 8px rgba", "shadow.2"),
        ("md", "`sm 8` (buttons", "`sm 7` (buttons", "radius.sm"),
        ("motion", "`200ms`", "`210ms`", "duration.base"),
    ],
)
def test_value_drift_fails_naming_the_token(
    root: Path, stack: str, old: str, new: str, token: str
) -> None:
    edit(root, stack, old, new)
    found = failures(root)
    assert any(token in line and "DRIFT" in line for line in found), found
    assert structural_check.main(root) == 1


def test_missing_in_a_stack_fails(root: Path) -> None:
    edit(root, "css", "--space-2: 8px;", "")
    assert any("space.sm" in f and "MISSING" in f for f in failures(root))


def test_unmapped_css_token_fails_completeness(root: Path) -> None:
    edit(root, "css", "--space-6: 48px;", "--space-6: 48px; --space-7: 64px;")
    assert any("css" in f and "--space-7" in f for f in failures(root))


def test_unmapped_dart_token_fails_completeness(root: Path) -> None:
    edit(root, "dart", "static const double xxl = 48;", "static const double xxl = 48;\n  static const double huge = 64;")
    assert any("dart" in f and "AppSpacing.huge" in f for f in failures(root))


def test_unmapped_tk_token_fails_completeness(root: Path) -> None:
    edit(root, "tk", "xxl: int = 48", "xxl: int = 48\n    huge: int = 64")
    assert any("tk" in f and "LockSpacing.huge" in f for f in failures(root))


def test_unmapped_md_token_fails_completeness(root: Path) -> None:
    edit(root, "motion", "| `slow`    | `320ms` |", "| `glacial` | `900ms` |\n| `slow`    | `320ms` |")
    assert any("md" in f and "duration.glacial" in f for f in failures(root))


def test_unmapped_shadow_in_md_fails(root: Path) -> None:
    edit(root, "md", "- Level 1 (e.g. a dropdown)", "- Level 3 (e.g. a toast): `0 8px 16px rgba(0, 0, 0, 0.2)`\n  - Level 1 (e.g. a dropdown)")
    assert any("shadow.3" in f for f in failures(root))


def test_stale_exemption_fails(root: Path) -> None:
    edit(root, "css", "--measure: 40rem;", "")
    assert any("--measure" in f and "stale" in f for f in failures(root))


def test_missing_section_fails_closed(root: Path) -> None:
    edit(root, "md", "## Spacing scale (4px base)", "## Renamed")
    with pytest.raises(SystemExit):
        structural_check.run(root)


def test_missing_class_fails_closed(root: Path) -> None:
    edit(root, "tk", "class LockSpacing", "class Renamed")
    # Renamed class still has int fields, so the tokens map to nothing.
    assert any("LockSpacing" in f for f in failures(root))


def test_no_dart_class_fails_closed(root: Path) -> None:
    path = root / structural_check.SOURCE_FILES["dart"]
    path.write_text("// empty\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        structural_check.run(root)


def test_no_tk_ints_fails_closed(root: Path) -> None:
    path = root / structural_check.SOURCE_FILES["tk"]
    path.write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        structural_check.run(root)


def test_css_without_media_fails_closed(root: Path) -> None:
    path = root / structural_check.SOURCE_FILES["css"]
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("@media", "@supports"), encoding="utf-8")
    with pytest.raises(SystemExit):
        structural_check.run(root)


def test_absent_stack_requires_a_reason() -> None:
    with pytest.raises(ValueError, match="why"):
        structural_map.Token("space.zz", "--space-zz", None, "x")


@pytest.mark.parametrize(
    ("kind", "raw", "expected"),
    [
        ("space", "8px", "8"),
        ("duration", "Duration.zero", "0"),
        ("duration", "0ms", "0"),
        ("duration", "Duration(milliseconds: 120)", "120"),
        ("ease", "cubic-bezier(0.2, 0, 0, 1)", "0.2,0,0,1"),
        ("ease", "Cubic(0.2, 0, 0, 1)", "0.2,0,0,1"),
        ("shadow", "0  2px   4px", "0 2px 4px"),
        ("space", "none", "none"),
    ],
)
def test_norm(kind: str, raw: str, expected: str) -> None:
    assert structural_check.norm(kind, raw) == expected


def test_cli_exit_codes(root: Path) -> None:
    script = REAL_ROOT / "unified-design-system/scripts/structural_check.py"
    ok = subprocess.run([sys.executable, str(script)], check=False, capture_output=True)
    assert ok.returncode == 0
    edit(root, "css", "--space-2: 8px", "--space-2: 9px")
    scratch = root / "unified-design-system/scripts"
    scratch.mkdir(parents=True)
    for name in ("structural_check.py", "structural_map.py", "structural_parse.py"):
        shutil.copy(script.parent / name, scratch / name)
    bad = subprocess.run(
        [sys.executable, str(scratch / "structural_check.py")],
        check=False,
        capture_output=True,
        text=True,
    )
    assert bad.returncode == 1
    assert "space.sm" in bad.stdout
    assert "DRIFT" in bad.stdout


def test_spacing_line_absent_is_not_invented(root: Path) -> None:
    edit(root, "md", "`xs 4 · sm 8", "xs 4 · sm 8")
    assert any("MISSING" in f and "space." in f for f in failures(root))
