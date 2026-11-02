"""Tests for `toolbox.load_safe`, the fail-open typed view the gates use."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import pytest

from leetcode_coach import toolbox

if TYPE_CHECKING:
    from pathlib import Path


def test_load_reads_the_configured_toolbox() -> None:
    box = toolbox.load_safe()
    xor = box.entries[0]
    assert xor.name == "XOR"
    assert xor.names() == ("XOR", "^", "exclusive or", "bitwise xor")
    assert xor.properties == ("self-inverse", "commutative", "associative")
    assert box.properties["constant-space"] == "memory does not grow with the input"


def test_aliases_and_properties_are_optional(tmp_path: Path) -> None:
    path = tmp_path / "box.json"
    path.write_text(json.dumps({"entries": [{"name": "stack"}]}), encoding="utf-8")
    box = toolbox.load_safe(path)
    assert box.entries[0].names() == ("stack",)
    assert box.entries[0].properties == ()
    assert box.properties == {}


@pytest.mark.parametrize(
    "body",
    [
        "not json",
        json.dumps([]),
        json.dumps({"entries": "XOR"}),
        json.dumps({"entries": [{"aliases": []}]}),
        json.dumps({"entries": [{"name": "x", "aliases": [1]}]}),
        json.dumps({"entries": [], "properties": {"p": 3}}),
    ],
)
def test_a_broken_toolbox_is_empty_and_logged(
    tmp_path: Path, body: str, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "box.json"
    path.write_text(body, encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="leetcode_coach.toolbox"):
        assert toolbox.load_safe(path) == toolbox.Toolbox()
    assert "unusable" in caplog.text


def test_a_missing_toolbox_is_empty(tmp_path: Path) -> None:
    assert toolbox.load_safe(tmp_path / "nope.json").entries == ()
