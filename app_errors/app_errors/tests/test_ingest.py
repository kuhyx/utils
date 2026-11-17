"""The ingest: RTDB and local spools in, one board report per app out."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app_errors import cli, ingest, spool
from app_errors.rtdb import RtdbError


class FakeRtdb:
    """An in-memory RTDB: ``get`` honours ``shallow``, ``patch`` deletes on None."""

    def __init__(self, data: dict[str, object]) -> None:
        self.data = data
        self.patches: list[tuple[str, dict[str, object]]] = []
        self.fail = False

    def _at(self, path: str) -> object:
        node: object = self.data
        for part in [p for p in path.split("/") if p]:
            if not isinstance(node, dict) or part not in node:
                return None
            node = node[part]
        return node

    def get(self, path: str, *, shallow: bool = False) -> object:
        if self.fail:
            raise RtdbError("down")
        node = self._at(path)
        if shallow and isinstance(node, dict):
            return dict.fromkeys(node, True)
        return node

    def patch(self, path: str, data: dict[str, object]) -> None:
        self.patches.append((path, data))
        for key, value in data.items():
            parts = [p for p in f"{path}/{key}".split("/") if p]
            node = self.data
            for part in parts[:-1]:
                node = node.setdefault(part, {})  # type: ignore[assignment]
            if value is None:
                node.pop(parts[-1], None)
            else:
                node[parts[-1]] = value


def _crash(at: str) -> dict[str, object]:
    return {
        "repo": "kuhyx/todo",
        "at": at,
        "kind": "uncaught.flutter",
        "error": "Bad state: x",
        "build": 3,
    }


@pytest.fixture
def dirs(tmp_path: Path) -> ingest.Paths:
    return ingest.Paths(
        state=tmp_path / "ingest" / "state.json",
        reports=tmp_path / "app-errors",
        spool=tmp_path / "app-errors-spool",
    )


def test_rtdb_entries_become_reports_and_are_deleted(dirs: ingest.Paths) -> None:
    db = FakeRtdb({
        "todo": {"errors": {"dev1": {"e1": _crash("2026-11-17T10:00:00Z"), "e2": _crash("2026-11-17T10:00:01Z")}}},
        "kartka": {"errors": {"dev": {"k": _crash("2026-11-17T10:00:00Z")}}},
        "other": {"data": 1},
    })  # fmt: skip
    summary = ingest.run(dirs, db)
    assert summary.merged == 2
    report = json.loads((dirs.reports / "todo.json").read_text())
    assert report["errors"][0]["count"] == 2
    assert not (dirs.reports / "kartka.json").exists()  # kartka keeps its own ingest
    assert db.data["todo"] == {"errors": {"dev1": {}}}  # ingested entries are removed from RTDB
    assert "k" in db.data["kartka"]["errors"]["dev"]  # type: ignore[index]


def test_keep_leaves_rtdb_and_still_counts_once(dirs: ingest.Paths) -> None:
    db = FakeRtdb({"todo": {"errors": {"d": {"e": _crash("2026-11-17T10:00:00Z")}}}})
    ingest.run(dirs, db, keep=True)
    ingest.run(dirs, db, keep=True)
    report = json.loads((dirs.reports / "todo.json").read_text())
    assert report["errors"][0]["count"] == 1
    assert db.patches == []


def test_rtdb_down_still_ingests_spool(dirs: ingest.Paths) -> None:
    spool.append(dirs.spool, "tk-app", {"repo": "kuhyx/tk", "at": "2026-11-17T10:00:00Z",
                                         "kind": "uncaught.python", "error": "ValueError: x"})  # fmt: skip
    db = FakeRtdb({})
    db.fail = True
    summary = ingest.run(dirs, db)
    assert summary.merged == 1
    assert summary.rtdb_error == "down"
    assert json.loads((dirs.reports / "tk-app.json").read_text())["errors"][0]["repo"] == "kuhyx/tk"
    assert list(dirs.spool.glob("*")) == []  # the spool is consumed


def test_no_rtdb_at_all(dirs: ingest.Paths) -> None:
    assert ingest.run(dirs, None).merged == 0


def test_spool_bad_lines_and_bad_names_are_skipped(dirs: ingest.Paths) -> None:
    dirs.spool.mkdir(parents=True)
    (dirs.spool / "ok.jsonl").write_text('not json\n{"at": "2026-11-17T10:00:00Z", "kind": "k", "error": "e"}\n[]\n')
    (dirs.spool / "Bad Name.jsonl").write_text('{"at": "x", "kind": "k", "error": "e"}\n')
    assert ingest.run(dirs, None).merged == 1


def test_leftover_claimed_spool_is_ingested(dirs: ingest.Paths) -> None:
    dirs.spool.mkdir(parents=True)
    (dirs.spool / "ok.jsonl.ingesting").write_text('{"at": "2026-11-17T10:00:00Z", "kind": "k", "error": "e"}\n')
    assert ingest.run(dirs, None).merged == 1
    assert list(dirs.spool.glob("*")) == []


def test_rtdb_odd_shapes_are_skipped(dirs: ingest.Paths) -> None:
    db = FakeRtdb(
        {
            "todo": {"errors": {"d": "nope", "e": {"x": "nope"}}},
            "bad key!": {"errors": {}},
        }
    )
    assert ingest.run(dirs, db).merged == 0


def test_cli_ingest_and_resolve(dirs: ingest.Paths, monkeypatch: pytest.MonkeyPatch,
                                capsys: pytest.CaptureFixture[str]) -> None:  # fmt: skip
    monkeypatch.setattr(ingest, "default_paths", lambda: dirs)
    spool.append(dirs.spool, "tk", {"at": "2026-11-17T10:00:00Z", "kind": "k", "error": "e"})
    assert cli.main(["ingest", "--no-rtdb"]) == 0
    sig = json.loads((dirs.reports / "tk.json").read_text())["errors"][0]["signature"]
    assert cli.main(["resolve", "tk", sig]) == 0
    assert json.loads((dirs.reports / "tk.json").read_text())["errors"][0]["open"] is False
    assert cli.main(["resolve", "tk", "missing"]) == 1
    assert "unknown" in capsys.readouterr().err


def test_cli_ingest_rtdb_session_missing(dirs: ingest.Paths, monkeypatch: pytest.MonkeyPatch,
                                         capsys: pytest.CaptureFixture[str]) -> None:  # fmt: skip
    monkeypatch.setattr(ingest, "default_paths", lambda: dirs)

    def no_session(_app: str) -> FakeRtdb:
        raise RtdbError("no session")

    monkeypatch.setattr(cli, "open_rtdb", no_session)
    spool.append(dirs.spool, "tk", {"at": "2026-11-17T10:00:00Z", "kind": "k", "error": "e"})
    assert cli.main(["ingest"]) == 1  # the spool still went in, but RTDB is reported broken
    assert (dirs.reports / "tk.json").exists()
    assert "no session" in capsys.readouterr().err


def test_cli_ingest_with_rtdb(dirs: ingest.Paths, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ingest, "default_paths", lambda: dirs)
    db = FakeRtdb({"todo": {"errors": {"d": {"e": _crash("2026-11-17T10:00:00Z")}}}})
    monkeypatch.setattr(cli, "open_rtdb", lambda _app: db)
    assert cli.main(["ingest", "--keep", "--session", "x"]) == 0
    assert (dirs.reports / "todo.json").exists()


def test_default_paths_follow_xdg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    paths = ingest.default_paths()
    assert paths.reports == tmp_path / "app-errors"
    assert paths.spool == tmp_path / "app-errors-spool"
    assert paths.state == tmp_path / "app-errors-ingest" / "state.json"
