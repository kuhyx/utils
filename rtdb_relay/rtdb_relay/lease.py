# Copyright (c) 2026 Krzysztof Rudnicki. MIT License.
"""Request ids and the claim lease on ``requests/{rid}/claim``.

The claim node is ``{"by", "lease_until", "attempt", "phase", "at"}`` (ms),
the format the tutor's worker writes. One :class:`Lease` per request is the
only writer of its claim: it holds the current ETag, so renewals never race
each other into a 412 of our own making.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any, Final

from rtdb_relay.rtdb import ConflictError

if TYPE_CHECKING:
    from collections.abc import Callable

    from rtdb_relay.rtdb import Rtdb

RID: Final = re.compile(r"[0-9A-HJKMNP-TV-Z]{26}", re.ASCII)
LEASE_S: Final = 300.0
RENEW_S: Final = 60.0
_logger = logging.getLogger(__name__)


def valid_rid(rid: str) -> bool:
    """Whether ``rid`` is a ULID (the only keys a path is built from)."""
    return bool(RID.fullmatch(rid))


def ms(t: float) -> int:
    """Unix seconds -> unix ms."""
    return int(t * 1000)


def claimable(claim: object, now: float, own: str = "") -> bool:
    """Null, a lease that ran out, or ``own`` (a dead process of this worker).

    The caller has checked there is no result.
    """
    if not isinstance(claim, dict):
        return True
    lease = claim.get("lease_until")
    mine = bool(own) and claim.get("by") == own
    return mine or not isinstance(lease, (int, float)) or lease < ms(now)


class Lease:
    """A claim this worker holds: attempt number, phase and current ETag."""

    def __init__(
        self, rtdb: Rtdb, rid: str, worker: str, now: Callable[[], float]
    ) -> None:
        """Not yet taken; see :meth:`take`."""
        self._rtdb, self.rid, self._worker, self._now = rtdb, rid, worker, now
        self.attempt = 0
        self.phase = "claimed"
        self._etag = ""

    @property
    def path(self) -> str:
        """``requests/{rid}/claim``."""
        return f"requests/{self.rid}/claim"

    def _node(self) -> dict[str, Any]:
        now = self._now()
        return {
            "by": self._worker,
            "lease_until": ms(now + LEASE_S),
            "attempt": self.attempt,
            "phase": self.phase,
            "at": ms(now),
        }

    async def take(self) -> bool:
        """Claim the request (False: someone else holds it, or lost the race)."""
        current, etag = await self._rtdb.get_etag(self.path)
        if not claimable(current, self._now(), self._worker):
            return False
        before = current.get("attempt", 0) if isinstance(current, dict) else 0
        self.attempt = (before if isinstance(before, int) else 0) + 1
        try:
            _, self._etag = await self._rtdb.put_etag(self.path, self._node(), etag)
        except ConflictError:
            _logger.warning("another worker claimed %s first", self.rid)
            return False
        return True

    async def renew(self, phase: str | None = None) -> None:
        """Extend the lease (and move to ``phase``); a lost race is only logged."""
        if phase is not None:
            self.phase = phase
        try:
            _, self._etag = await self._rtdb.put_etag(
                self.path, self._node(), self._etag
            )
        except ConflictError:
            _logger.warning("claim on %s lost to another writer", self.rid)
