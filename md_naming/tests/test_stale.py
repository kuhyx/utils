"""stale.py is a retired no-op; old workflow steps must keep passing."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from md_naming import stale

STALE = Path(__file__).resolve().parents[1] / "stale.py"


def test_stub_exits_zero_silently_with_any_args() -> None:
    result = subprocess.run(
        [sys.executable, str(STALE), "--days", "30", "junk", "--nope"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


def test_main_returns_zero() -> None:
    assert stale.main() == 0
