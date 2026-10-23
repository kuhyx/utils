"""AndroidManifest.xml reading, and rule 3: suffixed variants stay off the launcher.

A variant whose gradle block sets `applicationIdSuffix` installs beside the
real app (sandbox, debug), so it must not put a second icon in the launcher.
The statically checkable form is a variant manifest that removes the
LAUNCHER category and keeps MAIN, so `adb shell am start -n` still opens it:

    <activity android:name=".MainActivity">
        <intent-filter>
            <action android:name="android.intent.action.MAIN"/>
            <category android:name="android.intent.category.LAUNCHER"
                      tools:node="remove"/>
        </intent-filter>
    </activity>
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from repo_contract import gradle_blocks
from repo_contract.sources import read_text

ANDROID = "{http://schemas.android.com/apk/res/android}"
TOOLS = "{http://schemas.android.com/tools}"
TOOLS_DECL = 'xmlns:tools="http://schemas.android.com/tools"'
LAUNCHER = "android.intent.category.LAUNCHER"
MAIN_ACTION = "android.intent.action.MAIN"
APP = Path("android/app")
MAIN = APP / "src/main/AndroidManifest.xml"
GRADLE = (APP / "build.gradle.kts", APP / "build.gradle")
ACTIVITIES = ("activity", "activity-alias")
REMOVED = ("remove", "removeAll")


class ManifestError(ValueError):
    """A manifest is missing or not valid XML (message is the full reason)."""


def parse(app: Path, rel: Path) -> ET.Element:
    """Root element of `app/rel`; ManifestError when missing or malformed."""
    text = read_text(app / rel)
    if not text:
        raise ManifestError(f"{rel} is missing or unreadable")
    try:
        return ET.fromstring(text)
    except ET.ParseError as exc:
        raise ManifestError(f"{rel} is not valid XML: {exc}") from exc


def gradle_script(app: Path) -> tuple[Path | None, str]:
    """(relative path, text) of the app module's build script, if any."""
    for rel in GRADLE:
        if (app / rel).is_file():
            return rel, read_text(app / rel)
    return None, ""


def _short(name: str) -> str:
    """`.MainActivity` / `com.x.MainActivity` -> `MainActivity`."""
    return name.rsplit(".", 1)[-1]


def _categories(activity: ET.Element) -> list[tuple[ET.Element, ET.Element]]:
    """(intent-filter, category) pairs declaring LAUNCHER in `activity`."""
    return [
        (flt, cat)
        for flt in activity.iter("intent-filter")
        for cat in flt.iter("category")
        if cat.get(f"{ANDROID}name") == LAUNCHER
    ]


def launcher_activities(root: ET.Element) -> list[str]:
    """Names of the activities (and aliases) that show in the launcher."""
    return [
        act.get(f"{ANDROID}name", "")
        for kind in ACTIVITIES
        for act in root.iter(kind)
        if _categories(act)
    ]


def main_launchers(root: ET.Element) -> list[ET.Element]:
    """Activities (and aliases) with an intent-filter holding MAIN + LAUNCHER."""
    return [
        act
        for kind in ACTIVITIES
        for act in root.iter(kind)
        if any(
            action.get(f"{ANDROID}name") == MAIN_ACTION
            for flt, _ in _categories(act)
            for action in flt.iter("action")
        )
    ]


def _removes_main(activity: ET.Element) -> bool:
    """Whether the activity, a MAIN intent-filter or MAIN itself is removed."""
    if activity.get(f"{TOOLS}node") in REMOVED:
        return True
    return any(
        node.get(f"{TOOLS}node") in REMOVED
        for flt in activity.iter("intent-filter")
        for action in flt.iter("action")
        if action.get(f"{ANDROID}name") == MAIN_ACTION
        for node in (flt, action)
    )


def _hides(root: ET.Element, name: str, rel: Path, variant: str) -> list[str]:
    """Problems hiding launcher activity `name` in variant manifest `root`."""
    matches = [
        act
        for kind in ACTIVITIES
        for act in root.iter(kind)
        if _short(act.get(f"{ANDROID}name", "")) == _short(name)
    ]
    if any(_removes_main(act) for act in matches):
        return [
            (
                f"variant '{variant}': {rel} removes {MAIN_ACTION} from {name};"
                " keep MAIN so `am start -n` still works"
            )
        ]
    hidden = any(
        cat.get(f"{TOOLS}node") == "remove"
        for act in matches
        for _, cat in _categories(act)
    )
    if hidden:
        return []
    return [
        (
            f"variant '{variant}': {rel} does not remove the LAUNCHER category from"
            f' {name} (tools:node="remove" on the <category>)'
        )
    ]


def variant_problems(app: Path) -> list[str]:
    """Rule 3 for one Flutter app directory."""
    _, gradle = gradle_script(app)
    variants = gradle_blocks.suffixed_variants(gradle)
    try:
        names = launcher_activities(parse(app, MAIN))
    except ManifestError:
        return []  # rule 1 already reports the main manifest
    if not names:
        return []
    out: list[str] = []
    for variant in variants:
        rel = APP / "src" / variant / "AndroidManifest.xml"
        if not (app / rel).is_file():
            out.append(
                f"variant '{variant}' sets applicationIdSuffix but {rel} is missing:"
                f' hide it with <category android:name="{LAUNCHER}"'
                f' tools:node="remove"/> in {names[0]}\'s intent-filter'
            )
            continue
        try:
            root = parse(app, rel)
        except ManifestError as exc:
            out.append(str(exc))
            continue
        for name in names:
            out += _hides(root, name, rel, variant)
    return out
