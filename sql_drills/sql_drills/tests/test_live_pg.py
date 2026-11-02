"""Live checks against the real ``sql-drills-postgres`` container.

Skipped when the container is down. They never stop or recreate it, never
touch the MySQL container's data, and only use their own ``drill_*`` databases.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

import sql_drills as sd
from sql_drills import _engine, _pg_engine, _pg_sandbox
from sql_drills.tests.synthetic import ORDERS, ORDERS_SQL, PIVOT, PIVOT_SQL

if TYPE_CHECKING:
    from collections.abc import Callable

    from sql_drills._dialect import Dialect


def _up(check: Callable[[], bool]) -> bool:
    try:
        return check()
    except _engine.EngineError:
        return False


pytestmark = [
    pytest.mark.docker,
    pytest.mark.skipif(
        not _up(_pg_engine.is_ready), reason="sql-drills-postgres is not running"
    ),
]


def _roles_and_databases() -> tuple[set[str], set[str]]:
    dbs = _pg_engine.run_sql("SELECT datname FROM pg_database", header=False)
    roles = _pg_engine.run_sql("SELECT rolname FROM pg_roles", header=False)
    return set(dbs.stdout.split()), set(roles.stdout.split())


def test_pivot_passes_in_postgres() -> None:
    (res,) = sd.run_problem(PIVOT, PIVOT_SQL, "postgresql")
    assert res.ok, res.error
    assert res.match, res.cell_diff
    assert len(res.columns) == 13


def test_double_quoted_month_fails_in_postgres_but_passes_in_mysql() -> None:
    quoted = PIVOT_SQL.replace("month = 'Jan'", 'month = "Jan"')
    (pg,) = sd.run_problem(PIVOT, quoted, "postgresql")
    assert not pg.ok
    assert 'column "Jan" does not exist' in (pg.error or "")
    if not _up(_engine.is_ready):
        pytest.skip("mysql container is down")
    (my,) = sd.run_problem(PIVOT, quoted, "mysql")
    assert my.match


@pytest.mark.parametrize("dialect", ["postgresql", "mysql"])
def test_orders_pass_in_both_dialects(dialect: Dialect) -> None:
    if dialect == "mysql" and not _up(_engine.is_ready):
        pytest.skip("mysql container is down")
    month = ORDERS_SQL[dialect]
    sql = (
        f"SELECT {month}, region, COUNT(*), "
        "SUM(CASE WHEN status = 'shipped' THEN 1 ELSE 0 END), SUM(total), "
        "SUM(CASE WHEN status = 'shipped' THEN total ELSE 0 END) "
        f"FROM Orders GROUP BY {month}, region"
    )
    (res,) = sd.run_problem(ORDERS, sql, dialect)
    assert res.ok, res.error
    assert res.match, (res.cell_diff, res.rows)


def test_wrong_answer_reports_cells() -> None:
    (res,) = sd.run_problem(ORDERS, "SELECT 1, 2, 3, 4, 5, 6", "postgresql")
    assert res.ok
    assert not res.match
    assert res.cell_diff


def test_runs_are_isolated_and_leave_nothing_behind() -> None:
    before = _roles_and_databases()
    sd.run_problem(ORDERS, "DELETE FROM Orders", "postgresql")
    assert _roles_and_databases() == before


def test_user_sql_cannot_reach_other_sandboxes_or_the_shell() -> None:
    with (
        _pg_sandbox.sandbox("CREATE TABLE t (a INT);") as box,
        _pg_sandbox.sandbox("CREATE TABLE secret (a INT);") as other,
    ):
        assert not box.query(f"DROP DATABASE {other.db}").ok
        assert not box.query("CREATE ROLE intruder").ok
        assert not box.query("COPY t TO PROGRAM 'id'").ok
        assert not box.query(f"DROP ROLE {other.user}").ok
        assert "meta-command" in (box.query("\\! id").error or "")
        peek = _pg_engine.run_sql("SELECT 1", database=other.db, user=box.user)
        assert peek.returncode != 0
        assert other.db in _roles_and_databases()[0]


def test_statement_timeout_stops_runaway_queries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_pg_sandbox, "_STATEMENT_TIMEOUT", "1s")
    with _pg_sandbox.sandbox("") as box:
        done = box.query("SELECT pg_sleep(60)")
    assert not done.ok
    assert "statement timeout" in (done.error or "")


def test_ensure_running_does_not_recreate_a_running_container() -> None:
    def cid() -> str:
        return _engine.docker(
            "inspect", "-f", "{{.Id}}", _pg_engine.CONTAINER
        ).stdout.strip()

    before = cid()
    sd.ensure_running(dialect="postgresql")
    assert cid() == before


def test_builtin_drill_schema_loads_in_postgres() -> None:
    ids = [m.id for m in sd.list_drills()]
    failures = {
        i: r.error
        for i in ids
        if not (r := sd.run(i, "SELECT 1", dialect="postgresql")).ok
    }
    assert not failures
