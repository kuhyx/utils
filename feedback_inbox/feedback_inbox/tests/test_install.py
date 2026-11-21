# Copyright (c) 2026 Krzysztof Rudnicki
"""install.sh puts every declared dependency into the venv.

The package itself is installed with --no-deps (no network at install time),
so each sibling package from pyproject's dependencies needs its own pip line.
A missing one made every service run die with ModuleNotFoundError
(kuhy_credit, 2026-11-21) and no bundle became a task.
"""

from __future__ import annotations

from pathlib import Path
import re
import tomllib

ROOT = Path(__file__).resolve().parents[2]


def _sibling_dirs() -> list[str]:
    """Return the utils subdirectory each declared dependency lives in."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    dirs = []
    for dep in project["dependencies"]:
        match = re.search(r"subdirectory=([\w-]+)", dep)
        assert match, f"dependency without a utils subdirectory: {dep}"
        dirs.append(match.group(1))
    return dirs


def test_install_installs_every_dependency() -> None:
    script = (ROOT / "install.sh").read_text()
    for sub in _sibling_dirs():
        assert f'install --quiet --no-deps "$UTILS_DIR/{sub}"' in script, sub
        assert (ROOT.parent / sub).is_dir(), sub
