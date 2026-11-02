"""Validate and save a generated drill; the reference SQL is never stored."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import TYPE_CHECKING, Any

from sql_drills import _paths, _sandbox
from sql_drills._model import TOPICS, Table

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sql_drills._normalize import Rows

KINDS = ("write", "predict")
PREDICT_HOWTO = (
    "Predict the exact output of the query before running it: one grid row per\n"
    "result row, `NULL` for SQL NULL, no header. If the query fails, type `ERROR`\n"
    "in the first cell."
)
_TEXT_FIELDS = ("title", "task_md", "schema_sql", "reference_sql")


class SpecError(ValueError):
    pass


@dataclass(frozen=True)
class DrillSpec:
    kind: str
    topic: str
    title: str
    task_md: str
    schema_sql: str
    reference_sql: str  # write: the solution; predict: the query to predict
    expect_error: bool = False

    def __post_init__(self) -> None:
        for name in _TEXT_FIELDS:
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                msg = f"{name} must be a non-empty string"
                raise SpecError(msg)
        if self.kind not in KINDS:
            msg = f"kind must be one of {KINDS}"
            raise SpecError(msg)
        if self.topic not in TOPICS:
            msg = f"topic must be one of {TOPICS}"
            raise SpecError(msg)
        if self.expect_error and self.kind != "predict":
            msg = "expect_error only applies to a predict drill"
            raise SpecError(msg)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> DrillSpec:
        missing = [k for k in ("kind", "topic", *_TEXT_FIELDS) if k not in raw]
        if missing:
            msg = f"missing field: {', '.join(missing)}"
            raise SpecError(msg)
        known = ("kind", "topic", "expect_error", *_TEXT_FIELDS)
        fields: dict[str, Any] = {k: raw[k] for k in known if k in raw}
        return cls(**fields)

    def digest(self) -> str:
        blob = json.dumps(self.__dict__, sort_keys=True).encode()
        return hashlib.sha256(blob).hexdigest()[:8]


@dataclass(frozen=True)
class _Reference:
    ok: bool
    code: int | None
    error: str | None
    rows: Rows
    tables: dict[str, Table]


def _run_reference(spec: DrillSpec) -> _Reference:
    with _sandbox.sandbox(spec.schema_sql) as box:
        done = box.execute(spec.reference_sql)
        tables = box.tables()
    return _Reference(done.ok, done.code, done.error, done.rows, tables)


def _validated(spec: DrillSpec) -> _Reference:
    first = _run_reference(spec)
    if not first.ok and not spec.expect_error:
        msg = f"reference SQL failed: {first.error}"
        raise SpecError(msg)
    if first.ok and spec.expect_error:
        msg = "reference SQL did not fail but expect_error is set"
        raise SpecError(msg)
    if not first.ok and first.code is None:
        msg = f"no MySQL error code in: {first.error}"
        raise SpecError(msg)
    if first.ok and not first.rows:
        msg = "reference output is empty"
        raise SpecError(msg)
    again = _run_reference(spec)
    if (again.ok, again.code, again.rows) != (first.ok, first.code, first.rows):
        msg = "reference output is not deterministic"
        raise SpecError(msg)
    return first


def _write(spec: DrillSpec, ref: _Reference, drill_id: str) -> None:
    root = _paths.generated_dir()
    root.mkdir(parents=True, exist_ok=True)
    staging = root / f".tmp-{drill_id}"
    staging.mkdir(exist_ok=True)
    predict = spec.kind == "predict"
    info: dict[str, object] = {"kind": spec.kind, "topic": spec.topic}
    expected = "".join("\t".join(r) + "\n" for r in ref.rows)
    if not ref.ok:
        info |= {"error_code": ref.code, "error_message": ref.error}
        expected = f"ERROR {ref.code}\n"
    task = f"# {spec.title}\n\n{spec.task_md.strip()}\n"
    files = {
        "meta.json": json.dumps(info),
        "DOCS-task.md": task + (f"\n{PREDICT_HOWTO}\n" if predict else ""),
        "schema.sql": spec.schema_sql.strip() + "\n",
        "expected.txt": expected,
        "tables.json": json.dumps({n: t.__dict__ for n, t in ref.tables.items()}),
    }
    if predict:
        files["query.sql"] = spec.reference_sql.strip() + "\n"
    for name, text in files.items():
        (staging / name).write_text(text)
    staging.rename(root / drill_id)


def save_generated(spec: DrillSpec | Mapping[str, object]) -> str:
    """Return the id of the saved drill; raise ``SpecError`` if it is unusable."""
    parsed = spec if isinstance(spec, DrillSpec) else DrillSpec.from_mapping(spec)
    ref = _validated(parsed)
    drill_id = f"g-{parsed.topic}-{parsed.digest()}"
    if not (_paths.generated_dir() / drill_id).exists():
        _write(parsed, ref, drill_id)
    return drill_id
