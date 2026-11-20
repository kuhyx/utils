"""Generator: SVG parsing, token parsing, emitters and the drift check."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from generator import generate, svg, tokens

CREDIT_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = CREDIT_DIR.parent


def test_logo_parses_into_disjoint_polygons() -> None:
    logo = svg.parse_logo((REPO_ROOT / "unified-design-system/logo/final/kuhy.svg").read_text())
    assert logo.size == 512
    assert logo.field == "#211D1B"
    assert [s.fill for s in logo.shapes] == ["#B8862E"] * 2 + ["#ECEAE9"] * 2
    assert all(len(s.points) >= 3 for s in logo.shapes)


def test_overlapping_subpaths_are_rejected() -> None:
    doc = (
        '<svg viewBox="0 0 10 10"><rect id="field" fill="#000000"/>'
        '<path fill="#FFFFFF" d="M1 1L5 1L5 5ZM2 2L6 2L6 6Z"/></svg>'
    )
    with pytest.raises(ValueError, match="overlap"):
        svg.parse_logo(doc)


def test_unsupported_path_command_is_rejected() -> None:
    doc = (
        '<svg viewBox="0 0 10 10"><rect id="field" fill="#000000"/>'
        '<path fill="#FFFFFF" d="M1 1C5 1 5 5 1 1Z"/></svg>'
    )
    with pytest.raises(ValueError, match="unsupported"):
        svg.parse_logo(doc)


def test_missing_field_is_rejected() -> None:
    with pytest.raises(ValueError, match="field"):
        svg.parse_logo('<svg viewBox="0 0 10 10"></svg>')


def test_tokens_read_dark_and_light_from_css() -> None:
    tok = tokens.parse_tokens((REPO_ROOT / "web_ui/src/tokens.css").read_text())
    assert tok.dark.surface == "#2b2624"
    assert tok.light.surface == "#fcfbfb"
    assert tok.dark.text == "#eceae9"
    assert tok.light.text == "#211d1b"
    assert tok.focus == "#b8862e"
    assert (tok.radius, tok.space_sm, tok.space_md, tok.text_body) == (12, 8, 16, 16)


def test_missing_token_is_rejected() -> None:
    with pytest.raises(ValueError, match="--surface-1"):
        tokens.parse_tokens(":root { --bg: #000000; }")


def test_every_generated_file_matches_the_sources() -> None:
    assert generate.drift(CREDIT_DIR) == []


def test_main_check_passes_on_a_clean_tree(capsys: pytest.CaptureFixture[str]) -> None:
    assert generate.main(["--check"]) == 0
    assert "in sync" in capsys.readouterr().out


@pytest.fixture
def copy(tmp_path: Path) -> Path:
    """A throwaway copy of the repo bits the generator reads and writes."""
    root = tmp_path / "repo"
    for rel in ("unified-design-system/logo/final", "web_ui/src"):
        (root / rel).mkdir(parents=True)
    shutil.copy(
        REPO_ROOT / "unified-design-system/logo/final/kuhy.svg",
        root / "unified-design-system/logo/final",
    )
    shutil.copy(REPO_ROOT / "web_ui/src/tokens.css", root / "web_ui/src")
    (root / "kuhy_credit").mkdir()
    shutil.copy(CREDIT_DIR / "credit.json", root / "kuhy_credit")
    return root / "kuhy_credit"


def test_write_then_check_round_trips(copy: Path) -> None:
    assert {d.stack for d in generate.drift(copy)} == set(generate.STACKS)
    generate.write(copy)
    assert generate.drift(copy) == []


@pytest.mark.parametrize("stack", sorted(generate.STACKS))
def test_editing_one_stack_names_that_stack(
    copy: Path, stack: str, capsys: pytest.CaptureFixture[str]
) -> None:
    generate.write(copy)
    target = copy / generate.STACKS[stack]
    target.write_text(target.read_text().replace("https://kuhy.duckdns.org", "https://example.org"))
    assert [d.stack for d in generate.drift(copy)] == [stack]
    assert generate.main(["--check", "--dir", str(copy)]) == 1
    assert stack in capsys.readouterr().out


def test_changing_the_shared_url_drifts_every_stack(copy: Path) -> None:
    generate.write(copy)
    data = json.loads((copy / "credit.json").read_text())
    data["url"] = "https://example.org"
    (copy / "credit.json").write_text(json.dumps(data))
    assert {d.stack for d in generate.drift(copy)} == set(generate.STACKS)


def test_main_writes_without_check(copy: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert generate.main(["--dir", str(copy)]) == 0
    assert "wrote" in capsys.readouterr().out
    assert generate.drift(copy) == []


def test_css_without_root_is_rejected() -> None:
    with pytest.raises(ValueError, match="--surface-1"):
        tokens.parse_tokens("")


def test_whole_numbers_keep_a_decimal_point() -> None:
    from generator import emit

    assert emit._num(12.0) == "12.0"
    assert emit._num(12.5) == "12.5"
