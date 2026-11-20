"""Write, or check, every stack's generated credit data.

    python -m generator.generate            # rewrite all stacks
    python -m generator.generate --check    # exit 1 and name each drifted stack

Reads kuhy_credit/credit.json (URL + text), the M1 art and tokens.css; the
paths in credit.json are relative to the repo root (the credit dir's parent).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from generator import emit
from generator.svg import parse_logo
from generator.tokens import parse_tokens

CREDIT_DIR = Path(__file__).resolve().parents[1]

STACKS = {
    "python": "kuhy_credit/_data.py",
    "web": "web/src/credit-data.js",
    "flutter": "flutter/lib/src/credit_data.g.dart",
    "godot": "godot/addons/kuhy_credit/credit_data.gd",
    "terminal": "terminal/kuhy-credit.sh",
}
_EMITTERS = {
    "python": emit.python,
    "web": emit.web,
    "flutter": emit.flutter,
    "godot": emit.godot,
    "terminal": emit.terminal,
}


@dataclass(frozen=True)
class Drift:
    """A stack whose generated file differs from what the sources give."""

    stack: str
    path: str


def load(credit_dir: Path) -> emit.Credit:
    """Read credit.json and the files it points at."""
    data = json.loads((credit_dir / "credit.json").read_text())
    root = credit_dir.parent
    svg = (root / data["logo"]).read_text()
    return emit.Credit(
        url=data["url"],
        text=data["text"],
        svg=svg,
        logo=parse_logo(svg),
        tokens=parse_tokens((root / data["tokens"]).read_text()),
    )


def render(credit_dir: Path) -> dict[str, str]:
    """Every stack's expected file content."""
    credit = load(credit_dir)
    return {stack: _EMITTERS[stack](credit) for stack in STACKS}


def drift(credit_dir: Path) -> list[Drift]:
    """Stacks whose file on disk is missing or differs from render()."""
    out = []
    for stack, text in render(credit_dir).items():
        path = credit_dir / STACKS[stack]
        if not path.is_file() or path.read_text() != text:
            out.append(Drift(stack, STACKS[stack]))
    return out


def write(credit_dir: Path) -> None:
    """Rewrite every stack's generated file."""
    for stack, text in render(credit_dir).items():
        path = credit_dir / STACKS[stack]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        if stack == "terminal":
            path.chmod(0o755)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; returns the exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail on drift, write nothing")
    parser.add_argument("--dir", type=Path, default=CREDIT_DIR, help="the kuhy_credit dir")
    args = parser.parse_args(argv)
    if not args.check:
        write(args.dir)
        print(f"wrote {len(STACKS)} stacks")
        return 0
    found = drift(args.dir)
    for d in found:
        print(f"drift: {d.stack} ({d.path}) differs from credit.json/logo/tokens")
    if found:
        print("fix: python -m generator.generate (from kuhy_credit/)")
        return 1
    print(f"all {len(STACKS)} stacks in sync")
    return 0


if __name__ == "__main__":
    sys.exit(main())
