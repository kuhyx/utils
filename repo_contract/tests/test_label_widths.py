"""Rule 1 width cap: the rendered name fits the Pixel app drawer."""

from __future__ import annotations

from pathlib import Path

import pytest

from repo_contract import launcher
from repo_contract import launcher_label as ll
from repo_contract.label_widths import ADVANCE, MAX_WIDTH, label_width

from .conftest import write
from .flutter_app import MAIN, flutter_app, manifest, track

TOO_WIDE = "'FocusOwner' is 580 wide in the launcher font; at most 522 fit"


def test_table_covers_every_ascii_letter() -> None:
    assert sorted(ADVANCE) == sorted(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    )


@pytest.mark.parametrize(("name", "width"), [("WakeAlarm", 522), ("FocusOwner", 580)])
def test_label_width(name: str, width: int) -> None:
    assert label_width(name) == width


@pytest.mark.parametrize("name", ["WakeAlarm", "Focuser", "Homer"])
def test_fitting_names_pass(name: str) -> None:
    assert label_width(name) <= MAX_WIDTH
    assert ll.label_problems(name) == []


def test_focusowner_is_too_wide() -> None:
    assert ll.label_problems("FocusOwner") == [TOO_WIDE]


def test_width_sits_between_capital_and_length_rules() -> None:
    assert ll.label_problems("wwwwwwwwwww") == [
        "'wwwwwwwwwww' must start with a capital letter",
        "'wwwwwwwwwww' is 858 wide in the launcher font; at most 522 fit",
        "'wwwwwwwwwww' has 11 characters; at most 10 fit",
    ]


def test_width_skipped_for_non_letters() -> None:
    got = ll.label_problems("Wide Wide W")
    assert not any("wide in the launcher font" in p for p in got)


def test_app_label_too_wide(tmp_path: Path) -> None:
    app = flutter_app(tmp_path, label="FocusOwner")
    assert ll.problems(app) == [f"android:label {TOO_WIDE}"]


def test_activity_label_too_wide(tmp_path: Path) -> None:
    app = flutter_app(tmp_path)
    write(app, MAIN.as_posix(), manifest(activity_label="FocusOwner"))
    assert ll.problems(app) == [f"<activity .MainActivity> android:label {TOO_WIDE}"]


def test_desktop_name_too_wide(repo: Path) -> None:
    flutter_app(repo)
    write(repo, "linux/app.desktop", "[Desktop Entry]\nName=FocusOwner\n")
    track(repo)
    assert launcher.problems(repo) == [f"launcher: linux/app.desktop: Name={TOO_WIDE}"]
