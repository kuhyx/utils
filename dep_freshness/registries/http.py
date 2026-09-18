"""The only module that touches the network.

Three things matter here. First, a single 2s per-host reachability probe
short-circuits every later request, so an offline run fails in seconds instead
of timing out once per package across ~900 lookups. Second, each host is
resolved ONCE per run: `urlopen` asks the resolver (A and AAAA) on every
connection, and ~900 lookups eight at a time against six registry hosts sent
a burst the LAN router's DNS forwarder answered by dropping half of the
queries -- for every client on the LAN, for as long as the gate ran
(2026-09-18). Third, failures are returned, never raised: the gate must
degrade to a cached answer rather than crash a pre-commit hook the user is
forbidden from bypassing.
"""

from __future__ import annotations

import json
import socket
import threading
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from dep_freshness._tables import (
    HTTP_ATTEMPTS,
    HTTP_TIMEOUT,
    PROBE_TIMEOUT,
    USER_AGENT,
)


class Offline(Exception):
    """The host is unreachable; callers should fall back to the cache."""


_reachable: dict[str, bool] = {}
# Eight workers start on the same registry at once; without the lock each of
# them resolves and probes the host itself, and that burst alone (16 queries)
# was enough for the router's forwarder to drop some and mark Google Maven
# unreachable for the run.
_probe_lock = threading.Lock()
_forced_offline = False
_addresses: dict[tuple[Any, ...], list[Any]] = {}
_system_getaddrinfo = socket.getaddrinfo


def cached_getaddrinfo(host: Any, port: Any, *args: Any) -> list[Any]:
    """`socket.getaddrinfo`, memoised per (host, port, hints) for the run.

    `urllib` offers no resolver hook, so this replaces the socket-level
    function for the process. Failures are not memoised: a host that did not
    resolve is retried, and `host_reachable` remembers the verdict instead.
    """
    key = (host, port, *args)
    if key not in _addresses:
        _addresses[key] = _system_getaddrinfo(host, port, *args)
    return _addresses[key]


socket.getaddrinfo = cached_getaddrinfo


def force_offline(value: bool = True) -> None:
    """Make every request raise `Offline` without touching the network."""
    global _forced_offline
    _forced_offline = value


def reset_probes() -> None:
    """Forget cached reachability verdicts and addresses (tests, `--refresh`)."""
    _reachable.clear()
    _addresses.clear()


def host_reachable(url: str) -> bool:
    """One cheap TCP probe per host, memoised for the run."""
    if _forced_offline:
        return False
    parts = urlsplit(url)
    host = parts.hostname or ""
    port = parts.port or (443 if parts.scheme == "https" else 80)
    with _probe_lock:
        if host not in _reachable:
            _reachable[host] = _probe(host, port)
    return _reachable[host]


def _probe(host: str, port: int) -> bool:
    """One TCP connect; a *temporary* resolver failure is retried.

    `EAI_AGAIN` is the resolver saying "ask again", not "no such host": a
    LAN forwarder that drops a fifth of its queries produces it a few times
    per run, and one of them used to mark a registry unreachable for the
    whole run and degrade a strict gate to exit 3.
    """
    attempt = 0
    while True:
        attempt += 1
        try:
            with socket.create_connection((host, port), timeout=PROBE_TIMEOUT):
                return True
        except socket.gaierror as exc:
            if exc.errno != socket.EAI_AGAIN or attempt == HTTP_ATTEMPTS:
                return False
        except OSError:
            return False


def get_text(url: str, accept: str | None = None) -> str | None:
    """Fetch a body as text, or raise `Offline` / return None on 404.

    Same contract as `get_json`; Maven metadata is XML, not JSON.
    """
    if not host_reachable(url):
        raise Offline(url)
    headers = {"User-Agent": USER_AGENT}
    if accept:
        headers["Accept"] = accept
    request = Request(url, headers=headers)
    # A slow registry is retried with a longer timeout each time; an HTTP
    # status is an answer and is never retried.
    attempt = 0
    while True:
        attempt += 1
        try:
            with urlopen(request, timeout=HTTP_TIMEOUT * attempt) as response:
                return response.read().decode("utf-8")
        except HTTPError as exc:
            if exc.code == 404:
                return None
            raise Offline(f"{url}: HTTP {exc.code}") from exc
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            if attempt == HTTP_ATTEMPTS:
                raise Offline(f"{url}: {exc}") from exc


def get_json(url: str, accept: str | None = None) -> Any:
    """Fetch and decode JSON, or raise `Offline` / return None on 404.

    `Offline` means "ask the cache"; None means "the registry answered and
    this package genuinely is not there", which is a real finding rather than
    a degraded run and must not be papered over with a stale cache entry.
    """
    body = get_text(url, accept)
    if body is None:
        return None
    try:
        return json.loads(body)
    except ValueError as exc:
        raise Offline(f"{url}: {exc}") from exc
