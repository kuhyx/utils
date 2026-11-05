"""Tell kuhy: one replaceable desktop popup plus a Signal DM from the bot account."""

from __future__ import annotations

import subprocess
import sys
from typing import TYPE_CHECKING

from omniroute_offload import _gw_api as api

if TYPE_CHECKING:
    from pathlib import Path

    from omniroute_offload._gw_config import Config


class NotifyError(RuntimeError):
    """A channel could not be used."""


def _read_env(path: Path) -> dict[str, str]:
    pairs = (
        line.split("=", 1)
        for line in path.read_text().splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    )
    return {k.strip(): v.strip() for k, v in pairs}


def signal(cfg: Config, text: str) -> None:
    """DM the first TRUSTED_INVITERS number from the signal-bot account."""
    try:
        env = _read_env(cfg.signal_env)
        owner = env["TRUSTED_INVITERS"].split(",")[0].strip()
        body = {"number": env["PHONE_NUMBER"], "recipients": [owner], "message": text}
        api.call(f"{env['API_BASE_URL']}/v2/send", body, timeout=20)
    except (OSError, KeyError, api.ApiError) as err:
        msg = f"signal: {err!r}"
        raise NotifyError(msg) from err


def desktop(cfg: Config, text: str, urgency: str) -> None:
    """notify-send, replacing this instance's previous popup instead of stacking."""
    id_file = cfg.state_dir / "notify_id"
    previous = id_file.read_text().strip() if id_file.exists() else "0"
    proc = subprocess.run(
        [
            "notify-send", "--app-name=omniroute", "--print-id",
            f"--replace-id={previous}", f"--urgency={urgency}",
            f"OmniRoute ({cfg.name})", text,
        ],
        capture_output=True, text=True, check=False, timeout=10,
    )  # fmt: skip
    if proc.returncode:
        msg = f"notify-send: {proc.stderr.strip()}"
        raise NotifyError(msg)
    id_file.write_text(proc.stdout.strip())


def notify(cfg: Config, text: str, *, urgency: str = "normal") -> bool:
    """Send on both channels, log each failure; True only when Signal got it."""
    print(f"notify: {text}", file=sys.stderr)
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    try:
        desktop(cfg, text, urgency)
    except (NotifyError, OSError, subprocess.SubprocessError) as err:
        print(f"desktop notify failed: {err}", file=sys.stderr)
    try:
        signal(cfg, f"OmniRoute ({cfg.name}): {text}")
    except NotifyError as err:
        print(f"signal notify failed: {err}", file=sys.stderr)
        return False
    return True
