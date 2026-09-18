"""The resolver side of the network layer: one resolution and one probe per
host per run, and a *temporary* resolver failure that is retried rather than
declaring the registry unreachable.

Written after the gate's own DNS burst (~900 lookups, eight at a time) made
the LAN router's forwarder drop queries for every client on the LAN
(2026-09-18).
"""

from __future__ import annotations

import io
import socket
import threading

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


def test_each_host_is_resolved_once_per_run(monkeypatch):
    """The process-wide resolver is the memoised one, and a repeat (host,
    port, hints) key never reaches the system resolver again; `reset_probes`
    forgets the addresses along with the reachability verdicts."""
    assert socket.getaddrinfo is http.cached_getaddrinfo
    asked: list[tuple] = []

    def system(host, port, *hints):
        asked.append((host, port, *hints))
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.1", port))]

    monkeypatch.setattr(http, "_system_getaddrinfo", system)
    http.reset_probes()
    first = socket.getaddrinfo("repo.example", 443, 0, socket.SOCK_STREAM)
    assert socket.getaddrinfo("repo.example", 443, 0, socket.SOCK_STREAM) is first
    socket.getaddrinfo("repo.example", 80, 0, socket.SOCK_STREAM)
    assert [a[:2] for a in asked] == [("repo.example", 443), ("repo.example", 80)]
    http.reset_probes()
    socket.getaddrinfo("repo.example", 443, 0, socket.SOCK_STREAM)
    assert len(asked) == 3


def test_a_failed_resolution_is_not_remembered(monkeypatch):
    def failing(host, port, *hints):
        raise socket.gaierror(host)

    monkeypatch.setattr(http, "_system_getaddrinfo", failing)
    http.reset_probes()
    for _ in range(2):
        with pytest.raises(socket.gaierror):
            socket.getaddrinfo("gone.example", 443)
    assert not http._addresses


def test_concurrent_workers_share_one_probe_per_host(monkeypatch):
    """Eight threads asking about the same host at once produce one probe."""
    probes: list[str] = []
    gate = threading.Barrier(8)

    def fake_connect(address, timeout):
        probes.append(address[0])
        return io.BytesIO()

    monkeypatch.setattr(socket, "create_connection", fake_connect)

    def worker():
        gate.wait()
        assert http.host_reachable("https://repo.example/x")

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert probes == ["repo.example"]


def test_a_temporary_resolver_failure_is_retried_but_a_permanent_one_is_not(
    monkeypatch,
):
    outcomes = [socket.gaierror(socket.EAI_AGAIN, "try again"), io.BytesIO()]

    def flaky(address, timeout):
        result = outcomes.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(socket, "create_connection", flaky)
    assert http.host_reachable("https://flaky.example/x")
    assert not outcomes

    def permanent(address, timeout):
        raise socket.gaierror(socket.EAI_NONAME, "no such host")

    monkeypatch.setattr(socket, "create_connection", permanent)
    assert not http.host_reachable("https://nonesuch.example/x")

    always_again = [socket.gaierror(socket.EAI_AGAIN, "again")] * http.HTTP_ATTEMPTS

    def exhausted(address, timeout):
        raise always_again.pop(0)

    monkeypatch.setattr(socket, "create_connection", exhausted)
    assert not http.host_reachable("https://never.example/x")
    assert not always_again
