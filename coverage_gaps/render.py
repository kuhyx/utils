"""Filtering and rendering: markdown (agent task list) and JSON."""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence

from coverage_gaps.models import FileGap


def compact_ranges(lines: Iterable[int]) -> str:
    """Collapse line numbers into '12-18, 40'."""
    nums = sorted(set(lines))
    parts: list[str] = []
    idx = 0
    while idx < len(nums):
        end = idx
        while end + 1 < len(nums) and nums[end + 1] == nums[end] + 1:
            end += 1
        parts.append(_span(nums[idx], nums[end]))
        idx = end + 1
    return ", ".join(parts)


def _span(start: int, end: int) -> str:
    return str(start) if start == end else f"{start}-{end}"


def select(
    gaps: Sequence[FileGap], *, path_prefix: str = "", min_missed: int = 1
) -> list[FileGap]:
    """Keep files with gaps under the prefix, worst first (ties by path)."""
    kept = [
        gap
        for gap in gaps
        if gap.path.startswith(path_prefix) and gap.missed >= max(min_missed, 1)
    ]
    return sorted(kept, key=lambda gap: (-gap.missed, gap.path))


def _totals(files: Sequence[FileGap]) -> dict[str, int]:
    return {
        "files": len(files),
        "missed_lines": sum(len(gap.missed_lines) for gap in files),
        "missed_branches": sum(gap.missed_branches for gap in files),
    }


def to_json(fmt: str, files: Sequence[FileGap], shown: int) -> str:
    """Machine-readable output; `files` is already sorted and filtered."""
    entries = [
        {
            "path": gap.path,
            "percent_covered": round(gap.percent, 2),
            "missed": gap.missed,
            "missed_lines": compact_ranges(gap.missed_lines),
            "missed_line_numbers": list(gap.missed_lines),
            "missed_branch_count": gap.missed_branches,
            "missed_branch_lines": list(gap.missed_branch_lines),
        }
        for gap in files[:shown]
    ]
    doc = {
        "format": fmt,
        "total": _totals(files),
        "shown": len(entries),
        "files": entries,
    }
    return json.dumps(doc, indent=2)


def to_markdown(fmt: str, files: Sequence[FileGap], shown: int) -> str:
    """Markdown task list meant to be pasted to an agent verbatim."""
    total = _totals(files)
    out = [
        "# Coverage gaps",
        "",
        (
            f"Format: {fmt}. Total: {total['files']} files with gaps, "
            f"{total['missed_lines']} missed lines, "
            f"{total['missed_branches']} missed branches."
        ),
    ]
    if shown < len(files):
        out.append(f"Showing the {shown} worst files.")
    if not files:
        return "\n".join(out) + "\n\nNo coverage gaps.\n"
    out += ["", "Write tests that cover every item below, then re-run the report.", ""]
    for rank, gap in enumerate(files[:shown], start=1):
        out.append(f"## {rank}. `{gap.path}` - {gap.percent:.1f}% covered")
        if gap.missed_lines:
            out.append(
                f"- missed lines ({len(gap.missed_lines)}): "
                f"{compact_ranges(gap.missed_lines)}"
            )
        if gap.missed_branches:
            out.append(
                f"- missed branches ({gap.missed_branches}) at lines: "
                f"{compact_ranges(gap.missed_branch_lines)}"
            )
        out.append("")
    return "\n".join(out).rstrip() + "\n"
