"""Per-dialect facts: names, identifier quoting, types, literals, dispatch."""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING, Literal, cast, get_args

from sql_drills import _engine, _pg_engine, _pg_sandbox, _sandbox

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractContextManager

Dialect = Literal["mysql", "postgresql"]
DIALECTS: tuple[str, ...] = get_args(Dialect)

_COMMON = {
    "int": "INT",
    "integer": "INT",
    "bigint": "BIGINT",
    "date": "DATE",
    "decimal": "DECIMAL(20,6)",
    "text": "TEXT",
}
_TYPES: dict[Dialect, dict[str, str]] = {
    "mysql": {**_COMMON, "datetime": "DATETIME", "float": "DOUBLE", "double": "DOUBLE"},
    "postgresql": {
        **_COMMON,
        "datetime": "TIMESTAMP",
        "float": "DOUBLE PRECISION",
        "double": "DOUBLE PRECISION",
    },
}
_FALLBACK_TYPE = "VARCHAR(255)"
_WORD = re.compile(r"\w+")
_DATETIME = re.compile(r"\bDATETIME\b", re.IGNORECASE)


class DialectError(ValueError):
    pass


Box = _sandbox.Sandbox | _pg_sandbox.PgSandbox


def check(dialect: str) -> Dialect:
    if dialect not in DIALECTS:
        msg = f"unknown dialect {dialect!r}; use one of {', '.join(DIALECTS)}"
        raise DialectError(msg)
    return cast("Dialect", dialect)


def quote_ident(name: str, dialect: Dialect) -> str:
    """Quote a name; PostgreSQL gets it lower-cased to match unquoted queries."""
    if dialect == "mysql":
        return "`" + name.replace("`", "``") + "`"
    return '"' + name.lower().replace('"', '""') + '"'


def sql_type(statement_type: str, dialect: Dialect) -> str:
    word = _WORD.match(statement_type.strip())
    key = word[0].lower() if word else ""
    return _TYPES[dialect].get(key, _FALLBACK_TYPE)


def literal(value: str, dialect: Dialect) -> str:
    if value.lower() == "null":
        return "NULL"
    body = value.replace("'", "''")
    if dialect == "mysql":
        body = body.replace("\\", "\\\\")
    return f"'{body}'"


def to_postgres(schema_sql: str) -> str:
    """Best-effort MySQL-flavoured drill schema to PostgreSQL."""
    return _DATETIME.sub("TIMESTAMP", schema_sql.replace("`", '"'))


def ensure_running(
    timeout: float | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    dialect: Dialect = "mysql",
) -> None:
    engine = _pg_engine if check(dialect) == "postgresql" else _engine
    wait = engine.READY_TIMEOUT if timeout is None else timeout
    engine.ensure_running(wait, sleep, clock)


def stop(dialect: Dialect = "mysql") -> None:
    (_pg_engine if check(dialect) == "postgresql" else _engine).stop()


def sandbox_for(dialect: Dialect) -> Callable[[str], AbstractContextManager[Box]]:
    return _pg_sandbox.sandbox if check(dialect) == "postgresql" else _sandbox.sandbox
