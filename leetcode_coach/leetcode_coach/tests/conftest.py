"""Keep every coach test off the real machine.

No session log under ~/.local, no real `claude` binary, no Ollama on :11434,
no cluster leaking in from the shell, and the gates (`toolbox.load_safe`) on
the small fixture toolbox, so a reviewed edit of the real `toolbox.json` cannot
flip a leak test. `toolbox.load` (cards, clusters) still reads the real file.
Env vars are *set* (to empty or a dead path) rather than deleted, so teardown
also removes the `LEETCODE_COACH_LOG` the REPL exports for its hooks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from leetcode_coach import local_backend, progress, session_log, toolbox
from leetcode_coach.tests._shared import FIXTURE_TOOLBOX

if TYPE_CHECKING:
    from pathlib import Path

DEAD_OLLAMA = "http://127.0.0.1:9"  # the discard port: connection refused at once


@pytest.fixture(autouse=True)
def _hermetic_coach(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(progress.SESSIONS_ENV, str(tmp_path / "sessions"))
    monkeypatch.setenv(progress.CLUSTER_ENV, "")
    monkeypatch.setenv(session_log.LOG_ENV, "")
    monkeypatch.setenv("LEETCODE_CLAUDE_BIN", str(tmp_path / "no-such-claude"))
    monkeypatch.setattr(local_backend, "OLLAMA_URL", DEAD_OLLAMA)
    real = toolbox.load_safe

    def fixture_toolbox(path: Path | None = None) -> toolbox.Toolbox:
        return real(FIXTURE_TOOLBOX if path is None else path)

    monkeypatch.setattr(toolbox, "load_safe", fixture_toolbox)
