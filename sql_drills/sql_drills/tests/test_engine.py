"""Docker plumbing with ``subprocess.run`` mocked: no daemon needed."""

from __future__ import annotations

import shutil
import subprocess
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from sql_drills import _engine, _secret

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


def test_docker_missing_binary_is_engine_error() -> None:
    with (
        patch.object(shutil, "which", return_value=None),
        pytest.raises(_engine.EngineError, match="docker"),
    ):
        _engine.container_state()


def test_container_state_running_and_missing() -> None:
    with _run(_cp(0, "running\n")):
        assert _engine.container_state() == "running"
    with _run(_cp(1, "", "No such object")):
        assert _engine.container_state() == "missing"


def test_is_ready_follows_ping_exit_code() -> None:
    with _run(_cp(0)):
        assert _engine.is_ready()
    with _run(_cp(1)):
        assert not _engine.is_ready()


def test_creates_container_on_shared_network_when_it_exists() -> None:
    # inspect(missing), network inspect(ok), run, ping, root login check.
    with _run(_cp(1), _cp(0), _cp(0, "id"), _cp(0), _cp(0)) as run:
        _engine.ensure_running(timeout=5, sleep=_no_sleep)
    argv = run.call_args_list[2].args[0]
    assert argv[:3] == ["docker", "run", "-d"]
    assert "--tmpfs" in argv
    assert _engine.IMAGE in argv
    assert argv[argv.index("--network") + 1] == _engine.NETWORK
    assert argv[argv.index("--network-alias") + 1] == _engine.NETWORK_ALIAS


def test_new_container_gets_a_random_root_password_not_via_argv() -> None:
    with _run(_cp(1), _cp(1), _cp(0, "id"), _cp(0), _cp(0)) as run:
        _engine.ensure_running(timeout=5, sleep=_no_sleep)
    argv = run.call_args_list[2].args[0]
    password = run.call_args_list[2].kwargs["env"]["MYSQL_ROOT_PASSWORD"]
    assert len(password) >= 24
    assert "MYSQL_ALLOW_EMPTY_PASSWORD=yes" not in argv
    assert not any(password in part for part in argv)
    assert "MYSQL_ROOT_PASSWORD" in argv


def test_creates_container_plain_when_network_absent() -> None:
    with _run(_cp(1), _cp(1), _cp(0, "id"), _cp(0), _cp(0)) as run:
        _engine.ensure_running(timeout=5, sleep=_no_sleep)
    assert "--network" not in run.call_args_list[2].args[0]


def test_resumes_exited_container() -> None:
    with _run(_cp(0, "exited\n"), _cp(0), _cp(0), _cp(0)) as run:
        _engine.ensure_running(timeout=5, sleep=_no_sleep)
    assert run.call_args_list[1].args[0][:2] == ["docker", "start"]


def test_running_container_is_never_recreated() -> None:
    with _run(_cp(0, "running\n"), _cp(0), _cp(0)) as run:
        _engine.ensure_running(timeout=5, sleep=_no_sleep)
    verbs = [c.args[0][1] for c in run.call_args_list]
    assert verbs == ["inspect", "exec", "exec"]


def test_legacy_passwordless_root_gets_the_password_live() -> None:
    # inspect, ping, root login refused, passwordless ALTER USER works.
    denied = _cp(1, "", "ERROR 1045 (28000): Access denied")
    with _run(_cp(0, "running\n"), _cp(0), denied, _cp(0)) as run:
        _engine.ensure_running(timeout=5, sleep=_no_sleep)
    alter = run.call_args_list[3]
    password = _secret.root_password()
    assert "env" not in alter.kwargs or alter.kwargs["env"] is None
    assert (
        f"ALTER USER IF EXISTS 'root'@'localhost' IDENTIFIED BY '{password}'"
        in (alter.kwargs["input"])
    )
    assert "'root'@'%'" in alter.kwargs["input"]
    assert not any(password in part for part in alter.args[0])
    assert "-p" not in alter.args[0]


def test_root_rejecting_our_password_is_a_clear_error() -> None:
    denied = _cp(1, "", "ERROR 1045 (28000): Access denied")
    with (
        _run(_cp(0, "running\n"), _cp(0), denied, denied),
        pytest.raises(_engine.EngineError, match="not passwordless"),
    ):
        _engine.ensure_running(timeout=5, sleep=_no_sleep)


def test_create_failure_is_reported() -> None:
    with (
        _run(_cp(1), _cp(1), _cp(125, "", "pull access denied")),
        pytest.raises(_engine.EngineError, match="pull access denied"),
    ):
        _engine.ensure_running(timeout=5, sleep=_no_sleep)


def test_times_out_with_rerun_hint() -> None:
    ticks = iter([0.0, 1.0, 2.0, 99.0, 100.0])
    results = [_cp(0, "running\n")] + [_cp(1)] * 10
    with _run(*results), pytest.raises(_engine.EngineError, match="rerun"):
        _engine.ensure_running(timeout=10, sleep=_no_sleep, clock=lambda: next(ticks))


def test_stop_removes_container() -> None:
    with _run(_cp(0)) as run:
        _engine.stop()
    assert run.call_args.args[0] == ["docker", "rm", "-f", _engine.CONTAINER]


def test_run_sql_defaults_to_root_with_password_from_env_only() -> None:
    with _run(_cp(0, "1\n", "")) as run:
        res = _engine.run_sql("SELECT 1;", database="d1")
    argv = run.call_args.args[0]
    assert argv[:6] == ["docker", "exec", "-i", "-e", "MYSQL_PWD", _engine.CONTAINER]
    assert "-uroot" in argv
    assert "-u" not in argv
    password = _secret.root_password()
    assert run.call_args.kwargs["env"]["MYSQL_PWD"] == password
    assert not any(password in part for part in argv)
    assert "-N" in argv
    assert argv[-1] == "d1"
    assert run.call_args.kwargs["input"] == "SELECT 1;"
    assert (res.returncode, res.stdout) == (0, "1\n")


def test_every_run_is_binary_mode_so_client_commands_cannot_run() -> None:
    with _run(_cp(0), _cp(0)) as run:
        _engine.run_sql("SELECT 1;")
        _engine.run_sql("SELECT 1;", user="u_x")
    assert all("--binary-mode" in c.args[0] for c in run.call_args_list)


def test_learner_run_is_unprivileged_and_never_sees_the_password() -> None:
    with _run(_cp(0)) as run:
        _engine.run_sql("SELECT 1;", user="u_x")
    argv = run.call_args.args[0]
    assert argv[:6] == ["docker", "exec", "-i", "-u", "65534", _engine.CONTAINER]
    assert "MYSQL_PWD" not in argv
    assert run.call_args.kwargs["env"] is None


def test_run_sql_headers_user_and_no_database() -> None:
    with _run(_cp(0)) as run:
        _engine.run_sql("SELECT 1;", user="u_x", headers=True)
    argv = run.call_args.args[0]
    assert "-uu_x" in argv
    assert "-N" not in argv
    assert argv[-1] == "-B"


def test_run_sql_timeout_becomes_engine_error() -> None:
    boom = subprocess.TimeoutExpired(cmd="docker", timeout=1)
    with (
        patch.object(subprocess, "run", side_effect=boom),
        pytest.raises(_engine.EngineError, match="query timed out"),
    ):
        _engine.run_sql("SELECT SLEEP(99);", timeout=1)


def test_run_sql_missing_docker_is_not_relabelled() -> None:
    with (
        patch.object(shutil, "which", return_value=None),
        pytest.raises(_engine.EngineError, match="docker binary"),
    ):
        _engine.run_sql("SELECT 1;")
