"""Rule 1: the launcher name every Flutter app shows on the phone.

kuhy's rules (2026-10-23): a name starts with a capital, holds only ASCII
letters (no spaces, underscores or punctuation) and has at most 10 characters,
so the Pixel launcher never truncates it with an ellipsis. Its width in
the launcher font is capped too (`label_widths.py`): FocusOwner, 10
characters, was still cut. The same rules live
in `~/src/testsAndMisc/python_pkg/app_icons/labels.py` (`label_problems`);
the messages are mirrored here, not imported, because utils must not depend
on another repo.

The name is `<application android:label>` of the main manifest, plus the
`android:label` of any activity (or alias) whose intent-filter holds MAIN +
LAUNCHER, because that one overrides the application label on the launcher.
Each is resolved from a literal, `@string/<name>` (main res/values/strings.xml)
or `${placeholder}`: every `manifestPlaceholders` assignment in
android/app/build.gradle[.kts] outside a variant that sets applicationIdSuffix
(rule 3 hides those from the launcher, so they may say "SANDBOX").
Anything that cannot be resolved statically fails: never a silent pass.
"""

from __future__ import annotations

import re
from pathlib import Path

from repo_contract import gradle_blocks
from repo_contract.android_manifest import (
    ANDROID,
    MAIN,
    ManifestError,
    gradle_script,
    main_launchers,
    parse,
)
from repo_contract.label_widths import MAX_WIDTH, label_width

MAX_LENGTH = 10
STRINGS = Path("android/app/src/main/res/values/strings.xml")
_ASCII_LETTERS = re.compile(r"[A-Za-z]+")
_STRING_REF = re.compile(r"@string/(\w+)")
_PLACEHOLDER = re.compile(r"\$\{(\w+)\}")
_UNRESOLVED = "cannot resolve the launcher name"


def label_problems(name: str) -> list[str]:
    """Every launcher-name rule `name` breaks (app_icons labels.py wording)."""
    if not name:
        return ["label is empty"]
    problems: list[str] = []
    letters_only = _ASCII_LETTERS.fullmatch(name) is not None
    if not letters_only:
        problems.append(
            f"{name!r} must contain only ASCII letters (no spaces, _ or symbols)"
        )
    if not name[0].isupper():
        problems.append(f"{name!r} must start with a capital letter")
    # The width table only knows ASCII letters; other names already failed.
    if letters_only and label_width(name) > MAX_WIDTH:
        problems.append(
            f"{name!r} is {label_width(name)} wide in the launcher font; "
            f"at most {MAX_WIDTH} fit"
        )
    if len(name) > MAX_LENGTH:
        problems.append(
            f"{name!r} has {len(name)} characters; at most {MAX_LENGTH} fit"
        )
    return problems


def _string(app: Path, attr: str, name: str) -> list[str]:
    try:
        root = parse(app, STRINGS)
    except ManifestError:
        return [f"{attr}: {STRINGS} is missing or unreadable; {_UNRESOLVED}"]
    for node in root.iter("string"):
        if node.get("name") == name:
            value = "".join(node.itertext())
            return [f"{attr} = {p}" for p in label_problems(value)]
    return [f'{attr}: no <string name="{name}"> in {STRINGS}; {_UNRESOLVED}']


def _placeholder(app: Path, attr: str, key: str) -> list[str]:
    rel, gradle = gradle_script(app)
    if rel is None:
        return [f"{attr}: no android/app/build.gradle(.kts); {_UNRESOLVED}"]
    values = gradle_blocks.placeholder_values(gradle, key, unsuffixed_only=True)
    if not values:
        scope = (
            " for an unsuffixed variant"
            if gradle_blocks.placeholder_values(gradle, key)
            else ""
        )
        return [
            (
                f'{attr}: no manifestPlaceholders["{key}"] assignment{scope}'
                f" in {rel}; {_UNRESOLVED}"
            )
        ]
    out = []
    for where, value in values:
        if value is None:
            out.append(
                f"{attr}: the value set in {where} is not a string literal;"
                f" {_UNRESOLVED}"
            )
        else:
            out += [f"{attr} in {where} = {p}" for p in label_problems(value)]
    return out


def _resolve(app: Path, attr: str, label: str) -> list[str]:
    """Problems with one android:label value; `attr` prefixes each message."""
    if string := _STRING_REF.fullmatch(label):
        return _string(app, f"{attr} {label}", string.group(1))
    if placeholder := _PLACEHOLDER.fullmatch(label):
        return _placeholder(app, f"{attr} {label}", placeholder.group(1))
    if label.startswith("@") or "${" in label:
        return [
            (
                f"{attr} {label!r} cannot be resolved statically:"
                " use a literal, @string/<name> or ${<placeholder>}"
            )
        ]
    return [f"{attr} {p}" for p in label_problems(label)]


def problems(app: Path) -> list[str]:
    """Rule 1 for one Flutter app directory."""
    try:
        root = parse(app, MAIN)
    except ManifestError as exc:
        return [f"{exc}; {_UNRESOLVED}"]
    application = root.find("application")
    label = None if application is None else application.get(f"{ANDROID}label")
    if label is None:
        return [f"{MAIN}: <application> has no android:label; {_UNRESOLVED}"]
    out = _resolve(app, "android:label", label)
    for activity in main_launchers(root):
        own = activity.get(f"{ANDROID}label")
        if own is not None:
            name = activity.get(f"{ANDROID}name", "?")
            out += _resolve(app, f"<activity {name}> android:label", own)
    return out
