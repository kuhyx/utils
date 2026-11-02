"""Run a query against a LeetCode statement's examples, per dialect."""

from __future__ import annotations

import importlib
from pathlib import Path
import re
import runpy
from types import ModuleType, SimpleNamespace
from typing import TYPE_CHECKING

from sql_drills import _dialect
from sql_drills._lc_problem import Example, Problem, parse_problem, schema_sql
from sql_drills._lcnorm import compare_results
from sql_drills._model import RunResult

if TYPE_CHECKING:
    from collections.abc import Callable

    from sql_drills._dialect import Dialect
    from sql_drills._sandbox import Executed

PACKAGE = "leetcode_coach.fetch_problem"
FETCHER_PATH = Path.home() / ".claude" / "skills" / "leetcode" / "fetch_problem.py"
ELIDED = "..."
_URL = re.compile(r"leetcode\.(?:com|cn)/problems/([a-z0-9-]+)")
_BARE = re.compile(r"[a-z0-9-]+")


class ProblemUnavailableError(RuntimeError):
    pass


def _load_fetcher() -> ModuleType | SimpleNamespace:
    try:
        return importlib.import_module(PACKAGE)
    except ImportError:
        pass
    if not FETCHER_PATH.is_file():
        msg = f"fetch_problem not importable and {FETCHER_PATH} is missing"
        raise ProblemUnavailableError(msg) from None
    return SimpleNamespace(**runpy.run_path(str(FETCHER_PATH)))


def default_fetch(slug: str, dialect: str) -> str:
    """The statement markdown for ``slug`` via the leetcode skill's fetcher."""
    fetcher = _load_fetcher()
    try:
        question = fetcher.fetch(slug)
    except (OSError, ValueError) as exc:
        msg = f"fetching {slug!r} failed: {exc}"
        raise ProblemUnavailableError(msg) from exc
    if question is None or question.get("isPaidOnly") or not question.get("content"):
        msg = f"problem {slug!r} is unknown or premium-only (paste the statement)"
        raise ProblemUnavailableError(msg)
    return str(fetcher.render(question, dialect))


def _slug(text: str) -> str | None:
    one = text.strip()
    if "\n" in one or " " in one:
        return None
    if found := _URL.search(one):
        return found[1]
    return one if _BARE.fullmatch(one) else None


def _positions(actual: list[str], wanted: list[str]) -> list[int]:
    folded = [name.casefold() for name in actual]
    return [folded.index(w.casefold()) for w in wanted if w.casefold() in folded]


def _judge(
    done: Executed, example: Example, *, ordered: bool, dialect: Dialect
) -> RunResult:
    grid = example.expected
    if not done.ok:
        return RunResult(
            ok=False,
            error=done.error,
            columns=[],
            rows=[],
            expected_rows=grid.rows,
            match=False,
        )
    keep = [i for i, name in enumerate(grid.columns) if name != ELIDED]
    wanted = [row for row in grid.rows if any(cell != ELIDED for cell in row)]
    notes: list[str] = []
    exp_rows, act_rows = wanted, done.rows
    if len(keep) != len(grid.columns):
        notes.append(
            "output has elided columns (...): compared the listed ones by name"
        )
        exp_rows = [[row[i] for i in keep] for row in wanted]
        pos = _positions(done.columns, [grid.columns[i] for i in keep])
        act_rows = [[row[i] for i in pos if i < len(row)] for row in done.rows]
    sample = len(wanted) != len(grid.rows)
    if sample:
        notes.append("output has elided rows (...): the listed rows must be present")
    cmp = compare_results(
        exp_rows, act_rows, dialect, ordered=ordered and not sample, subset=sample
    )
    return RunResult(
        ok=True,
        error=None,
        columns=done.columns,
        rows=done.rows,
        expected_rows=grid.rows,
        match=cmp.match,
        cell_diff=cmp.cell_diff,
        extra_rows=cmp.extra_rows,
        missing_rows=cmp.missing_rows,
        note="; ".join(notes) or None,
    )


def run_problem(
    slug_or_statement: str,
    sql: str,
    dialect: Dialect = "mysql",
    *,
    fetch: Callable[[str, str], str] = default_fetch,
) -> list[RunResult]:
    """Run ``sql`` on each statement example in its own fresh sandbox.

    ``slug_or_statement`` is a slug, a problem URL, or the statement text
    (markdown or HTML). Raises ``NoExamplesError`` when no example parses.
    """
    _dialect.check(dialect)
    slug = _slug(slug_or_statement)
    statement = fetch(slug, dialect) if slug else slug_or_statement
    problem = parse_problem(statement)
    return [_run_example(problem, ex, sql, dialect) for ex in problem.examples]


def _run_example(
    problem: Problem, example: Example, sql: str, dialect: Dialect
) -> RunResult:
    with _dialect.sandbox_for(dialect)(schema_sql(problem, example, dialect)) as box:
        done = box.query(sql)
    return _judge(done, example, ordered=problem.ordered, dialect=dialect)
