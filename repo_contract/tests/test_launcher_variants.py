"""Rule 3: an applicationIdSuffix variant hides LAUNCHER but keeps MAIN."""

from __future__ import annotations

from pathlib import Path

from repo_contract import android_manifest as am

from .conftest import write
from .flutter_app import MAIN, NS, REMOVE, SANDBOX_GRADLE, flutter_app, hide, manifest

SANDBOX = "android/app/src/sandbox/AndroidManifest.xml"


def sandbox_app(root: Path) -> Path:
    return flutter_app(root, gradle=SANDBOX_GRADLE)


def test_no_suffix_variant_passes(tmp_path: Path) -> None:
    assert am.variant_problems(flutter_app(tmp_path)) == []


def test_no_gradle_passes(tmp_path: Path) -> None:
    assert am.variant_problems(flutter_app(tmp_path, gradle=None)) == []


def test_hidden_variant_passes(tmp_path: Path) -> None:
    app = sandbox_app(tmp_path)
    write(app, SANDBOX, hide())
    assert am.variant_problems(app) == []


def test_fully_qualified_activity_name_matches(tmp_path: Path) -> None:
    app = sandbox_app(tmp_path)
    write(app, SANDBOX, hide("com.kuhy.demo.MainActivity"))
    assert am.variant_problems(app) == []


def test_missing_variant_manifest_fails(tmp_path: Path) -> None:
    got = am.variant_problems(sandbox_app(tmp_path))
    assert got == [
        (
            f"variant 'sandbox' sets applicationIdSuffix but {SANDBOX} is missing:"
            ' hide it with <category android:name="android.intent.category.LAUNCHER"'
            ' tools:node="remove"/> in .MainActivity\'s intent-filter'
        )
    ]


def test_variant_manifest_without_remove_fails(tmp_path: Path) -> None:
    app = sandbox_app(tmp_path)
    write(app, SANDBOX, hide(tag=""))
    assert am.variant_problems(app) == [
        (
            f"variant 'sandbox': {SANDBOX} does not remove the LAUNCHER category from"
            ' .MainActivity (tools:node="remove" on the <category>)'
        )
    ]


def test_remove_on_other_activity_fails(tmp_path: Path) -> None:
    app = sandbox_app(tmp_path)
    write(app, SANDBOX, hide(".OtherActivity"))
    assert len(am.variant_problems(app)) == 1


def test_removing_main_fails(tmp_path: Path) -> None:
    app = sandbox_app(tmp_path)
    write(app, SANDBOX, hide(main=REMOVE))
    assert am.variant_problems(app) == [
        (
            f"variant 'sandbox': {SANDBOX} removes android.intent.action.MAIN from"
            " .MainActivity; keep MAIN so `am start -n` still works"
        )
    ]


def test_removing_whole_activity_fails(tmp_path: Path) -> None:
    app = sandbox_app(tmp_path)
    body = hide().replace(
        '<activity android:name=".MainActivity">',
        '<activity android:name=".MainActivity" tools:node="remove">',
    )
    write(app, SANDBOX, body)
    assert "removes android.intent.action.MAIN" in am.variant_problems(app)[0]


def test_removing_main_intent_filter_fails(tmp_path: Path) -> None:
    app = sandbox_app(tmp_path)
    write(
        app,
        SANDBOX,
        hide(tag="").replace("<intent-filter>", f"<intent-filter{REMOVE}>"),
    )
    assert "removes android.intent.action.MAIN" in am.variant_problems(app)[0]


def test_invalid_variant_manifest_fails(tmp_path: Path) -> None:
    app = sandbox_app(tmp_path)
    write(app, SANDBOX, hide().replace(f" {am.TOOLS_DECL}", ""))
    got = am.variant_problems(app)
    assert len(got) == 1 and got[0].startswith(f"{SANDBOX} is not valid XML:")


def test_main_manifest_without_launcher_needs_nothing(tmp_path: Path) -> None:
    app = sandbox_app(tmp_path)
    write(app, MAIN.as_posix(), f"<manifest {NS}><application/></manifest>")
    assert am.variant_problems(app) == []


def test_unreadable_main_manifest_needs_nothing(tmp_path: Path) -> None:
    app = sandbox_app(tmp_path)
    write(app, MAIN.as_posix(), "<manifest")
    assert am.variant_problems(app) == []


def test_activity_alias_is_a_launcher_too(tmp_path: Path) -> None:
    app = sandbox_app(tmp_path)
    body = (
        manifest()
        .replace("<activity ", "<activity-alias ")
        .replace("</activity>", "</activity-alias>")
    )
    write(app, MAIN.as_posix(), body)
    got = am.variant_problems(app)
    assert len(got) == 1 and "is missing" in got[0]


def test_groovy_buildtype_suffix(tmp_path: Path) -> None:
    gradle = "android { buildTypes { debug { applicationIdSuffix '.debug' } } }\n"
    app = flutter_app(tmp_path, gradle=gradle, kts=False)
    write(app, "android/app/src/debug/AndroidManifest.xml", hide())
    assert am.variant_problems(app) == []
