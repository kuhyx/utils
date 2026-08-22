"""Tests for the one-shot OAuth redirect catcher in ``tool/_oauth_callback``.

No network access: everything binds 127.0.0.1 on a port the module itself
picks. The handler is driven over real HTTP rather than with a faked request
object, because the branches worth protecting here are the ones that only
appear once a socket is involved -- the favicon fetch that must *not* end the
flow, and the serve loop's exit conditions, which run on a worker thread.
"""

from __future__ import annotations

import http.client
import http.server
import time
from typing import TYPE_CHECKING

import pytest

from tool import _oauth_callback as oc

if TYPE_CHECKING:
    from collections.abc import Iterator
    import threading

_STATE = "state-the-callback-must-echo"


def _get(port: int, path: str) -> tuple[int, bytes]:
    """Issue one GET against the loopback server and read the whole reply."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request("GET", path)
        response = conn.getresponse()
        return response.status, response.read()
    finally:
        conn.close()


def _retire(srv: http.server.HTTPServer, thread: threading.Thread) -> None:
    """Stop the serve thread, then close the socket -- in that order.

    ``server_close()`` while the thread is still inside ``handle_request()``
    pulls the socket out from under it and raises on the worker. Setting a
    result is what the loop's own exit condition tests, so it retires the
    thread the same way a real callback does.
    """
    oc._CallbackHandler.result = oc._CallbackHandler.result or {"code": "teardown"}
    thread.join(timeout=5)
    srv.server_close()


@pytest.fixture
def server() -> Iterator[tuple[int, threading.Thread]]:
    """Start the callback server on a free port and always tear it down."""
    port = oc._free_port()
    srv, thread = oc._start_callback_server(port, _STATE)
    try:
        yield port, thread
    finally:
        _retire(srv, thread)


def test_free_port_returns_a_bindable_loopback_port() -> None:
    """The port is real and free: binding it again must succeed."""
    port = oc._free_port()

    assert 1024 < port <= 65535
    # The socket is closed by the time _free_port returns, so a second server
    # can take the port. If it could not, the callback server would race the
    # probe socket and fail to bind.
    srv, thread = oc._start_callback_server(port, _STATE)
    _retire(srv, thread)


def test_callback_with_matching_state_is_recorded_and_acked(
    server: tuple[int, threading.Thread],
) -> None:
    """The happy path: code + matching state -> 200, and the loop exits."""
    port, thread = server

    status, body = _get(port, f"/?code=the-code&state={_STATE}")

    assert status == 200
    assert b"you can close this tab" in body
    assert oc._CallbackHandler.result == {"code": "the-code", "state": _STATE}
    # The serve loop's `while not result` condition must now be false, so the
    # thread retires on its own rather than sitting on the socket.
    thread.join(timeout=5)
    assert not thread.is_alive()


def test_mismatched_state_is_recorded_but_reported_as_failure(
    server: tuple[int, threading.Thread],
) -> None:
    """A code echoing the wrong state is a failure, not a success."""
    port, thread = server

    status, body = _get(port, "/?code=the-code&state=not-the-state")

    assert status == 400
    assert b"Authorization failed" in body
    # Still recorded: the caller needs to see what came back to explain it.
    assert oc._CallbackHandler.result["state"] == "not-the-state"
    thread.join(timeout=5)


def test_error_callback_without_a_code_is_reported_as_failure(
    server: tuple[int, threading.Thread],
) -> None:
    """Google reports a declined consent as ``error``, with no ``code``."""
    port, thread = server

    status, body = _get(port, "/?error=access_denied")

    assert status == 400
    assert b"Authorization failed" in body
    assert oc._CallbackHandler.result == {"error": "access_denied"}
    thread.join(timeout=5)


def test_favicon_fetch_is_answered_but_does_not_end_the_flow(
    server: tuple[int, threading.Thread],
) -> None:
    """The regression this module's docstring is about.

    Browsers fetch /favicon.ico against the redirect origin. Treating that as
    the callback retires the server before Google ever redirects, which the
    user sees as a consent timeout.
    """
    port, thread = server

    status, body = _get(port, "/favicon.ico")

    assert status == 204
    assert body == b""
    assert oc._CallbackHandler.result == {}
    # Still serving: the real callback can still arrive and be recorded.
    assert thread.is_alive()

    status, _ = _get(port, f"/?code=late-code&state={_STATE}")
    assert status == 200
    assert oc._CallbackHandler.result["code"] == "late-code"
    thread.join(timeout=5)


def test_serve_loop_gives_up_once_the_consent_deadline_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other loop exit: no callback ever arrives.

    The deadline is 300s of wall clock, so it is moved into the past instead
    of waited out. `server.timeout` bounds handle_request(), which is what
    lets the loop re-test the deadline at all.
    """
    monkeypatch.setattr(oc, "_CONSENT_TIMEOUT_SECONDS", -1)

    port = oc._free_port()
    srv, thread = oc._start_callback_server(port, _STATE)
    try:
        thread.join(timeout=5)
        assert not thread.is_alive()
        assert oc._CallbackHandler.result == {}
    finally:
        _retire(srv, thread)


def test_log_message_is_silenced() -> None:
    """The default handler logs every request to stderr; this one must not."""
    # Called unbound with no request context: the override must accept any
    # arguments and do nothing, which is exactly what makes that safe.
    assert oc._CallbackHandler.log_message(None, '"GET / HTTP/1.1"', 200) is None


def test_starting_the_server_resets_state_from_a_previous_run() -> None:
    """Class attributes outlive one flow, so a stale result must not leak."""
    oc._CallbackHandler.result = {"code": "stale-from-an-earlier-flow"}
    oc._CallbackHandler.expected_state = "stale-state"

    port = oc._free_port()
    srv, thread = oc._start_callback_server(port, _STATE)
    try:
        assert oc._CallbackHandler.result == {}
        assert oc._CallbackHandler.expected_state == _STATE
    finally:
        _retire(srv, thread)


def test_time_is_not_slept_away_by_the_fixture() -> None:
    """Guard against the deadline being computed once at import time.

    If ``deadline`` were module-level rather than per-call, a server started
    later in the session would inherit an already-expired deadline and never
    serve. Starting one now and checking it is alive catches that.
    """
    port = oc._free_port()
    srv, thread = oc._start_callback_server(port, _STATE)
    try:
        time.sleep(0.05)
        assert thread.is_alive()
    finally:
        _retire(srv, thread)
