"""Rule 1 scope: suffixed variants are exempt; launcher activity labels count."""

from __future__ import annotations

from pathlib import Path

from repo_contract import launcher_label as ll

from .conftest import write
from .flutter_app import MAIN, NS, flutter_app, manifest

WORKOUT = """android {
    defaultConfig { manifestPlaceholders["appLabel"] = "Workout" }
    productFlavors {
        create("daily") { manifestPlaceholders["appLabel"] = "Workout" }
        create("sandbox") {
            applicationIdSuffix = ".sandbox"
            manifestPlaceholders["appLabel"] = "Workout SANDBOX"
        }
    }
}
"""
STRINGS = "android/app/src/main/res/values/strings.xml"


def test_suffixed_flavor_label_is_exempt(tmp_path: Path) -> None:
    """screen-locker's workout_app: the hidden sandbox may say SANDBOX."""
    app = flutter_app(tmp_path, label="${appLabel}", gradle=WORKOUT)
    assert ll.problems(app) == []


def test_unsuffixed_flavor_still_checked(tmp_path: Path) -> None:
    gradle = WORKOUT.replace(
        'create("daily") { manifestPlaceholders["appLabel"] = "Workout" }',
        'create("daily") { manifestPlaceholders["appLabel"] = "workout" }',
    )
    app = flutter_app(tmp_path, label="${appLabel}", gradle=gradle)
    assert ll.problems(app) == [
        (
            "android:label ${appLabel} in productFlavors.daily = 'workout'"
            " must start with a capital letter"
        )
    ]


def test_suffixed_buildtype_label_is_exempt(tmp_path: Path) -> None:
    gradle = """android {
    defaultConfig { manifestPlaceholders["appLabel"] = "Demo" }
    buildTypes { debug { applicationIdSuffix ".debug"; manifestPlaceholders["appLabel"] = "Demo dbg" } }
}
"""
    app = flutter_app(tmp_path, label="${appLabel}", gradle=gradle, kts=False)
    assert ll.problems(app) == []


def test_only_suffixed_assignments_is_unresolvable(tmp_path: Path) -> None:
    gradle = """android { productFlavors { create("sandbox") {
    applicationIdSuffix = ".sandbox"
    manifestPlaceholders["appLabel"] = "Sandbox"
} } }
"""
    app = flutter_app(tmp_path, label="${appLabel}", gradle=gradle)
    assert ll.problems(app) == [
        (
            'android:label ${appLabel}: no manifestPlaceholders["appLabel"] assignment'
            " for an unsuffixed variant in android/app/build.gradle.kts;"
            " cannot resolve the launcher name"
        )
    ]


def test_launcher_activity_label_checked(tmp_path: Path) -> None:
    app = flutter_app(tmp_path)
    write(app, MAIN.as_posix(), manifest(activity_label="punch me"))
    assert ll.problems(app) == [
        (
            "<activity .MainActivity> android:label 'punch me' must contain only ASCII"
            " letters (no spaces, _ or symbols)"
        ),
        (
            "<activity .MainActivity> android:label 'punch me' must start with a"
            " capital letter"
        ),
    ]


def test_launcher_activity_label_good(tmp_path: Path) -> None:
    app = flutter_app(tmp_path)
    write(app, MAIN.as_posix(), manifest(activity_label="PunchMe"))
    assert ll.problems(app) == []


def test_launcher_activity_label_resolved_like_the_app_label(tmp_path: Path) -> None:
    app = flutter_app(tmp_path)
    write(app, MAIN.as_posix(), manifest(activity_label="@string/launcher"))
    write(
        app, STRINGS, '<resources><string name="launcher">My App</string></resources>'
    )
    got = ll.problems(app)
    assert got[0].startswith(
        "<activity .MainActivity> android:label @string/launcher = 'My App'"
    )


def test_activity_label_also_checked_without_app_label_issue(tmp_path: Path) -> None:
    app = flutter_app(tmp_path)
    write(app, MAIN.as_posix(), manifest(label="demo", activity_label="Demo"))
    assert ll.problems(app) == ["android:label 'demo' must start with a capital letter"]


def test_non_launcher_activity_label_ignored(tmp_path: Path) -> None:
    app = flutter_app(tmp_path)
    body = manifest().replace(
        "    </application>",
        '        <activity android:name=".Settings" android:label="settings page"/>\n'
        '        <activity android:name=".Share" android:label="share it">\n'
        "            <intent-filter>\n"
        '                <category android:name="android.intent.category.LAUNCHER"/>\n'
        "            </intent-filter>\n"
        "        </activity>\n"
        "    </application>",
    )
    write(app, MAIN.as_posix(), body)
    assert ll.problems(app) == []


def test_activity_alias_label_checked(tmp_path: Path) -> None:
    app = flutter_app(tmp_path)
    body = f"""<manifest {NS}><application android:label="Demo">
<activity-alias android:name=".Alias" android:label="alias">
<intent-filter><action android:name="android.intent.action.MAIN"/>
<category android:name="android.intent.category.LAUNCHER"/></intent-filter>
</activity-alias></application></manifest>"""
    write(app, MAIN.as_posix(), body)
    assert ll.problems(app) == [
        "<activity .Alias> android:label 'alias' must start with a capital letter"
    ]
