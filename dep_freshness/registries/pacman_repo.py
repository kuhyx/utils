"""Arch-style package repos: the one version a repo `.db` lists for a package.

A repo db (`cachyos.db`, `extra.db`) is a tar, gzip- or zstd-compressed, with
one `<name>-<version>/desc` entry per package. The desc file holds `%NAME%`,
`%VERSION%` and `%SHA256SUM%` blocks. A repo keeps exactly ONE version of each
package, so "newest stable" is simply whatever the db lists.

The repo URL travels inside the dep name as `<repo-url>#<package>`, because
the resolver and the cache only ever see the name (the gittag lesson). Arch
package names cannot contain `#`, so `rpartition` splits it unambiguously.
That string is also the cache key and the allowlist label.

The answer is `"<version> <sha256>"`, space-joined like gitcommit's heads:
the judge needs the version to compare and the checksum to check the lock's.

Versions compare with pacman's `vercmp` (a port of libalpm's version.c),
never PEP 440: `1:11.0.20261015-1` is not a version `packaging` can read.
"""

from __future__ import annotations

import io
import tarfile

from dep_freshness.registries.http import Offline, get_bytes

try:  # stdlib since Python 3.14; tarfile's "r:*" reads zstd through it
    import compression.zstd  # noqa: F401

    _HAS_ZSTD = True
except ImportError:  # pragma: no cover - this machine runs 3.15
    _HAS_ZSTD = False

_ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"
_SEPARATOR = "#"


def qualified_name(repo: str, package: str) -> str:
    """The dep name for `package` out of the db at `repo`."""
    return f"{repo.strip()}{_SEPARATOR}{package.strip()}"


def split_name(name: str) -> tuple[str, str]:
    """`(repo_url, package)` back out of a `qualified_name`."""
    repo, _, package = name.rpartition(_SEPARATOR)
    return repo, package


def _fields(desc: str) -> dict[str, str]:
    """`{"NAME": ..., "VERSION": ...}`: the first line under each `%KEY%`."""
    fields: dict[str, str] = {}
    lines = desc.splitlines()
    for number, line in enumerate(lines[:-1]):
        if len(line) > 2 and line.startswith("%") and line.endswith("%"):
            fields.setdefault(line.strip("%"), lines[number + 1].strip())
    return fields


def _open(url: str, body: bytes) -> tarfile.TarFile:
    if body.startswith(_ZSTD_MAGIC) and not _HAS_ZSTD:
        # `Offline`, not a bare error: `Resolver.latest` catches only that, so
        # anything else would crash the gate instead of reporting UNKNOWN
        # (exit 3 under --strict) with this message in the degraded banner.
        raise Offline(
            f"{url} is zstd-compressed; reading it needs Python 3.14+ "
            "(compression.zstd)"
        )
    try:
        return tarfile.open(fileobj=io.BytesIO(body), mode="r:*")
    except tarfile.TarError as exc:
        # A captive portal's HTML is a broken network, not an answer.
        raise Offline(f"{url}: not a repo db ({exc})") from exc


def latest(name: str) -> str | None:
    """`"<version> <sha256>"` the repo lists for the package, or None.

    Matched on `%NAME%`, not the directory name: `foo-` also prefixes
    `foo-git-1.0-1/`. The tar is untrusted, so it is read, never extracted.
    """
    repo, package = split_name(name)
    body = get_bytes(repo)
    if body is None:
        return None
    with _open(repo, body) as tar:
        for member in tar:
            if not (
                member.isfile()
                and member.name.startswith(f"{package}-")
                and member.name.endswith("/desc")
            ):
                continue
            handle = tar.extractfile(member)
            if handle is None:
                continue
            fields = _fields(handle.read().decode("utf-8", errors="replace"))
            if fields.get("NAME") == package and fields.get("VERSION"):
                sha = fields.get("SHA256SUM", "")
                return f"{fields['VERSION']} {sha}".strip()
    return None


# --- vercmp -----------------------------------------------------------------


def _alnum(char: str) -> bool:
    return char.isascii() and char.isalnum()


def _rpmvercmp(a: str, b: str) -> int:
    """libalpm's `rpmvercmp`: segment-wise compare of one EVR component."""
    if a == b:
        return 0
    i = j = 0
    while i < len(a) and j < len(b):
        sep_a, sep_b = i, j
        while i < len(a) and not _alnum(a[i]):
            i += 1
        while j < len(b) and not _alnum(b[j]):
            j += 1
        if i >= len(a) or j >= len(b):
            break
        # A longer separator run sorts higher (`1.0..1` > `1.0.1`).
        if i - sep_a != j - sep_b:
            return -1 if i - sep_a < j - sep_b else 1
        start_a, start_b = i, j
        numeric = a[i].isdigit()
        same_kind = str.isdigit if numeric else (lambda c: c.isascii() and c.isalpha())
        while i < len(a) and same_kind(a[i]):
            i += 1
        while j < len(b) and same_kind(b[j]):
            j += 1
        seg_a, seg_b = a[start_a:i], b[start_b:j]
        if not seg_b:
            # Different segment kinds: a number beats letters.
            return 1 if numeric else -1
        if numeric:
            seg_a, seg_b = seg_a.lstrip("0"), seg_b.lstrip("0")
            if len(seg_a) != len(seg_b):
                return 1 if len(seg_a) > len(seg_b) else -1
        if seg_a != seg_b:
            return 1 if seg_a > seg_b else -1
    if i >= len(a) and j >= len(b):
        return 0
    # One side has more left: `1.0.a` > `1.0`, but `1.0a` < `1.0`.
    if (i >= len(a) and not b[j].isalpha()) or (i < len(a) and a[i].isalpha()):
        return -1
    return 1


def _evr(text: str) -> tuple[str, str, str | None]:
    """`(epoch, pkgver, pkgrel)`; epoch defaults to "0", pkgrel may be None."""
    digits = 0
    while digits < len(text) and text[digits].isdigit():
        digits += 1
    if digits < len(text) and text[digits] == ":":
        epoch, rest = text[:digits] or "0", text[digits + 1 :]
    else:
        epoch, rest = "0", text
    version, dash, release = rest.rpartition("-")
    if not dash:
        return epoch, rest, None
    return epoch, version, release


def vercmp(left: str, right: str) -> int:
    """-1, 0 or 1, exactly as pacman's `vercmp left right` prints.

    A missing pkgrel on either side compares equal on pkgrel, so `1.0`
    matches `1.0-7`.
    """
    if left == right:
        return 0
    epoch_l, ver_l, rel_l = _evr(left)
    epoch_r, ver_r, rel_r = _evr(right)
    result = _rpmvercmp(epoch_l, epoch_r) or _rpmvercmp(ver_l, ver_r)
    if result == 0 and rel_l is not None and rel_r is not None:
        result = _rpmvercmp(rel_l, rel_r)
    return result
