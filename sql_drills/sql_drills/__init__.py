"""SQL drills (MySQL, PostgreSQL): sandboxed grading and LeetCode examples."""

from __future__ import annotations

from sql_drills._dialect import DIALECTS, Dialect, DialectError, ensure_running, stop
from sql_drills._engine import CONTAINER, IMAGE, EngineError
from sql_drills._generate import DrillSpec, SpecError, save_generated
from sql_drills._grade import check_prediction, run
from sql_drills._lc_problem import Example, NoExamplesError, Problem, parse_problem
from sql_drills._lc_run import ProblemUnavailableError, run_problem
from sql_drills._model import (
    TOPICS,
    CellDiff,
    Drill,
    DrillKindError,
    DrillMeta,
    PredResult,
    RunResult,
    Table,
    UnknownDrillError,
)
from sql_drills._paths import data_dir
from sql_drills._pg_engine import CONTAINER as PG_CONTAINER
from sql_drills._pg_engine import IMAGE as PG_IMAGE
from sql_drills._store import get_drill, list_drills, topics

__all__ = [
    "CONTAINER",
    "DIALECTS",
    "IMAGE",
    "PG_CONTAINER",
    "PG_IMAGE",
    "TOPICS",
    "CellDiff",
    "Dialect",
    "DialectError",
    "Drill",
    "DrillKindError",
    "DrillMeta",
    "DrillSpec",
    "EngineError",
    "Example",
    "NoExamplesError",
    "PredResult",
    "Problem",
    "ProblemUnavailableError",
    "RunResult",
    "SpecError",
    "Table",
    "UnknownDrillError",
    "check_prediction",
    "data_dir",
    "ensure_running",
    "get_drill",
    "list_drills",
    "parse_problem",
    "run",
    "run_problem",
    "save_generated",
    "stop",
    "topics",
]
