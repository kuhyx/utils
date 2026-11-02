# Copyright (c) 2026 Krzysztof Rudnicki
"""The harvester: turn credited focus minutes into signed ledger rows.

Run by ``focus-project-harvest.service`` (``.path`` on activity.jsonl plus a
one-minute ``.timer``). Harvests yesterday too, so work recorded just before
midnight is paid once the next run sees it. Failure modes, by path:

* a source that errors: logged, contributes 0, the run continues (fail closed);
* an unreadable registry, signing key or ledger: logged, exit status 1, so
  the unit shows ``failed`` instead of silently crediting nothing.
"""

from __future__ import annotations

from datetime import date, timedelta
import logging
import sys
import time

from focus_project import _api, ledger
from focus_project._errors import RegistryError
from focus_project.minutes import minutes_for

_LOG = logging.getLogger("focus_project.harvest")


def harvest_day(day: date, now: float) -> int:
    """Credit ``day``; return the minutes added (0 with no project)."""
    project = _api.active(day)
    if project is None:
        return 0
    total = minutes_for(day)
    added = ledger.credit_to(project, day, total, now=now)
    if added:
        _LOG.info(
            "credited %d min to %s on %s (total %d)", added, project.id, day, total
        )
    return added


def harvest(now: float | None = None) -> int:
    """Harvest yesterday and today; 0 on success, 1 if any path failed."""
    moment = time.time() if now is None else now
    today = date.fromtimestamp(moment)  # noqa: DTZ012 (local day)
    status = 0
    for day in (today - timedelta(days=1), today):
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
