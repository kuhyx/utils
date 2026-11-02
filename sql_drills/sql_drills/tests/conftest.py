"""Shared fixtures: redirect the data dir, and a scripted fake MySQL."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pytest

from sql_drills import _engine

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def _redirect_data(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Generated drills never land in the real ``~/.local/share/sql_drills``."""
    monkeypatch.setenv("SQL_DRILLS_DATA", str(tmp_path / "data"))


@dataclass
class FakeMysql:
    """Stands in for ``_engine.run_sql``; answers by substring of the SQL."""

    replies: dict[str, _engine.SqlResult] = field(default_factory=dict)
    heads: dict[str, str] = field(default_factory=dict)
    sequences: dict[str, list[_engine.SqlResult]] = field(default_factory=dict)
    calls: list[dict[str, object]] = field(default_factory=list)

    def say(
        self,
        needle: str,
        stdout: str = "",
        stderr: str = "",
        rc: int = 0,
        header: str | None = None,
    ) -> None:
        """Answer SQL containing ``needle``; ``header`` shows in headers mode."""
        self.replies[needle] = _engine.SqlResult(rc, stdout, stderr)
        if header is not None:
            self.heads[needle] = header

    def say_seq(self, needle: str, outs: list[str]) -> None:
        """Answer ``needle`` with successive stdout values, one per call."""
        self.sequences[needle] = [_engine.SqlResult(0, out, "") for out in outs]

    def __call__(
        self,
        sql: str,
        database: str | None = None,
        user: str = "root",
        *,
        headers: bool = False,
        timeout: float = 30.0,
    ) -> _engine.SqlResult:
        self.calls.append(
            {"sql": sql, "database": database, "user": user, "headers": headers}
        )
        for needle, queue in self.sequences.items():
            if needle in sql and queue:
                return queue.pop(0)
        for needle, reply in self.replies.items():
            if needle in sql:
                head = self.heads.get(needle)
                if headers and head is not None:
                    return _engine.SqlResult(
                        reply.returncode, f"{head}\n{reply.stdout}", ""
                    )
                return reply
        return _engine.SqlResult(0, "", "")


@pytest.fixture
def fake_mysql(monkeypatch: pytest.MonkeyPatch) -> FakeMysql:
    """Replace the engine's ``run_sql`` with a scripted fake (no Docker)."""
    fake = FakeMysql()
    monkeypatch.setattr(_engine, "run_sql", fake)
    return fake
