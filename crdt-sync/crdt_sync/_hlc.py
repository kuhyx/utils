"""Hybrid Logical Clock: a totally-ordered, monotonic per-node timestamp.

An HLC combines wall-clock time with a logical counter so that two ticks
issued by the same node in the same millisecond still get a strict order,
and two ticks from different nodes are always comparable (the node id breaks
ties), without requiring synchronized clocks across devices.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import time

_ISO_PREFIX_LEN = 23  # len("YYYY-MM-DDTHH:MM:SS.mmm")
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


@dataclass(frozen=True, order=True)
class Hlc:
    """A Hybrid Logical Clock value.

    Ordered by ``(wall_time_ms, counter, node_id)`` tuple comparison, which
    is also the order ``@dataclass(order=True)`` derives from the field
    declaration order below -- two clocks from different nodes never compare
    equal, since ``node_id`` is the final, always-distinguishing tiebreaker.
    """

    wall_time_ms: int
    counter: int
    node_id: str

    @staticmethod
    def new_tick(
        node_id: str,
        previous: Hlc | None = None,
        wall_time_ms: int | None = None,
    ) -> Hlc:
        """Return the next clock value for ``node_id``.

        Args:
            node_id: The issuing node's identifier.
            previous: This node's last-issued clock value, if any. Passing
                the previous value is what makes the clock monotonic even
                when the wall clock hasn't advanced (or has gone backwards).
            wall_time_ms: Override for the current wall-clock time in
                milliseconds since the Unix epoch; defaults to the real
                clock. Exposed for deterministic tests.

        Returns:
            A new ``Hlc`` strictly greater than ``previous`` (if given).
        """
        now = wall_time_ms if wall_time_ms is not None else int(time.time() * 1000)
        if previous is None:
            return Hlc(wall_time_ms=now, counter=0, node_id=node_id)
        new_wall = max(now, previous.wall_time_ms)
        counter = previous.counter + 1 if new_wall == previous.wall_time_ms else 0
        return Hlc(wall_time_ms=new_wall, counter=counter, node_id=node_id)

    def to_str(self) -> str:
        """Serialize to a human-readable, lexicographically sortable string.

        Format: ``<iso8601-millis>Z-<counter:04x>-<node_id>``. The iso8601
        portion is fixed-width (always exactly ``YYYY-MM-DDTHH:MM:SS.mmm``),
        which is what makes plain string comparison agree with ``Hlc``
        comparison for the wall-clock component.
        """
        seconds, millis = divmod(self.wall_time_ms, 1000)
        dt = datetime.fromtimestamp(seconds, tz=UTC)
        iso = dt.strftime("%Y-%m-%dT%H:%M:%S")
        return f"{iso}.{millis:03d}Z-{self.counter:04x}-{self.node_id}"

    @classmethod
    def from_str(cls, text: str) -> Hlc:
        """Parse the format produced by :meth:`to_str`.

        Raises:
            ValueError: If ``text`` is not in the expected format.
        """
        iso_part, sep, rest = text.partition("Z-")
        if not sep or len(iso_part) != _ISO_PREFIX_LEN:
            msg = f"not a valid Hlc string: {text!r}"
            raise ValueError(msg)
        counter_hex, sep, node_id = rest.partition("-")
        if not sep:
            msg = f"not a valid Hlc string: {text!r}"
            raise ValueError(msg)
        dt = datetime.strptime(iso_part, "%Y-%m-%dT%H:%M:%S.%f").replace(tzinfo=UTC)
        delta = dt - _EPOCH
        wall_time_ms = (
            delta.days * 86_400_000 + delta.seconds * 1000 + delta.microseconds // 1000
        )
        return cls(
            wall_time_ms=wall_time_ms, counter=int(counter_hex, 16), node_id=node_id
        )
