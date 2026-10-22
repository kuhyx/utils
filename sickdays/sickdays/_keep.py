# Copyright (c) 2026 Krzysztof Rudnicki
"""The per-day keep set: which lockers stay active on a sick day.

The keep set is one more last-writer-wins field on the day's record
(``FIELD_KEEP``), holding a **sorted, de-duplicated** JSON list of locker
ids. Sorting is wire format, not tidiness: the RTDB rev is a SHA-256 of the
exact serialised string, so two devices holding the same set must write the
same bytes.

Reading is where the safety lives, and each rule is pinned by a test:

- no ``keep`` field (every 0.1.0 record) -- keep nothing: every locker
  stands down, exactly as before 0.2.0;
- a ``keep`` stamped *older* than ``state`` -- stale (an old client re-added
  the day without writing it), so keep nothing;
- a ``keep`` that is not a list of strings -- fail closed: every locker is
  kept, i.e. the locks apply, and a warning is logged;
- an id this version does not know, inside an otherwise valid list -- ignored,
  so a newer phone can add a locker without breaking this reader.

Staleness is decided first: a superseded value is ignored whatever it holds.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from crdt_sync import Record

from sickdays._constants import FIELD_ACTOR, FIELD_KEEP, FIELD_STATE, LOCKERS

if TYPE_CHECKING:
    from collections.abc import Iterable

    from crdt_sync import Hlc

_logger = logging.getLogger(__name__)

_ALL: frozenset[str] = frozenset(LOCKERS)


def validate_locker(locker: str) -> str:
    """Return ``locker`` if it is a known id.

    Raises:
        ValueError: ``locker`` is not one of :data:`sickdays.LOCKERS`.
    """
    if locker not in _ALL:
        msg = f"unknown locker {locker!r}; expected one of {', '.join(LOCKERS)}"
        raise ValueError(msg)
    return locker


def normalise_keep(keep: Iterable[str]) -> frozenset[str]:
    """Validate every id in ``keep`` and return them as a set.

    A bare string is refused rather than iterated character by character.

    Raises:
        TypeError: ``keep`` is a bare string, not a collection of ids.
        ValueError: An id is not one of :data:`sickdays.LOCKERS`.
    """
    if isinstance(keep, str):
        msg = f"keep must be a collection of locker ids, not the string {keep!r}"
        raise TypeError(msg)
    return frozenset(validate_locker(locker) for locker in keep)


def keep_wire(keep: frozenset[str]) -> list[str]:
    """The on-the-wire value of ``keep``: sorted, so the bytes are stable."""
    return sorted(keep)


def read_keep(record: Record) -> frozenset[str]:
    """Which known lockers ``record``'s day keeps active (the rules above).

    Only meaningful while the day is sick; callers check that first.
    """
    field = record.fields.get(FIELD_KEEP)
    if field is None:
        return frozenset()
    value, hlc = field
    state = record.fields.get(FIELD_STATE)
    if state is not None and hlc < state[1]:
        return frozenset()
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        _logger.warning(
            "sick day %s has a malformed keep field %r -- every locker applies",
            record.id,
            value,
        )
        return _ALL
    return frozenset(value) & _ALL


def with_keep(record: Record, keep: frozenset[str], *, actor: str, tick: Hlc) -> Record:
    """Return ``record`` with only ``keep`` and ``actor`` re-stamped ``tick``.

    ``state`` keeps its own clock on purpose: re-stamping it would make a
    keep edit re-assert "sick" over a concurrent clear from another device.
    """
    fields = dict(record.fields)
    fields[FIELD_KEEP] = (keep_wire(keep), tick)
    fields[FIELD_ACTOR] = (actor, tick)
    return Record(
        id=record.id,
        fields=fields,
        deleted=record.deleted,
        deleted_hlc=record.deleted_hlc,
    )
