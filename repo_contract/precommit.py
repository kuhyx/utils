"""Add a local hook to a repo's .pre-commit-config.yaml without a YAML round-trip.

A round-trip would drop the comments explaining why each hook is there, so the
snippet is spliced in as text at the end of the LAST `- repo: local` block.
"""

from __future__ import annotations

from pathlib import Path

PRECOMMIT = Path(".pre-commit-config.yaml")
LOCAL_REPO = "  - repo: local"
EMPTY_PRECOMMIT = f"repos:\n{LOCAL_REPO}\n    hooks:\n"


def needs_hook(repo: Path, hook_id: str) -> bool:
    """True when the pre-commit config is missing or lacks `id: <hook_id>`."""
    target = repo / PRECOMMIT
    return not target.is_file() or f"id: {hook_id}" not in target.read_text(
        encoding="utf-8"
    )


def local_block_end(lines: list[str]) -> int:
    """Index just past the LAST `- repo: local` block, or -1 if there is none."""
    starts = [n for n, line in enumerate(lines) if line.rstrip() == LOCAL_REPO]
    if not starts:
        return -1
    after = [
        n for n in range(starts[-1] + 1, len(lines)) if lines[n].startswith("  - repo:")
    ]
    return after[0] if after else len(lines)


def write_hook(repo: Path, snippet: str) -> None:
    """Insert `snippet` (comment lines dropped) into the LAST local hooks list."""
    target = repo / PRECOMMIT
    body = target.read_text(encoding="utf-8") if target.is_file() else EMPTY_PRECOMMIT
    lines = (body if body.endswith("\n") else body + "\n").split("\n")[:-1]
    cut = local_block_end(lines)
    if cut < 0:
        raise ValueError(
            f"{target} has no `{LOCAL_REPO}` block to add the hook to; "
            "add one by hand, then re-run"
        )
    block = [ln for ln in snippet.rstrip("\n").split("\n") if not ln.startswith("#")]
    lines[cut:cut] = ["", *block]
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _hook_block(lines: list[str], hook_id: str) -> tuple[int, int]:
    """[start, end) of the hook's lines, trailing blanks excluded.

    Precondition for this and the two callers below: the hook exists
    (`needs_hook` is False), so the id line is there to anchor on.
    """
    start = lines.index(f"      - id: {hook_id}")
    end = next(
        (
            n
            for n in range(start + 1, len(lines))
            if lines[n].startswith(("      - ", "  - "))
        ),
        len(lines),
    )
    while not lines[end - 1].strip():
        end -= 1
    return start, end


def hook_line(repo: Path, hook_id: str, key: str) -> str | None:
    """The hook's `<key>:` line (8-space indent) as written, or None."""
    lines = (repo / PRECOMMIT).read_text(encoding="utf-8").split("\n")
    start, end = _hook_block(lines, hook_id)
    prefix = f"        {key}:"
    return next((ln for ln in lines[start:end] if ln.startswith(prefix)), None)


def set_hook_line(repo: Path, hook_id: str, key: str, line: str) -> None:
    """Replace the hook's `<key>:` line with `line`, or append it to the block."""
    target = repo / PRECOMMIT
    lines = target.read_text(encoding="utf-8").split("\n")
    start, end = _hook_block(lines, hook_id)
    prefix = f"        {key}:"
    found = [n for n in range(start, end) if lines[n].startswith(prefix)]
    if found:
        lines[found[0]] = line
    else:
        lines.insert(end, line)
    target.write_text("\n".join(lines), encoding="utf-8")
