"""Design-token conformance per UI surface: tokens used vs raw literals.

Install counts and component counts are vanity metrics. What shows whether a
design system is working is how often a surface reaches for a token versus a
hard-coded value (learn.thedesignsystem.guide, "Half my design system metrics
don't work anymore"). This script counts, per UI surface of one repo:

  * token usages: ``var(--x)`` in CSS/TS/TSX/Astro, ``AppPalette.x`` style
    constants and ``Theme.of`` / ``colorScheme`` / ``textTheme`` in Dart
  * raw literals: hex colours (``#rrggbb``, ``0xAARRGGBB``) and non-zero
    ``px`` / ``pt`` numbers, outside the token files

A surface is the nearest ancestor directory holding a manifest
(``pubspec.yaml``, ``package.json``, ``astro.config.*``), else the repo root.
Token files (tokens/theme/palette/colors), custom-property definitions,
comments, tests, ``@media`` lines and generated/build dirs are skipped.
The counts are a heuristic trend signal, not an audit.

Run: python3 conformance.py <repo> [--json] [--previous <earlier.json>]
Exit 0 = report printed; 2 = bad arguments or unreadable previous file.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from conformance_diff import delta, load_previous, table

Json = dict[str, Any]

EXTENSIONS = frozenset({".dart", ".css", ".ts", ".tsx", ".astro"})
SKIP_DIRS = frozenset({
    ".git", "node_modules", "build", "dist", ".dart_tool", ".astro", ".next",
    "coverage", "generated", "__pycache__", ".venv", "test", "tests",
    "__tests__", ".fvm", ".pub-cache",
})
SKIP_NAME = re.compile(
    r"(\.g\.dart|\.freezed\.dart|\.d\.ts|\.test\.[jt]sx?|_test\.dart)$"
)
TOKEN_FILE = re.compile(r"^_?(tokens?|theme|palette|colou?rs?)\b", re.IGNORECASE)
MANIFESTS = ("pubspec.yaml", "package.json")
MAX_BYTES = 1_000_000

BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
LINE_COMMENT = re.compile(r"(?<![:\w])//.*")
TOKEN_DEFINITION = re.compile(r"--[\w-]+\s*:[^;}]*;?")
MEDIA_LINE = re.compile(r"@(media|container)\b")
HEX = re.compile(
    r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})\b|\b0x[0-9A-Fa-f]{8}\b"
)
UNIT = re.compile(r"(?<![\w.#-])(?!0+(?:\.0+)?(?:px|pt)\b)\d+(?:\.\d+)?(?:px|pt)\b")
TOKEN_USE = re.compile(
    r"var\(--|\bApp(?:Palette|Spacing|Radius|TextSize|Duration|Curve)\.\w+"
    r"|\bTheme\.of\(|\bcolorScheme\.|\btextTheme\."
)


@dataclass
class Surface:
    """Counts for one UI surface."""

    name: str
    files: int = 0
    token_usages: int = 0
    raw_literals: int = 0

    @property
    def conformance(self) -> float | None:
        """Percent of style values that are tokens, or None with no values."""
        total = self.token_usages + self.raw_literals
        if total == 0:
            return None
        return round(100.0 * self.token_usages / total, 1)

    def as_dict(self) -> Json:
        """JSON-ready form."""
        return {
            "name": self.name,
            "files": self.files,
            "token_usages": self.token_usages,
            "raw_literals": self.raw_literals,
            "conformance": self.conformance,
        }


def strip_comments(text: str, suffix: str) -> str:
    """Remove comments so a hex in prose is not counted as a literal."""
    text = BLOCK_COMMENT.sub("", text)
    if suffix == ".css":
        return text
    return LINE_COMMENT.sub("", text)


def count_text(text: str, suffix: str) -> tuple[int, int]:
    """Return (token usages, raw literals) for one file's text."""
    tokens = 0
    literals = 0
    for line in strip_comments(text, suffix).splitlines():
        tokens += len(TOKEN_USE.findall(line))
        if MEDIA_LINE.search(line):
            continue
        line = TOKEN_DEFINITION.sub("", line)
        literals += len(HEX.findall(line)) + len(UNIT.findall(line))
    return tokens, literals


def _has_manifest(directory: Path) -> bool:
    """True when ``directory`` holds a package/app manifest."""
    return any((directory / m).exists() for m in MANIFESTS) or any(
        directory.glob("astro.config.*")
    )


def surface_root(path: Path, repo: Path) -> Path:
    """Nearest ancestor of ``path`` (within ``repo``) holding a manifest."""
    parent = path.parent
    while parent != repo and not _has_manifest(parent):
        parent = parent.parent
    return parent


def ui_files(repo: Path) -> list[Path]:
    """UI source files, skipping build/generated dirs and token files."""
    found: list[Path] = []
    for root, dirs, names in os.walk(repo):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(names):
            path = Path(root) / name
            if path.suffix not in EXTENSIONS or SKIP_NAME.search(name):
                continue
            if TOKEN_FILE.match(path.stem):
                continue
            if path.is_file() and path.stat().st_size <= MAX_BYTES:
                found.append(path)
    return found


def scan(repo: Path) -> list[Surface]:
    """Count every UI surface under ``repo``, sorted by name."""
    surfaces: dict[Path, Surface] = {}
    for path in ui_files(repo):
        root = surface_root(path, repo)
        name = str(root.relative_to(repo))
        surface = surfaces.setdefault(root, Surface(name))
        text = path.read_text(encoding="utf-8", errors="replace")
        tokens, literals = count_text(text, path.suffix)
        surface.files += 1
        surface.token_usages += tokens
        surface.raw_literals += literals
    return sorted(surfaces.values(), key=lambda s: s.name)


def totals(surfaces: list[Surface]) -> Surface:
    """Sum of all surfaces."""
    return Surface(
        "TOTAL",
        sum(s.files for s in surfaces),
        sum(s.token_usages for s in surfaces),
        sum(s.raw_literals for s in surfaces),
    )


def report(repo: Path) -> Json:
    """Whole-repo report as a JSON-ready dict."""
    surfaces = scan(repo)
    return {
        "repo": str(repo),
        "surfaces": [s.as_dict() for s in surfaces],
        "totals": totals(surfaces).as_dict(),
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("repo", type=Path)
    parser.add_argument("--json", action="store_true", help="print JSON")
    parser.add_argument("--previous", type=Path, help="earlier --json output")
    args = parser.parse_args(argv)
    if not args.repo.is_dir():
        print(f"not a directory: {args.repo}", file=sys.stderr)
        return 2
    rep = report(args.repo.resolve())
    diff = None
    if args.previous:
        try:
            diff = delta(rep, load_previous(args.previous))
        except (OSError, ValueError) as exc:
            print(f"cannot read previous report: {exc}", file=sys.stderr)
            return 2
    if args.json:
        print(json.dumps({**rep, **({"delta": diff} if diff else {})}, indent=2))
    else:
        print(table(rep, diff))
    return 0


if __name__ == "__main__":
    sys.exit(main())
