"""Live checks against the real ``sql-drills-mysql`` container.

Skipped when the container is down. They never stop or recreate it and never
touch any database but their own throwaway ``drill_*`` ones.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

import sql_drills as sd
from sql_drills import _engine, _paths, _sandbox

if TYPE_CHECKING:
    from pathlib import Path

SOLUTIONS = _paths.builtin_dir().parent / "tests" / "solutions"
WRITE_IDS = [m.id for m in sd.list_drills() if m.kind == "write"]
PREDICT_IDS = [m.id for m in sd.list_drills() if m.kind == "predict"]


def _engine_up() -> bool:
    try:
        return _engine.is_ready()
    except _engine.EngineError:
        return False


pytestmark = [
    pytest.mark.docker,
    pytest.mark.skipif(not _engine_up(), reason="sql-drills-mysql is not running"),
]


def _container_id() -> str:
    return _engine._docker("inspect", "-f", "{{.Id}}", _engine.CONTAINER).stdout.strip()


def _databases() -> set[str]:
    res = _engine.run_sql("SHOW DATABASES;")
    return set(res.stdout.split())


@pytest.mark.parametrize("drill_id", WRITE_IDS)
def test_reference_solution_matches_expected(drill_id: str) -> None:
    res = sd.run(drill_id, (SOLUTIONS / f"{drill_id}.sql").read_text())
    assert res.match, (res.error, res.cell_diff)


@pytest.mark.parametrize("drill_id", PREDICT_IDS)
def test_predict_query_reproduces_the_stored_expected(drill_id: str) -> None:
    drill = sd.get_drill(drill_id)
    assert drill.query is not None
    assert sd.run(drill_id, drill.query).match


@pytest.mark.parametrize("drill_id", [m.id for m in sd.list_drills()])
def test_stored_tables_match_the_live_schema(drill_id: str) -> None:
    drill = sd.get_drill(drill_id)
    with _sandbox.sandbox(drill.schema_sql) as box:
        assert box.tables() == drill.tables


def test_wrong_query_reports_cells() -> None:
    res = sd.run(
        "01_pivot_sum", "SELECT region, 1, 2, 3, 4 FROM shop_sales GROUP BY region;"
    )
    assert not res.match
    assert res.cell_diff


def test_syntax_error_is_reported() -> None:
    res = sd.run("01_pivot_sum", "SELECT * FROM;")
    assert not res.ok
    assert "1064" in (res.error or "")


def test_runs_are_isolated_and_leave_nothing_behind() -> None:
    before = _databases()
    sd.run("01_pivot_sum", "DELETE FROM shop_sales;")
    again = sd.run("01_pivot_sum", (SOLUTIONS / "01_pivot_sum.sql").read_text())
    assert again.match
    assert _databases() == before


def test_user_sql_cannot_see_or_drop_other_databases() -> None:
    _engine.run_sql("CREATE DATABASE IF NOT EXISTS drill_canary_guard;")
    try:
        drill = sd.get_drill("01_pivot_sum")
        with _sandbox.sandbox(drill.schema_sql) as box:
            seen = {r[0] for r in box.execute("SHOW DATABASES;").rows}
            assert "drill_canary_guard" not in seen
            assert not box.execute("DROP DATABASE drill_canary_guard;").ok
        assert "drill_canary_guard" in _databases()
    finally:
        _engine.run_sql("DROP DATABASE IF EXISTS drill_canary_guard;")


_ATTACKS = [
    "\\! id",
    "-- c\n\\! mysql -uroot -N -e 'show databases'",
    "SELECT 1;\n\\! id",
    "\ufeff\\! id",
    "SELECT 1 -- \\! id",
    "SELECT 1; \\! id",
    "SELECT 1 \\! id",
    "source /etc/passwd",
]


@pytest.mark.parametrize("attack", _ATTACKS)
def test_client_commands_never_reach_a_shell(attack: str) -> None:
    """Red-team: ``\\!`` used to run a root shell inside the container."""
    drill = sd.get_drill("01_pivot_sum")
    with _sandbox.sandbox(drill.schema_sql) as box:
        done = box.query(attack)
        # Even bypassing the text guard, the client itself must refuse.
        raw = _engine.run_sql(attack, box.db, box.user)
    assert "uid=" not in str(done.rows) + str(done.error)
    assert "uid=" not in raw.stdout
    assert "theory" not in raw.stdout


def test_client_runs_without_a_shell_escape_or_root_os_user() -> None:
    drill = sd.get_drill("01_pivot_sum")
    with _sandbox.sandbox(drill.schema_sql) as box:
        raw = _engine.run_sql("\\! id", box.db, box.user)
    assert raw.returncode != 0
    assert "Unknown command" in raw.stderr
    # The unprivileged OS user is what ``run_sql`` execs as.
    ident = _engine.docker("exec", "-u", "65534", _engine.CONTAINER, "id", "-u")
    assert ident.stdout.strip() == "65534"


def test_learner_cannot_see_theory_or_other_drill_databases() -> None:
    drill = sd.get_drill("01_pivot_sum")
    with _sandbox.sandbox(drill.schema_sql) as box, _sandbox.sandbox("") as other:
        seen = {r[0] for r in box.execute("SHOW DATABASES;").rows}
        assert seen <= {box.db, "information_schema", "performance_schema"}
        assert "theory" not in seen
        assert other.db not in seen
        assert not box.execute("SELECT * FROM theory.anything;").ok
        assert not box.execute("SELECT * FROM mysql.user;").ok


def test_root_is_passwordless_no_more() -> None:
    """Root without the engine's password is refused, locally and over TCP."""
    for host in ("-hlocalhost", "-h127.0.0.1"):
        res = _engine.docker(
            "exec", _engine.CONTAINER, "mysql", "-uroot", host, "-N", "-e", "SELECT 1"
        )
        assert res.returncode != 0
        assert "Access denied" in res.stderr
    assert _engine.run_sql("SELECT 1;").stdout.strip() == "1"


def test_ensure_running_does_not_recreate_a_running_container() -> None:
    before = _container_id()
    sd.ensure_running()
    sd.ensure_running()
    assert _container_id() == before


def test_save_generated_end_to_end(tmp_path: Path) -> None:
    spec = {
        "kind": "write",
        "topic": "group-having",
        "title": "Busy tags",
        "task_md": "Tags used at least twice, most used first (then tag).",
        "schema_sql": (
            "CREATE TABLE uses (id INT PRIMARY KEY, tag VARCHAR(10));"
            "INSERT INTO uses VALUES (1,'a'),(2,'b'),(3,'a'),(4,'c'),(5,'b'),(6,'a');"
        ),
        "reference_sql": (
            "SELECT tag, COUNT(*) FROM uses GROUP BY tag HAVING COUNT(*) >= 2 "
            "ORDER BY COUNT(*) DESC, tag;"
        ),
    }
    drill_id = sd.save_generated(spec)
    assert _paths.data_dir().is_relative_to(tmp_path)
    assert sd.get_drill(drill_id).expected_preview == [["a", "3"], ["b", "2"]]
    assert sd.run(drill_id, str(spec["reference_sql"])).match
    assert not sd.run(drill_id, "SELECT tag, 1 FROM uses;").match
