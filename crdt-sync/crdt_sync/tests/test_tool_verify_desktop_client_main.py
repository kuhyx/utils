# Copyright (c) 2026 Krzysztof Rudnicki
"""Tests for ``verify_desktop_client.main``: every exit path and its message."""

from __future__ import annotations

import base64
import json
import logging
from unittest.mock import MagicMock, patch

import pytest

from crdt_sync._autherrors import FirebaseAuthError
from crdt_sync._config import ConfigError, FirebaseConfig
from tool import verify_desktop_client as vdc
from tool._token_exchange import TokenError
from tool.client_probe import ProbeResult
from tool.desktop_client import ClientFileError, DesktopClient

_HELD = "stored-client-credential"
_CLIENT = DesktopClient("1-abc.apps.googleusercontent.com", _HELD, "kuhy-syncs")
_CONFIG = FirebaseConfig("api", "https://db", "kuhy-syncs", "uid-1", "me@example.com")
_ID_VALUE = (
    "header."
    + base64.urlsafe_b64encode(json.dumps({"aud": _CLIENT.client_id}).encode())
    .decode()
    .rstrip("=")
    + ".sig"
)


def _run(
    *,
    probe_ok: bool = True,
    token: object = _ID_VALUE,
    sign_in: object = "me@example.com",
    argv: list[str] | None = None,
) -> tuple[int, MagicMock]:
    fetch = MagicMock(
        side_effect=token if isinstance(token, Exception) else None, return_value=token
    )
    signer = MagicMock(
        side_effect=sign_in if isinstance(sign_in, Exception) else None,
        return_value=sign_in,
    )
    with (
        patch.object(vdc.FirebaseConfig, "load", return_value=_CONFIG),
        patch.object(vdc, "load_client", return_value=_CLIENT),
        patch.object(
            vdc, "probe_client", return_value=[ProbeResult(probe_ok, "probed")]
        ),
        patch.object(vdc, "fetch_id_token", fetch),
        patch.object(vdc, "sign_in", signer),
    ):
        return vdc.main(argv or []), fetch


def test_main_passes_and_names_the_uid(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    code, _ = _run()
    assert code == 0
    assert "PASS" in caplog.text
    assert "uid-1" in caplog.text
    assert "me@example.com" in caplog.text


def test_main_stops_before_consent_when_the_probe_fails(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    code, fetch = _run(probe_ok=False)
    assert code == 1
    assert "FAIL" in caplog.text
    fetch.assert_not_called()


def test_main_probe_only_never_opens_consent() -> None:
    code, fetch = _run(argv=["--probe-only"])
    assert code == 0
    fetch.assert_not_called()


def test_main_skip_probe_goes_straight_to_consent() -> None:
    code, fetch = _run(probe_ok=False, argv=["--skip-probe", "--no-browser"])
    assert code == 0
    assert fetch.call_args.kwargs["open_browser"] is False


@pytest.mark.parametrize(
    ("kwargs", "needle"),
    [
        (
            {"token": TokenError("token exchange failed: HTTP 400 invalid_grant")},
            "invalid_grant",
        ),
        (
            {
                "sign_in": FirebaseAuthError(
                    "INVALID_IDP_RESPONSE : id_token audience mismatch"
                )
            },
            "Safelist",
        ),
    ],
)
def test_main_prints_the_exact_error_and_exits_1(
    kwargs: dict[str, object], needle: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    code, _ = _run(**kwargs)
    assert code == 1
    assert "FAIL" in caplog.text
    assert needle in caplog.text


@pytest.mark.parametrize(
    "error", [ConfigError("no config"), ClientFileError("no client")]
)
def test_main_reports_setup_errors(
    error: Exception, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    with patch.object(vdc.FirebaseConfig, "load", side_effect=error):
        assert vdc.main([]) == 1
    assert "FAIL" in caplog.text
