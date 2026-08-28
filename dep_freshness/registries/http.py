"""The only module that touches the network.

Two things matter here. First, a single 2s per-host reachability probe
short-circuits every later request, so an offline run fails in seconds instead
of timing out once per package across ~900 lookups. Second, failures are
returned, never raised: the gate must degrade to a cached answer rather than
crash a pre-commit hook the user is forbidden from bypassing.
"""

from __future__ import annotations

import json
import socket
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from dep_freshness._tables import HTTP_TIMEOUT, PROBE_TIMEOUT, USER_AGENT


class Offline(Exception):
    """The host is unreachable; callers should fall back to the cache."""


_reachable: dict[str, bool] = {}
_forced_offline = False


def force_offline(value: bool = True) -> None:
    """Make every request raise `Offline` without touching the network."""
    global _forced_offline
    _forced_offline = value


def reset_probes() -> None:
    """Forget cached reachability verdicts (tests, and `--refresh`)."""
    _reachable.clear()


def host_reachable(url: str) -> bool:
    """One cheap TCP probe per host, memoised for the run."""
    if _forced_offline:
        return False
    parts = urlsplit(url)
    host = parts.hostname or ""
    if host in _reachable:
        return _reachable[host]
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=PROBE_TIMEOUT):
            _reachable[host] = True
    except OSError:
        _reachable[host] = False
    return _reachable[host]


def get_json(url: str, accept: str | None = None) -> Any:
    """Fetch and decode JSON, or raise `Offline` / return None on 404.

    `Offline` means "ask the cache"; None means "the registry answered and
    this package genuinely is not there", which is a real finding rather than
    a degraded run and must not be papered over with a stale cache entry.
    """
    if not host_reachable(url):
        raise Offline(url)
    headers = {"User-Agent": USER_AGENT}
    if accept:
        headers["Accept"] = accept
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=HTTP_TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 404:
            return None
        raise Offline(f"{url}: HTTP {exc.code}") from exc
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        raise Offline(f"{url}: {exc}") from exc
