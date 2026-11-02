# Copyright (c) 2026 Krzysztof Rudnicki
"""Evidence adapters: each turns one record of work into time intervals.

An adapter is a module ``focus_project.sources.<name>`` exposing one pure,
read-only function::

    def intervals(day: date, project: Project) -> list[Interval]

``Interval`` is ``(start, end)`` in unix seconds, ``start <= end``. Adapters
may return spans outside ``day``; :func:`collect` clips them. To add a source,
add the module and its name to :data:`ADAPTERS`; a name whose module does not
exist yet is skipped as inactive.

Failure mode (fail closed, named): an adapter that raises is logged and
contributes nothing; it never stops the others or the harvester.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
import importlib
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from focus_project._model import Project

Interval = tuple[float, float]

# Each heartbeat vouches for the five minutes before it.
HEARTBEAT_WINDOW_S = 300.0
ADAPTERS = ("activity", "leetcode", "browser")
_LOG = logging.getLogger(__name__)


def heartbeat_interval(ts: float) -> Interval:
    """The span a heartbeat at ``ts`` covers: ``[ts - 300, ts]``."""
    return (ts - HEARTBEAT_WINDOW_S, ts)


def day_bounds(day: date) -> Interval:
    """Local midnight to the next local midnight, as unix seconds."""
    start = datetime.combine(day, time.min).astimezone()
    end = datetime.combine(day + timedelta(days=1), time.min).astimezone()
    return (start.timestamp(), end.timestamp())


def clip(spans: list[Interval], bounds: Interval) -> list[Interval]:
    """``spans`` limited to ``bounds``; empty and inverted spans dropped."""
    lo, hi = bounds
    out = [(max(a, lo), min(b, hi)) for a, b in spans]
    return [(a, b) for a, b in out if b > a]


def collect_by_source(day: date, project: Project) -> dict[str, list[Interval]]:
    """Every adapter's clipped intervals for ``day``, keyed by adapter name.

    Missing adapters are absent from the result; failing ones map to ``[]``.
    """
    bounds = day_bounds(day)
    found: dict[str, list[Interval]] = {}
    for name in ADAPTERS:
        module_name = f"{__name__}.{name}"
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:  # noqa: BLE001 (a broken adapter must add 0)
            if isinstance(exc, ModuleNotFoundError) and exc.name == module_name:
                _LOG.info("source %s: not installed (inactive)", name)
                continue
            _LOG.exception("source %s: import failed, contributes 0", name)
            found[name] = []
            continue
        try:
            found[name] = clip(list(module.intervals(day, project)), bounds)
        except Exception:  # noqa: BLE001 (fail closed: this source adds 0)
            _LOG.exception("source %s: failed, contributes 0", name)
            found[name] = []
    return found


def collect(day: date, project: Project) -> list[Interval]:
    """All adapters' clipped intervals for ``day``, concatenated."""
    return [s for spans in collect_by_source(day, project).values() for s in spans]
