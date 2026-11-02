"""Per-run PostgreSQL database + restricted role, against a scripted fake psql."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from sql_drills import _engine, _pg_sandbox

if TYPE_CHECKING:
    from sql_drills.tests.conftest import FakePsql


def test_lifecycle_provisions_loads_schema_and_cleans_up(fake_pg: FakePsql) -> None:
    with _pg_sandbox.sandbox("CREATE TABLE t (a INT);") as box:
        assert box.db.startswith("drill_")
        assert box.user.startswith("u_")
    first, second, last = fake_pg.calls[0], fake_pg.calls[1], fake_pg.calls[-1]
    cmds = " ".join(str(c) for c in first["commands"])
    assert first["user"] == "postgres"
    assert f"CREATE ROLE {box.user} LOGIN" in cmds
    assert f"CREATE DATABASE {box.db} OWNER {box.user}" in cmds
    assert "REVOKE ALL ON DATABASE" in cmds
    assert "statement_timeout" in cmds
    assert second["commands"] == ("CREATE TABLE t (a INT);",)
    assert (second["user"], second["database"]) == (box.user, box.db)
    dropped = " ".join(str(c) for c in last["commands"])
    assert f"DROP DATABASE IF EXISTS {box.db} WITH (FORCE)" in dropped
    assert f"DROP ROLE IF EXISTS {box.user}" in dropped


def test_every_sandbox_gets_fresh_names(fake_pg: FakePsql) -> None:
    with _pg_sandbox.sandbox("") as one, _pg_sandbox.sandbox("") as two:
        assert one.db != two.db
        assert one.user != two.user


def _fail_inside() -> None:
    with _pg_sandbox.sandbox(""):
        msg = "boom"
        raise RuntimeError(msg)


def test_cleanup_runs_when_the_body_raises(fake_pg: FakePsql) -> None:
    with pytest.raises(RuntimeError, match="boom"):
        _fail_inside()
    assert "DROP DATABASE" in str(fake_pg.calls[-1]["commands"])


def test_provision_failure_is_engine_error_and_still_cleans(fake_pg: FakePsql) -> None:
    fake_pg.say("CREATE ROLE", stderr="ERROR: exists", rc=3)
    with pytest.raises(_engine.EngineError, match="sandbox"):
        _pg_sandbox.sandbox("").__enter__()
    assert "DROP DATABASE" in str(fake_pg.calls[-1]["commands"])


def test_schema_failure_is_engine_error(fake_pg: FakePsql) -> None:
    fake_pg.say("BAD", stderr="ERROR:  syntax error", rc=3)
    with pytest.raises(_engine.EngineError, match=r"schema failed.*syntax"):
        _pg_sandbox.sandbox("BAD").__enter__()


def test_query_parses_csv_header_rows_and_nulls(fake_pg: FakePsql) -> None:
    fake_pg.say("SELECT", stdout='id,note\n1,"a,b"\n2,\\N\n3,"two\nlines"\n')
    box = _pg_sandbox.PgSandbox("d", "u")
    done = box.query("SELECT 1")
    assert done.ok
    assert done.columns == ["id", "note"]
    assert done.rows == [["1", "a,b"], ["2", "NULL"], ["3", "two\nlines"]]
    assert fake_pg.calls[-1]["header"] is True
    assert (fake_pg.calls[-1]["user"], fake_pg.calls[-1]["database"]) == ("u", "d")


def test_query_with_no_output_has_no_columns(fake_pg: FakePsql) -> None:
    done = _pg_sandbox.PgSandbox("d", "u").query("DELETE FROM t")
    assert done.ok
    assert (done.columns, done.rows) == ([], [])


def test_query_error_is_visible_text(fake_pg: FakePsql) -> None:
    fake_pg.say("Jan", stderr='ERROR:  column "Jan" does not exist\n', rc=3)
    done = _pg_sandbox.PgSandbox("d", "u").query('SELECT "Jan"')
    assert not done.ok
    assert done.error == 'ERROR:  column "Jan" does not exist'
    assert done.code is None
    assert done.rows == []


@pytest.mark.parametrize("sql", ["\\! id", "  \n\\copy t to stdout", "\\c postgres"])
def test_meta_commands_are_refused_without_running(fake_pg: FakePsql, sql: str) -> None:
    done = _pg_sandbox.PgSandbox("d", "u").query(sql)
    assert not done.ok
    assert "meta-command" in (done.error or "")
    assert fake_pg.calls == []
