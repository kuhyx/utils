"""The desktop's loopback API on 127.0.0.1:8777 (DOCS-coach-relay.md 1, 4).

Reached only through the app's wrapper on :8776, never by the browser. It
binds the loopback address, refuses a ``Host`` other than its own (DNS
rebinding) and takes POST bodies only as ``application/json``, so a
cross-origin POST needs a preflight that is never granted. No route takes a
path, a command or a URL; a request body goes to `protocol.parse` and from
there to the lane, like the phone's.
"""

from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
from typing import TYPE_CHECKING, Any, Final, Protocol
from urllib.parse import parse_qs, urlsplit

from leetcode_coach.relay import protocol

if TYPE_CHECKING:
    from leetcode_coach.relay.coach import Coach
    from leetcode_coach.relay.lane import Lane

_logger: Final = logging.getLogger(__name__)

PREFIX: Final = "/coach/"
REQUESTS: Final = "/coach/requests"
CHAT_KEY_RE_LEN: Final = 5


class App(Protocol):
    """What the API serves: the lane, the backend and the heartbeat."""

    lane: Lane
    coach: Coach

    def heartbeat(self) -> dict[str, Any]:
        """The heartbeat object, ``beat`` as unix ms."""


class Server(ThreadingHTTPServer):
    """A threading server that knows its relay."""

    daemon_threads = True

    def __init__(self, address: tuple[str, int], app: App) -> None:
        """Bind `address` and keep `app` for the handlers."""
        super().__init__(address, Handler)
        self.app = app


class Handler(BaseHTTPRequestHandler):
    """The four GET routes and the one POST."""

    server: Server
    server_version = "leetcode-coach-relay"

    def log_message(self, fmt: str, /, *args: object) -> None:
        """Request lines to the journal at debug, not stderr."""
        _logger.debug("%s - %s", self.address_string(), fmt % args)

    def _send(self, status: HTTPStatus, payload: object) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: HTTPStatus, code: str, error: str) -> None:
        self._send(status, {"ok": False, "code": code, "error": error})

    def _host_ok(self) -> bool:
        port = self.server.server_address[1]
        host = self.headers.get("Host", "")
        if host in {f"127.0.0.1:{port}", f"localhost:{port}"}:
            return True
        _logger.warning("refused a request for Host %r", host)
        self._error(HTTPStatus.FORBIDDEN, "bad_host", "loopback only")
        return False

    def do_GET(self) -> None:
        """State, heartbeat, chat, or one request's result."""
        if not self._host_ok():
            return
        url = urlsplit(self.path)
        app = self.server.app
        if url.path == "/coach/state":
            self._send(HTTPStatus.OK, app.coach.state())
        elif url.path == "/coach/heartbeat":
            self._send(HTTPStatus.OK, app.heartbeat())
        elif url.path == "/coach/chat":
            after = parse_qs(url.query).get("after", [None])[0]
            self._send(HTTPStatus.OK, app.coach.chat_after(after))
        elif url.path.startswith(REQUESTS + "/"):
            rid = url.path.removeprefix(REQUESTS + "/")
            if not protocol.RID_RE.fullmatch(rid) or not app.lane.known(rid):
                self._error(HTTPStatus.NOT_FOUND, "unknown_rid", "no such request")
                return
            self._send(HTTPStatus.OK, {"result": app.lane.result(rid)})
        else:
            self._error(HTTPStatus.NOT_FOUND, "not_found", "no such route")

    def _body(self) -> object:
        """The decoded JSON body, or None after an error answer was sent."""
        ctype = self.headers.get("Content-Type", "").split(";")[0].strip()
        if ctype != "application/json":
            self._error(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "bad_request", "JSON bodies only"
            )
            return None
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
            _logger.warning("a POST with a bad Content-Length")
        if length > protocol.MAX_REQ_BYTES:
            self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "bad_request", "too big")
            return None
        if length < 0:
            self._error(HTTPStatus.BAD_REQUEST, "bad_request", "bad length")
            return None
        try:
            return json.loads(self.rfile.read(length) or b"null")
        except ValueError as exc:
            _logger.warning("a POST body that is not JSON: %s", exc)
            self._error(HTTPStatus.BAD_REQUEST, "bad_request", "not JSON")
            return None

    def do_POST(self) -> None:
        """Queue one request: 202, or 200 with its result when already known."""
        if not self._host_ok():
            return
        if urlsplit(self.path).path != REQUESTS:
            self._error(HTTPStatus.NOT_FOUND, "not_found", "no such route")
            return
        raw = self._body()
        if raw is None:
            return
        lane = self.server.app.lane
        try:
            req = protocol.parse(raw, "desktop")
        except protocol.BadRidError as exc:
            _logger.warning("desktop request refused: %s", exc)
            self._error(HTTPStatus.BAD_REQUEST, "bad_request", str(exc))
            return
        except protocol.BadRequestError as exc:
            _logger.warning("bad desktop request: %s", exc)
            rid = str(raw["rid"]) if isinstance(raw, dict) else ""
            if (done := lane.result(rid)) is None:
                done = protocol.failure("bad_request", str(exc), at=lane.now())
                lane.finish(rid, "desktop", done)
            self._send(HTTPStatus.OK, done)
            return
        result = lane.submit(req)
        if result is None:
            self._send(HTTPStatus.ACCEPTED, {"rid": req.rid})
        else:
            self._send(HTTPStatus.OK, result)
