# Copyright (c) 2026 Krzysztof Rudnicki
"""The todo MCP server's desktop session is seeded by ``seed_session``.

Split from :mod:`test_tool_seed_session_main` for the 250-line cap.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from unittest.mock import patch

from crdt_sync._config import credential_store_for
from crdt_sync._credentials import FirebaseCredentials
from tool import seed_session as ss

_APP = "todo-mcp"


def test_todo_mcp_is_a_default_app() -> None:
    """``~/src/todo/mcp`` reads ``~/.config/todo-mcp/firebase_auth.json`` once
    at start; ``--app todo-mcp`` is rejected by argparse unless it is listed."""
    assert _APP in ss.DEFAULT_APPS


def test_the_seed_lands_where_the_todo_mcp_server_reads_it(tmp_path: Path) -> None:
    """The Dart server's ``seedCredentials`` path, in the usual shape."""
    with patch.object(Path, "home", return_value=tmp_path):
        credential_store_for(_APP).save(
            FirebaseCredentials("fake-id", "fake-refresh", datetime.now(UTC))
        )
    written = tmp_path / ".config" / _APP / "firebase_auth.json"
    assert set(json.loads(written.read_text())) == {
        "id_token",
        "refresh_token",
        "expires_at",
    }
