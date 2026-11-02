"""A throwaway database plus a user that can touch nothing else."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import re
import secrets
from typing import TYPE_CHECKING

from sql_drills import _engine
from sql_drills._model import Table
from sql_drills._normalize import Rows, parse_rows

if TYPE_CHECKING:
    from collections.abc import Iterator

SNAPSHOT_ROWS = 200
_MAX_EXECUTION_MS = 20000
_CODE = re.compile(r"ERROR (\d+)")
_COLUMNS_SQL = (
    "SELECT table_name, column_name FROM information_schema.columns "
    "WHERE table_schema = DATABASE() ORDER BY table_name, ordinal_position;"
)


@dataclass(frozen=True)
class Executed:
    ok: bool
    error: str | None
    code: int | None
    rows: Rows


def _outcome(res: _engine.SqlResult) -> Executed:
    if res.returncode != 0:
        error = res.stderr.strip()
        found = _CODE.search(error)
        return Executed(
            ok=False, error=error, code=int(found[1]) if found else None, rows=[]
        )
    return Executed(ok=True, error=None, code=None, rows=parse_rows(res.stdout))


@dataclass(frozen=True)
class Sandbox:
    db: str
    user: str

    def _run(self, sql: str, *, headers: bool) -> _engine.SqlResult:
        limit = f"SET SESSION max_execution_time={_MAX_EXECUTION_MS}; "
        return _engine.run_sql(limit + sql, self.db, self.user, headers=headers)

    def execute(self, sql: str) -> Executed:
        return _outcome(self._run(sql, headers=False))

    def columns_of(self, sql: str, row_count: int) -> list[str]:
        """Column names of ``sql``'s output; a name may itself span lines."""
        lines = self._run(sql, headers=True).stdout.splitlines()
        head = len(lines) - row_count
        return "\n".join(lines[:head]).split("\t") if head > 0 else []

    def tables(self) -> dict[str, Table]:
        listing = self.execute(_COLUMNS_SQL)
        if not listing.ok:
            msg = f"could not list tables: {listing.error}"
            raise _engine.EngineError(msg)
        columns: dict[str, list[str]] = {}
        for name, column in listing.rows:
            columns.setdefault(name, []).append(column)
        return {name: self._table(name, cols) for name, cols in columns.items()}

    def _table(self, name: str, columns: list[str]) -> Table:
        got = self.execute(f"SELECT * FROM `{name}` LIMIT {SNAPSHOT_ROWS};")
        if not got.ok:
            msg = f"could not read table {name}: {got.error}"
            raise _engine.EngineError(msg)
        return Table(columns, got.rows)


def _provision(db: str, user: str) -> str:
    return (
        f"CREATE DATABASE `{db}`; CREATE USER '{user}'@'localhost'; "
        f"GRANT ALL ON `{db}`.* TO '{user}'@'localhost';"
    )


@contextmanager
def sandbox(schema_sql: str) -> Iterator[Sandbox]:
    suffix = secrets.token_hex(4)
    box = Sandbox(f"drill_{suffix}", f"u_{suffix}")
    try:
        made = _engine.run_sql(_provision(box.db, box.user))
        if made.returncode != 0:
            msg = f"could not create sandbox: {made.stderr.strip()}"
            raise _engine.EngineError(msg)
        loaded = _engine.run_sql(schema_sql, box.db, box.user)
        if loaded.returncode != 0:
            msg = f"drill schema failed: {loaded.stderr.strip()}"
            raise _engine.EngineError(msg)
        yield box
    finally:
        _engine.run_sql(
            f"DROP DATABASE IF EXISTS `{box.db}`; "
            f"DROP USER IF EXISTS '{box.user}'@'localhost';"
        )
