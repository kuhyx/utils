"""Keep every coach test off the real machine.

No session log under ~/.local, no real `claude` binary, no Ollama on :11434,
and the fixture toolbox instead of whatever `toolbox.json` holds today
(another session fills it in). Env vars are *set* (to empty or a dead path)
rather than deleted, so teardown also removes the `LEETCODE_COACH_LOG` the
REPL exports for its hooks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from leetcode_coach import local_backend, toolbox
from leetcode_coach.tests._shared import FIXTURE_TOOLBOX

if TYPE_CHECKING:
    from pathlib import Path

DEAD_OLLAMA = "http://127.0.0.1:9"  # the discard port: connection refused at once


@pytest.fixture(autouse=True)
def _hermetic_coach(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEETCODE_COACH_SESSIONS", str(tmp_path / "sessions"))
    monkeypatch.setenv("LEETCODE_COACH_LOG", "")
    monkeypatch.setenv("LEETCODE_CLAUDE_BIN", str(tmp_path / "no-such-claude"))
    monkeypatch.setattr(local_backend, "OLLAMA_URL", DEAD_OLLAMA)
    monkeypatch.setattr(toolbox, "TOOLBOX_PATH", FIXTURE_TOOLBOX)
