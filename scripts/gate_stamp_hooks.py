#!/usr/bin/python3
"""Print the manual-stage hook ids of a .pre-commit-config.yaml, one per line.

Used by gate_stamp.sh (`full --list`, `step <id>`) so the heavy gate can be
split into one hook per call. A hook is manual-stage when its `stages` list
contains `manual`, or when it has no `stages` key and the top-level
`default_stages` includes `manual`. A missing `default_stages` means "every
stage" to pre-commit, so those hooks count too: otherwise `step` could stamp a
tree that `full` (`--hook-stage manual`) would have run more hooks on.

Ids are de-duplicated in first-seen order: `pre-commit run <id>` already runs
every hook sharing that id, so one step covers them all.

Limitation: `stages` declared only in a remote repo's .pre-commit-hooks.yaml
manifest is invisible here; set it in the config to have it counted.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

MANUAL = "manual"


def _as_list(value: Any) -> list[str]:
    """Normalise a YAML `stages`-like value to a list of strings."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value]


def manual_hook_ids(config: dict[str, Any]) -> list[str]:
    """Return the ids that `pre-commit run --hook-stage manual` would run."""
    default_has_manual = "default_stages" not in config or MANUAL in _as_list(
        config.get("default_stages")
    )
    ids: list[str] = []
    for repo in config.get("repos") or []:
        for hook in repo.get("hooks") or []:
            if "stages" in hook:
                is_manual = MANUAL in _as_list(hook["stages"])
            else:
                is_manual = default_has_manual
            hook_id = str(hook.get("id", ""))
            if is_manual and hook_id and hook_id not in ids:
                ids.append(hook_id)
    return ids


def main(argv: list[str]) -> int:
    """Entry point: `gate_stamp_hooks.py <path-to-.pre-commit-config.yaml>`."""
    if len(argv) != 1:
        sys.stderr.write("usage: gate_stamp_hooks.py <.pre-commit-config.yaml>\n")
        return 2
    path = Path(argv[0])
    try:
        config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        sys.stderr.write(f"gate_stamp_hooks: cannot read {path}: {exc}\n")
        return 1
    if not isinstance(config, dict):
        sys.stderr.write(f"gate_stamp_hooks: {path} is not a mapping\n")
        return 1
    for hook_id in manual_hook_ids(config):
        sys.stdout.write(f"{hook_id}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
