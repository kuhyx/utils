"""Git-tag deps outside kuhyx/utils are looked up in THEIR repo, not utils.

`leisure-watch @ git+https://github.com/kuhyx/leisure-watch@leisure-watch-v0.1.0`
was asked of kuhyx/utils, which has no `leisure-watch-v*` tag, so the answer
came back undeterminable (exit 3) in steam-backlog-enforcer. The shared libs
in utils must keep their bare names: those are the allowlist labels and the
cache keys every consumer already has.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dep_freshness._tables import UTILS_TAG_REMOTE
from dep_freshness.parsers import python
from dep_freshness.registries import gittag

LW_URL = "https://github.com/kuhyx/leisure-watch"
REQS = f"""\
leisure-watch @ git+{LW_URL}@leisure-watch-v0.1.0
earned-time @ git+https://github.com/kuhyx/utils@earned-time-v0.14.0#subdirectory=earned_time
gatelock @ git+https://github.com/kuhyx/utils.git@gatelock-v0.11.0#subdirectory=gatelock
"""


def _names(tmp_path: Path) -> dict[str, str]:
    path = tmp_path / "requirements.txt"
    path.write_text(REQS, encoding="utf-8")
    return {d.constraint: d.name for d in python.parse_requirements(path)}


def test_a_foreign_repo_pin_is_qualified_by_its_source(tmp_path):
    names = _names(tmp_path)
    assert (
        names["leisure-watch-v0.1.0"] == "github.com/kuhyx/leisure-watch:leisure-watch"
    )


def test_utils_pins_keep_their_bare_names(tmp_path):
    names = _names(tmp_path)
    assert names["earned-time-v0.14.0"] == "earned-time"
    assert names["gatelock-v0.11.0"] == "gatelock"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://github.com/kuhyx/utils", "pkg"),
        ("https://GitHub.com/Kuhyx/Utils.git/", "pkg"),
        ("ssh://git@github.com/kuhyx/utils.git", "pkg"),
        ("https://gitlab.com/someone/thing.git", "gitlab.com/someone/thing:pkg"),
        ("not a url", "pkg"),
        ("https://github.com/lonely", "pkg"),
    ],
)
def test_qualified_name(url, expected):
    assert gittag.qualified_name(url, "pkg") == expected


@pytest.fixture
def remotes(monkeypatch):
    seen: list[str] = []

    def fake_ls_remote(remote, *_args):
        seen.append(remote)
        return [
            "aaa\trefs/tags/leisure-watch-v0.1.0",
            "bbb\trefs/tags/leisure-watch-v0.1.1",
        ]

    monkeypatch.setattr(gittag, "ls_remote", fake_ls_remote)
    return seen


def test_a_qualified_name_asks_its_own_repo(remotes):
    assert gittag.latest("github.com/kuhyx/leisure-watch:leisure-watch") == "0.1.1"
    assert remotes == [LW_URL]


def test_a_bare_name_still_asks_utils(remotes):
    assert gittag.latest("leisure-watch") == "0.1.1"
    assert remotes == [UTILS_TAG_REMOTE]
