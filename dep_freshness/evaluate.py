"""Decide, for one `Dep` and its registry answer, whether the gate objects.

Kept separate from `check.py` so the rules are readable in one screen and
testable without a filesystem. The rules differ per constraint style on
purpose:

* Ordinary packages must carry an exact pin (Q6) — a range is not comparable
  to a registry answer, which is what made "are we current?" unanswerable.
* Q13's carve-out packages may keep a caret; their *lower bound* is compared
  instead, so a stale `^10.2.0` is still caught.
* Toolchain ranges are checked for whether they still admit the current
  toolchain. `sdk: ^3.12.2` is not stale because Dart shipped 3.13.2 — that
  constraint already permits it — but `<3.13` would be a real break.
"""

from __future__ import annotations

from dep_freshness._tables import TOOLCHAIN
from dep_freshness.constraints import lower_bound, satisfies
from dep_freshness.models import Dep, Finding, Severity
from dep_freshness.resolve import Answer
from dep_freshness.versions import behind


def _toolchain(dep: Dep, latest: str) -> Finding | None:
    if dep.pinned:
        if behind(dep.pinned, latest):
            return Finding(dep, Severity.STALE, latest)
        return None
    if not dep.constraint or dep.caret_ok is False:
        return Finding(
            dep, Severity.UNPINNED, latest,
            detail="a channel name is not a version: two machines on the same "
                   "commit can build with different SDKs",
        )
    if not satisfies(dep.constraint, latest):
        return Finding(
            dep, Severity.STALE, latest,
            detail=f"the constraint excludes the current toolchain {latest}",
        )
    return None


def judge(dep: Dep, answer: Answer) -> Finding | None:
    """The gate's objection to `dep`, or None when it is fine."""
    if dep.override:
        return Finding(
            dep, Severity.OVERRIDE, answer.version,
            detail="an override pins a transitive dependency nothing else "
                   "watches; allowlist it or remove it",
        )
    if answer.unavailable:
        return Finding(
            dep, Severity.UNKNOWN, None,
            detail="no network and no cached answer",
        )
    latest = answer.version
    if latest is None:
        return Finding(
            dep, Severity.UNKNOWN, None,
            detail="the registry has no stable release for this package",
        )

    if dep.ecosystem == TOOLCHAIN:
        return _toolchain(dep, latest)

    if dep.peer:
        # A peerDependency declares what a CONSUMER may bring, so exact-pinning
        # it is actively wrong: it would force every consumer onto one version.
        # The meaningful question is whether the range still admits latest.
        if not satisfies(dep.constraint, latest):
            return Finding(
                dep, Severity.STALE, latest,
                detail=f"the peer range excludes the current {latest}",
            )
        return None

    if dep.pinned is None:
        if dep.caret_ok:
            floor = lower_bound(dep.constraint)
            if floor and behind(floor, latest):
                return Finding(
                    dep, Severity.STALE, latest,
                    detail=f"range floor {floor} is behind latest stable",
                )
            return None
        return Finding(
            dep, Severity.UNPINNED, latest,
            detail=f"exact-pin it ({latest}) so freshness is checkable",
        )

    if behind(dep.pinned, latest):
        return Finding(dep, Severity.STALE, latest)
    if dep.locked and dep.locked != dep.pinned:
        return Finding(
            dep, Severity.LOCK_MISMATCH, latest,
            detail=f"lockfile resolved {dep.locked}, manifest pins {dep.pinned}",
        )
    return None
