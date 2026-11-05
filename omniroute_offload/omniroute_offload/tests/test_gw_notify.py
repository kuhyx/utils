from __future__ import annotations

import subprocess
import urllib.request
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

from omniroute_offload import _gw_api as api
from omniroute_offload import _gw_config as gwc
from omniroute_offload import _gw_notify as note

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def blocked(*_args: Any, **_kwargs: Any) -> Any:
        msg = "real process/network access is blocked in tests"
        raise AssertionError(msg)

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(subprocess, "run", blocked)
    monkeypatch.setattr(subprocess, "Popen", blocked)
    monkeypatch.setattr(urllib.request, "urlopen", blocked)
    monkeypatch.setattr(urllib.request, "build_opener", blocked)


@pytest.fixture
def cfg(tmp_path: Path) -> gwc.Config:
    return gwc.Config.from_env(
        {"HOME": str(tmp_path), "OMNIROUTE_SIGNAL_ENV": str(tmp_path / "sig.env")}
    )


@pytest.fixture
def signal_env(cfg: gwc.Config) -> Path:
    cfg.signal_env.write_text(
        "# comment\n"
        "\n"
        "no equals sign\n"
        "  # indented comment=1\n"
        "PHONE_NUMBER = +48111\n"
        "TRUSTED_INVITERS=+48222, +48333\n"
        "API_BASE_URL=http://127.0.0.1:8080\n"
    )
    return cfg.signal_env


class Sent:
    """Replaces api.call and subprocess.run; records what would go out."""

    def __init__(self) -> None:
        self.posts: list[tuple[str, dict[str, Any], float]] = []
        self.popups: list[list[str]] = []
        self.post_error: Exception | None = None
        self.popup_error: Exception | None = None
        self.popup_rc = 0
        self.next_id = 41

    def call(self, url: str, body: dict[str, Any], *, timeout: float) -> Any:
        if self.post_error:
            raise self.post_error
        self.posts.append((url, body, timeout))
        return {}

    def run(self, argv: list[str], **_kw: Any) -> Any:
        if self.popup_error:
            raise self.popup_error
        self.popups.append(argv)
        self.next_id += 1
        return SimpleNamespace(
            returncode=self.popup_rc, stdout=f"{self.next_id}\n", stderr=" no dbus \n"
        )


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> Sent:
    fake = Sent()
    monkeypatch.setattr(api, "call", fake.call)
    monkeypatch.setattr(subprocess, "run", fake.run)
    return fake


def test_signal_dms_first_trusted_inviter(
    cfg: gwc.Config, signal_env: Path, sent: Sent
) -> None:
    note.signal(cfg, "hello")
    assert sent.posts == [
        (
            "http://127.0.0.1:8080/v2/send",
            {"number": "+48111", "recipients": ["+48222"], "message": "hello"},
            20,
        )
    ]


def test_signal_missing_file_missing_key_and_api_error(
    cfg: gwc.Config, signal_env: Path, sent: Sent
) -> None:
    signal_env.write_text("PHONE_NUMBER=+1\n")
    with pytest.raises(note.NotifyError, match="signal"):
        note.signal(cfg, "x")
    signal_env.unlink()
    with pytest.raises(note.NotifyError, match="signal"):
        note.signal(cfg, "x")
    signal_env.write_text(
        "PHONE_NUMBER=+1\nTRUSTED_INVITERS=+2\nAPI_BASE_URL=http://h\n"
    )
    sent.post_error = api.ApiError("refused")
    with pytest.raises(note.NotifyError, match="refused"):
        note.signal(cfg, "x")


def test_desktop_stores_id_and_replaces_previous(cfg: gwc.Config, sent: Sent) -> None:
    cfg.state_dir.mkdir(parents=True)
    note.desktop(cfg, "first", "low")
    assert "--replace-id=0" in sent.popups[0]
    assert "--urgency=low" in sent.popups[0]
    assert sent.popups[0][-2:] == [f"OmniRoute ({cfg.name})", "first"]
    assert (cfg.state_dir / "notify_id").read_text() == "42"
    note.desktop(cfg, "second", "critical")
    assert "--replace-id=42" in sent.popups[1]
    assert (cfg.state_dir / "notify_id").read_text() == "43"


def test_desktop_failure_raises_and_keeps_id(cfg: gwc.Config, sent: Sent) -> None:
    cfg.state_dir.mkdir(parents=True)
    sent.popup_rc = 1
    with pytest.raises(note.NotifyError, match="no dbus"):
        note.desktop(cfg, "x", "normal")
    assert not (cfg.state_dir / "notify_id").exists()


def test_notify_both_channels_true(
    cfg: gwc.Config,
    signal_env: Path,
    sent: Sent,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert note.notify(cfg, "all good", urgency="low") is True
    assert len(sent.popups) == 1
    assert sent.posts[0][1]["message"] == f"OmniRoute ({cfg.name}): all good"
    assert "notify: all good" in capsys.readouterr().err


@pytest.mark.parametrize(
    "error",
    [
        FileNotFoundError("notify-send"),
        subprocess.TimeoutExpired("notify-send", 10),
    ],
)
def test_desktop_failure_does_not_block_signal(
    cfg: gwc.Config,
    signal_env: Path,
    sent: Sent,
    capsys: pytest.CaptureFixture[str],
    error: Exception,
) -> None:
    sent.popup_error = error
    assert note.notify(cfg, "x") is True
    assert len(sent.posts) == 1
    assert "desktop notify failed" in capsys.readouterr().err


def test_desktop_notify_error_is_logged_too(
    cfg: gwc.Config,
    signal_env: Path,
    sent: Sent,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sent.popup_rc = 1
    assert note.notify(cfg, "x") is True
    assert "desktop notify failed" in capsys.readouterr().err


def test_missing_signal_env_returns_false(
    cfg: gwc.Config, sent: Sent, capsys: pytest.CaptureFixture[str]
) -> None:
    assert note.notify(cfg, "x") is False
    assert len(sent.popups) == 1
    assert "signal notify failed" in capsys.readouterr().err
