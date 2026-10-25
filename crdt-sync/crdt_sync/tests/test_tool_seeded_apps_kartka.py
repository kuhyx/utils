# Copyright (c) 2026 Krzysztof Rudnicki
"""kartka's two desktop sessions are seeded by one ``seed_session`` run.

Split from :mod:`test_tool_seed_session_main` for the 250-line cap.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from crdt_sync._config import credential_store_for
from crdt_sync._credentials import FirebaseCredentials
from crdt_sync.tests.test_tool_seed_session import _CONFIG, _ID_VALUE
from tool import google_id_token as git
from tool import seed_session as ss

_ARGV = ["--client-id", "the-web-client-id", "--client-secret", "the-secret"]
_KARTKA = ("kartka-agent", "kartka-source-eval")


def test_both_kartka_sessions_are_default_apps() -> None:
    """The agent wrapper serves ``~/.config/kartka-agent/`` as
    ``/sync-credentials``; the source evaluator reads
    ``credential_store_for("kartka-source-eval")``."""
    assert set(_KARTKA) <= set(ss.DEFAULT_APPS)


def test_one_run_with_two_app_flags_seeds_both() -> None:
    """``--app`` is repeatable, so one consent tap covers both."""
    with (
        patch.object(ss.FirebaseConfig, "load", return_value=_CONFIG),
        patch.object(git, "fetch_id_token", return_value=_ID_VALUE),
        patch.object(ss, "seed_apps", return_value=list(_KARTKA)) as seeded,
    ):
        code = ss.main([*_ARGV, "--app", _KARTKA[0], "--app", _KARTKA[1]])

    assert code == 0
    assert seeded.call_args.args[2] == _KARTKA


@pytest.mark.parametrize("app", _KARTKA)
def test_the_seed_lands_where_kartka_reads_it(app: str, tmp_path: Path) -> None:
    """``~/.config/<app>/firebase_auth.json``, the path both readers use, in
    the ``{id_token, refresh_token, expires_at}`` shape the wrapper serves."""
    with patch.object(Path, "home", return_value=tmp_path):
        credential_store_for(app).save(
            FirebaseCredentials("fake-id", "fake-refresh", datetime.now(UTC))
        )
    written = tmp_path / ".config" / app / "firebase_auth.json"
    assert set(json.loads(written.read_text())) == {
        "id_token",
        "refresh_token",
        "expires_at",
    }
