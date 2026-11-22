"""The pacman-repo adapter: pacman `vercmp` order and reading a repo `.db`.

Versions here are `epoch:pkgver-pkgrel`, which PEP 440 cannot read at all:
`versions.behind` answers False for every pair, so a stale lock would read
as current. The ordering tests below come from the vercmp(8) man page, and
the differential test checks them against the real `/usr/bin/vercmp`.
"""

from __future__ import annotations

import io
import itertools
import shutil
import subprocess
import tarfile

import pytest

from dep_freshness.registries import pacman_repo
from dep_freshness.registries.http import Offline

REPO = "https://mirror.example.org/repo/x86_64/extra/extra.db"
SHA = "ab" * 32

# vercmp(8): "1.0a < 1.0b < 1.0beta < 1.0p < 1.0pre < 1.0rc < 1.0 < 1.0.a < 1.0.1"
MAN_ORDER = ["1.0a", "1.0b", "1.0beta", "1.0p", "1.0pre", "1.0rc", "1.0", "1.0.a",
             "1.0.1"]
PAIRS = [
    ("1:1.0", "2.0", 1),
    ("0:2.0", "2.0", 0),
    ("1:11.0.20261015-1", "1:10.0.20250101-1", 1),
    ("1:11.0.20261015-1", "1:11.0.20261015-1", 0),
    ("1.0-1", "1.0-2", -1),
    ("1.0", "1.0-7", 0),  # a missing pkgrel compares equal
    ("1.0.0", "1.0", 1),
    ("1.0_1", "1.0.1", 0),  # any non-alphanumeric run is one separator
    ("1.0", "1.0.0.0", -1),
    ("2.0", "10.0", -1),
    ("1.001", "1.1", 0),
    ("r123", "r45", 1),
]


@pytest.mark.parametrize(("left", "right"), list(itertools.pairwise(MAN_ORDER)))
def test_vercmp_follows_the_man_page_order(left, right):
    assert pacman_repo.vercmp(left, right) == -1
    assert pacman_repo.vercmp(right, left) == 1


@pytest.mark.parametrize(("left", "right", "expected"), PAIRS)
def test_vercmp_epoch_and_pkgrel(left, right, expected):
    assert pacman_repo.vercmp(left, right) == expected


@pytest.mark.skipif(not shutil.which("vercmp"), reason="pacman's vercmp absent")
@pytest.mark.parametrize(
    ("left", "right"),
    [*itertools.pairwise(MAN_ORDER), *((a, b) for a, b, _ in PAIRS)],
)
def test_vercmp_agrees_with_pacman(left, right):
    real = subprocess.run(
        ["vercmp", left, right], capture_output=True, text=True, check=True
    ).stdout.strip()
    assert pacman_repo.vercmp(left, right) == int(real)


def _desc(name: str, version: str, sha: str = SHA) -> bytes:
    return (
        f"%FILENAME%\n{name}-{version}-x86_64.pkg.tar.zst\n\n%NAME%\n{name}\n\n"
        f"%VERSION%\n{version}\n\n%SHA256SUM%\n{sha}\n\n"
    ).encode()


def build_db(
    packages: dict[str, str], compression: str = "gz", sha: str = SHA
) -> bytes:
    """A repo db the way repo-add writes it: one `<name>-<ver>/desc` per package."""
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode=f"w:{compression}") as tar:
        for name, version in packages.items():
            body = _desc(name, version, sha)
            info = tarfile.TarInfo(f"{name}-{version}/desc")
            info.size = len(body)
            tar.addfile(info, io.BytesIO(body))
    return raw.getvalue()


@pytest.fixture
def serve(monkeypatch):
    """Answer the next `get_bytes` with `body`, recording the URL asked for."""
    asked: list[str] = []

    def install(body):
        def fake(url):
            asked.append(url)
            return body
        monkeypatch.setattr(pacman_repo, "get_bytes", fake)
        return asked
    return install


@pytest.mark.parametrize("compression", ["gz", "zst"])
def test_latest_reads_version_and_sha_from_the_db(serve, compression):
    asked = serve(build_db({"proton-native": "1:11.0-1", "zlib": "1.3-1"},
                           compression))
    name = pacman_repo.qualified_name(REPO, "proton-native")
    assert pacman_repo.latest(name) == f"1:11.0-1 {SHA}"
    assert asked == [REPO]


def test_a_sibling_sharing_the_name_prefix_is_not_the_package(serve):
    serve(build_db({"proton-native-v3": "9:9.0-1", "proton-native": "1:2.0-1"}))
    name = pacman_repo.qualified_name(REPO, "proton-native")
    assert pacman_repo.latest(name).split()[0] == "1:2.0-1"


def test_a_package_the_db_does_not_list_is_none(serve):
    serve(build_db({"zlib": "1.3-1"}))
    assert pacman_repo.latest(pacman_repo.qualified_name(REPO, "nope")) is None


def test_a_missing_db_is_none(serve):
    serve(None)
    assert pacman_repo.latest(pacman_repo.qualified_name(REPO, "x")) is None


def test_a_db_that_is_not_a_tar_is_offline(serve):
    serve(b"<html>captive portal</html>")
    with pytest.raises(Offline):
        pacman_repo.latest(pacman_repo.qualified_name(REPO, "x"))


def test_zstd_without_compression_zstd_names_the_missing_module(
    serve, monkeypatch
):
    serve(build_db({"x": "1.0-1"}, "zst"))
    monkeypatch.setattr(pacman_repo, "_HAS_ZSTD", False)
    with pytest.raises(Offline, match="compression.zstd"):
        pacman_repo.latest(pacman_repo.qualified_name(REPO, "x"))


def test_qualified_name_round_trips():
    assert pacman_repo.split_name(pacman_repo.qualified_name(REPO, "x")) == (
        REPO,
        "x",
    )
