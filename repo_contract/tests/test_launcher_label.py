"""Rule 1: the resolved android:label is a short capitalised ASCII word."""

from __future__ import annotations

from pathlib import Path

import pytest

from repo_contract import launcher_label as ll

from .conftest import write
from .flutter_app import MAIN, flutter_app, manifest

STRINGS = Path("android/app/src/main/res/values/strings.xml")


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("PunchMe", []),
        ("DailyLimit", []),
        ("", ["label is empty"]),
        ("punchme", ["'punchme' must start with a capital letter"]),
        (
            "Umbrella?",
            ["'Umbrella?' must contain only ASCII letters (no spaces, _ or symbols)"],
        ),
        (
            "focus_owner",
            [
                "'focus_owner' must contain only ASCII letters (no spaces, _ or symbols)",
                "'focus_owner' must start with a capital letter",
                "'focus_owner' has 11 characters; at most 10 fit",
            ],
        ),
        (
            "Zażółć",
            ["'Zażółć' must contain only ASCII letters (no spaces, _ or symbols)"],
        ),
    ],
)
def test_label_problems_mirror_app_icons(name: str, expected: list[str]) -> None:
    assert ll.label_problems(name) == expected


def test_literal_label(tmp_path: Path) -> None:
    assert ll.problems(flutter_app(tmp_path, label="Demo")) == []
    assert ll.problems(flutter_app(tmp_path, label="demo")) == [
        "android:label 'demo' must start with a capital letter"
    ]


def test_string_resource(tmp_path: Path) -> None:
    app = flutter_app(tmp_path, label="@string/app_name")
    write(
        app,
        STRINGS.as_posix(),
        '<resources><string name="app_name">My App</string></resources>',
    )
    assert ll.problems(app) == [
        (
            "android:label @string/app_name = 'My App' must contain only ASCII letters"
            " (no spaces, _ or symbols)"
        )
    ]


def test_string_resource_missing(tmp_path: Path) -> None:
    app = flutter_app(tmp_path, label="@string/app_name")
    assert ll.problems(app) == [
        (
            f"android:label @string/app_name: {STRINGS} is missing or unreadable;"
            " cannot resolve the launcher name"
        )
    ]
    write(
        app,
        STRINGS.as_posix(),
        '<resources><string name="other">X</string></resources>',
    )
    assert ll.problems(app) == [
        (
            f'android:label @string/app_name: no <string name="app_name"> in {STRINGS};'
            " cannot resolve the launcher name"
        )
    ]


def test_placeholder_every_assignment_checked(tmp_path: Path) -> None:
    gradle = """android {
    defaultConfig { manifestPlaceholders["appLabel"] = "Workout" }
    productFlavors {
        create("daily") { manifestPlaceholders["appLabel"] = "workout_app" }
        create("sandbox") { manifestPlaceholders["appLabel"] = "Workout SANDBOX" }
    }
}
"""
    app = flutter_app(tmp_path, label="${appLabel}", gradle=gradle)
    got = ll.problems(app)
    assert got[0] == (
        "android:label ${appLabel} in productFlavors.daily = 'workout_app'"
        " must contain only ASCII letters (no spaces, _ or symbols)"
    )
    assert len(got) == 5
    assert all("defaultConfig" not in p for p in got)


def test_placeholder_groovy_passes(tmp_path: Path) -> None:
    gradle = "android { defaultConfig { manifestPlaceholders = [appLabel: 'Demo'] } }\n"
    app = flutter_app(tmp_path, label="${appLabel}", gradle=gradle, kts=False)
    assert ll.problems(app) == []


def test_placeholder_not_literal(tmp_path: Path) -> None:
    gradle = 'android { defaultConfig { manifestPlaceholders["appLabel"] = name } }\n'
    app = flutter_app(tmp_path, label="${appLabel}", gradle=gradle)
    assert ll.problems(app) == [
        (
            "android:label ${appLabel}: the value set in defaultConfig is not a string"
            " literal; cannot resolve the launcher name"
        )
    ]


def test_placeholder_unassigned(tmp_path: Path) -> None:
    app = flutter_app(tmp_path, label="${appLabel}")
    assert ll.problems(app) == [
        (
            'android:label ${appLabel}: no manifestPlaceholders["appLabel"] assignment'
            " in android/app/build.gradle.kts; cannot resolve the launcher name"
        )
    ]


def test_placeholder_without_gradle_file(tmp_path: Path) -> None:
    app = flutter_app(tmp_path, label="${appLabel}", gradle=None)
    assert ll.problems(app) == [
        (
            "android:label ${appLabel}: no android/app/build.gradle(.kts);"
            " cannot resolve the launcher name"
        )
    ]


@pytest.mark.parametrize(
    "label", ["Demo ${suffix}", "@string/a/b", "@android:string/x"]
)
def test_unresolvable_forms(tmp_path: Path, label: str) -> None:
    assert ll.problems(flutter_app(tmp_path, label=label)) == [
        (
            f"android:label {label!r} cannot be resolved statically:"
            " use a literal, @string/<name> or ${<placeholder>}"
        )
    ]


def test_no_label(tmp_path: Path) -> None:
    assert ll.problems(flutter_app(tmp_path, label=None)) == [
        f"{MAIN}: <application> has no android:label; cannot resolve the launcher name"
    ]


def test_missing_or_broken_manifest(tmp_path: Path) -> None:
    app = flutter_app(tmp_path)
    (app / MAIN).unlink()
    assert ll.problems(app) == [
        f"{MAIN} is missing or unreadable; cannot resolve the launcher name"
    ]
    write(app, MAIN.as_posix(), manifest()[:-20])
    got = ll.problems(app)
    assert len(got) == 1 and got[0].startswith(f"{MAIN} is not valid XML:")


def test_manifest_without_application(tmp_path: Path) -> None:
    app = flutter_app(tmp_path)
    write(app, MAIN.as_posix(), "<manifest/>")
    assert ll.problems(app) == [
        f"{MAIN}: <application> has no android:label; cannot resolve the launcher name"
    ]
