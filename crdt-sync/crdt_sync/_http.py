"""Pooled HTTP sessions, so every request does not re-handshake.

Every call site in this package used the module-level ``requests.get`` /
``put`` / ``post`` / ``delete`` helpers, each of which opens a throwaway
connection: fresh DNS, TCP and TLS on every single request. Measured against
the two real backends on 2026-08-21 that costs 82ms per request to
``api.github.com`` and 51ms to Realtime Database -- on a 27-request sync tick,
most of the wall clock.

A :class:`requests.Session` keeps the connection alive between requests, and
is a drop-in for the module-level helpers: same verb names, same signatures.
So each transport module binds one of these to the name ``requests`` and its
call sites are unchanged.

**One session per module, deliberately not one global.** The tests patch the
verb on the module attribute (``patch.object(fb.requests, "get", ...)``), and
several use sequence-consuming ``side_effect`` lists. Were all three modules
to share a single object, a call from one would consume another's queued
response and the failure would look like a logic bug. Per-module also happens
to be per-host here -- GitHub, Realtime Database, and the token endpoint are
three different origins -- so pooling loses nothing by the split.

Not thread-safe, in that :class:`requests.Session` is not documented to be;
this package spawns no threads and its consumers drive sync from one.
"""

from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter, Retry

_RETRY_TOTAL = 3
_RETRY_BACKOFF_SECONDS = 0.3
_RETRY_STATUSES = (429, 500, 502, 503, 504)


def new_session() -> requests.Session:
    """Return a connection-pooling session that retries transient GET failures.

    Retries are restricted to ``GET``. A ``PUT`` here carries a Contents-API
    ``sha`` (and a Realtime Database write is a full-node replace); replaying
    one whose response was merely lost would push a second write built on a
    now-stale precondition, against a remote another device reads. Reads are
    idempotent, so only they are replayed.
    """
    session = requests.Session()
    retry = Retry(
        total=_RETRY_TOTAL,
        backoff_factor=_RETRY_BACKOFF_SECONDS,
        status_forcelist=_RETRY_STATUSES,
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session
