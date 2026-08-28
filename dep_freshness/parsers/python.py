"""`pyproject.toml` and `requirements*.txt` -> PyPI dependencies.

PEP 508 markers, extras and environment conditions all appear in the wild here,
so the name is taken as the leading identifier and everything after the first
comparator is the constraint. Anything that is not a single `==` pin is
reported unpinned rather than guessed at.
"""

from __future__ import annotations

from pathlib import Path
import re
import tomllib

from dep_freshness._tables import PYPI, TOOLCHAIN
from dep_freshness.models import Dep
from dep_freshness.parsers._lines import index
from dep_freshness.versions import exact_pin

_REQ = re.compile(
    r"^\s*(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)"
    r"(?:\[(?P<extras>[^\]]*)\])?"
    r"\s*(?P<constraint>.*)$"
)
_SKIP_PREFIXES = ("-", "#", "git+", "http://", "https://", ".", "/")


def _split(requirement: str) -> tuple[str, str] | None:
    """`('ruff', '==0.16.5')` from a PEP 508 requirement string."""
    text = requirement.split("#", 1)[0].split(";", 1)[0].strip()
    if not text or text.startswith(_SKIP_PREFIXES):
        return None
    match = _REQ.match(text)
    if not match:
        return None
    return (match.group("name"), match.group("constraint").strip())


def _dep(name: str, constraint: str, path: Path, line: int) -> Dep:
    pinned = exact_pin(constraint) if constraint.startswith("==") else None
    return Dep(
        ecosystem=PYPI, name=name, constraint=constraint or "(unconstrained)",
        path=path, line=line, pinned=pinned,
    )


def parse_requirements(path: Path) -> list[Dep]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    deps: list[Dep] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        split = _split(raw)
        if split:
            deps.append(_dep(split[0], split[1], path, number))
    return deps


def parse_pyproject(path: Path) -> list[Dep]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return []
    lines = index(path)
    project = data.get("project") or {}
    deps: list[Dep] = []

    requires = project.get("requires-python")
    if isinstance(requires, str):
        deps.append(Dep(
            ecosystem=TOOLCHAIN, name="python", constraint=requires, path=path,
            line=lines.get("requires-python", 0), caret_ok=True,
        ))

    groups: list[list] = [list(project.get("dependencies") or [])]
    for extra in (project.get("optional-dependencies") or {}).values():
        groups.append(list(extra))
    for group in (data.get("dependency-groups") or {}).values():
        groups.append([g for g in group if isinstance(g, str)])

    for group in groups:
        for requirement in group:
            split = _split(str(requirement))
            if split:
                deps.append(_dep(split[0], split[1], path, lines.get(split[0], 0)))
    return deps


def parse_python_version(path: Path) -> list[Dep]:
    """`.python-version` — compared against the installed interpreter."""
    try:
        value = path.read_text(encoding="utf-8").strip().splitlines()[0].strip()
    except (OSError, IndexError):
        return []
    return [Dep(
        ecosystem=TOOLCHAIN, name="python", constraint=value, path=path,
        line=1, pinned=exact_pin(value),
    )]
