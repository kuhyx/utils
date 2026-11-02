"""Verify spacing, radius, type, shadow and motion agree across all stacks.

`palette_check.py` guards colour only (every parser wants `#RRGGBB`), so these
scales were unprotected until now. Same two halves:

  * agreement -- each mapped token resolves in every stack that is not `n/a`
    for it, and all stacks carry the same value
  * completeness -- every structural name any source defines is mapped or
    exempted with a reason, in both directions (a stale exemption also fails)

Sources: DOCS-tokens.md + DOCS-motion.md (prose freeze), web_ui tokens.css,
design_system tokens.dart, gatelock _theme.py.

Run: python3 unified-design-system/scripts/structural_check.py
Exit 0 = agree and complete; 1 = drift, a missing value or an unmapped name.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

import structural_parse as sp
from structural_map import EXEMPT, STACKS, TOKENS

ROOT = Path(__file__).resolve().parents[2]
SOURCE_FILES: dict[str, str] = {
    "md": "unified-design-system/DOCS-tokens.md",
    "motion": "unified-design-system/DOCS-motion.md",
    "css": "web_ui/src/tokens.css",
    "dart": "design_system/lib/src/tokens.dart",
    "tk": "gatelock/gatelock/_theme.py",
}


@dataclass
class Result:
    """One check outcome."""

    ok: bool
    detail: str


def norm(kind: str, raw: str) -> str:
    """Reduce a raw source value to a comparable string for its kind."""
    if kind == "shadow":
        return " ".join(raw.split())
    nums = re.findall(r"-?\d*\.?\d+", raw)
    if kind == "ease":
        return ",".join(f"{float(n):g}" for n in nums)
    if not nums:
        return "0" if "zero" in raw else raw.strip()
    return f"{float(nums[0]):g}"


def load(root: Path) -> dict[str, sp.Table]:
    """Parse every source under `root` into `{stack: {key: raw}}`."""

    def read(key: str) -> str:
        return (root / SOURCE_FILES[key]).read_text(encoding="utf-8")

    return {
        "md": {**sp.parse_tokens_md(read("md")), **sp.parse_motion_md(read("motion"))},
        "css": sp.parse_css(read("css")),
        "dart": sp.parse_dart(read("dart")),
        "tk": sp.parse_tk(read("tk")),
    }


def check_agreement(src: dict[str, sp.Table]) -> list[Result]:
    """Every mapped token must carry one value in every non-`n/a` stack."""
    results: list[Result] = []
    for token in TOKENS:
        kind = token.canonical.split(".")[0]
        names = {"md": token.canonical, **{s: getattr(token, s) for s in STACKS}}
        seen: dict[str, str] = {}
        missing: list[str] = []
        for stack, name in names.items():
            if name is None:
                continue
            if name in src[stack]:
                seen[stack] = norm(kind, src[stack][name])
            else:
                missing.append(f"{stack}:{name} ({SOURCE_FILES[stack]})")
        if missing:
            results.append(Result(False, f"{token.canonical:<20} MISSING {', '.join(missing)}"))
        elif len(set(seen.values())) > 1:
            detail = ", ".join(f"{s}={v}" for s, v in seen.items())
            files = ", ".join(SOURCE_FILES[s] for s in seen)
            results.append(Result(False, f"{token.canonical:<20} DRIFT {detail}  [{files}]"))
        else:
            results.append(
                Result(True, f"{token.canonical:<20} {next(iter(seen.values()))} x{len(seen)}")
            )
    return results


def check_completeness(src: dict[str, sp.Table]) -> list[Result]:
    """No unmapped name in any source, and no exemption for a vanished name."""
    results: list[Result] = []
    for stack in ("md", *STACKS):
        if stack == "md":
            mapped = {t.canonical for t in TOKENS}
        else:
            mapped = {getattr(t, stack) for t in TOKENS if getattr(t, stack)}
        exempt = EXEMPT.get(stack, {})
        extras = sorted(n for n in src[stack] if n not in mapped and n not in exempt)
        stale = sorted(n for n in exempt if n not in src[stack])
        if extras:
            msg = f"{stack:<4} defines unmapped name(s): {', '.join(extras)} -- add to TOKENS or EXEMPT"
            results.append(Result(False, msg))
        if stale:
            results.append(Result(False, f"{stack:<4} stale exemption(s): {', '.join(stale)}"))
        if not extras and not stale:
            results.append(Result(True, f"{stack:<4} all {len(src[stack])} parsed name(s) accounted for"))
    return results


def run(root: Path) -> list[Result]:
    """Both halves of the check against the sources under `root`."""
    src = load(root)
    return [*check_agreement(src), *check_completeness(src)]


def main(root: Path = ROOT) -> int:
    """Print the report; non-zero on any failing check."""
    results = run(root)
    for r in results:
        print(("PASS " if r.ok else "FAIL ") + r.detail)
    failures = sum(not r.ok for r in results)
    print(f"\n{failures} failing check(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
