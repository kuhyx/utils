# Copyright (c) 2026 Krzysztof Rudnicki. MIT License.
"""Serve ``requests/{rid}`` with registered kind handlers (the PC side).

A client writes ``requests/{rid}/req`` = ``{"kind", "dev", "created",
"sent_at", "body"}`` (sealed). The server claims it (:class:`Lease`), runs
the handler for ``kind`` and writes ``requests/{rid}/result`` =
``{"ok": true, "kind", "at", **data}`` or ``{"ok": false, "kind", "code",
"error", "retry", "at"}``. Guards (fail closed):

- only kinds in ``handlers`` run; any other kind gets ``unknown_kind``;
- an unsealed (plaintext) or undecryptable ``req`` gets ``unsealed``;
- a non-ULID rid is never used in a path (skipped);
- a handler bug becomes a visible ``internal`` result, never a silent drop.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import TYPE_CHECKING, Any, Final

from rtdb_relay import mirror, sse
from rtdb_relay.lease import RENEW_S, Lease, valid_rid
from rtdb_relay.rtdb import SERVER_TIME
from rtdb_relay.seal import SEALED

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping

    from rtdb_relay.rtdb import Rtdb

type Handler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
_logger = logging.getLogger(__name__)
UNKNOWN_KIND: Final = "unknown_kind"
UNSEALED: Final = "unsealed"
INTERNAL: Final = "internal"


class RequestError(Exception):
    """A handler's refusal: ``code`` and ``message`` reach the client."""

    def __init__(self, code: str, message: str, *, retry: bool = False) -> None:
        """Fail the request with ``code``; ``retry`` tells the client it may."""
        super().__init__(message)
        self.code, self.message, self.retry = code, message, retry


def failure(
    kind: object, code: str, message: str, *, retry: bool = False
) -> dict[str, Any]:
    """A failed ``result`` node (``at`` resolved by the server)."""
    return {
        "ok": False,
        "kind": kind if isinstance(kind, str) else "",
        "code": code,
        "error": message,
        "retry": retry,
        "at": SERVER_TIME,
    }


class RequestServer:
    """Claims and answers requests under ``rtdb``'s root."""

    def __init__(
        self,
        rtdb: Rtdb,
        worker: str,
        handlers: Mapping[str, Handler],
        now: Callable[[], float] = time.time,
    ) -> None:
        """Serve with ``rtdb`` (sealed client); ``worker`` names this process."""
        self.rtdb, self.worker, self.handlers, self._now = rtdb, worker, handlers, now
        self._raw = rtdb.at(rtdb.root)
        self._busy: set[str] = set()
        self.tasks: set[asyncio.Task[None]] = set()

    def request_of(self, rid: str, raw: object) -> dict[str, Any] | None:
        """The opened ``req``, or ``None`` when it was not sealed or not ours."""
        if not isinstance(raw, dict) or not isinstance(raw.get(SEALED), str):
            return None
        req = self.rtdb.opened(f"requests/{rid}/req", raw)
        return req if isinstance(req, dict) and SEALED not in req else None

    async def answer(self, rid: str, node: dict[str, Any]) -> dict[str, Any] | None:
        """Serve one pending request node; ``None`` when not ours to answer."""
        if not valid_rid(rid) or "result" in node or "req" not in node:
            return None
        req = self.request_of(rid, node["req"])
        kind = req.get("kind") if req else None
        lease = Lease(self.rtdb, rid, self.worker, self._now)
        if not await lease.take():
            return None
        if req is None:
            result = failure(kind, UNSEALED, "request was not sealed")
        elif not isinstance(kind, str) or kind not in self.handlers:
            result = failure(kind, UNKNOWN_KIND, f"no handler for {kind!r}")
        else:
            result = await self._run(lease, kind, req)
        await self.rtdb.put(f"requests/{rid}/result", result)
        return result

    async def _run(
        self, lease: Lease, kind: str, req: dict[str, Any]
    ) -> dict[str, Any]:
        body = req.get("body")
        keeper = asyncio.create_task(self._keep(lease))
        try:
            data = await self.handlers[kind](body if isinstance(body, dict) else {})
        except RequestError as err:
            return failure(kind, err.code, err.message, retry=err.retry)
        except Exception as err:
            _logger.exception("handler %s failed", kind)
            return failure(kind, INTERNAL, type(err).__name__, retry=True)
        finally:
            keeper.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await keeper
        return {**data, "ok": True, "kind": kind, "at": SERVER_TIME}

    async def _keep(self, lease: Lease) -> None:
        while True:
            await asyncio.sleep(RENEW_S)
            await lease.renew("running")

    def dispatch(self, tree: dict[str, Any]) -> None:
        """Start a task for every pending request not already in flight."""
        for rid, node in tree.items():
            if rid in self._busy or not isinstance(node, dict) or "result" in node:
                continue
            self._busy.add(rid)
            task = asyncio.create_task(self._serve(rid, node))
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)

    async def _serve(self, rid: str, node: dict[str, Any]) -> None:
        try:
            await self.answer(rid, node)
        except Exception:
            _logger.exception("request %s failed", rid)
        finally:
            self._busy.discard(rid)

    async def run(self) -> None:
        """Watch ``requests`` (raw, so sealing is checked) until cancelled."""
        tree: dict[str, Any] = {}
        async for event in sse.listen(self._raw, "requests"):
            tree = mirror.apply(tree, event)
            self.dispatch(tree)
