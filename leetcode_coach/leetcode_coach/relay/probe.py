"""Step 4: has LeetCode seen an Accepted for this problem since it started?

The harvester's own read-only probe (``fetch_recent_ac`` with the client
``_settings.build_client`` builds), at most once a minute: LeetCode answers
a rate limit exactly like a dead session, so polling harder manufactures
the failure. Three answers, never two: ``accepted``, ``not_yet``, and
``unknown`` when the probe is unusable -- "could not check" is never "not
solved" (CLAUDE.md). The probe mints nothing; crediting stays the
harvester's job. ``timestamp`` is unix SECONDS, ``started`` is ms.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Final

from leetcode_guard._settings import build_client
from leetcode_guard._submissions import SolveProbe, fetch_recent_ac

if TYPE_CHECKING:
    from collections.abc import Callable

_logger: Final = logging.getLogger(__name__)

EVERY_S: Final = 60.0
ACCEPTED: Final = "accepted"
NOT_YET: Final = "not_yet"
UNKNOWN: Final = "unknown"


def live_probe() -> SolveProbe:
    """One read of kuhy's recent accepted submissions."""
    client = build_client()
    return fetch_recent_ac(client.post, client.username)


class AcceptedProbe:
    """Rate-limited, three-valued Accepted check."""

    def __init__(
        self,
        probe: Callable[[], SolveProbe] = live_probe,
        monotonic: Callable[[], float] = time.monotonic,
        every_s: float = EVERY_S,
    ) -> None:
        """Bind the probe and the clock that spaces it."""
        self._probe = probe
        self._monotonic = monotonic
        self._every = every_s
        self._last: float | None = None

    def due(self) -> bool:
        """Whether a minute has passed since the last probe."""
        last = self._last
        return last is None or self._monotonic() - last >= self._every

    def check(self, slug: str, started_ms: int) -> str:
        """``accepted`` / ``not_yet`` / ``unknown`` for `slug` since `started_ms`."""
        self._last = self._monotonic()
        try:
            answer = self._probe()
        except Exception:  # pylint: disable=broad-exception-caught
            # Anything the probe raises is a probe we cannot believe.
            _logger.exception("the Accepted probe failed")
            return UNKNOWN
        if not answer.usable:
            _logger.warning("Accepted probe unusable: %s", answer.reason)
            return UNKNOWN
        seen = any(
            s.title_slug == slug and s.timestamp * 1000 >= started_ms
            for s in answer.submissions
        )
        return ACCEPTED if seen else NOT_YET
