# Copyright (c) 2026 Krzysztof Rudnicki. MIT License.
"""A minimal async RTDB REST client: GET/PUT/PATCH/DELETE, ETags, server time.

Under the app's root every value goes through a ``seal.Sealer`` (sealed on
write, opened on read) once ``sealer`` is set; ``at()`` gives the raw
client the e2e header and one-time copies use.

Every call authenticates with ``?auth=<idToken>`` (RTDB REST has no header
form), so nothing here ever formats a URL or an ``httpx`` error into a
message or a log line: errors name the method, the path and the status only.
httpx's own request log (INFO, full URL) is silenced for the same reason.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import quote

import httpx

from rtdb_relay.layout import parts_of

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable

    from rtdb_relay.seal import Sealer

SERVER_TIME: Final = {".sv": "timestamp"}
NULL_ETAG: Final = "null_etag"
_PRECONDITION_FAILED: Final = 412
_TIMEOUT: Final = httpx.Timeout(30.0, connect=15.0)
# The SSE read timeout: RTDB sends keep-alive every 30 s.
_STREAM_TIMEOUT: Final = httpx.Timeout(30.0, connect=15.0, read=75.0)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


class RtdbError(RuntimeError):
    """A request failed; the message never contains the URL or the token."""


class ConflictError(RtdbError):
    """A conditional write lost the race (HTTP 412): the current value and ETag."""

    def __init__(self, path: str, value: object, etag: str) -> None:
        """Keep what the server holds now."""
        super().__init__(f"conditional write lost on {path}")
        self.value = value
        self.etag = etag


class Rtdb:
    """REST calls under ``root``; ``token`` yields a fresh id token."""

    def __init__(
        self,
        database_url: str,
        token: Callable[[], Awaitable[str]],
        client: httpx.AsyncClient | None = None,
        *,
        root: str,
        sealer: Sealer | None = None,
    ) -> None:
        """Bind the database; ``client`` is injectable (tests use a fake)."""
        self._base = database_url.rstrip("/")
        self._token = token
        self.client = client or httpx.AsyncClient(timeout=_TIMEOUT)
        self.root = root
        self.sealer = sealer

    def at(self, root: str) -> Rtdb:
        """A raw (unsealed) client on ``root`` sharing this one's connection."""
        return type(self)(self._base, self._token, self.client, root=root)

    def url(self, path: str) -> str:
        """The REST URL of ``path`` (relative to the root), no token."""
        parts = [*parts_of(self.root), *parts_of(path)]
        return f"{self._base}/{'/'.join(quote(p, safe='') for p in parts)}.json"

    def _seal(self, path: str, value: object) -> object:
        return value if self.sealer is None else self.sealer.seal(path, value)

    def opened(self, path: str, value: object) -> object:
        """``value`` read at ``path`` with its sealed units opened."""
        return value if self.sealer is None else self.sealer.open(path, value)

    async def params(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        """Query parameters: the auth token plus ``extra``."""
        return {"auth": await self._token(), **(extra or {})}

    async def _call(
        self,
        method: str,
        path: str,
        *,
        value: object = None,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
    ) -> httpx.Response:
        kwargs: dict[str, Any] = {"params": await self.params(params)}
        if method in {"PUT", "PATCH"}:
            kwargs["content"] = json.dumps(value).encode()  # json=None sends no body
        try:
            response = await self.client.request(
                method, self.url(path), headers=headers or {}, **kwargs
            )
        except httpx.HTTPError as err:
            msg = f"{method} {path}: {type(err).__name__}"
            raise RtdbError(msg) from None
        if response.status_code == _PRECONDITION_FAILED:
            current = self.opened(path, response.json())
            raise ConflictError(path, current, response.headers.get("etag", ""))
        if response.is_error:
            msg = f"{method} {path}: HTTP {response.status_code}"
            raise RtdbError(msg)
        return response

    async def get(self, path: str, params: dict[str, str] | None = None) -> object:
        """The value at ``path`` (``None`` when absent).

        Below a sealed unit the whole unit is read and opened, then walked.
        """
        unit = None if self.sealer is None else self.sealer.unit_path(path)
        if unit is not None:
            node: Any = await self.get(unit)
            for part in parts_of(path)[len(parts_of(unit)) :]:
                node = node.get(part) if isinstance(node, dict) else None
            return node
        value: object = (await self._call("GET", path, params=params)).json()
        return self.opened(path, value)

    async def get_etag(self, path: str) -> tuple[Any, str]:
        """The value at ``path`` and its ETag (``null_etag`` when absent)."""
        response = await self._call("GET", path, headers={"X-Firebase-ETag": "true"})
        value = self.opened(path, response.json())
        return value, response.headers.get("etag", NULL_ETAG)

    async def put(self, path: str, value: object) -> object:
        """Write ``value``; returns it as stored (server timestamps resolved)."""
        sealed = self._seal(path, value)
        stored: object = (await self._call("PUT", path, value=sealed)).json()
        return self.opened(path, stored)

    async def put_etag(
        self, path: str, value: object, if_match: str
    ) -> tuple[Any, str]:
        """A conditional PUT that also returns the new ETag."""
        headers = {"if-match": if_match, "X-Firebase-ETag": "true"}
        sealed = self._seal(path, value)
        response = await self._call("PUT", path, value=sealed, headers=headers)
        return self.opened(path, response.json()), response.headers.get("etag", "")

    async def patch(self, path: str, value: dict[str, Any]) -> None:
        """Merge ``value``'s children into ``path`` (``None`` children delete)."""
        if self.sealer is not None:
            value = self.sealer.seal_patch(path, value)
        await self._call("PATCH", path, value=value)

    async def delete(self, path: str, if_match: str | None = None) -> None:
        """Remove ``path``; with ``if_match`` only if unchanged."""
        headers = {"if-match": if_match} if if_match else {}
        await self._call("DELETE", path, headers=headers)

    async def open_stream(
        self, path: str, params: dict[str, str] | None = None
    ) -> AsyncIterator[str]:
        """The raw SSE lines of one connection to ``path`` (see ``sse``)."""
        request = self.client.build_request(
            "GET",
            self.url(path),
            params=await self.params(params),
            headers={"Accept": "text/event-stream"},
            timeout=_STREAM_TIMEOUT,
        )
        try:
            response = await self.client.send(request, stream=True)
        except httpx.HTTPError as err:
            msg = f"STREAM {path}: {type(err).__name__}"
            raise RtdbError(msg) from None
        try:
            if response.is_error:
                msg = f"STREAM {path}: HTTP {response.status_code}"
                raise RtdbError(msg)
            async for line in response.aiter_lines():
                yield line
        except httpx.HTTPError as err:
            msg = f"STREAM {path}: {type(err).__name__}"
            raise RtdbError(msg) from None
        finally:
            await response.aclose()

    async def aclose(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()
