# Copyright (c) 2026 Krzysztof Rudnicki
"""The browser adapter's plumbing: env-file config, HTTP, span maths."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING, Any

from focus_project.sources import browser

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

CFG = browser.Config("http://tracker.test", "tok")


def test_config_from_env_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    env = tmp_path / "env"
    env.write_text("# c\nKT_URL=http://h:1\nKT_TOKEN='abc'\nJUNK\n")
    monkeypatch.setenv("KUHYTRACK_ENV", str(env))
    assert browser._config() == browser.Config("http://h:1", "abc")


def test_config_missing_file_is_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("KUHYTRACK_ENV", str(tmp_path / "absent"))
    assert browser._config() is None


def test_config_without_url_is_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env = tmp_path / "env"
    env.write_text("KT_TOKEN=abc\n")
    monkeypatch.setenv("KUHYTRACK_ENV", str(env))
    assert browser._config() is None


def test_get_json_sends_bearer_and_query(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_open(req: Any, timeout: float) -> io.BytesIO:  # noqa: ANN401
        seen["url"] = req.full_url
        seen["auth"] = req.get_header("Authorization")
        seen["timeout"] = timeout
        return io.BytesIO(b'{"ok": 1}')

    monkeypatch.setattr(browser, "_urlopen", fake_open)
    assert browser._get_json(CFG, "/x", {"a": "b"}) == {"ok": 1}
    assert seen == {
        "url": "http://tracker.test/x?a=b",
        "auth": "Bearer tok",
        "timeout": 5,
    }


def test_get_json_without_token_sends_no_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    def fake_open(req: Any, timeout: float) -> io.BytesIO:  # noqa: ANN401
        seen["auth"] = req.get_header("Authorization")
        return io.BytesIO(b"[]")

    monkeypatch.setattr(browser, "_urlopen", fake_open)
    assert browser._get_json(browser.Config("http://t", ""), "/x") == []
    assert seen["auth"] is None


def test_intersect_and_merge() -> None:
    merged = browser._merge([(5, 9), (0, 3), (2, 4), (9, 10)])
    assert merged == [(0, 4), (5, 10)]
    assert browser._intersect(merged, [(3, 6), (8, 20)]) == [(3, 4), (5, 6), (8, 10)]


def test_blank_pattern_is_ignored() -> None:
    assert browser._needles((" ", "LeetCode.com")) == (["leetcode.com"], ["leetcode"])
