"""MySQL SQL drills: a sandboxed exact-match grading engine."""

from __future__ import annotations

from sql_drills._engine import CONTAINER, IMAGE, EngineError, ensure_running, stop
from sql_drills._generate import DrillSpec, SpecError, save_generated
from sql_drills._grade import check_prediction, run
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
from sql_drills._store import get_drill, list_drills, topics

__all__ = [
    "CONTAINER",
    "IMAGE",
    "TOPICS",
    "CellDiff",
    "Drill",
    "DrillKindError",
    "DrillMeta",
    "DrillSpec",
    "EngineError",
    "PredResult",
    "RunResult",
    "SpecError",
    "Table",
    "UnknownDrillError",
    "check_prediction",
    "data_dir",
    "ensure_running",
    "get_drill",
    "list_drills",
    "run",
    "save_generated",
    "stop",
    "topics",
]
