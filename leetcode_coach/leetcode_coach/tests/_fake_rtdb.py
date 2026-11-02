"""An in-process fake Firebase RTDB: REST (GET/PUT/PATCH/DELETE) plus SSE streams.

Enough of RTDB's semantics for the relay's tests: a JSON tree where a ``null``
write deletes and an empty object vanishes, ``{".sv": "timestamp"}`` resolved to
`now_ms`, ``print=silent`` answered 204, ``?auth=`` required. A GET with
``Accept: text/event-stream`` opens a stream that starts with a ``put`` of the
whole node at ``/`` and then reports every later write at or under it -- over
HTTP/1.1 chunked encoding, as Firebase sends it, so a client that buffers until
EOF would hang here too. `write` is the phone's side.
"""

from __future__ import annotations

from http.server import ThreadingHTTPServer
import json
import queue
import threading
from typing import TYPE_CHECKING, Any, Self

from leetcode_coach.tests._fake_rtdb_handler import handler_for, segments

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import TracebackType

ROOT = "leetcode-guard/coach"
NOW_MS = 1_792_771_488_000
Item = tuple[str, str] | None


def _clean(value: Any, now: int) -> Any:
    """Resolve server timestamps and drop nulls and empty objects."""
    if isinstance(value, dict):
        if value == {".sv": "timestamp"}:
            return now
        kept = {k: c for k, v in value.items() if (c := _clean(v, now)) is not None}
        return kept or None
    return value


def _set_in(node: dict[str, Any], segs: list[str], value: Any) -> dict[str, Any]:
    """A copy of `node` with `value` at `segs`; emptied objects pruned."""
    head, rest = segs[0], segs[1:]
    if rest:
        child = node.get(head)
        here = _set_in(child if isinstance(child, dict) else {}, rest, value) or None
    else:
        here = value
    out = dict(node)
    if here is None:
        out.pop(head, None)
    else:
        out[head] = here
    return out


class _Stream:
    def __init__(self, path: list[str]) -> None:
        self.path = path
        self.items: queue.Queue[Item] = queue.Queue()


class FakeRtdb:
    """The fake database and its HTTP server."""

    def __init__(self, now_ms: Callable[[], int] | None = None) -> None:
        self.now_ms = now_ms or (lambda: NOW_MS)
        self.tree: dict[str, Any] = {}
        self.tokens: list[str] = []
        self.requests: list[tuple[str, str, str]] = []
        self._failures: list[int] = []
        self._streams: list[_Stream] = []
        self._lock = threading.RLock()
        self._stopping = threading.Event()
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(self))
        self._server.daemon_threads = True
        self._thread = threading.Thread(
            target=self._server.serve_forever, args=(0.01,), daemon=True
        )

    @classmethod
    def start(cls, now_ms: Callable[[], int] | None = None) -> FakeRtdb:
        fake = cls(now_ms)
        fake._thread.start()
        return fake

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host!s}:{port}"

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.stop()

    def stop(self) -> None:
        self._stopping.set()
        with self._lock:
            for stream in self._streams:
                stream.items.put(None)
        self._server.shutdown()
        self._server.server_close()

    # -- the tree ------------------------------------------------------------

    def _get(self, segs: list[str]) -> Any:
        node: Any = self.tree
        for seg in segs:
            if not isinstance(node, dict) or seg not in node:
                return None
            node = node[seg]
        return node

    def _set(self, segs: list[str], value: Any) -> None:
        if not segs:
            self.tree = value if isinstance(value, dict) else {}
            return
        self.tree = _set_in(self.tree, segs, value)

    def node(self, segs: list[str]) -> Any:
        """The value at absolute `segs` (``None`` when absent)."""
        with self._lock:
            return self._get(segs)

    def read(self, path: str = "") -> Any:
        with self._lock:
            return json.loads(json.dumps(self._get(segments(f"{ROOT}/{path}"))))

    def write(self, path: str, value: Any) -> None:
        """The phone's PUT under the coach root."""
        self.apply("PUT", segments(f"{ROOT}/{path}"), value)

    def apply(self, method: str, segs: list[str], value: Any) -> Any:
        now = self.now_ms()
        with self._lock:
            if method == "PATCH":
                if not isinstance(value, dict):
                    raise TypeError
                patch = {k: _clean(v, now) for k, v in value.items()}
                for key, child in patch.items():
                    self._set(segs + segments(key), child)
                self._notify(segs, "patch", patch)
                return patch
            stored = None if method == "DELETE" else _clean(value, now)
            self._set(segs, stored)
            self._notify(segs, "put", stored)
            return stored

    def _notify(self, segs: list[str], kind: str, data: Any) -> None:
        for stream in self._streams:
            depth = len(stream.path)
            if segs[:depth] == stream.path:
                rel = "/" + "/".join(segs[depth:])
                stream.items.put((kind, json.dumps({"path": rel, "data": data})))
            elif stream.path[: len(segs)] == segs:
                whole = {"path": "/", "data": self._get(stream.path)}
                stream.items.put(("put", json.dumps(whole)))

    # -- test controls -------------------------------------------------------

    def fail_next(self, n: int, status: int = 500) -> None:
        with self._lock:
            self._failures += [status] * n

    def take_failure(self) -> int | None:
        with self._lock:
            return self._failures.pop(0) if self._failures else None

    def _end_streams(self, event: str, data: str) -> None:
        with self._lock:
            for stream in self._streams:
                stream.items.put((event, data))
                stream.items.put(None)

    def revoke_streams(self) -> None:
        self._end_streams("auth_revoked", '"credential is no longer valid"')

    def cancel_streams(self) -> None:
        self._end_streams("cancel", "null")

    def stream_count(self) -> int:
        with self._lock:
            return len(self._streams)

    def open_stream(self, segs: list[str]) -> _Stream:
        stream = _Stream(segs)
        with self._lock:
            whole = {"path": "/", "data": self._get(segs)}
            stream.items.put(("put", json.dumps(whole)))
            self._streams.append(stream)
        return stream

    def close_stream(self, stream: _Stream) -> None:
        with self._lock:
            self._streams.remove(stream)

    @property
    def stopping(self) -> bool:
        return self._stopping.is_set()
