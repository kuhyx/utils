"""Value types passed between the parsers, the registries and the report.

Frozen dataclasses on purpose: a parser hands a `Dep` to a registry resolver
and gets a `Finding` back, and nothing in between may mutate what was read off
disk. `Severity` is what the exit code is derived from, so the mapping from
"what we noticed" to "what the shell sees" lives in one place.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class Severity(str, Enum):
    """Why a dependency is being reported."""

    STALE = "stale"                 # pinned below latest stable
    UNPINNED = "unpinned"           # no exact version to compare against
    LOCK_MISMATCH = "lock-mismatch"  # manifest pin != lockfile resolved version
    OVERRIDE = "override"           # dependency_overrides / resolutions entry
    UNKNOWN = "unknown"             # latest could not be determined at all


@dataclass(frozen=True)
class Dep:
    """One declared dependency, as written in a manifest."""

    ecosystem: str
    name: str
    constraint: str
    path: Path
    line: int
    pinned: str | None = None   # exact version, when the constraint is one
    locked: str | None = None   # version the lockfile resolved to
    dev: bool = False
    caret_ok: bool = False      # Q13 carve-out: a range is legal here
    override: bool = False
    peer: bool = False          # a compatibility range, not a build pin


@dataclass(frozen=True)
class Finding:
    """A dependency that fails the gate, or is excused by the allowlist."""

    dep: Dep
    severity: Severity
    latest: str | None
    detail: str = ""
    excused: str | None = None  # allowlist reason, when one applies

    @property
    def label(self) -> str:
        """`ecosystem:name` — the key the allowlist matches on."""
        return f"{self.dep.ecosystem}:{self.dep.name}"


@dataclass(frozen=True)
class Exception_:
    """One parsed allowlist entry.

    Named with a trailing underscore so it cannot shadow the builtin in the
    modules that import it; `blocked_by` carries the whole semantics split
    between the predicate and discretionary classes.
    """

    ecosystem: str
    package: str
    pinned: str
    reason: str
    blocked_by: str
    latest_known: str | None = None
    expires: str | None = None
    source: Path | None = None

    @property
    def transitive(self) -> bool:
        """True when this is a predicate entry that never expires on a date."""
        from dep_freshness._tables import TRANSITIVE_PREFIX

        return self.blocked_by.startswith(TRANSITIVE_PREFIX)

    @property
    def blocker(self) -> tuple[str, str] | None:
        """`(package, version)` this entry claims is holding the pin back."""
        from dep_freshness._tables import TRANSITIVE_PREFIX

        if not self.transitive:
            return None
        rest = self.blocked_by[len(TRANSITIVE_PREFIX):]
        name, _, version = rest.partition("@")
        return (name.strip(), version.strip())
