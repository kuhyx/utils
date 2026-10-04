"""Deterministic coverage-gap lister: a coverage report in, a task list out.

Replaces "spawn an LLM agent to explore where coverage is missing". Reads lcov,
Cobertura XML, JaCoCo XML or coverage.py JSON and lists, per file, exactly
which lines and branches are uncovered. Exit codes are the verdict (0 covered,
1 gaps, 2 unreadable) so CI and hooks adjudicate without a model.
"""
