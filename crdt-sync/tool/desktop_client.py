# Copyright (c) 2026 Krzysztof Rudnicki
"""Pick up, validate and store the Desktop OAuth client JSON from the console.

Android and iOS clients download as the same top-level ``installed`` object, so
the type alone proves nothing: only a ``client_secret`` plus the
``http://localhost`` redirect marks a Desktop client.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from functools import partial
import json
import logging
import os
from pathlib import Path
import sys
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

PROJECT_ID = "kuhy-syncs"
DEFAULT_DEST = Path.home() / ".config" / "crdt-sync" / "desktop_client.json"
DEFAULT_DOWNLOADS = Path.home() / "Downloads"
_POLL_SECONDS = 2.0
_pause_between_polls = partial(time.sleep, _POLL_SECONDS)
_CLIENT_ID_SUFFIX = ".apps.googleusercontent.com"
_LOOPBACK_REDIRECT = "http://localhost"

_logger = logging.getLogger("desktop_client")


class ClientFileError(Exception):
    """The client JSON is missing, malformed or not a Desktop client."""


@dataclass(frozen=True)
class DesktopClient:
    """The installed-app client as downloaded from the console."""

    client_id: str
    client_secret: str
    project_id: str


@dataclass(frozen=True)
class Pickup:
    """A valid client JSON found in the downloads folder."""

    path: Path
    client: DesktopClient


def parse_client_json(text: str, project_id: str = PROJECT_ID) -> DesktopClient:
    """Return the Desktop client in ``text``, or raise saying what is wrong."""
    try:
        document = json.loads(text)
    except ValueError as exc:
        msg = f"not valid JSON: {exc}"
        raise ClientFileError(msg) from exc
    if not isinstance(document, dict):
        msg = "must contain a JSON object"
        raise ClientFileError(msg)
    installed = document.get("installed")
    if not isinstance(installed, dict):
        msg = f"no 'installed' object (found {sorted(document)}); pick 'Desktop app'"
        raise ClientFileError(msg)
    if installed.get("project_id") != project_id:
        msg = f"belongs to project {installed.get('project_id')!r}, not {project_id!r}"
        raise ClientFileError(msg)
    client_id = str(installed.get("client_id", ""))
    if not client_id.endswith(_CLIENT_ID_SUFFIX):
        msg = f"client_id {client_id!r} is not a Google OAuth client id"
        raise ClientFileError(msg)
    held = str(installed.get("client_secret", ""))
    if not held:
        msg = "no client_secret: this is an Android/iOS client, not a Desktop app"
        raise ClientFileError(msg)
    if _LOOPBACK_REDIRECT not in installed.get("redirect_uris", []):
        msg = f"redirect_uris lacks {_LOOPBACK_REDIRECT}: not a Desktop app client"
        raise ClientFileError(msg)
    return DesktopClient(client_id=client_id, client_secret=held, project_id=project_id)


def _scan(
    downloads: Path, since: float, rejected: set[str], report: Callable[[str], None]
) -> Pickup | None:
    candidates = [
        path
        for path in downloads.glob("client_secret_*.json")
        if path.stat().st_mtime >= since
    ]
    for path in sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            client = parse_client_json(path.read_text(encoding="utf-8"))
        except ClientFileError as exc:
            if path.name not in rejected:
                rejected.add(path.name)
                report(f"ignoring {path.name}: {exc}")
            continue
        return Pickup(path=path, client=client)
    return None


def wait_for_client_json(
    downloads: Path,
    since: float,
    *,
    attempts: int,
    pause: Callable[[], None] = _pause_between_polls,
    report: Callable[[str], None] = print,
) -> Pickup | None:
    """Scan ``downloads`` up to ``attempts`` times for a JSON newer than ``since``."""
    rejected: set[str] = set()
    for attempt in range(attempts):
        found = _scan(downloads, since, rejected, report)
        if found:
            return found
        if attempt < attempts - 1:
            pause()
    return None


def store_client(source: Path, dest: Path) -> None:
    """Move ``source`` to ``dest`` with mode 0600, so no copy lingers in Downloads."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(source.read_text(encoding="utf-8"))
    dest.chmod(0o600)
    source.unlink()


def load_client(dest: Path = DEFAULT_DEST) -> DesktopClient:
    """Load the stored client, pointing at the register script when absent."""
    try:
        return parse_client_json(dest.read_text(encoding="utf-8"))
    except OSError as exc:
        msg = f"{dest} unreadable ({exc}); run tool/register_desktop_client.sh"
        raise ClientFileError(msg) from exc


def main(argv: list[str] | None = None) -> int:
    """Wait for the downloaded JSON and store it. Returns an exit code."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=["pickup"])
    parser.add_argument("--since", type=float, required=True, help="epoch seconds")
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--downloads", type=Path, default=DEFAULT_DOWNLOADS)
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    args = parser.parse_args(argv)
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")
    found = wait_for_client_json(
        args.downloads,
        args.since,
        attempts=int(args.timeout / _POLL_SECONDS) + 1,
        report=_logger.info,
    )
    if found is None:
        _logger.error("  FAIL  no Desktop client JSON appeared in %s", args.downloads)
        return 1
    store_client(found.path, args.dest)
    _logger.info(
        "  PASS  stored %s at %s (mode 600)", found.client.client_id, args.dest
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
