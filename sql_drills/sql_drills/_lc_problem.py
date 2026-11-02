"""A LeetCode SQL statement as a runnable spec: schemas, examples, DDL, order."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import TYPE_CHECKING

from sql_drills._dialect import literal, quote_ident, sql_type
from sql_drills._lc_tables import Grid, find_tables, to_text

if TYPE_CHECKING:
    from sql_drills._dialect import Dialect

_TABLE_DEF = re.compile(r"Table:\s*(\w+)", re.IGNORECASE)
_INPUT_NAME = re.compile(r"(\w+) table:?", re.IGNORECASE)
_EXAMPLE = re.compile(r"Example\s*\d+", re.IGNORECASE)
_FENCED = re.compile(r"```.*?```|<pre\b.*?</pre>", re.DOTALL | re.IGNORECASE)
_ORDER = re.compile(
    r"\border(?:ed)?\s+by\b|\bsorted\b|\b(?:ascending|descending)\s+order\b",
    re.IGNORECASE,
)
_INT = re.compile(r"[+-]?\d+")
_DECIMAL = re.compile(r"[+-]?\d+\.\d+")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_DATETIME = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")
_INT_MAX = 2**31 - 1
_SCHEMA_HEADER = ["column name", "type"]


class NoExamplesError(ValueError):
    pass


@dataclass(frozen=True)
class Example:
    inputs: dict[str, Grid]
    expected: Grid


@dataclass(frozen=True)
class Problem:
    schemas: dict[str, list[tuple[str, str]]]
    examples: list[Example]
    ordered: bool


@dataclass
class _Walk:
    schemas: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    examples: list[Example] = field(default_factory=list)
    inputs: dict[str, Grid] = field(default_factory=dict)
    expected: Grid | None = None
    section: str | None = None
    schema_name: str | None = None
    input_name: str | None = None

    def flush(self) -> None:
        if self.inputs and self.expected is not None:
            self.examples.append(Example(self.inputs, self.expected))
        self.inputs, self.expected, self.section = {}, None, None

    def line(self, text: str) -> None:
        if _EXAMPLE.match(text):
            self.flush()
        elif text.startswith("Input:"):
            if self.expected is not None:
                self.flush()
            self.section = "input"
        elif text.startswith("Output:"):
            self.section = "output"
        elif found := _TABLE_DEF.match(text):
            self.schema_name = found[1]
        elif found := _INPUT_NAME.fullmatch(text):
            self.input_name = found[1]

    def table(self, grid: Grid) -> None:
        if [c.lower() for c in grid.columns] == _SCHEMA_HEADER:
            if self.schema_name is not None:
                self.schemas[self.schema_name] = [(r[0], r[1]) for r in grid.rows]
        elif self.section == "input":
            name = self.input_name
            if name is None and len(self.schemas) == 1:
                name = next(iter(self.schemas))
            if name is not None:
                self.inputs[name] = grid
            self.input_name = None
        elif self.section == "output" and self.expected is None:
            self.expected = grid


def is_ordered(statement: str) -> bool:
    """True when the prose before Example 1 asks for a sort order."""
    prose = re.split(r"Example\s*\d+", statement, maxsplit=1, flags=re.IGNORECASE)[0]
    return bool(_ORDER.search(_FENCED.sub("", prose)))


def parse_problem(statement: str) -> Problem:
    """Parse a fetched statement (markdown or HTML); raises ``NoExamplesError``."""
    lines = to_text(statement).splitlines()
    tables = {found.start: found for found in find_tables(lines)}
    walk = _Walk()
    i = 0
    while i < len(lines):
        if i in tables:
            walk.table(tables[i].grid)
            i = tables[i].end
        else:
            walk.line(lines[i].strip())
            i += 1
    walk.flush()
    if not walk.examples:
        msg = "no examples with Input and Output tables found in the statement"
        raise NoExamplesError(msg)
    return Problem(walk.schemas, walk.examples, is_ordered(statement))


def _infer(values: list[str]) -> str:
    cells = [v for v in values if v.lower() != "null"]
    if cells and all(_INT.fullmatch(v) for v in cells):
        return "bigint" if any(abs(int(v)) > _INT_MAX for v in cells) else "int"
    if cells and all(_INT.fullmatch(v) or _DECIMAL.fullmatch(v) for v in cells):
        return "decimal"
    if cells and all(_DATE.fullmatch(v) for v in cells):
        return "date"
    if cells and all(_DATETIME.fullmatch(v) for v in cells):
        return "datetime"
    return "varchar"


def _declared(schemas: dict[str, list[tuple[str, str]]], name: str) -> dict[str, str]:
    for known, columns in schemas.items():
        if known.casefold() == name.casefold():
            return {col.casefold(): typ for col, typ in columns}
    return {}


def _table_sql(
    name: str, grid: Grid, schemas: dict[str, list[tuple[str, str]]], dialect: Dialect
) -> str:
    declared = _declared(schemas, name)
    defs, names = [], []
    for index, column in enumerate(grid.columns):
        kind = declared.get(column.casefold()) or _infer([r[index] for r in grid.rows])
        names.append(quote_ident(column, dialect))
        defs.append(f"{names[-1]} {sql_type(kind, dialect)}")
    table = quote_ident(name, dialect)
    out = f"CREATE TABLE {table} ({', '.join(defs)});"
    if grid.rows:
        rows = ", ".join(
            "(" + ", ".join(literal(c, dialect) for c in row) + ")" for row in grid.rows
        )
        out += f"\nINSERT INTO {table} ({', '.join(names)}) VALUES {rows};"
    return out


def schema_sql(problem: Problem, example: Example, dialect: Dialect) -> str:
    """CREATE + INSERT for every input table of ``example`` in ``dialect``."""
    return "\n".join(
        _table_sql(name, grid, problem.schemas, dialect)
        for name, grid in example.inputs.items()
    )
