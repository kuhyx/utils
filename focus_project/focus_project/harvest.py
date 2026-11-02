# Copyright (c) 2026 Krzysztof Rudnicki
"""The harvester: turn credited focus minutes into signed ledger rows.

Run by ``focus-project-harvest.service`` (``.path`` on activity.jsonl plus a
one-minute ``.timer``). Harvests every project day of the last
:data:`BACKFILL_DAYS` days, so work recorded late (a phone synced days
after the fact) is paid once a run sees it; ``credit_to`` is idempotent, so
settled days cost one read and write nothing. Failure modes, by path:

* a source that errors: logged, contributes 0, the run continues (fail closed);
* an unreadable registry, signing key or ledger: logged, exit status 1, so
  the unit shows ``failed`` instead of silently crediting nothing.
"""

from __future__ import annotations

from datetime import date, timedelta
import logging
import sys

from focus_project import _api, _clock, ledger
from focus_project._errors import RegistryError
from focus_project.minutes import minutes_for

BACKFILL_DAYS = 31  # bounds the per-run cost; the relay accepts events <= 48 h old
_LOG = logging.getLogger("focus_project.harvest")


def project_days(today: date) -> list[date]:
    """Every project day in the backfill window up to ``today``, oldest first."""
    oldest = today - timedelta(days=BACKFILL_DAYS - 1)
    days: set[date] = set()
    for project in _api.list_projects():
        day = max(project.start, oldest)
        while day <= min(project.last_day, today):
            days.add(day)
            day += timedelta(days=1)
    return sorted(days)


def harvest_day(day: date, now: float) -> int:
    """Credit ``day``; return the minutes added (0 with no project)."""
    project = _api.active(day)
    if project is None:
        return 0
    total = minutes_for(day, now=now)
    added = ledger.credit_to(project, day, total, now=now)
    if added:
        _LOG.info(
            "credited %d min to %s on %s (total %d)", added, project.id, day, total
        )
    return added


def harvest(now: float | None = None) -> int:
    """Harvest the backfill window; 0 on success, 1 if any path failed."""
    moment = _clock.now() if now is None else now
    today = date.fromtimestamp(moment)  # noqa: DTZ012 (local day)
    try:
        days = project_days(today)
    except (RegistryError, OSError) as exc:
        _LOG.error("harvest registry unreadable: %s", exc)
        return 1
    status = 0
    for day in days:
        try:
            harvest_day(day, moment)
        except (RegistryError, ledger.LedgerError, OSError) as exc:
            _LOG.error("harvest %s failed: %s", day, exc)
            status = 1
    return status


def main() -> None:
    """Entry point of ``python -m focus_project.harvest``."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    sys.exit(harvest())


if __name__ == "__main__":
    main()
