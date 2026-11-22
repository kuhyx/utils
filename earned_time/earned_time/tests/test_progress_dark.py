# Copyright (c) 2026 Krzysztof Rudnicki
"""Dark by default: with no progress row every answer is 0.23.0's, bit for bit.

``_golden_0_23_0.json`` pins a digest per (registry, day) of every resolution
over a grid of answers, sick and leisure switches, produced by 0.23.0 itself
(``_grid_dump.py``). The live oracle re-derives it from an installed 0.23.0
when the interpreter has one, in a subprocess so ``sys.path`` stays untouched.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from earned_time.tests._grid_dump import dump

HERE = Path(__file__).parent
GOLDEN = json.loads((HERE / "_golden_0_23_0.json").read_text(encoding="utf-8"))
OLD = "0.23.0"


def _differing(got: dict[str, str]) -> list[str]:
    return sorted(k for k in GOLDEN if got.get(k) != GOLDEN[k]) + sorted(
        set(got) - set(GOLDEN)
    )


def test_no_progress_resolve_equals_the_0_23_0_result_for_every_registry() -> None:
    assert _differing(dump()) == []


def test_an_empty_progress_map_resolves_as_no_map() -> None:
    assert _differing(dump(progress={})) == []
    assert _differing(dump(progress=None)) == []


def test_the_installed_0_23_0_agrees_with_the_pin(tmp_path: Path) -> None:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    probe = subprocess.run(
        [
            sys.executable,
            "-P",
            "-c",
            "import importlib.metadata as m; print(m.version('earned-time'))",
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
        env=env,
    )
    if probe.stdout.strip() != OLD:
        pytest.skip(f"no installed earned-time {OLD} to ask")
    oracle = subprocess.run(
        [sys.executable, "-P", str(HERE / "_grid_dump.py")],
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
        env=env,
    )
    assert json.loads(oracle.stdout) == GOLDEN
