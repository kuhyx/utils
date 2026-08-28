"""Find manifests, and route each one to the parser that understands it.

Discovery skips git-ignored files for the same reason the file-length gate
does: a violation in build output or a vendored tree is not something a commit
could ever fix, so reporting it only teaches the user to ignore the gate.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess

from dep_freshness._tables import EXCLUDED_DIRS, MANIFEST_GLOBS, REQUIREMENTS_PATTERN
from dep_freshness.models import Dep
from dep_freshness.parsers import (
    fvm, golang, javascript, pubspec, python, rust, workflow,
)

_REQUIREMENTS = re.compile(REQUIREMENTS_PATTERN)

_BY_NAME = {
    "pubspec.yaml": pubspec.parse,
    "pyproject.toml": python.parse_pyproject,
    "package.json": javascript.parse_package_json,
    "Cargo.toml": rust.parse,
    "go.mod": golang.parse,
    ".fvmrc": fvm.parse,
    ".nvmrc": javascript.parse_nvmrc,
    ".python-version": python.parse_python_version,
}


def is_manifest(path: Path) -> bool:
    return (
        path.name in MANIFEST_GLOBS
        or bool(_REQUIREMENTS.match(path.name))
        or workflow.is_workflow(path)
    )


def parse_manifest(path: Path) -> list[Dep]:
    """Every dependency declared in `path`, or [] if it is not a manifest."""
    parser = _BY_NAME.get(path.name)
    if parser is not None:
        return parser(path)
    if _REQUIREMENTS.match(path.name):
        return python.parse_requirements(path)
    if workflow.is_workflow(path):
        return workflow.parse(path)
    return []


def _git_ignored(paths: list[Path], root: Path) -> set[Path]:
    if not paths:
        return set()
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "check-ignore", "--stdin"],
            input="\n".join(str(p) for p in paths),
            capture_output=True, text=True, check=False,
        )
    except OSError:
        return set()
    if result.returncode not in (0, 1):  # 128 = not a repo
        return set()
    return {Path(line) for line in result.stdout.splitlines() if line}


def find_manifests(root: Path) -> list[Path]:
    """Every tracked manifest under `root`, deepest-first for stable output."""
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
        for name in filenames:
            candidate = Path(dirpath) / name
            if is_manifest(candidate) and not candidate.is_symlink():
                found.append(candidate)
    ignored = _git_ignored(found, root)
    return sorted(p for p in found if p not in ignored)
