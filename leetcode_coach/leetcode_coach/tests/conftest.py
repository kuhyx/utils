"""Keep every coach test off the real machine.

No session log under ~/.local, no real `claude` binary, no Ollama on :11434,
no OmniRoute on :20128 (a dead port and a scratch key),
no cluster leaking in from the shell, and the gates (`toolbox.load_safe`) on
the small fixture toolbox, so a reviewed edit of the real `toolbox.json` cannot
flip a leak test. `toolbox.load` (cards, clusters) still reads the real file.
Env vars are *set* (to empty or a dead path) rather than deleted, so teardown
also removes the `LEETCODE_COACH_LOG` the REPL exports for its hooks.

The review flow gets the same treatment: its ledger and signing key live in
tmp, the guard CLI seam is a dead path and the sheet dir is empty. After every
test the real review ledger must be exactly as it was: a test that got past
the `review_ledger.LEDGER_PATH` seam fails here, loudly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from leetcode_coach import (
    flagged,
    local_backend,
    omniroute_backend,
    progress,
    review_cli,
    review_ledger,
    session_log,
    toolbox,
)
from leetcode_coach.tests._review_support import REAL_REVIEW_LEDGER, REVIEW_KEY
from leetcode_coach.tests._shared import FIXTURE_TOOLBOX

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

DEAD_OLLAMA = "http://127.0.0.1:9"  # the discard port: connection refused at once


def _stamp(path: Path) -> tuple[int, int] | None:
    """(mtime, size) of `path`, or None while it does not exist."""
    if not path.exists():
        return None
    stat = path.stat()
    return stat.st_mtime_ns, stat.st_size


@pytest.fixture(autouse=True)
def _hermetic_coach(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    real_ledger = _stamp(REAL_REVIEW_LEDGER)
    key_file = tmp_path / "review-hmac.key"
    key_file.write_bytes(REVIEW_KEY + b"\n")
    monkeypatch.setattr(
        review_ledger, "LEDGER_PATH", tmp_path / "coach" / "review_ledger.json"
    )
    monkeypatch.setattr(review_ledger, "KEY_FILE", key_file)
    monkeypatch.setattr(flagged, "GUARD_COMMAND", (str(tmp_path / "no-such-guard"),))
    monkeypatch.setattr(review_cli, "SKELETON_DIR", tmp_path / "skeletons")
    monkeypatch.setenv(progress.SESSIONS_ENV, str(tmp_path / "sessions"))
    monkeypatch.setenv(progress.CLUSTER_ENV, "")
    monkeypatch.setenv(session_log.LOG_ENV, "")
    monkeypatch.setenv("LEETCODE_CLAUDE_BIN", str(tmp_path / "no-such-claude"))
    monkeypatch.setattr(local_backend, "OLLAMA_URL", DEAD_OLLAMA)
    monkeypatch.setenv(omniroute_backend.URL_ENV, DEAD_OLLAMA)
    monkeypatch.setattr(omniroute_backend, "KEY_FILE", tmp_path / "omniroute-key")
    (tmp_path / "omniroute-key").write_text("test-key\n", encoding="utf-8")
    real = toolbox.load_safe

    def fixture_toolbox(path: Path | None = None) -> toolbox.Toolbox:
        return real(FIXTURE_TOOLBOX if path is None else path)

    monkeypatch.setattr(toolbox, "load_safe", fixture_toolbox)
    yield
    assert _stamp(REAL_REVIEW_LEDGER) == real_ledger, (
        f"a test wrote the real review ledger at {REAL_REVIEW_LEDGER}"
    )
