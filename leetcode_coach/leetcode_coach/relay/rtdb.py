"""A minimal synchronous RTDB REST client: GET/PUT/PATCH/DELETE and SSE streams.

Ported from tutor's async ``tutor/relay/rtdb.py`` onto ``requests`` (this repo's
one network dependency; the relay runs on threads, not asyncio). Every call
authenticates with ``?auth=<idToken>`` (RTDB REST has no header form), so
nothing here ever formats a URL or a ``requests`` error into a message: errors
name the method, the path and the status only. Writes ask for
``print=silent``, so RTDB does not echo every body back (`_snapshot_rtdb`).
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Final
from urllib.parse import quote

import requests

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

ROOT: Final = "leetcode-guard/coach"
SERVER_TIME: Final = {".sv": "timestamp"}
_CONNECT_S: Final = 15.0
_STREAM_READ_S: Final = 75.0
"""RTDB sends a keep-alive every 30 s, so 75 s of silence is a dead stream."""

# urllib3 logs every request line, query string (the token) included, at DEBUG.
logging.getLogger("urllib3").setLevel(logging.WARNING)


class RtdbError(RuntimeError):
    """A request failed; the message never contains the URL or the token."""


def parse(lines: list[str]) -> tuple[str, str]:
    """``(event, data)`` of one SSE block (its lines, blank line excluded)."""
    event, data = "message", []
    for line in lines:
        field, _, value = line.partition(":")
        value = value.removeprefix(" ")
        if field == "event":
            event = value
        elif field == "data":
            data.append(value)
    return event, "\n".join(data)


class Rtdb:
    """REST calls under ``/leetcode-guard/coach``; ``id_token`` yields a fresh token."""

    def __init__(
        self,
        database_url: str,
        id_token: Callable[[], str],
        *,
        session: requests.Session | None = None,
        timeout_s: float = 30.0,
    ) -> None:
        """Bind the database; ``session`` is injectable for tests."""
        self._base = database_url.rstrip("/")
        self._token = id_token
        self._session = session or requests.Session()
        self._timeout = timeout_s

    def url(self, path: str) -> str:
        """The REST URL of ``path`` (relative to the coach root), no token."""
        rel = "/".join(quote(p, safe="") for p in path.strip("/").split("/") if p)
        return f"{self._base}/{ROOT}/{rel}.json" if rel else f"{self._base}/{ROOT}.json"

    def _call(
        self, method: str, path: str, value: object = None, *, body: bool = False
    ) -> requests.Response:
        params = {"auth": self._token()}
        if body:
            params["print"] = "silent"
        data = json.dumps(value).encode() if body else None
        try:
            response = self._session.request(
                method, self.url(path), params=params, data=data, timeout=self._timeout
            )
        except requests.RequestException as err:
            msg = f"{method} {path}: {type(err).__name__}"
            raise RtdbError(msg) from None
        if not response.ok:
            msg = f"{method} {path}: HTTP {response.status_code}"
            raise RtdbError(msg)
        return response

    def get(self, path: str) -> object:
        """The value at ``path`` (``None`` when absent)."""
        response = self._call("GET", path)
        try:
            value: object = response.json()
        except ValueError:
            msg = f"GET {path}: not JSON"
            raise RtdbError(msg) from None
        return value

    def put(self, path: str, value: object) -> None:
        """Replace ``path`` with ``value`` (a str is stored as a string leaf)."""
        self._call("PUT", path, value, body=True)

    def patch(self, path: str, value: dict[str, object]) -> None:
        """Merge ``value``'s children (keys may be nested ``a/b`` paths)."""
        self._call("PATCH", path, value, body=True)

    def delete(self, path: str) -> None:
        """Remove ``path``."""
        self._call("DELETE", path)

    def stream(self, path: str) -> Generator[tuple[str, str]]:
        """The ``(event, data)`` blocks of ONE SSE connection to ``path``.

        Ends at EOF; the response is closed however the iteration stops.

        Raises:
            RtdbError: The connection could not open, or it dropped mid-read.
        """
        try:
            response = self._session.get(
                self.url(path),
                params={"auth": self._token()},
                headers={"Accept": "text/event-stream"},
                stream=True,
                timeout=(_CONNECT_S, _STREAM_READ_S),
            )
        except requests.RequestException as err:
            msg = f"STREAM {path}: {type(err).__name__}"
            raise RtdbError(msg) from None
        try:
            if not response.ok:
                msg = f"STREAM {path}: HTTP {response.status_code}"
                raise RtdbError(msg)
            block: list[str] = []
            # chunk_size=1: a non-chunked stream would otherwise hold a small
            # event back until 512 bytes arrived (SSE events are tiny).
            for raw in response.iter_lines(chunk_size=1):
                if raw:
                    block.append(raw.decode("utf-8", errors="replace"))
                elif block:
                    yield parse(block)
                    block = []
        except requests.RequestException as err:
            msg = f"STREAM {path}: {type(err).__name__}"
            raise RtdbError(msg) from None
        finally:
            response.close()
