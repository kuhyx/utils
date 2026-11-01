# Copyright (c) 2026 Krzysztof Rudnicki
"""Tests for ``tool/desktop_client``: picking up and validating the client JSON.

The Android client JSON Google offers for download has the same top-level
``installed`` key and project as a Desktop one, so the negative fixture here is
that exact shape: it must be refused, or the wrong client gets stored.
"""

from __future__ import annotations

import json
import os
import stat
from typing import TYPE_CHECKING

import pytest

from tool import desktop_client as dc

if TYPE_CHECKING:
    from pathlib import Path

_CLIENT_ID = "1-abc.apps.googleusercontent.com"
_HELD = "the-desktop-client-credential"


def _installed(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "client_id": _CLIENT_ID,
        "project_id": "kuhy-syncs",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_secret": _HELD,
        "redirect_uris": ["http://localhost"],
    }
    body.update(overrides)
    return body


def _text(**overrides: object) -> str:
    return json.dumps({"installed": _installed(**overrides)})


def _android_text() -> str:
    body = _installed()
    del body["client_secret"]
    del body["redirect_uris"]
    return json.dumps({"installed": body})


def test_valid_desktop_json_parses() -> None:
    client = dc.parse_client_json(_text())
    assert client == dc.DesktopClient(_CLIENT_ID, _HELD, "kuhy-syncs")


@pytest.mark.parametrize(
    ("text", "needle"),
    [
        ("{not json", "not valid JSON"),
        ("[]", "JSON object"),
        (json.dumps({"web": _installed()}), "'installed'"),
        (_text(project_id="other"), "other"),
        (_text(client_id="plain"), "client_id"),
        (_android_text(), "client_secret"),
        (_text(redirect_uris=["https://x.example"]), "http://localhost"),
        (json.dumps({"installed": "nope"}), "'installed'"),
    ],
)
def test_invalid_json_is_refused_with_a_reason(text: str, needle: str) -> None:
    with pytest.raises(dc.ClientFileError, match=needle):
        dc.parse_client_json(text)


def _touch(directory: Path, name: str, text: str, mtime: float) -> Path:
    path = directory / name
    path.write_text(text, encoding="utf-8")
    os.utime(path, (mtime, mtime))
    return path


def _wait(directory: Path, since: float, skipped: list[str]) -> dc.Pickup | None:
    return dc.wait_for_client_json(
        directory, since, attempts=3, pause=lambda: None, report=skipped.append
    )


def test_pickup_ignores_old_files_and_the_android_json(tmp_path: Path) -> None:
    _touch(tmp_path, "client_secret_old.json", _text(), 50.0)
    _touch(tmp_path, "client_secret_android.json", _android_text(), 150.0)
    _touch(tmp_path, "notes.json", _text(), 150.0)
    skipped: list[str] = []
    assert _wait(tmp_path, 100.0, skipped) is None
    assert len(skipped) == 1
    assert "client_secret_android.json" in skipped[0]
    assert "client_secret" in skipped[0]


def test_pickup_takes_the_newest_valid_file(tmp_path: Path) -> None:
    _touch(
        tmp_path,
        "client_secret_a.json",
        _text(client_id="1-a.apps.googleusercontent.com"),
        120.0,
    )
    newest = _touch(tmp_path, "client_secret_b.json", _text(), 130.0)
    found = _wait(tmp_path, 100.0, [])
    assert found is not None
    assert found.path == newest
    assert found.client.client_id == _CLIENT_ID


def test_pickup_waits_for_the_file_to_appear(tmp_path: Path) -> None:
    def pause() -> None:
        _touch(tmp_path, "client_secret_late.json", _text(), 500.0)

    found = dc.wait_for_client_json(tmp_path, 100.0, attempts=3, pause=pause)
    assert found is not None


def test_pickup_pauses_between_attempts_only(tmp_path: Path) -> None:
    pauses: list[int] = []
    result = dc.wait_for_client_json(
        tmp_path, 0.0, attempts=3, pause=lambda: pauses.append(1)
    )
    assert result is None
    assert len(pauses) == 2


def test_store_client_is_private_and_consumes_the_download(tmp_path: Path) -> None:
    source = _touch(tmp_path, "client_secret_x.json", _text(), 1.0)
    dest = tmp_path / "conf" / "desktop_client.json"
    dc.store_client(source, dest)
    assert stat.S_IMODE(dest.stat().st_mode) == 0o600
    assert dc.load_client(dest).client_id == _CLIENT_ID
    assert not source.exists()


def test_store_client_overwrites_and_tightens_an_existing_file(tmp_path: Path) -> None:
    dest = tmp_path / "desktop_client.json"
    dest.write_text("old", encoding="utf-8")
    dest.chmod(0o644)
    dc.store_client(_touch(tmp_path, "client_secret_y.json", _text(), 1.0), dest)
    assert stat.S_IMODE(dest.stat().st_mode) == 0o600
    assert dest.read_text(encoding="utf-8") == _text()


def test_load_client_points_at_the_register_script_when_missing(tmp_path: Path) -> None:
    with pytest.raises(dc.ClientFileError, match=r"register_desktop_client\.sh"):
        dc.load_client(tmp_path / "absent.json")


def test_main_pickup_stores_the_client(tmp_path: Path) -> None:
    _touch(tmp_path, "client_secret_z.json", _text(), 200.0)
    dest = tmp_path / "out" / "desktop_client.json"
    code = dc.main(
        [
            "pickup",
            "--since",
            "100",
            "--timeout",
            "5",
            "--downloads",
            str(tmp_path),
            "--dest",
            str(dest),
        ]
    )
    assert code == 0
    assert dc.load_client(dest).project_id == "kuhy-syncs"


def test_main_pickup_times_out(tmp_path: Path) -> None:
    code = dc.main(
        [
            "pickup",
            "--since",
            "100",
            "--timeout",
            "0",
            "--downloads",
            str(tmp_path),
            "--dest",
            str(tmp_path / "d.json"),
        ]
    )
    assert code == 1
