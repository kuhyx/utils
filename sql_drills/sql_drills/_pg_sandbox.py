"""A throwaway PostgreSQL database plus a role that can touch nothing else."""

from __future__ import annotations

from contextlib import contextmanager
import csv
from dataclasses import dataclass
import io
import secrets
from typing import TYPE_CHECKING

from sql_drills import _pg_engine
from sql_drills._engine import EngineError, SqlResult
from sql_drills._sandbox import Executed

if TYPE_CHECKING:
    from collections.abc import Iterator

_STATEMENT_TIMEOUT = "20s"
_NO_META = "psql meta-commands (backslash) are not allowed"


def _outcome(res: SqlResult) -> Executed:
    if res.returncode != 0:
        return Executed(ok=False, error=res.stderr.strip(), code=None, rows=[])
    records = list(csv.reader(io.StringIO(res.stdout)))
    fixed = [
        ["NULL" if cell == _pg_engine.NULL_MARK else cell for cell in rec]
        for rec in records
    ]
    columns, rows = (fixed[0], fixed[1:]) if fixed else ([], [])
    return Executed(ok=True, error=None, code=None, rows=rows, columns=columns)


@dataclass(frozen=True)
class PgSandbox:
    db: str
    user: str

    def query(self, sql: str) -> Executed:
        # ``psql -c '\...'`` runs a backslash command (``\!`` is a shell escape).
        if sql.lstrip().startswith("\\"):
            return Executed(ok=False, error=_NO_META, code=None, rows=[])
        res = _pg_engine.run_sql(sql, database=self.db, user=self.user, header=True)
        return _outcome(res)


def _provision(db: str, user: str) -> tuple[str, ...]:
    return (
        f"CREATE ROLE {user} LOGIN",
        f"CREATE DATABASE {db} OWNER {user}",
        f"REVOKE ALL ON DATABASE {db} FROM PUBLIC",
        f"ALTER ROLE {user} SET statement_timeout = '{_STATEMENT_TIMEOUT}'",
    )


@contextmanager
def sandbox(schema_sql: str) -> Iterator[PgSandbox]:
    suffix = secrets.token_hex(4)
    box = PgSandbox(f"drill_{suffix}", f"u_{suffix}")
    try:
        made = _pg_engine.run_sql(*_provision(box.db, box.user))
        if made.returncode != 0:
            msg = f"could not create sandbox: {made.stderr.strip()}"
            raise EngineError(msg)
        loaded = _pg_engine.run_sql(schema_sql, database=box.db, user=box.user)
        if loaded.returncode != 0:
            msg = f"drill schema failed: {loaded.stderr.strip()}"
            raise EngineError(msg)
        yield box
    finally:
        _pg_engine.run_sql(
            f"DROP DATABASE IF EXISTS {box.db} WITH (FORCE)",
            f"DROP ROLE IF EXISTS {box.user}",
        )
