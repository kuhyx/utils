"""Run a learner's solution against a problem's examples in a bubblewrap sandbox."""

from __future__ import annotations

from code_runner._examples import parse_examples
from code_runner._model import CaseResult, Example, Limits, RunnerError
from code_runner._run import run
from code_runner._starter import Entry, extract_starter, parse_starter

__all__ = [
    "CaseResult",
    "Entry",
    "Example",
    "Limits",
    "RunnerError",
    "extract_starter",
    "parse_examples",
    "parse_starter",
    "run",
]
