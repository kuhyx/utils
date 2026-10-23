"""Launcher rules for every Flutter app in a repo (kuhy, 2026-10-23).

Applies to each tracked `pubspec.yaml` whose `dependencies:` include the
Flutter SDK and that has an `android/` directory beside it, at the repo root
or nested (screen-locker's workout_app):

1. the launcher name (`launcher_label.py`);
2. every tracked `*.desktop` file's `[Desktop Entry] Name=` meets the same rule;
3. a suffixed variant stays off the launcher (`android_manifest.py`);
4. `assets/icon/icon_foreground.png` fills the family ink circle
   (`png_ink.py`), unless the app's `repo-contract.toml` declares

       [launcher_icon]
       skip = "<why this app cannot ship the PNG foreground>"
"""

from __future__ import annotations

import re
import subprocess
import tomllib
from pathlib import Path, PurePosixPath

from repo_contract import android_manifest, launcher_label, png_ink
from repo_contract.stacks import PRUNE

CONFIG = Path("repo-contract.toml")
TABLE = "launcher_icon"
ICON = Path("assets/icon/icon_foreground.png")
_SDK = re.compile(r"^\s+sdk:\s*flutter\s*$")


class ConfigError(ValueError):
    """`[launcher_icon]` exists but is malformed."""


def _tracked(repo: Path, *patterns: str) -> list[PurePosixPath] | None:
    """Tracked paths matching `patterns`; None when git cannot list them."""
    done = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-z", "--", *patterns],
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        return None
    return [PurePosixPath(p) for p in done.stdout.split("\0") if p]


def _needs_flutter(pubspec: Path) -> bool:
    """Whether the top-level `dependencies:` block pulls in the Flutter SDK."""
    try:
        lines = pubspec.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return False
    inside = False
    for line in lines:
        code = line.split("#", 1)[0].rstrip()  # comments never end a block
        if not code.strip():
            continue
        if not code[0].isspace():
            inside = code == "dependencies:"
        elif inside and _SDK.match(code):
            return True
    return False


def flutter_apps(repo: Path) -> list[Path]:
    """Android-enabled Flutter app dirs in `repo` (root-only outside git)."""
    found = _tracked(repo, "pubspec.yaml", "*/pubspec.yaml")
    rels = [PurePosixPath("pubspec.yaml")] if found is None else found
    apps = []
    for rel in sorted(rels):
        if PRUNE.intersection(rel.parts):
            continue
        app = repo / rel.parent
        if (app / "android").is_dir() and _needs_flutter(app / "pubspec.yaml"):
            apps.append(app)
    return apps


def _desktop_name(text: str) -> list[str]:
    """`Name=` values of the `[Desktop Entry]` group (not actions/locales)."""
    names, inside = [], False
    for line in text.splitlines():
        if line.startswith("["):
            inside = line.strip() == "[Desktop Entry]"
        elif inside and line.startswith("Name="):
            names.append(line[len("Name=") :].strip())
    return names


def desktop_problems(repo: Path) -> list[str]:
    """Rule 2 over every tracked .desktop file in the repo."""
    out = []
    for rel in _tracked(repo, "*.desktop") or []:
        try:
            text = (repo / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            out.append(f"{rel}: unreadable")
            continue
        names = _desktop_name(text)
        if not names:
            out.append(f"{rel}: no Name= in [Desktop Entry]")
        for name in names:
            out += [f"{rel}: Name={p}" for p in launcher_label.label_problems(name)]
    return out


def icon_skip(app: Path) -> str | None:
    """The `[launcher_icon] skip` reason; None when the icon rule applies."""
    path = app / CONFIG
    if not path.is_file():
        return None
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"not valid TOML: {exc}") from exc
    if TABLE not in data:
        return None
    table = data[TABLE]
    if not isinstance(table, dict):
        raise ConfigError(f"'{TABLE}' must be a table: [{TABLE}]")
    unknown = sorted(set(table) - {"skip"})
    if unknown:
        raise ConfigError(f"unknown key(s) in [{TABLE}]: {', '.join(unknown)}")
    reason = table.get("skip")
    if not isinstance(reason, str) or not reason.strip():
        raise ConfigError(f'[{TABLE}] skip = "<reason>" needs a non-empty reason')
    return reason


def _icon(app: Path) -> list[str]:
    try:
        if icon_skip(app) is not None:
            return []
    except ConfigError as exc:
        return [f"{CONFIG}: {exc}"]
    if not (app / ICON).is_file():
        return []
    return png_ink.icon_problems(app / ICON, str(ICON))


def problems(repo: Path) -> list[str]:
    """Every launcher-rule violation in `repo`, prefixed `launcher[ [app]]: `."""
    apps = flutter_apps(repo)
    if not apps:
        return []
    out = []
    for app in apps:
        rel = app.relative_to(repo).as_posix()
        prefix = "launcher: " if rel == "." else f"launcher [{rel}]: "
        found = launcher_label.problems(app)
        found += android_manifest.variant_problems(app)
        found += _icon(app)
        out += [prefix + p for p in found]
    return out + [f"launcher: {p}" for p in desktop_problems(repo)]
