"""LaTeX stack: the generated package compiles and links the logo to the site."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from generator import generate

CREDIT_DIR = Path(__file__).resolve().parents[1]
LATEX_DIR = CREDIT_DIR / "latex"


def test_latex_is_a_generated_stack() -> None:
    assert generate.STACKS["latex"] == "latex/kuhy-credit.sty"


def _compile(tmp_path: Path) -> bytes:
    """Build latex/demo/demo.tex uncompressed and return the PDF bytes."""
    pdflatex = shutil.which("pdflatex")
    if pdflatex is None:
        pytest.fail("pdflatex is required for the LaTeX stack E2E")
    shutil.copy(LATEX_DIR / "demo/demo.tex", tmp_path)
    env = {**os.environ, "TEXINPUTS": f"{LATEX_DIR}//:"}
    subprocess.run(
        [pdflatex, "-interaction=nonstopmode", "-halt-on-error", "demo.tex"],
        cwd=tmp_path,
        env=env,
        check=True,
        capture_output=True,
    )
    return (tmp_path / "demo.pdf").read_bytes()


def test_demo_pdf_links_the_logo_to_the_site(tmp_path: Path) -> None:
    pdf = _compile(tmp_path)
    url = json.loads((CREDIT_DIR / "credit.json").read_text())["url"]
    # One link per \kuhycredit call in the demo (footer, body, page corner).
    assert pdf.count(f"/URI({url})".encode()) == 3
    # The field and both glyph colours are painted (non-stroking rgb fills).
    for rgb in (b"0.12941 0.11374 0.10588", b"0.72157 0.5255 0.18039", b"0.92549 0.91765 0.91374"):
        assert rgb + b" rg" in pdf
    # Links draw no border box: the logo is the only visible mark.
    assert b"/Border[0 0 0]" in pdf


def test_logo_only_no_visible_words(tmp_path: Path) -> None:
    """The PDF shows the logo; the words live only in the link tooltip/metadata."""
    pdf = _compile(tmp_path)
    text = json.loads((CREDIT_DIR / "credit.json").read_text())["text"]
    shown = re.findall(rb"\[\((.*?)\)\]\s*TJ", pdf)
    assert not any(text.encode() in s for s in shown)


@pytest.mark.parametrize("value", ["https://x.org/a%20b", "50% off", "a_b"])
def test_tex_special_characters_are_refused(value: str) -> None:
    from generator import emit

    with pytest.raises(ValueError, match="TeX-special"):
        emit._tex_safe(value)


def test_corner_logo_sits_in_the_bottom_right_margin(tmp_path: Path) -> None:
    """\\kuhycreditcorner[4mm] puts a 12mm logo 4mm from the page's corner."""
    pdf = _compile(tmp_path)
    rects = [tuple(float(v) for v in m.split()) for m in re.findall(rb"/Rect\s*\[([^\]]*)\]", pdf)]
    mm = 72 / 25.4
    width = 8.5 * 72  # letterpaper in the demo
    want = (width - 16 * mm, 4 * mm, width - 4 * mm, 16 * mm)
    assert any(all(abs(a - b) < 1 for a, b in zip(r, want, strict=True)) for r in rects), rects
