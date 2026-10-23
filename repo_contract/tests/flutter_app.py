"""Builders for minimal Flutter app fixtures: pubspec, manifests, gradle."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .conftest import write

PUBSPEC = "name: demo\ndependencies:\n  flutter:\n    sdk: flutter\n"
NS = 'xmlns:android="http://schemas.android.com/apk/res/android"'
TOOLS = 'xmlns:tools="http://schemas.android.com/tools"'
ACTIVITY = """        <activity android:name="{name}"{extra}>
            <intent-filter>
                <action android:name="android.intent.action.MAIN"{main}/>
                <category android:name="android.intent.category.LAUNCHER"{tag}/>
            </intent-filter>
        </activity>
"""
GRADLE = """android {
    defaultConfig {
        applicationId = "com.kuhy.demo"
    }
}
"""
SANDBOX_GRADLE = """android {
    productFlavors {
        create("daily") { dimension = "store" }
        create("sandbox") { applicationIdSuffix = ".sandbox" }
    }
}
"""
MAIN = Path("android/app/src/main/AndroidManifest.xml")
REMOVE = ' tools:node="remove"'


def manifest(
    label: str | None = "Demo",
    activity: str = ".MainActivity",
    activity_label: str | None = None,
) -> str:
    """The main AndroidManifest.xml with one LAUNCHER activity."""
    attr = "" if label is None else f' android:label="{label}"'
    extra = "" if activity_label is None else f' android:label="{activity_label}"'
    body = ACTIVITY.format(name=activity, main="", tag="", extra=extra)
    return f"<manifest {NS}>\n    <application{attr}>\n{body}    </application>\n</manifest>\n"


def hide(activity: str = ".MainActivity", *, main: str = "", tag: str = REMOVE) -> str:
    """A variant manifest that removes LAUNCHER (by default) from `activity`."""
    body = ACTIVITY.format(name=activity, main=main, tag=tag, extra="")
    return f"<manifest {NS} {TOOLS}>\n    <application>\n{body}    </application>\n</manifest>\n"


def flutter_app(
    root: Path,
    rel: str = ".",
    *,
    label: str | None = "Demo",
    gradle: str | None = GRADLE,
    kts: bool = True,
) -> Path:
    """A minimal Android-enabled Flutter app at `root/rel`; returns its dir."""
    app = root / rel
    write(app, "pubspec.yaml", PUBSPEC)
    write(app, MAIN.as_posix(), manifest(label))
    if gradle is not None:
        name = "build.gradle.kts" if kts else "build.gradle"
        write(app, f"android/app/{name}", gradle)
    return app


def track(repo: Path) -> None:
    """Stage everything so `git ls-files` sees it."""
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
