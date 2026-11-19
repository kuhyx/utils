"""The REST client: URLs, shallow reads, typed errors that never name the token."""

from __future__ import annotations

import email.message
import io
import json
from pathlib import Path
import sys
import types
from typing import cast
import urllib.error
import urllib.request

import pytest

from app_errors import ingest, rtdb, store
from app_errors.rtdb import RestRtdb, RtdbError


class _Res(io.BytesIO):
    def __enter__(self) -> _Res:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def test_get_and_patch_build_urls() -> None:
    seen: list[tuple[str, str, object]] = []

    def opener(req: urllib.request.Request, timeout: float) -> _Res:
        seen.append((req.get_method(), req.full_url, req.data))
        return _Res(b'{"a": true}')

    db = RestRtdb("https://db.example/", lambda: "TOK", opener)
    assert db.get("", shallow=True) == {"a": True}
    db.patch("todo/errors", {"d/e": None})
    assert seen[0][:2] == ("GET", "https://db.example/.json?auth=TOK&shallow=true")
    assert seen[1][0] == "PATCH"
    assert json.loads(cast("bytes", seen[1][2])) == {"d/e": None}


def test_empty_body_is_none() -> None:
    assert RestRtdb("https://x", lambda: "t", lambda req, timeout: _Res(b"")).get("p") is None


@pytest.mark.parametrize(
    "exc",
    [
        urllib.error.HTTPError("u", 401, "no", email.message.Message(), None),
        urllib.error.URLError("down"),
        OSError("x"),
    ],
)
def test_failures_are_typed_and_tokenless(exc: Exception) -> None:
    def opener(req: urllib.request.Request, timeout: float) -> _Res:
        raise exc

    with pytest.raises(RtdbError) as info:
        RestRtdb("https://x", lambda: "SECRET", opener).get("p")
    assert "SECRET" not in str(info.value)


def test_token_failure_is_typed() -> None:
    def boom() -> str:
        raise ValueError("SECRET")

    with pytest.raises(RtdbError, match="token refresh failed"):
        RestRtdb("https://x", boom).get("p")


def _fake_crdt(monkeypatch: pytest.MonkeyPatch, *, session: bool, config_ok: bool = True) -> None:
    mod = types.ModuleType("crdt_sync")

    class Config:
        api_key, database_url = "k", "https://db"

        @staticmethod
        def load() -> Config:
            if not config_ok:
                raise FileNotFoundError("cfg")
            return Config()

    class Provider:
        def __init__(self, *_: object, **__: object) -> None: ...
        def has_session(self) -> bool:
            return session

        def id_token(self) -> str:
            return "t"

    mod.FirebaseConfig = Config  # type: ignore[attr-defined]
    mod.FirebaseTokenProvider = Provider  # type: ignore[attr-defined]
    mod.credential_store_for = lambda name: name  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "crdt_sync", mod)


def test_open_rtdb(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_crdt(monkeypatch, session=True)
    assert isinstance(rtdb.open_rtdb("s"), RestRtdb)
    _fake_crdt(monkeypatch, session=False)
    with pytest.raises(RtdbError, match="no seeded"):
        rtdb.open_rtdb("s")
    _fake_crdt(monkeypatch, session=True, config_ok=False)
    with pytest.raises(RtdbError, match="no Firebase config"):
        rtdb.open_rtdb("s")


class _PatchFails:
    def get(self, path: str, *, shallow: bool = False) -> object:
        if shallow:
            return {"todo": True}
        return {"d": {"e": {"at": "2026-11-17T10:00:00Z", "kind": "k", "error": "x"}}}

    def patch(self, path: str, data: dict[str, object]) -> None:
        raise RtdbError("patch down")


def test_delete_failure_is_reported_after_save(tmp_path: Path) -> None:
    paths = ingest.Paths(tmp_path / "s.json", tmp_path / "r", tmp_path / "sp", tmp_path / "src")
    summary = ingest.run(paths, _PatchFails())
    assert summary == ingest.Summary(1, "patch down")
    assert (tmp_path / "r" / "todo.json").exists()


def test_old_state_version_and_seen_trim(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "s.json"
    path.write_text('{"version": 0}')
    assert store.load(path) == store.empty()
    monkeypatch.setattr(store, "MAX_SEEN", 2)
    state = store.empty()
    for i in range(3):
        store.merge(
            state,
            "a",
            str(i),
            {"at": f"2026-11-17T10:00:0{i}Z", "kind": "k", "error": "x"},
        )
    assert list(state["seen"]) == ["a/1", "a/2"]
