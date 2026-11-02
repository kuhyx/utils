"""``run_problem``: several examples, unknown input, slug/URL resolution."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

import sql_drills as sd
from sql_drills.tests.stubs import GOOD_ROWS, MONTHS, done, install
from sql_drills.tests.synthetic import PIVOT

if TYPE_CHECKING:
    from sql_drills._dialect import Dialect


def test_every_example_runs_in_its_own_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    text = """Example 1:
Input:
T table:
+---+
| a |
+---+
| 1 |
+---+
Output:
+---+
| a |
+---+
| 1 |
+---+
Example 2:
Input:
T table:
+---+
| a |
+---+
| 2 |
+---+
Output:
+---+
| a |
+---+
| 2 |
+---+
"""
    schemas, boxes = install(monkeypatch, done(["a"], [["1"]]))
    first, second = sd.run_problem(text, "x", "mysql")
    assert first.match
    assert not second.match
    assert len(boxes) == 2
    assert sum(s.startswith("CREATE TABLE") for s in schemas) == 2


def test_unknown_dialect_is_rejected_before_anything_runs() -> None:
    with pytest.raises(sd.DialectError):
        sd.run_problem("Example 1:", "x", cast("Dialect", "oracle"))


def test_statement_without_examples_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(sd.NoExamplesError):
        sd.run_problem("nothing to see here, really", "x", "mysql")


@pytest.mark.parametrize(
    "arg",
    [
        "pivot-shipments",
        "https://leetcode.com/problems/pivot-shipments/description/",
    ],
)
def test_slug_and_url_are_fetched(monkeypatch: pytest.MonkeyPatch, arg: str) -> None:
    asked: list[tuple[str, str]] = []

    def fetch(slug: str, dialect: str) -> str:
        asked.append((slug, dialect))
        return PIVOT

    install(monkeypatch, done(["id", *MONTHS], GOOD_ROWS))
    (res,) = sd.run_problem(arg, "x", "postgresql", fetch=fetch)
    assert res.match
    assert asked == [("pivot-shipments", "postgresql")]
