"""Propose (or with --write, create) the `## Commands` section and test script.

Usage: bootstrap.py --repo PATH [--write]. Never overwrites: the section is
appended (or missing lines inserted at the end of an existing section) and
scripts/test_changed.sh is only created when absent.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - plain-script import path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from repo_contract.contract import HEADING, has_section, parse_entries
from repo_contract.infer import TEST_CHANGED, Proposal, propose
from repo_contract.stacks import detect_stacks

TEMPLATES = Path(__file__).resolve().parent / "templates"


def insert_lines(text: str, new: list[str]) -> str:
    """`text` with `new` lines added: appended section, or end of existing one."""
    if not new:
        return text
    if not has_section(text):
        sep = (
            ""
            if not text or text.endswith("\n\n")
            else ("\n" if text.endswith("\n") else "\n\n")
        )
        return f"{text}{sep}{HEADING}\n\n" + "\n".join(new) + "\n"
    lines = text.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.strip() == HEADING)
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )
    while end > start + 1 and not lines[end - 1].strip():
        end -= 1
    lines[end:end] = new
    return "\n".join(lines) + "\n"


def doc_path(repo: Path) -> Path:
    """The file to edit: CLAUDE.md (through a symlink), else AGENTS.md, else new CLAUDE.md."""
    claude, agents = repo / "CLAUDE.md", repo / "AGENTS.md"
    if claude.exists():
        return claude.resolve()
    return agents if agents.is_file() else claude


def missing_lines(prop: Proposal, text: str) -> list[str]:
    """Proposal lines for keys the existing document does not yet define."""
    present, _ = parse_entries(text)
    return [ln for ln in prop.lines() if ln.split(":", 1)[0][2:] not in present]


def script_plan(repo: Path, prop: Proposal) -> Path | None:
    """The template to copy for scripts/test_changed.sh, or None if not needed."""
    wants = prop.values.get("test-changed", "") == f"`{TEST_CHANGED}`"
    if not wants or (repo / TEST_CHANGED).exists():
        return None
    template = TEMPLATES / f"{prop.stack}.sh"
    return template if template.is_file() else None


def apply(
    repo: Path, doc: Path, text: str, new: list[str], script: Path | None
) -> list[str]:
    """Write the changes; returns human-readable actions taken."""
    done: list[str] = []
    if not (repo / "CLAUDE.md").exists() and (repo / "AGENTS.md").is_file():
        (repo / "CLAUDE.md").symlink_to("AGENTS.md")
        done.append("symlinked CLAUDE.md -> AGENTS.md")
    if new:
        doc.write_text(insert_lines(text, new), encoding="utf-8")
        done.append(f"wrote {len(new)} line(s) to {doc.name}")
    if script is not None:
        target = repo / TEST_CHANGED
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(script, target)
        target.chmod(0o755)
        done.append(f"created {TEST_CHANGED} from {script.name}")
    return done


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; 0 on success, 2 for a path that is not a git repo."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    repo = args.repo.expanduser().resolve()
    if not repo.is_dir() or not (repo / ".git").exists():
        print(f"bootstrap: {repo} is not a git repo", file=sys.stderr)
        return 2
    stacks = detect_stacks(repo)
    prop = propose(repo, stacks)
    doc = doc_path(repo)
    text = doc.read_text(encoding="utf-8") if doc.is_file() else ""
    new = missing_lines(prop, text)
    script = script_plan(repo, prop)
    print(f"# {repo.name} (stack: {', '.join(stacks) or 'unknown'})")
    print("\n".join(new) if new else "(Commands section already complete)")
    print(
        f"# script: {TEST_CHANGED} <- {script.name}"
        if script
        else "# script: none to create"
    )
    for note in prop.notes:
        print(f"# note: {note}")
    if args.write:
        for action in apply(repo, doc, text, new, script):
            print(f"# {action}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
