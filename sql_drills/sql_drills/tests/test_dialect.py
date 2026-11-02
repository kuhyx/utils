"""Dialect plumbing: names, quoting, types, literals, dispatch."""

from __future__ import annotations

import pytest

from sql_drills import _dialect, _engine, _pg_engine, _pg_sandbox, _sandbox


def test_check_accepts_known_and_rejects_unknown() -> None:
    assert _dialect.check("mysql") == "mysql"
    assert _dialect.check("postgresql") == "postgresql"
    with pytest.raises(_dialect.DialectError, match="oracle"):
        _dialect.check("oracle")


def test_identifier_quoting() -> None:
    assert _dialect.quote_ident("Month", "mysql") == "`Month`"
    assert _dialect.quote_ident("Month", "postgresql") == '"month"'
    assert _dialect.quote_ident('a"b', "postgresql") == '"a""b"'
    assert _dialect.quote_ident("a`b", "mysql") == "`a``b`"


def test_type_mapping_and_fallback() -> None:
    assert _dialect.sql_type("DateTime", "mysql") == "DATETIME"
    assert _dialect.sql_type("datetime", "postgresql") == "TIMESTAMP"
    assert _dialect.sql_type("float", "postgresql") == "DOUBLE PRECISION"
    assert _dialect.sql_type("varchar(20)", "mysql") == "VARCHAR(255)"
    assert _dialect.sql_type("weird", "mysql") == "VARCHAR(255)"


def test_literals() -> None:
    assert _dialect.literal("null", "mysql") == "NULL"
    assert _dialect.literal("NULL", "postgresql") == "NULL"
    assert _dialect.literal("it's", "postgresql") == "'it''s'"
    assert _dialect.literal("a\\b", "mysql") == "'a\\\\b'"
    assert _dialect.literal("a\\b", "postgresql") == "'a\\b'"


def test_to_postgres_translates_the_mysql_flavour() -> None:
    sql = "CREATE TABLE `t` (a DATETIME, b datetime);"
    assert _dialect.to_postgres(sql) == 'CREATE TABLE "t" (a TIMESTAMP, b TIMESTAMP);'


def test_ensure_running_dispatches(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    monkeypatch.setattr(_engine, "ensure_running", lambda *_a: seen.append("my"))
    monkeypatch.setattr(_pg_engine, "ensure_running", lambda *_a: seen.append("pg"))
    _dialect.ensure_running()
    _dialect.ensure_running(dialect="postgresql")
    assert seen == ["my", "pg"]


def test_stop_dispatches(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    monkeypatch.setattr(_engine, "stop", lambda: seen.append("my"))
    monkeypatch.setattr(_pg_engine, "stop", lambda: seen.append("pg"))
    _dialect.stop("mysql")
    _dialect.stop("postgresql")
    assert seen == ["my", "pg"]


def test_sandbox_for_picks_the_module() -> None:
    assert _dialect.sandbox_for("postgresql") is _pg_sandbox.sandbox
    assert _dialect.sandbox_for("mysql") is _sandbox.sandbox
