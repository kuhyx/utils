"""Ask the gate which files it currently rejects, per repo.

Deriving the migration's worklist from the gate itself -- rather than from a
saved list -- is what keeps the two from disagreeing. A file the gate stops
rejecting drops out of the migration automatically.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from md_naming.rules import is_third_party

HOME = Path("/home/kuhy")

#: Repos that are clones of other people's work get no migration at all.
SKIP = {
    "aur",
    "actions-runner",
    "awesome-mcp-explorer",
    "byox-ladder",
    "untools",
    "llama_cpp_dart_local",
}


def kuhy_repos() -> list[Path]:
    """Every git repo directly under ~ that is kuhy's own work."""
    found = []
    for entry in sorted(HOME.iterdir()):
        if not (entry / ".git").exists():
            continue
        if entry.name in SKIP or is_third_party(entry):
            continue
        found.append(entry)
    return found


def gate_violations() -> list[Path]:
    """Files the naming gate rejects, across every kuhy-owned repo."""
    checker = HOME / "utils" / "scripts" / "check_md_naming.sh"
    found: list[Path] = []
    for repo in kuhy_repos():
        result = subprocess.run(
            ["bash", str(checker), "--all"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
        for line in result.stderr.splitlines():
            if "name must start with" not in line:
                continue
            found.append(Path(line.split(":")[0].strip()))
    return found
