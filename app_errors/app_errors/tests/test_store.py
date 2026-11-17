"""The merged state: counts, builds, resolve and reopen, and the board report."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from app_errors import store

SCHEMA = json.loads((Path(__file__).parent / "data" / "app-error.schema.json").read_text())


def _crash(at: str, build: int = 7, **extra: object) -> dict[str, object]:
    return {
        "app": "todo",
        "repo": "kuhyx/todo",
        "at": at,
        "kind": "uncaught.flutter",
        "error": "Bad state: boom",
        "stack": ["#0 Home.build (package:todo/home.dart:3:1)"],
        "build": build,
        "version": "1.0.0",
        **extra,
    }


def _report(state: store.State, app: str) -> dict[str, object]:
    report = store.report(state, app)
    jsonschema.Draft202012Validator({**SCHEMA, "$ref": "#/$defs/report"}).validate(report)
    return report


def test_ten_identical_errors_are_one_record_with_count_ten() -> None:
    state = store.empty()
    for i in range(10):
        assert store.merge(state, "todo", f"dev/{i}", _crash(f"2026-11-17T10:00:{i:02d}Z"))
    errors = _report(state, "todo")["errors"]
    assert isinstance(errors, list)
    assert len(errors) == 1
    rec = errors[0]
    assert rec["count"] == 10
    assert rec["first_seen"] == "2026-11-17T10:00:00Z"
    assert rec["last_seen"] == "2026-11-17T10:00:09Z"
    assert rec["build"] == 7
    assert rec["version_name"] == "1.0.0"
    assert rec["open"] is True
    assert rec["repo"] == "kuhyx/todo"


def test_same_entry_id_counts_once() -> None:
    state = store.empty()
    assert store.merge(state, "todo", "dev/a", _crash("2026-11-17T10:00:00Z"))
    assert not store.merge(state, "todo", "dev/a", _crash("2026-11-17T10:00:00Z"))
    assert state["apps"]["todo"][next(iter(state["apps"]["todo"]))]["count"] == 1


def test_newest_build_wins() -> None:
    state = store.empty()
    store.merge(state, "todo", "a", _crash("2026-11-17T10:00:00Z", build=9))
    store.merge(state, "todo", "b", _crash("2026-11-17T11:00:00Z", build=4))
    assert _report(state, "todo")["errors"][0]["build"] == 9  # type: ignore[index]


def test_slow_wait_detail_names_longest_wait() -> None:
    state = store.empty()
    for i, ms in enumerate((1500, 2100)):
        store.merge(
            state,
            "todo",
            f"w{i}",
            {"app": "todo", "repo": "kuhyx/todo", "at": f"2026-11-17T10:00:0{i}Z", "kind": "perf.slow",
             "error": f"list.load waited {ms} ms", "operation": "list.load", "route": "/", "durationMs": ms},
        )  # fmt: skip
    rec = _report(state, "todo")["errors"][0]  # type: ignore[index]
    assert rec["kind"] == "perf.slow"
    assert rec["count"] == 2
    assert "2100 ms" in rec["detail"]
    assert rec["build"] == 0


def test_resolve_closes_and_older_build_does_not_reopen() -> None:
    state = store.empty()
    store.merge(state, "todo", "a", _crash("2026-11-17T10:00:00Z", build=7))
    sig = _report(state, "todo")["errors"][0]["signature"]  # type: ignore[index]
    assert store.resolve(state, "todo", sig, now="2026-11-17T12:00:00Z")
    assert _report(state, "todo")["errors"][0]["open"] is False  # type: ignore[index]
    store.merge(state, "todo", "b", _crash("2026-11-17T13:00:00Z", build=7))
    assert _report(state, "todo")["errors"][0]["open"] is False  # type: ignore[index]
    store.merge(state, "todo", "c", _crash("2026-11-17T14:00:00Z", build=8))
    assert _report(state, "todo")["errors"][0]["open"] is True  # type: ignore[index]


def test_resolve_without_build_reopens_on_later_report() -> None:
    state = store.empty()
    store.merge(state, "tk", "a", _crash("2026-11-17T10:00:00Z", build=0, app="tk"))
    sig = _report(state, "tk")["errors"][0]["signature"]  # type: ignore[index]
    store.resolve(state, "tk", sig, now="2026-11-17T12:00:00Z")
    store.merge(state, "tk", "b", _crash("2026-11-17T11:00:00Z", build=0, app="tk"))
    assert _report(state, "tk")["errors"][0]["open"] is False  # type: ignore[index]
    store.merge(state, "tk", "c", _crash("2026-11-17T13:00:00Z", build=0, app="tk"))
    assert _report(state, "tk")["errors"][0]["open"] is True  # type: ignore[index]


def test_resolve_unknown_signature_is_false() -> None:
    assert not store.resolve(store.empty(), "todo", "nope", now="2026-11-17T12:00:00Z")


def test_missing_repo_defaults_to_kuhyx_app() -> None:
    state = store.empty()
    entry = _crash("2026-11-17T10:00:00Z")
    del entry["repo"]
    store.merge(state, "todo", "a", entry)
    assert _report(state, "todo")["errors"][0]["repo"] == "kuhyx/todo"  # type: ignore[index]


def test_bad_entry_is_skipped() -> None:
    state = store.empty()
    assert not store.merge(state, "todo", "a", {"kind": 3})
    assert not store.merge(state, "todo", "b", "nope")
    assert store.report(state, "todo")["errors"] == []


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    state = store.empty()
    store.merge(state, "todo", "a", _crash("2026-11-17T10:00:00Z"))
    path = tmp_path / "s" / "state.json"
    store.save(path, state)
    assert store.load(path) == state
    path.write_text("{broken")
    assert store.load(path) == store.empty()
    assert store.load(tmp_path / "missing.json") == store.empty()


def test_write_reports_writes_one_file_per_app(tmp_path: Path) -> None:
    state = store.empty()
    store.merge(state, "todo", "a", _crash("2026-11-17T10:00:00Z"))
    store.merge(state, "tk", "a", _crash("2026-11-17T10:00:00Z", app="tk"))
    written = store.write_reports(tmp_path, state)
    assert sorted(p.name for p in written) == ["tk.json", "todo.json"]
    data = json.loads((tmp_path / "todo.json").read_text())
    assert data["version"] == 1
    assert len(data["errors"]) == 1
