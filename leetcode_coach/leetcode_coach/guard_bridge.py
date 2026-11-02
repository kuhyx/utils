"""The three read-only calls the coach borrows from leetcode-guard, on demand.

Without leetcode-guard installed (tutor server, CI) every other module still
imports; these raise `GuardUnavailableError`, never a silent "nothing solved".
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Final, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from types import ModuleType

    class Submission(Protocol):
        title_slug: str
        timestamp: int

    class SolveProbe(Protocol):
        @property
        def usable(self) -> bool: ...

        reason: str
        submissions: Sequence[Submission]


SETTINGS: Final = "leetcode_guard._settings"
LIVE_SOLVED: Final = "leetcode_guard._live_solved"
SUBMISSIONS: Final = "leetcode_guard._submissions"
SNAPSHOT_AUTH: Final = "leetcode_guard._snapshot_auth"
ALLOWED: Final = frozenset({SETTINGS, LIVE_SOLVED, SUBMISSIONS, SNAPSHOT_AUTH})


class GuardUnavailableError(RuntimeError):
    pass


def _load(name: str) -> ModuleType:
    try:
        return importlib.import_module(name)
    except ImportError as exc:
        msg = f"{name} needs leetcode-guard installed ({exc})"
        raise GuardUnavailableError(msg) from exc


def solved_slugs(slugs: Sequence[str]) -> frozenset[str]:
    client = _load(SETTINGS).build_client()
    evidence = _load(LIVE_SOLVED).check_solved(client.post, list(slugs))
    return frozenset(evidence.solved)


def recent_accepted() -> SolveProbe:
    client = _load(SETTINGS).build_client()
    probe: SolveProbe = _load(SUBMISSIONS).fetch_recent_ac(client.post, client.username)
    return probe


def phone_id_token(app_name: str, *, timeout_seconds: float) -> Callable[[], str]:
    client = _load(SNAPSHOT_AUTH).connect(app_name, timeout_seconds=timeout_seconds)
    token: Callable[[], str] = client.auth.id_token
    return token
