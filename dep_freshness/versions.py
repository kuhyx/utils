"""Version parsing shared by every ecosystem adapter.

The dangerous bug class here fails *green*: npm publishes pre-releases to
`dist-tags.latest` and crates.io's `max_version` includes them, so an adapter
that trusts either reports "up to date" while the pin is behind. Every
"latest" that leaves this package goes through `newest_stable`.
"""

from __future__ import annotations

import re

from packaging.version import InvalidVersion, Version

# Dart/pub and Go use semver; PyPI uses PEP 440. `packaging` parses both well
# enough to compare, with this as the fallback for the odd Go pseudo-version.
_SEMVER = re.compile(
    r"^v?(?P<core>\d+(?:\.\d+){0,2})"
    r"(?:-(?P<pre>[0-9A-Za-z.-]+))?"
    r"(?:\+(?P<build>[0-9A-Za-z.-]+))?$"
)


def parse(raw: str) -> Version | None:
    """A comparable version, or None when the string is not one."""
    text = raw.strip().lstrip("v")
    try:
        return Version(text)
    except InvalidVersion:
        match = _SEMVER.match(raw.strip())
        if not match:
            return None
        # `core` is `\d+(\.\d+){0,2}`, which Version always accepts.
        return Version(match.group("core"))


def is_prerelease(raw: str) -> bool:
    """True for `1.2.0-beta.1`, `2.0.0rc1`, `1.0.0-dev` and friends.

    Checked on the raw string as well as the parsed object because PEP 440
    silently normalises some semver pre-release tags (`-alpha` survives, but
    an unknown suffix can be dropped) and a dropped suffix reads as stable.
    """
    if "-" in raw.split("+", 1)[0].lstrip("v"):
        return True
    version = parse(raw)
    return bool(version and (version.is_prerelease or version.is_devrelease))


def newest_stable(candidates) -> str | None:
    """The highest non-pre-release version in `candidates`, or None."""
    best: tuple[Version, str] | None = None
    for raw in candidates:
        if not raw or is_prerelease(raw):
            continue
        version = parse(raw)
        if version is None:
            continue
        if best is None or version > best[0]:
            best = (version, str(raw).strip().lstrip("v"))
    return best[1] if best else None


def behind(pinned: str, latest: str) -> bool:
    """True when `pinned` is strictly older than `latest`.

    Unparseable input is never reported as behind: an unpinned or exotic
    constraint is a different finding (`UNPINNED`) and must not be dressed up
    as staleness.
    """
    left, right = parse(pinned), parse(latest)
    if left is None or right is None:
        return False
    return left < right


# Any number of numeric release components, not three: PyPI stub packages
# date-stamp a fourth (`types-requests==2.33.0.20260712`), and capping at
# three reported an exact pin as unpinned against itself.
EXACT = re.compile(r"^\s*(?:==\s*)?v?\d+(?:\.\d+)*(?:[-+][0-9A-Za-z.-]+)?\s*$")


def exact_pin(constraint: str) -> str | None:
    """The version an exact constraint names, or None if it is a range.

    `1.6.0` and `==1.6.0` are exact; `^1.6.0`, `>=1.6.0`, `any` and `*` are
    not. A range is not comparable to a registry answer, which is the whole
    reason Q6 asked for exact pins.
    """
    if not constraint:
        return None
    text = str(constraint).strip()
    if not EXACT.match(text):
        return None
    return text.lstrip("=").strip().lstrip("v")
