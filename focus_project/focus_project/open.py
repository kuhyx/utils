# Copyright (c) 2026 Krzysztof Rudnicki
"""``python3 -m focus_project.open [--no-site]``: go where the work is done.

Opens the tutor app's focus screen (``run.sh --route``, which starts the tutor
server if it is down and shows the app in its Chrome ``--app`` window) and,
unless ``--no-site``, the project's work URL in the default browser. The link
carries ``start=1`` only while a project is active: the app starts the timer
if it is not already running. The site opens last so it ends up in front.

One place for every caller (the i3blocks block, the daily-limits popup). No
active project, or an unreadable registry, still opens the focus screen.
"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import TYPE_CHECKING

from focus_project import _api, _clock
from focus_project._errors import RegistryError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from focus_project._model import Project

_LOG = logging.getLogger(__name__)
TUTOR_RUN_ENV = "FOCUS_TUTOR_RUN"
_TUTOR_WAIT_SECONDS = 60  # run.sh may have to start the server first
_ROUTE = "/focus"
_ROUTE_START = "/focus?start=1"


def work_url(project: Project) -> str | None:
    """The project's work URL, else ``https://<first usable site pattern>``."""
    if project.work_url:
        return project.work_url
    for pattern in project.site_patterns:
        host = pattern.removeprefix("*.")
        if host and "*" not in host:
            return f"https://{host}"
    return None


def _active() -> Project | None:
    try:
        return _api.active(_clock.today())
    except (RegistryError, OSError) as exc:
        _LOG.warning("focus registry unreadable, opening the tutor only: %s", exc)
        return None


def _open_tutor(route: str) -> bool:
    run = Path(os.environ.get(TUTOR_RUN_ENV) or "~/src/tutor/run.sh").expanduser()
    try:
        subprocess.run(
            [str(run), "--route", route],
            check=True,
            stdin=subprocess.DEVNULL,
            timeout=_TUTOR_WAIT_SECONDS,
            start_new_session=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        _LOG.error("could not open the tutor via %s: %s", run, exc)
        return False
    return True


def _open_site(url: str) -> bool:
    opener = shutil.which("xdg-open")
    if opener is None:
        _LOG.error("xdg-open not found, cannot open %s", url)
        return False
    try:
        # Not a `with`: the browser must outlive this process.
        subprocess.Popen(
            [opener, url],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        _LOG.error("could not run xdg-open: %s", exc)
        return False
    return True


def main(argv: Sequence[str] | None = None) -> int:
    """Open the focus screen and the work URL; 1 only if nothing opened."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--no-site", action="store_true", help="only the tutor focus screen"
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="focus_project.open: %(message)s")
    project = _active()
    opened = _open_tutor(_ROUTE if project is None else _ROUTE_START)
    url = None if project is None or args.no_site else work_url(project)
    if url is not None:
        opened = _open_site(url) or opened
    return 0 if opened else 1


if __name__ == "__main__":
    sys.exit(main())
