# Copyright (c) 2026 Krzysztof Rudnicki
"""A minimal RTDB REST client on a seeded crdt-sync Google session.

Ported from kartka's ``tools/errors`` (``kartka_errors.rtdb``), plus
``shallow`` reads to list the apps. The sync account is Google-only, so the
session is an already seeded ``~/.config/<store>/firebase_auth.json`` (crdt-
sync's ``tool.seed_session`` writes one; it refreshes itself). The request URL
carries the ID token (``?auth=``), so no error raised here ever includes it.
"""

from __future__ import annotations

from collections.abc import Callable
import json
from typing import Protocol
import urllib.error
import urllib.request

#: The credential store read by default: the backup timer's, a PC-side reader
#: of the same database (any seeded store of the sync account works).
DEFAULT_SESSION = "firebase_backup"
#: Per-request timeout, seconds (token refresh has its own, below).
TIMEOUT = 15.0
TOKEN_TIMEOUT = 8.0

type Opener = Callable[..., object]


class RtdbError(RuntimeError):
    """An RTDB request failed, or there is no session (the message never names the URL)."""


class Rtdb(Protocol):
    """Read and multi-path write access to RTDB."""

    def get(self, path: str, *, shallow: bool = False) -> object:
        """Return the decoded JSON at ``path`` (None when absent)."""
        ...

    def patch(self, path: str, data: dict[str, object]) -> None:
        """Apply a multi-path update of ``path`` (a None value deletes)."""
        ...


class RestRtdb:
    """RTDB over REST with ``?auth=<id token>``."""

    def __init__(
        self,
        database_url: str,
        id_token: Callable[[], str],
        opener: Opener = urllib.request.urlopen,
    ) -> None:
        """Talk to ``database_url`` with tokens from ``id_token``."""
        self._url = database_url.rstrip("/")
        self._id_token = id_token
        self._open = opener

    def _send(self, method: str, path: str, body: bytes | None, query: str = "") -> object:
        try:
            token = self._id_token()
        except Exception as e:  # noqa: BLE001 -- any refresh failure, typed only
            msg = f"RTDB {method} {path}: token refresh failed ({type(e).__name__})"
            raise RtdbError(msg) from None
        req = urllib.request.Request(  # noqa: S310 -- https only, built here
            f"{self._url}/{path}.json?auth={token}{query}",
            data=body,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with self._open(req, timeout=TIMEOUT) as res:  # type: ignore[attr-defined]
                return json.loads(res.read() or b"null")
        except urllib.error.HTTPError as e:
            msg = f"RTDB {method} {path}: HTTP {e.code}"
            raise RtdbError(msg) from None
        except (urllib.error.URLError, OSError, ValueError) as e:
            msg = f"RTDB {method} {path}: {type(e).__name__}"
            raise RtdbError(msg) from None

    def get(self, path: str, *, shallow: bool = False) -> object:
        """GET ``path``; raises :class:`RtdbError` on any failure."""
        return self._send("GET", path, None, "&shallow=true" if shallow else "")

    def patch(self, path: str, data: dict[str, object]) -> None:
        """PATCH ``data`` into ``path``; raises :class:`RtdbError`."""
        self._send("PATCH", path, json.dumps(data).encode())


def open_rtdb(session: str = DEFAULT_SESSION) -> RestRtdb:
    """Return the client on the seeded ``session``; :class:`RtdbError` without one."""
    import crdt_sync  # noqa: PLC0415 -- only the RTDB path needs it; spool-only runs stay stdlib

    try:
        config = crdt_sync.FirebaseConfig.load()
    except Exception as e:  # noqa: BLE001 -- a missing or broken config, typed only
        msg = f"no Firebase config ({type(e).__name__})"
        raise RtdbError(msg) from None
    store = crdt_sync.credential_store_for(session)
    auth = crdt_sync.FirebaseTokenProvider(config.api_key, store, timeout_seconds=TOKEN_TIMEOUT)
    if not auth.has_session():
        msg = f"no seeded sign-in session '{session}'; seed one with crdt-sync's tool.seed_session --app {session}"
        raise RtdbError(msg)
    return RestRtdb(config.database_url, auth.id_token)
