"""Backend edge cases: URL mapping, memoized failures, traversal, deadline."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_ready.backends import DirSite, HttpSite, Response, Site
from agent_ready.report import Undeterminable
from agent_ready.tests.fakes import FakeHttp, resp


class FlakySite(Site):
    """Raises Undeterminable on every fetch and counts the attempts."""

    live = True

    def __init__(self) -> None:
        super().__init__("https://flaky.test")
        self.attempts = 0

    def _fetch(self, path: str, ua: str) -> Response:
        self.attempts += 1
        raise Undeterminable(f"{path}: boom")


def test_to_path_rejects_offsite_and_non_http(tmp_path: Path) -> None:
    site = DirSite(tmp_path)
    assert site.to_path("https://other.test/x") is None
    assert site.to_path("mailto:a@b.test") is None
    assert site.to_path("/rel/") == "/rel/"
    assert site.to_path("https://dist.invalid") == "/"


def test_failures_are_memoized() -> None:
    site = FlakySite()
    for _ in range(2):
        with pytest.raises(Undeterminable, match="boom"):
            site.get("/x")
    assert site.attempts == 1


def test_prefetch_swallows_failures_then_get_raises() -> None:
    site = FlakySite()
    site.prefetch(["/a", "/b", "/a"])
    assert site.attempts == 2
    with pytest.raises(Undeterminable):
        site.get("/a")


def test_base_fetch_is_abstract() -> None:
    with pytest.raises(NotImplementedError):
        Site("https://x.test")._fetch("/", "ua")


def test_dist_never_serves_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "dist"
    root.mkdir()
    (tmp_path / "secret.txt").write_text("nope")
    site = DirSite(root)
    assert site.file_for("/../secret.txt") is None
    assert site.get("/../secret.txt").status == 404


def test_exhausted_budget_is_undeterminable() -> None:
    site = HttpSite("https://budget.test/anything", budget=0)
    with pytest.raises(Undeterminable, match="time budget"):
        site.get("/")


def test_fake_http_serves_canned_pages() -> None:
    site = FakeHttp({"/": resp("hi")})
    assert site.get("/").text == "hi"
    assert site.get("/nope").status == 404
