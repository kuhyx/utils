"""Grade a query run or a typed prediction against a drill's expected rows."""

from __future__ import annotations

from sql_drills import _sandbox, _store
from sql_drills._model import DrillKindError, PredResult, RunResult
from sql_drills._normalize import Rows, clean_grid, compare


def _actual(done: _sandbox.Executed, rec: _store.Record) -> Rows:
    if done.ok:
        return done.rows
    if rec.error_code is not None and done.code is not None:
        return [[f"ERROR {done.code}"]]
    return []


def run(drill_id: str, sql: str) -> RunResult:
    rec = _store.find(drill_id)
    with _sandbox.sandbox(rec.text("schema.sql")) as box:
        done = box.execute(sql)
        shown = done.ok and bool(done.rows)
        columns = box.columns_of(sql, len(done.rows)) if shown else []
    expected = rec.expected_rows()
    actual = _actual(done, rec)
    cmp = compare(expected, actual)
    return RunResult(
        ok=done.ok,
        error=done.error,
        columns=columns,
        rows=actual,
        expected_rows=expected,
        match=cmp.match,
        cell_diff=cmp.cell_diff,
        extra_rows=cmp.extra_rows,
        missing_rows=cmp.missing_rows,
    )


def _typed(grid: Rows, rec: _store.Record) -> Rows:
    rows = clean_grid(grid)
    typed = [cell.casefold() for row in rows for cell in row if cell]
    if rec.error_code is not None and typed == ["error"]:
        return [[f"ERROR {rec.error_code}"]]
    return rows


def check_prediction(drill_id: str, grid: Rows) -> PredResult:
    rec = _store.find(drill_id)
    if rec.meta.kind != "predict":
        msg = f"{drill_id} is a write drill; use run()"
        raise DrillKindError(msg)
    expected = rec.expected_rows()
    cmp = compare(expected, _typed(grid, rec))
    return PredResult(
        match=cmp.match,
        cell_diff=cmp.cell_diff,
        actual_rows=expected,
        error=rec.error_message,
        extra_rows=cmp.extra_rows,
        missing_rows=cmp.missing_rows,
    )
