"""Real LeetCode problems, fetched at runtime and never stored in the repo.

Needs the network and the live containers; skipped when either is missing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

import sql_drills as sd
from sql_drills import _engine, _lc_run, _pg_engine

if TYPE_CHECKING:
    from collections.abc import Callable

    from sql_drills._dialect import Dialect

MONTHS = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
]
PIVOT_SQL = (
    "SELECT id, "
    + ", ".join(
        f"SUM(CASE WHEN month = '{m}' THEN revenue END) AS {m}_Revenue" for m in MONTHS
    )
    + " FROM Department GROUP BY id"
)
MONTHLY_SQL = {
    "mysql": "DATE_FORMAT(trans_date, '%Y-%m')",
    "postgresql": "TO_CHAR(trans_date, 'YYYY-MM')",
}


def _ready(check: Callable[[], bool]) -> bool:
    try:
        return check()
    except _engine.EngineError:
        return False


pytestmark = [
    pytest.mark.docker,
    pytest.mark.network,
    pytest.mark.skipif(
        not _ready(_pg_engine.is_ready), reason="sql-drills-postgres is not running"
    ),
]


def _fetch(slug: str, dialect: str) -> str:
    try:
        return _lc_run.default_fetch(slug, dialect)
    except sd.ProblemUnavailableError as exc:
        return pytest.skip(str(exc))


def test_reformat_department_table() -> None:
    text = _fetch("reformat-department-table", "postgresql")
    (res,) = sd.run_problem(text, PIVOT_SQL, "postgresql")
    assert res.match, (res.error, res.cell_diff)
    quoted = PIVOT_SQL.replace("month = 'Jan'", 'month = "Jan"')
    (bad,) = sd.run_problem(text, quoted, "postgresql")
    assert 'column "Jan" does not exist' in (bad.error or "")


@pytest.mark.parametrize("dialect", ["postgresql", "mysql"])
def test_monthly_transactions_i(dialect: Dialect) -> None:
    if dialect == "mysql" and not _ready(_engine.is_ready):
        pytest.skip("mysql container is down")
    month = MONTHLY_SQL[dialect]
    sql = (
        f"SELECT {month}, country, COUNT(*), "
        "SUM(CASE WHEN state = 'approved' THEN 1 ELSE 0 END), SUM(amount), "
        "SUM(CASE WHEN state = 'approved' THEN amount ELSE 0 END) "
        f"FROM Transactions GROUP BY {month}, country"
    )
    (res,) = sd.run_problem(_fetch("monthly-transactions-i", dialect), sql, dialect)
    assert res.match, (res.error, res.cell_diff)
