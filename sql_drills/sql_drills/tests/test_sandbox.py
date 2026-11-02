"""Per-run database + restricted user, against the scripted fake MySQL."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from sql_drills import _engine, _sandbox

if TYPE_CHECKING:
    from sql_drills.tests.conftest import FakeMysql


def test_lifecycle_provisions_loads_schema_and_cleans_up(
    fake_mysql: FakeMysql,
) -> None:
    with _sandbox.sandbox("CREATE TABLE t (a INT);") as box:
        assert box.db.startswith("drill_")
        assert box.user.startswith("u_")
        assert box.db != "theory"
    calls = fake_mysql.calls
    assert "CREATE DATABASE" in str(calls[0]["sql"])
    assert calls[0]["user"] == "root"
    assert calls[1]["sql"] == "CREATE TABLE t (a INT);"
    assert (calls[1]["user"], calls[1]["database"]) == (box.user, box.db)
    assert "DROP DATABASE IF EXISTS" in str(calls[-1]["sql"])
    assert "DROP USER IF EXISTS" in str(calls[-1]["sql"])


def test_every_sandbox_gets_fresh_names(fake_mysql: FakeMysql) -> None:
    with _sandbox.sandbox("") as one, _sandbox.sandbox("") as two:
        assert one.db != two.db
        assert one.user != two.user


def _fail_inside() -> None:
    with _sandbox.sandbox(""):
        msg = "boom"
        raise RuntimeError(msg)


def test_cleanup_runs_when_the_body_raises(fake_mysql: FakeMysql) -> None:
    with pytest.raises(RuntimeError, match="boom"):
        _fail_inside()
    assert "DROP DATABASE" in str(fake_mysql.calls[-1]["sql"])


def test_provision_failure_is_engine_error_and_still_cleans(
    fake_mysql: FakeMysql,
) -> None:
    fake_mysql.say("CREATE DATABASE", stderr="ERROR 1007: exists", rc=1)
    with pytest.raises(_engine.EngineError, match="sandbox"):
        _sandbox.sandbox("").__enter__()
    assert "DROP DATABASE" in str(fake_mysql.calls[-1]["sql"])


def test_schema_failure_is_engine_error(fake_mysql: FakeMysql) -> None:
    fake_mysql.say("BAD SCHEMA", stderr="ERROR 1064 (42000) at line 1: syntax", rc=1)
    with (
        pytest.raises(_engine.EngineError, match=r"drill schema failed.*1064"),
        _sandbox.sandbox("BAD SCHEMA"),
    ):
        pytest.fail("body must not run")
    assert "DROP DATABASE" in str(fake_mysql.calls[-1]["sql"])


def test_execute_parses_rows(fake_mysql: FakeMysql) -> None:
    fake_mysql.say("SELECT 1", stdout="1\tNULL\n")
    with _sandbox.sandbox("") as box:
        out = box.execute("SELECT 1;")
    assert out.ok
    assert out.rows == [["1", "NULL"]]
    last_run = fake_mysql.calls[-2]
    assert last_run["headers"] is False
    assert str(last_run["sql"]).endswith("SELECT 1;")
    assert str(last_run["sql"]).startswith("SET SESSION max_execution_time=")


def test_columns_of_uses_headers_mode(fake_mysql: FakeMysql) -> None:
    fake_mysql.say("SELECT 1", stdout="1\tNULL\n", header="a\tb")
    with _sandbox.sandbox("") as box:
        assert box.columns_of("SELECT 1;", 1) == ["a", "b"]
    assert fake_mysql.calls[-2]["headers"] is True


def test_columns_of_keeps_a_multiline_name_whole(fake_mysql: FakeMysql) -> None:
    fake_mysql.say("SELECT 1", stdout="x\n", header="CONCAT(a,\n  b)")
    with _sandbox.sandbox("") as box:
        assert box.columns_of("SELECT 1;", 1) == ["CONCAT(a,\n  b)"]


def test_columns_of_without_a_header_is_empty(fake_mysql: FakeMysql) -> None:
    fake_mysql.say("SELECT 1", stdout="1\n")
    with _sandbox.sandbox("") as box:
        assert box.columns_of("SELECT 1;", 1) == []


def test_execute_with_no_output(fake_mysql: FakeMysql) -> None:
    with _sandbox.sandbox("") as box:
        out = box.execute("SELECT 1 WHERE 0;")
    assert out.ok
    assert out.rows == []


def test_execute_error_carries_message_and_code(fake_mysql: FakeMysql) -> None:
    fake_mysql.say(
        "nope", stderr="ERROR 1054 (42S22) at line 2: Unknown column\n", rc=1
    )
    with _sandbox.sandbox("") as box:
        out = box.execute("nope")
    assert not out.ok
    assert out.code == 1054
    assert out.error == "ERROR 1054 (42S22) at line 2: Unknown column"
    assert out.rows == []


def test_execute_error_without_code(fake_mysql: FakeMysql) -> None:
    fake_mysql.say("weird", stderr="something odd", rc=1)
    with _sandbox.sandbox("") as box:
        out = box.execute("weird")
    assert (out.ok, out.code, out.error) == (False, None, "something odd")


_COLUMNS = "customers\tid\ncustomers\tname\nempty\tx\n"


def test_tables_snapshot_reads_columns_and_rows(fake_mysql: FakeMysql) -> None:
    fake_mysql.say("information_schema", stdout=_COLUMNS)
    fake_mysql.say("FROM `customers`", stdout="1\tAnn\n2\tBob\n")
    with _sandbox.sandbox("") as box:
        tables = box.tables()
    assert list(tables) == ["customers", "empty"]
    assert tables["customers"].columns == ["id", "name"]
    assert tables["customers"].rows == [["1", "Ann"], ["2", "Bob"]]
    assert "LIMIT" in str(fake_mysql.calls[-3]["sql"])


def test_tables_snapshot_of_empty_table_keeps_columns(fake_mysql: FakeMysql) -> None:
    fake_mysql.say("information_schema", stdout=_COLUMNS)
    with _sandbox.sandbox("") as box:
        empty = box.tables()["empty"]
    assert (empty.columns, empty.rows) == (["x"], [])


def test_tables_snapshot_of_schema_without_tables(fake_mysql: FakeMysql) -> None:
    with _sandbox.sandbox("") as box:
        assert box.tables() == {}


def test_tables_listing_error_is_engine_error(fake_mysql: FakeMysql) -> None:
    fake_mysql.say("information_schema", stderr="ERROR 1: x", rc=1)
    with (
        _sandbox.sandbox("") as box,
        pytest.raises(_engine.EngineError, match="list tables"),
    ):
        box.tables()


def test_tables_row_error_is_engine_error(fake_mysql: FakeMysql) -> None:
    fake_mysql.say("information_schema", stdout=_COLUMNS)
    fake_mysql.say("FROM `customers`", stderr="ERROR 2: y", rc=1)
    with (
        _sandbox.sandbox("") as box,
        pytest.raises(_engine.EngineError, match="customers"),
    ):
        box.tables()


def test_query_returns_rows_and_columns(fake_mysql: FakeMysql) -> None:
    fake_mysql.say("SELECT 1", stdout="1\tNULL\n", header="a\tb")
    with _sandbox.sandbox("") as box:
        done = box.query("SELECT 1;")
    assert done.ok
    assert done.rows == [["1", "NULL"]]
    assert done.columns == ["a", "b"]


def test_query_without_rows_skips_the_header_run(fake_mysql: FakeMysql) -> None:
    with _sandbox.sandbox("") as box:
        done = box.query("SELECT 1 WHERE 0;")
    assert (done.ok, done.rows, done.columns) == (True, [], [])
    assert [c["headers"] for c in fake_mysql.calls].count(True) == 0


def test_query_error_has_no_columns(fake_mysql: FakeMysql) -> None:
    fake_mysql.say("nope", stderr="ERROR 1054 (42S22): bad", rc=1)
    with _sandbox.sandbox("") as box:
        done = box.query("nope")
    assert not done.ok
    assert done.columns == []


RED_TEAM = [
    "\\! id",
    "-- harmless comment\n\\! id",
    "SELECT 1;\n\\! mysql -uroot -e 'show databases'",
    "﻿\\! id",
    "  \t\\system id",
    "SELECT 1;\r\\! id",
    "/* c */\n\n   \\. /etc/passwd",
]


@pytest.mark.parametrize("payload", RED_TEAM)
def test_meta_commands_are_refused_before_reaching_the_client(
    fake_mysql: FakeMysql, payload: str
) -> None:
    with _sandbox.sandbox("") as box:
        before = len(fake_mysql.calls)
        done = box.query(payload)
        also = box.execute(payload)
    assert not done.ok
    assert done.error == "mysql client commands (backslash) are not allowed"
    assert not also.ok
    assert all(payload not in str(c["sql"]) for c in fake_mysql.calls[before:]), (
        "refused SQL must never be sent"
    )


@pytest.mark.parametrize(
    "sql",
    ["SELECT 1;", "SELECT 'a\\\\b';", "SELECT 1 -- \\! id", "SELECT 'x\\n';"],
)
def test_backslash_inside_a_line_is_ordinary_sql(sql: str) -> None:
    assert not _sandbox.has_meta_command(sql)
