"""Which repos owe the launcher rules, rule 2 (.desktop), and rule 4 wiring."""

from __future__ import annotations

from pathlib import Path

import pytest

from repo_contract import check, launcher

from .conftest import good_repo, write
from .flutter_app import flutter_app, track
from .pngkit import write_icon

ICON = "assets/icon/icon_foreground.png"
DESKTOP = "[Desktop Entry]\nType=Application\nName={name}\nName[pl]=Zadania pl\n"


def test_root_app_found(repo: Path) -> None:
    flutter_app(repo)
    track(repo)
    assert launcher.flutter_apps(repo) == [repo]
    assert launcher.problems(repo) == []


def test_nested_app_found_and_prefixed(repo: Path) -> None:
    flutter_app(repo, "tools/workout_app", label="workout_app")
    track(repo)
    got = launcher.problems(repo)
    assert got[0].startswith(
        "launcher [tools/workout_app]: android:label 'workout_app'"
    )
    assert len(got) == 3


def test_untracked_and_pruned_pubspecs_ignored(repo: Path) -> None:
    flutter_app(repo, "build/stale", label="x")
    flutter_app(repo, ".utils/vendored", label="x")
    flutter_app(repo, "deleted", label="x")
    track(repo)
    (repo / "deleted/pubspec.yaml").unlink()
    flutter_app(repo, "untracked", label="x")
    assert launcher.flutter_apps(repo) == []


def test_not_flutter_or_no_android_skipped(repo: Path) -> None:
    write(repo, "dart_pkg/pubspec.yaml", "name: p\ndependencies:\n  path: 1.9.0\n")
    write(repo, "dart_pkg/android/x", "")
    write(
        repo,
        "web_only/pubspec.yaml",
        "name: w\ndependencies:\n  flutter:\n    sdk: flutter\n",
    )
    write(
        repo,
        "dev_only/pubspec.yaml",
        "dev_dependencies:\n  flutter:\n    sdk: flutter\n",
    )
    write(repo, "dev_only/android/x", "")
    track(repo)
    assert launcher.flutter_apps(repo) == []


def test_pubspec_comments_do_not_hide_an_app(repo: Path) -> None:
    body = "dependencies:  # exact pins\n# column-0 note\n\n  flutter:\n    sdk: flutter # sdk\n"
    write(repo, "a/pubspec.yaml", body)
    write(repo, "a/android/x", "")
    track(repo)
    assert launcher.flutter_apps(repo) == [repo / "a"]


def test_not_a_git_repo_checks_root_only(tmp_path: Path) -> None:
    flutter_app(tmp_path, label="demo")
    flutter_app(tmp_path, "nested", label="demo")
    assert launcher.flutter_apps(tmp_path) == [tmp_path]


def test_no_flutter_app_no_rules(repo: Path) -> None:
    write(repo, "x.desktop", DESKTOP.format(name="bad name"))
    track(repo)
    assert launcher.problems(repo) == []


def test_desktop_names_checked(repo: Path) -> None:
    flutter_app(repo)
    write(repo, "linux/good.desktop", DESKTOP.format(name="Todo"))
    write(repo, "linux/bad.desktop", DESKTOP.format(name="todo app"))
    write(
        repo,
        "linux/action.desktop",
        DESKTOP.format(name="Todo") + "[Desktop Action new]\nName=New window\n",
    )
    write(repo, "linux/none.desktop", "[Desktop Entry]\nType=Application\n")
    track(repo)
    write(repo, "linux/untracked.desktop", DESKTOP.format(name="bad name"))
    assert launcher.problems(repo) == [
        (
            "launcher: linux/bad.desktop: Name='todo app' must contain only ASCII"
            " letters (no spaces, _ or symbols)"
        ),
        "launcher: linux/bad.desktop: Name='todo app' must start with a capital letter",
        "launcher: linux/none.desktop: no Name= in [Desktop Entry]",
    ]


def test_unreadable_desktop_file(repo: Path) -> None:
    flutter_app(repo)
    write(repo, "a.desktop", "x")
    track(repo)
    (repo / "a.desktop").write_bytes(b"\xff\xfe")
    assert launcher.problems(repo) == ["launcher: a.desktop: unreadable"]


def test_icon_checked_when_present(repo: Path) -> None:
    app = flutter_app(repo)
    write_icon(app / ICON, 250)
    track(repo)
    got = launcher.problems(repo)
    assert len(got) == 1 and got[0].startswith(f"launcher: {ICON}: ink radius 2")


def test_no_icon_no_icon_rule(repo: Path) -> None:
    flutter_app(repo)
    track(repo)
    assert launcher.problems(repo) == []


def test_icon_skip_with_reason(repo: Path) -> None:
    app = flutter_app(repo, "focus-owner")
    write_icon(app / ICON, 250)
    write(app, "repo-contract.toml", '[launcher_icon]\nskip = "vector drawables"\n')
    track(repo)
    assert launcher.problems(repo) == []


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (
            '[launcher_icon]\nskip = ""\n',
            '[launcher_icon] skip = "<reason>" needs a non-empty reason',
        ),
        (
            "[launcher_icon]\nskip = true\n",
            '[launcher_icon] skip = "<reason>" needs a non-empty reason',
        ),
        (
            "[launcher_icon]\n",
            '[launcher_icon] skip = "<reason>" needs a non-empty reason',
        ),
        (
            '[launcher_icon]\nskip = "x"\nwhy = 1\n',
            "unknown key(s) in [launcher_icon]: why",
        ),
        ("launcher_icon = 1\n", "'launcher_icon' must be a table: [launcher_icon]"),
        ("[launcher_icon\n", "not valid TOML"),
    ],
)
def test_icon_skip_malformed(repo: Path, body: str, message: str) -> None:
    app = flutter_app(repo)
    write_icon(app / ICON, 250)
    write(app, "repo-contract.toml", body)
    track(repo)
    got = launcher.problems(repo)
    assert len(got) == 1
    assert got[0].startswith(f"launcher: repo-contract.toml: {message}")


def test_other_tables_do_not_skip(repo: Path) -> None:
    app = flutter_app(repo)
    write_icon(app / ICON, 250)
    write(app, "repo-contract.toml", '[agent_ready]\nskip = "not a site"\n')
    track(repo)
    assert len(launcher.problems(repo)) == 1


def test_check_reports_launcher_problems(repo: Path) -> None:
    good_repo(repo)
    flutter_app(repo, label="demo")
    track(repo)
    found, _ = check.violations(repo)
    assert found == ["launcher: android:label 'demo' must start with a capital letter"]
