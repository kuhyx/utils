"""The network layer: one probe per host, and failures that never raise out.

The gate is called from a pre-commit hook the user may not bypass, so every
transport error has to arrive as `Offline` -- something the caller can answer
with a cached value -- rather than as a traceback.
"""

from __future__ import annotations

import io
import socket
from urllib.error import HTTPError, URLError

import pytest

from dep_freshness.registries import http


@pytest.fixture(autouse=True)
def real_probe(monkeypatch):
    """Undo conftest's blanket `host_reachable` stub for this module."""
    monkeypatch.undo()
    http.reset_probes()
    http.force_offline(False)
    yield
    http.reset_probes()
    http.force_offline(False)


def test_the_probe_is_made_once_per_host(monkeypatch):
    calls = []

    def fake_connect(address, timeout=None):
        calls.append(address)
        return io.BytesIO()

    monkeypatch.setattr(socket, "create_connection", fake_connect)
    assert http.host_reachable("https://pub.dev/a")
    assert http.host_reachable("https://pub.dev/b")
    assert len(calls) == 1
    assert calls[0] == ("pub.dev", 443)


def test_an_unreachable_host_is_remembered_as_unreachable(monkeypatch):
    monkeypatch.setattr(socket, "create_connection", _refuse)
    assert not http.host_reachable("https://nowhere.invalid/x")


def test_force_offline_short_circuits_even_a_known_good_host(monkeypatch):
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: io.BytesIO())
    assert http.host_reachable("https://pub.dev/a")
    http.force_offline(True)
    assert not http.host_reachable("https://pub.dev/a")


def test_get_json_raises_offline_when_the_host_is_down(monkeypatch):
    monkeypatch.setattr(socket, "create_connection", _refuse)
    with pytest.raises(http.Offline):
        http.get_json("https://nowhere.invalid/x")


def test_a_404_means_the_package_does_not_exist(monkeypatch):
    _reachable(monkeypatch)
    monkeypatch.setattr(http, "urlopen", _raiser(
        HTTPError("u", 404, "Not Found", {}, None)))
    assert http.get_json("https://pub.dev/api/packages/nope") is None


def test_a_500_degrades_to_offline_rather_than_a_missing_package(monkeypatch):
    _reachable(monkeypatch)
    monkeypatch.setattr(http, "urlopen", _raiser(
        HTTPError("u", 500, "Boom", {}, None)))
    with pytest.raises(http.Offline):
        http.get_json("https://pub.dev/api/packages/x")


def test_a_transport_error_degrades_to_offline(monkeypatch):
    _reachable(monkeypatch)
    monkeypatch.setattr(http, "urlopen", _raiser(URLError("reset")))
    with pytest.raises(http.Offline):
        http.get_json("https://pub.dev/api/packages/x")


def test_a_successful_body_is_decoded(monkeypatch):
    _reachable(monkeypatch)
    monkeypatch.setattr(http, "urlopen", lambda *a, **k: _Response(b'{"a": 1}'))
    assert http.get_json("https://pub.dev/x", accept="application/json") == {"a": 1}


def test_undecodable_json_degrades_to_offline(monkeypatch):
    _reachable(monkeypatch)
    monkeypatch.setattr(http, "urlopen", lambda *a, **k: _Response(b"not json"))
    with pytest.raises(http.Offline):
        http.get_json("https://pub.dev/x")


def _refuse(*_args, **_kwargs):
    raise OSError("connection refused")


def _reachable(monkeypatch):
    monkeypatch.setattr(http, "host_reachable", lambda _url: True)


def _raiser(error):
    def raise_it(*_args, **_kwargs):
        raise error
    return raise_it


class _Response:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False
