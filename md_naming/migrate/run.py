"""CLI: dry-run or apply the markdown-naming migration.

    python3 -m md_naming.migrate.run            # show what would happen
    python3 -m md_naming.migrate.run --apply    # do it

Triaged classifications that are not in classify.py are loaded from a JSON
sidecar, so a re-triage does not require editing code.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - plain-script import path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from md_naming.migrate import apply as apply_mod
from md_naming.migrate import classify
from md_naming.migrate.plan import HOME, add_auto, build
from md_naming.migrate.survey import gate_violations

TRIAGE = Path(__file__).parent / "triage.json"


def load_triage() -> tuple[dict[str, str], dict[str, str]]:
    """Extra task/record classifications from the JSON sidecar."""
    if not TRIAGE.is_file():
        return {}, {}
    data = json.loads(TRIAGE.read_text(encoding="utf-8"))
    return data.get("tasks", {}), data.get("records", {})


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate markdown filenames.")
    parser.add_argument(
        "--apply", action="store_true", help="perform the moves (default: dry run)"
    )
    args = parser.parse_args()

    extra_tasks, extra_records = load_triage()
    plan = build(extra_tasks, extra_records)

    # Anything the gate still flags that no table named: rename it
    # mechanically. Computed live from the gate rather than a saved list, so
    # the migration cannot drift from what the gate actually rejects.
    classified = {str(move.old) for move in plan.moves} | {
        str(HOME / rel) for rel in (*classify.PROVEN_DONE, *classify.CLAIMED_DONE)
    }
    remaining = [
        str(path.relative_to(HOME))
        for path in gate_violations()
        if str(path) not in classified
    ]
    add_auto(plan, remaining)

    if plan.unresolved:
        print(f"WARNING: {len(plan.unresolved)} classified path(s) missing:")
        for path in plan.unresolved:
            print(f"  {path}")

    # References first: a half-applied run must never leave the harness
    # config pointing at a file that has already moved.
    for line in apply_mod.repair_references(plan, apply=args.apply):
        print(line)

    for move in plan.moves:
        print(apply_mod.git_mv(move, apply=args.apply))
        target = move.new if args.apply and move.new.is_file() else move.old
        if move.needs_marker and target.is_file():
            note = apply_mod.ensure_marker(target, apply=args.apply)
            if note:
                print(f"  {note}")

    tasks = sum(1 for m in plan.moves if m.kind == "task")
    records = len(plan.moves) - tasks
    mode = "APPLIED" if args.apply else "DRY RUN"
    print(f"\n{mode}: {len(plan.moves)} moves ({tasks} TODO, {records} DOCS)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
