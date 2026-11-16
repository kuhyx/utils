# Copyright (c) 2026 Krzysztof Rudnicki
"""Which telemetry entries become moments, and what each one keeps."""

from typing import TYPE_CHECKING

import pytest

from game_recording import moments
from game_recording.tests.test_helpers import MOMENT_MAP, entry

if TYPE_CHECKING:
    from game_recording.config import Moment, Row


def one(row: Row, kind: str) -> Moment:
    found = moments.classify([row], MOMENT_MAP)
    assert [m["kind"] for m in found] == [kind], row
    return found[0]


def test_session_start_and_hub_are_moments() -> None:
    one(entry("session_start", 0, 1), "session_start")
    assert one(entry("hub_open", 50, 2), "hub_open")["label"] == "hub_open"


def test_game_start_keeps_the_whole_loadout() -> None:
    row = entry("game_start", 9000, 2, game="command", loadout=["double_men", "stew"], cost=6, men=200, seed=7)
    m = one(row, "game_start")
    assert m["game"] == "command"
    assert m["loadout"] == ["double_men", "stew"]
    assert (m["cost"], m["men"], m["seed"]) == (6, 200, 7)
    assert m["label"] == "game_start command double_men,stew 6 200 7"
    assert (m["ms"], m["seq"], m["event"]) == (9000, 2, "game_start")


def test_game_end_names_the_outcome() -> None:
    m = one(entry("game_end", 9000, 2, outcome="win", elapsed_s=20.5), "game_end")
    assert m["label"] == "game_end win"
    assert m["elapsed_s"] == 20.5


def test_a_buy_and_an_order_keep_their_fields() -> None:
    buy = one(entry("buy", 100, 2, buff="moose", bought=True, cost=3), "buy")
    assert buy["label"] == "buy moose True 3"
    order = one(entry("command", 200, 3, order="rally", pos=[120.0, 80.0]), "command")
    assert order["order"] == "rally"
    assert order["label"] == "command rally 120.0,80.0"


def test_pause_lab_reset_quit_and_session_end() -> None:
    one(entry("pause_open", 9000, 2), "pause_open")
    assert one(entry("pause_close", 9000, 2, paused_s=3.0), "pause_close")["paused_s"] == 3.0
    lab = one(entry("lab_result", 9000, 2, wins=12, runs=30, mean_seconds=19.5), "lab_result")
    assert lab["label"] == "lab_result 12 30 19.5"
    assert one(entry("reset_progress", 9000, 2, files=1), "reset_progress")["files"] == 1
    assert one(entry("quit", 9000, 2, reason="menu"), "quit")["reason"] == "menu"
    end = one(entry("session_end", 9000, 2, reason="exit", elapsed_s=120.0), "session_end")
    assert end["label"] == "session_end exit 120.0"


def test_an_annotation_carries_its_png_and_mark_count() -> None:
    m = one(entry("annotation", 9000, 2, image="/fb/x/annotated.png", marks=3, bundle="/fb/x"), "annotation")
    assert m["label"] == "F12 annotation"
    assert m["png"] == "/fb/x/annotated.png"
    assert m["marks"] == 3


def test_real_engine_errors_are_moments() -> None:
    row = entry("engine_error", 9000, 2, kind="script_error", message="boom " * 30, file="a.gd", line=3)
    m = one(row, "engine_error")
    assert m["error_kind"] == "script_error"
    assert m["label"] == "engine_error " + ("boom " * 30)[:60]
    assert (m["file"], m["line"]) == ("a.gd", 3)


@pytest.mark.parametrize("kind", ["warning", "stderr"])
def test_engine_noise_is_not_a_moment(kind: str) -> None:
    assert moments.classify([entry("engine_error", 1, 1, kind=kind, message="x")], MOMENT_MAP) == []


def test_sim_events_the_game_may_log_later_pass_through() -> None:
    m = one(entry("evt_wall_breached", 9000, 2, at=[1, 2], tag="v01"), "evt_wall_breached")
    assert m["at"] == [1, 2]
    assert "tag" not in m
    assert "session" not in m
    one(entry("milestone_first_win", 9000, 2), "milestone_first_win")


@pytest.mark.parametrize("name", ["recording_sync", "screen", "hitch", "", "perf"])
def test_everything_else_is_not_a_moment(name: str) -> None:
    assert moments.classify([entry(name, 9000, 2)], MOMENT_MAP) == []


def test_event_name_is_the_event_field() -> None:
    assert moments.event_name({"event": "buy"}) == "buy"
    assert moments.event_name({}) == ""
