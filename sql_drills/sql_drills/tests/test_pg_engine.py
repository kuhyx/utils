"""PostgreSQL container plumbing with ``subprocess.run`` mocked."""

from __future__ import annotations

import shutil
import subprocess
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from sql_drills import _engine, _pg_engine

if TYPE_CHECKING:
    from collections.abc import Iterator
    from contextlib import AbstractContextManager


@pytest.fixture(autouse=True)
def _fake_docker_on_path() -> Iterator[None]:
    with patch.object(shutil, "which", return_value="docker"):
        yield


def _cp(rc: int = 0, out: str = "", err: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], rc, out, err)


def _run(
    *results: subprocess.CompletedProcess[str],
) -> AbstractContextManager[MagicMock]:
    return patch.object(subprocess, "run", side_effect=list(results))


def _no_sleep(_s: float) -> None:
    return None


def test_pin_is_exact_and_distinct_from_mysql() -> None:
    assert _pg_engine.IMAGE == "postgres:18.6"
    assert _pg_engine.CONTAINER == "sql-drills-postgres"
    assert _pg_engine.CONTAINER != _engine.CONTAINER


def test_container_state_running_and_missing() -> None:
    with _run(_cp(0, "running\n")):
        assert _pg_engine.container_state() == "running"
    with _run(_cp(1, "", "No such object")):
        assert _pg_engine.container_state() == "missing"


def test_is_ready_uses_tcp_so_the_init_server_does_not_count() -> None:
    with _run(_cp(0)) as run:
        assert _pg_engine.is_ready()
    assert "-h127.0.0.1" in run.call_args.args[0]
    with _run(_cp(2)):
        assert not _pg_engine.is_ready()


def test_creates_isolated_tmpfs_container() -> None:
    with _run(_cp(1), _cp(0, "id"), _cp(0)) as run:
        _pg_engine.ensure_running(timeout=5, sleep=_no_sleep)
    argv = run.call_args_list[1].args[0]
    assert argv[:3] == ["docker", "run", "-d"]
    assert argv[argv.index("--name") + 1] == "sql-drills-postgres"
    assert "--tmpfs" in argv
    assert "--network" not in argv
    assert "-p" not in argv
    assert argv[-1] == _pg_engine.IMAGE


def test_resumes_exited_and_never_recreates_running() -> None:
    with _run(_cp(0, "exited\n"), _cp(0), _cp(0)) as run:
        _pg_engine.ensure_running(timeout=5, sleep=_no_sleep)
    assert run.call_args_list[1].args[0][:2] == ["docker", "start"]
    with _run(_cp(0, "running\n"), _cp(0)) as run:
        _pg_engine.ensure_running(timeout=5, sleep=_no_sleep)
    assert [c.args[0][1] for c in run.call_args_list] == ["inspect", "exec"]


def test_create_failure_is_reported() -> None:
    with (
        _run(_cp(1), _cp(125, "", "pull access denied")),
        pytest.raises(_engine.EngineError, match="pull access denied"),
    ):
        _pg_engine.ensure_running(timeout=5, sleep=_no_sleep)


def test_times_out_with_rerun_hint() -> None:
    ticks = iter([0.0, 1.0, 99.0, 100.0])
    results = [_cp(0, "running\n")] + [_cp(1)] * 10
    with _run(*results), pytest.raises(_engine.EngineError, match=r"PostgreSQL.*rerun"):
        _pg_engine.ensure_running(
            timeout=10, sleep=_no_sleep, clock=lambda: next(ticks)
        )


def test_stop_removes_only_the_postgres_container() -> None:
    with _run(_cp(0)) as run:
        _pg_engine.stop()
    assert run.call_args.args[0] == ["docker", "rm", "-f", "sql-drills-postgres"]


def test_run_sql_argv_without_header() -> None:
    with _run(_cp(0, "1\n")) as run:
        res = _pg_engine.run_sql("SELECT 1;", database="d1", user="u_x")
    argv = run.call_args.args[0]
    assert argv[:4] == ["docker", "exec", "-i", "sql-drills-postgres"]
    assert argv[4] == "psql"
    assert "--csv" in argv
    assert "-t" in argv
    assert argv[argv.index("-U") + 1] == "u_x"
    assert argv[argv.index("-d") + 1] == "d1"
    assert "ON_ERROR_STOP=1" in argv
    assert argv[-2:] == ["-c", "SELECT 1;"]
    assert run.call_args.kwargs["input"] is None
    assert (res.returncode, res.stdout) == (0, "1\n")


def test_run_sql_header_mode_and_many_commands() -> None:
    with _run(_cp(0)) as run:
        _pg_engine.run_sql("A;", "B;", header=True)
    argv = run.call_args.args[0]
    assert "-t" not in argv
    assert argv[-4:] == ["-c", "A;", "-c", "B;"]
    assert argv[argv.index("-U") + 1] == "postgres"
    assert argv[argv.index("-d") + 1] == "postgres"


def test_run_sql_timeout_becomes_engine_error() -> None:
    boom = subprocess.TimeoutExpired(cmd="docker", timeout=1)
    with (
        patch.object(subprocess, "run", side_effect=boom),
        pytest.raises(_engine.EngineError, match="query timed out"),
    ):
        _pg_engine.run_sql("SELECT pg_sleep(99);", timeout=1)


def test_run_sql_missing_docker_is_not_relabelled() -> None:
    with (
        patch.object(shutil, "which", return_value=None),
        pytest.raises(_engine.EngineError, match="docker binary"),
    ):
        _pg_engine.run_sql("SELECT 1;")
