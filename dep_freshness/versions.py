"""Version parsing shared by every ecosystem adapter.

The dangerous bug class here fails *green*: npm publishes pre-releases to
`dist-tags.latest` and crates.io's `max_version` includes them, so an adapter
that trusts either reports "up to date" while the pin is behind. Every
"latest" that leaves this package goes through `newest_stable` or, for a
package that has never shipped a stable release, `reference`.
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
# A tag that carries its project name: JitPack serves `java-nat-sort` only as
# `natural-comparator-1.1`. Only a digit-free name that STARTS with a letter
# and is followed by the version counts: `2.3.0-rc1` is untouched and stays a
# pre-release, and Google's `v3-rev197-1.25.0` API clients are NOT split,
# because `v3-` is an API generation, not a project name, and reading it as
# one proposed a `v2-...-2.0.0` artifact as "newer".
_TAG_PREFIX = re.compile(r"^(?P<prefix>[A-Za-z][A-Za-z_.-]*?-)(?=v?\d)")


def split_tag_prefix(raw: str) -> tuple[str, str]:
    """`("natural-comparator-", "1.1")`; an unprefixed version keeps `("", ...)`."""
    text = raw.strip()
    match = _TAG_PREFIX.match(text)
    if not match:
        return ("", text)
    return (match.group("prefix"), text[match.end() :])


def parse(raw: str, strict: bool = False) -> Version | None:
    """A comparable version, or None when the string is not one.

    `strict` refuses the semver-core fallback: `v3-rev197-1.25.0` reads as
    `3` loosely, which is enough to order it but says nothing about what it
    is, and the pre-release fallback below must not build on that.
    """
    tail = split_tag_prefix(raw)[1]
    try:
        return Version(tail.lstrip("v"))
    except InvalidVersion:
        if strict:
            return None
        match = _SEMVER.match(tail)
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
    tail = split_tag_prefix(raw)[1]
    if "-" in tail.split("+", 1)[0].lstrip("v"):
        return True
    version = parse(raw)
    return bool(version and (version.is_prerelease or version.is_devrelease))


def _canonical(raw: str) -> str:
    prefix, tail = split_tag_prefix(raw)
    return prefix + tail.lstrip("v")


def _newest(candidates, prereleases: bool) -> str | None:
    best: tuple[Version, str] | None = None
    for raw in candidates:
        if not raw or (not prereleases and is_prerelease(raw)):
            continue
        version = parse(raw, strict=prereleases)
        if version is None:
            continue
        if best is None or version > best[0]:
            best = (version, _canonical(str(raw)))
    return best[1] if best else None


def newest_stable(candidates) -> str | None:
    """The highest non-pre-release version in `candidates`, or None."""
    return _newest(candidates, prereleases=False)


def reference(candidates) -> str | None:
    """Newest stable, or newest pre-release when no stable was EVER shipped.

    `androidx.biometric:biometric-ktx` has been alpha-only since 2021; holding
    such a package to "newest stable" is a question with no answer, and an
    allowlist entry for it would need renewing every 90 days forever. The
    fallback is a predicate: the day a stable release appears, it wins.

    Only pre-releases PEP 440 can read qualify. Google's Drive client ships
    `v3-rev197-1.25.0`-style versions that are not pre-releases at all; the
    loose parser orders them by API generation, and a fallback built on that
    once declared a 2019 pin current against every newer revision.
    """
    candidates = list(candidates)
    return newest_stable(candidates) or _newest(candidates, prereleases=True)


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
# three reported an exact pin as unpinned against itself. A project-name
# prefix (`natural-comparator-1.1`) is part of the pin, since it is what the
# registry's version list spells.
EXACT = re.compile(
    r"^\s*(?:==\s*)?(?:[A-Za-z][A-Za-z_.-]*?-(?=v?\d))?"
    r"v?\d+(?:\.\d+)*(?:[-+][0-9A-Za-z.-]+)?\s*$"
)


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
    return _canonical(text.lstrip("=").strip())
