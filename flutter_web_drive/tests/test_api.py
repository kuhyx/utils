"""Driver: unit lifecycle, state file, and each verb's attach-act-detach."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from flutter_web_drive import browser
from flutter_web_drive.api import Driver
from flutter_web_drive.errors import EXIT_BROWSER, EXIT_UNSAFE, EXIT_USAGE, DriveError
from flutter_web_drive.tests.fakes import (
    HEADLESS,
    PAGE_TARGETS,
    FakeClock,
    FakePage,
    node,
)


class Rig:
    """A fake systemd + chromium: systemd-run makes the CDP port answer."""

    def __init__(
        self, tmp_path: Path, *, up: bool = False, active: bool = False
    ) -> None:
        self.page = FakePage(nodes=[node(5, "Browse")])
        self.up = up
        self.active = active
        self.cmds: list[list[str]] = []
        self.run_rc = 0
        self.comes_up = True
        self.root = tmp_path / "e2e"

    def fetch(self, port: int, path: str) -> Any:
        if not self.up:
            raise OSError("refused")
        return HEADLESS if path == "/json/version" else PAGE_TARGETS

    def runner(self, cmd: list[str]) -> int:
        self.cmds.append(cmd)
        if cmd[:3] == ["systemctl", "--user", "is-active"]:
            return 0 if self.active else 3
        if cmd[0] == "systemd-run":
            self.up = self.comes_up
            return self.run_rc
        return 0

    def driver(self, **kw: Any) -> Driver:
        return Driver(
            "kartka",
            root=self.root,
            fetch=self.fetch,
            create=lambda url: self.page.ws(),
            runner=self.runner,
            clock=FakeClock(),
            **kw,
        )

    def state(self) -> dict[str, Any]:
        return json.loads((self.root / "kartka" / "state.json").read_text())


def _start(rig: Rig, tmp_path: Path) -> str:
    return rig.driver().start(
        "http://127.0.0.1:1/", tmp_path / "prof", 9341, size="800x600"
    )


def test_start_launches_unit_saves_state_and_enables_semantics(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    out = _start(rig, tmp_path)
    assert (
        out == "started fwd-kartka: http://127.0.0.1:1/ on CDP 9341, viewport 1400x900"
    )
    run = next(c for c in rig.cmds if c[0] == "systemd-run")
    assert "--unit=fwd-kartka" in run
    assert "UnsetEnvironment=DISPLAY WAYLAND_DISPLAY" in run
    assert "--headless=new" in run
    assert "--window-size=800,600" in run
    assert ["systemctl", "--user", "reset-failed", "fwd-kartka"] in rig.cmds
    assert (tmp_path / "prof").is_dir()
    assert rig.state()["cdp_port"] == 9341


def test_start_refuses_a_port_someone_else_owns(tmp_path: Path) -> None:
    rig = Rig(tmp_path, up=True)
    with pytest.raises(DriveError) as err:
        _start(rig, tmp_path)
    assert err.value.code == EXIT_UNSAFE
    assert not any(c[0] == "systemd-run" for c in rig.cmds)


def test_start_reuses_a_running_unit_and_navigates_if_needed(tmp_path: Path) -> None:
    rig = Rig(tmp_path, up=True, active=True)
    rig.page.href = "about:blank"
    rig.page.evals = {}
    out = _start(rig, tmp_path)
    assert out.startswith("reused fwd-kartka")
    assert not any(c[0] == "systemd-run" for c in rig.cmds)
    rig.page.href = "http://127.0.0.1:1/#/browse"
    assert _start(rig, tmp_path).startswith("reused")


def test_start_fails_when_systemd_run_fails(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.run_rc = 1
    with pytest.raises(DriveError, match="systemd-run exited 1") as err:
        _start(rig, tmp_path)
    assert err.value.code == EXIT_BROWSER


def test_start_fails_when_cdp_never_answers(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.comes_up = False
    with pytest.raises(DriveError, match="never answered"):
        _start(rig, tmp_path)


def test_start_fails_when_flutter_never_boots(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.page.flutter_ready = False
    with pytest.raises(DriveError, match="Flutter never booted"):
        _start(rig, tmp_path)


def test_start_rejects_bad_size(tmp_path: Path) -> None:
    with pytest.raises(DriveError) as err:
        Rig(tmp_path).driver().start("u", tmp_path, 1, size="big")
    assert err.value.code == EXIT_USAGE


def test_stop_stops_unit_and_clears_state(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    _start(rig, tmp_path)
    assert rig.driver().stop() == "stopped fwd-kartka"
    assert ["systemctl", "--user", "stop", "fwd-kartka"] in rig.cmds
    assert not (rig.root / "kartka" / "state.json").exists()
    assert rig.driver().stop() == "stopped fwd-kartka"


def test_verbs_need_start_first_unless_port_given(tmp_path: Path) -> None:
    rig = Rig(tmp_path, up=True)
    with pytest.raises(DriveError, match="run start first") as err:
        rig.driver().tree()
    assert err.value.code == EXIT_BROWSER
    assert "#5" in rig.driver(cdp_port=9341).tree()


def test_verbs_round_trip_through_the_page(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    _start(rig, tmp_path)
    drv = rig.driver()
    assert "#5" in drv.tree(filt="brow")
    assert drv.tree(row="Nope") == "(no matching semantics nodes)"
    assert drv.tap("Browse").startswith("tapped #5")
    assert drv.tap_xy(1, 2) == "tapped (1, 2)"
    assert drv.text("hi") == "inserted 2 characters"
    assert drv.key("Tab") == "pressed Tab"
    assert drv.scroll(0, 10, at=(1, 1)) == "scrolled (0, 10) at (1, 1)"
    assert drv.wait("Browse").startswith("found #5")
    rig.page.evals = {"1": 1}
    assert drv.eval("1") == "1"
    assert drv.console() == "no console errors"
    shot = drv.shot()
    assert shot.startswith(str(rig.root / "kartka" / "shot-"))


def test_wait_timeout_writes_screenshot_and_caps_timeout(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    _start(rig, tmp_path)
    with pytest.raises(DriveError, match="wait-timeout-"):
        rig.driver().wait("Nope", timeout=1)
    with pytest.raises(DriveError, match="<= 50") as err:
        rig.driver().wait("Nope", timeout=51)
    assert err.value.code == EXIT_USAGE


def test_console_can_fail_on_errors(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    _start(rig, tmp_path)
    events = [
        {
            "method": "Log.entryAdded",
            "params": {"entry": {"level": "error", "text": "x"}},
        }
    ]
    drv = Driver(
        "kartka",
        root=rig.root,
        fetch=rig.fetch,
        create=lambda u: rig.page.ws(events),
        runner=rig.runner,
    )
    with pytest.raises(DriveError, match="1 console error"):
        drv.console(fail_on_error=True)


def test_browser_helpers() -> None:
    argv = browser.chromium_argv("http://x/", Path("/p"), 9, (10, 20))
    assert argv[0] == browser.CHROMIUM
    assert argv[-1] == "http://x/"
    assert "--password-store=basic" in argv
    assert browser.parse_size("10x20") == (10, 20)
    assert browser.unit_argv("u", ["a"])[-1] == "a"


def test_real_runner_returns_exit_code() -> None:
    assert browser.run(["true"]) == 0
    assert browser.run(["false"]) == 1
