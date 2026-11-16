# Copyright (c) 2026 Krzysztof Rudnicki. MIT License.
"""An in-memory Firebase RTDB behind ``httpx.MockTransport``.

REST semantics the relay relies on: GET (shallow, orderBy/startAt), PUT,
PATCH, DELETE, ``X-Firebase-ETag`` / ``if-match`` with 412 + current value,
``{".sv": "timestamp"}``, ``?auth=`` checking, and SSE streams (initial put,
put/patch events, keep-alive, auth_revoked, cancel, drop).

The stored tree (``raw``) is what RTDB would hold: under the tutor layout
every unit is sealed with :data:`TEST_KEY`, as the relay writes it.
``get``/``set`` are the test's clear view (``set`` writes like a client
would: sealed); ``sealed=False`` stores and serves plaintext.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

from crdt_sync import E2eCipher
import httpx

from rtdb_relay.layout import E2eLayoutError
from rtdb_relay.rtdb import Rtdb
from rtdb_relay.seal import Sealer
from rtdb_relay.tests._fake_tree import (
    _assign,
    _event,
    _parts,
    _prune,
    _reply,
    etag,
)
from rtdb_relay.tests._layouts import TUTOR

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

AUTH = "test-token"
DB = "https://db.test"
TEST_KEY = bytes(range(32))
ROOT = TUTOR.root


def sealer() -> Sealer:
    """The sealer of :data:`TEST_KEY`."""
    return Sealer(E2eCipher(TEST_KEY), TUTOR)


class FakeRtdb:
    """The database; ``now_ms`` resolves server timestamps."""

    def __init__(self, now_ms: int = 1_800_000_000_000, *, sealed: bool = True) -> None:
        self.raw: dict[str, Any] = {}
        self.sealer = sealer() if sealed else None
        self.now_ms = now_ms
        self.streams: list[tuple[list[str], asyncio.Queue[str | None]]] = []
        self.fail: dict[tuple[str, str], int] = {}  # (method, rel path) -> status
        self.raise_on: set[tuple[str, str]] = set()  # -> httpx.ConnectError
        self.log: list[tuple[str, str]] = []
        self.token = AUTH

    # -- the test's clear view -------------------------------------------------
    def _rel(self, path: str) -> list[str] | None:
        parts = _parts(path)
        root = _parts(ROOT)
        return parts[len(root) :] if parts[: len(root)] == root else None

    def get(self, path: str) -> Any:
        """The value at ``path``, sealed units opened."""
        rel = self._rel(path)
        if self.sealer is None or rel is None:
            return self.raw_get(path)
        opened = self.sealer.open("", self.raw_get(ROOT))
        node: Any = opened
        for part in rel:
            if not isinstance(node, dict) or part not in node:
                return None
            node = node[part]
        return node

    def set(self, path: str, value: Any) -> None:
        """Write ``value`` as a client would (sealed; inside a unit: resealed)."""
        rel = self._rel(path)
        if self.sealer is None or rel is None:
            self.raw_set(path, value)
            return
        unit = TUTOR.unit_path("/".join(rel))
        if unit is None:
            try:
                sealed = self.sealer.seal("/".join(rel), self._sv(value))
            except E2eLayoutError as err:
                # A mis-shaped node no sealer writes: stored as a hostile client would.
                logging.getLogger(__name__).warning("stored unsealed: %s", err)
                sealed = value
            self.raw_set(path, sealed)
            return
        node = self.get(f"{ROOT}/{unit}")
        node = node if isinstance(node, dict) else {}
        _assign(node, rel[len(_parts(unit)) :], value)
        self.raw_set(f"{ROOT}/{unit}", self.sealer.seal(unit, self._sv(node)))

    # -- tree -----------------------------------------------------------------
    def raw_get(self, path: str) -> Any:
        """The stored value at ``path`` (ciphertext under the root)."""
        node: Any = self.raw
        for part in _parts(path):
            if not isinstance(node, dict) or part not in node:
                return None
            node = node[part]
        return node

    def _sv(self, value: Any) -> Any:
        if value == {".sv": "timestamp"}:
            return self.now_ms
        if isinstance(value, dict):
            out = {k: self._sv(v) for k, v in value.items()}
            return {k: v for k, v in out.items() if v is not None} or None
        return value

    def raw_set(self, path: str, value: Any) -> None:
        """Store ``value`` at ``path`` as given (server timestamps resolved)."""
        parts = _parts(path)
        value = self._sv(value)
        if not parts:
            self.raw = value if isinstance(value, dict) else {}
            return
        node = self.raw
        for part in parts[:-1]:
            if not isinstance(node.get(part), dict):
                node[part] = {}
            node = node[part]
        if value is None:
            node.pop(parts[-1], None)
        else:
            node[parts[-1]] = value
        self.raw = _prune(self.raw) or {}

    # -- streams --------------------------------------------------------------
    def _notify(self, kind: str, path: str, data: Any) -> None:
        where = _parts(path)
        for listen, queue in self.streams:
            if where[: len(listen)] == listen:
                rel = "/" + "/".join(where[len(listen) :])
                queue.put_nowait(_event(kind, rel, data))
            elif listen[: len(where)] == where:
                queue.put_nowait(_event("put", "/", self.raw_get("/".join(listen))))

    def push(self, raw: str | None) -> None:
        """Send a raw SSE block (or ``None``: close) to every stream."""
        for _, queue in self.streams:
            queue.put_nowait(raw)

    # -- HTTP -----------------------------------------------------------------
    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handle))

    def rtdb(self) -> Rtdb:
        async def token() -> str:
            return self.token

        return Rtdb(DB, token, client=self.client(), root=ROOT, sealer=self.sealer)

    async def handle(self, request: httpx.Request) -> httpx.Response:
        full = request.url.path.removesuffix(".json").strip("/")
        path = (
            "/" + full.removeprefix(ROOT).strip("/")
            if full.startswith(ROOT)
            else "/" + full
        )
        method = request.method
        self.log.append((method, path))
        if (method, path) in self.raise_on:
            msg = "boom"
            raise httpx.ConnectError(msg, request=request)
        if request.url.params.get("auth") != AUTH:
            return _reply(401, {"error": "Permission denied"})
        if (method, path) in self.fail:
            return _reply(self.fail[(method, path)], {"error": "x"})
        if request.headers.get("accept") == "text/event-stream":
            return self._stream(full)
        current = self.raw_get(full)
        match = request.headers.get("if-match")
        if match is not None and match != etag(current):
            return _reply(412, current, headers={"ETag": etag(current)})
        if method == "GET":
            return self._get(request, full, current)
        return self._write(method, full, request)

    def _write(self, method: str, full: str, request: httpx.Request) -> httpx.Response:
        if method == "PUT":
            self.raw_set(full, json.loads(request.content))
            self._notify("put", full, self.raw_get(full))
            stored = self.raw_get(full)
            return _reply(200, stored, headers={"ETag": etag(stored)})
        if method == "PATCH":
            body = json.loads(request.content)
            for key, value in body.items():
                self.raw_set(f"{full}/{key}", value)
            self._notify("patch", full, self._sv(body))
            return _reply(200, body)
        self.raw_set(full, None)  # DELETE
        self._notify("put", full, None)
        return _reply(200, None)

    def _get(self, request: httpx.Request, full: str, value: Any) -> httpx.Response:
        params = request.url.params
        if params.get("shallow") == "true" and isinstance(value, dict):
            value = dict.fromkeys(value, True)
        start = params.get("startAt")
        if start and isinstance(value, dict):
            value = {k: v for k, v in value.items() if k >= json.loads(start)}
        headers = (
            {"ETag": etag(value)} if request.headers.get("x-firebase-etag") else {}
        )
        return _reply(200, value, headers=headers)

    def _stream(self, full: str) -> httpx.Response:
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        entry = (_parts(full), queue)
        self.streams.append(entry)
        queue.put_nowait(_event("put", "/", self.raw_get(full)))

        async def body() -> AsyncIterator[bytes]:
            try:
                while (block := await queue.get()) is not None:
                    yield block.encode()
            finally:
                self.streams.remove(entry)

        return httpx.Response(
            200, content=body(), headers={"content-type": "text/event-stream"}
        )
