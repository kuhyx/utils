# Copyright (c) 2026 Krzysztof Rudnicki
"""When a run is recorded (a person's dev play) and when never (bots, tests, headless)."""

import pytest

from game_recording import policy
from game_recording.config import Config
from game_recording.tests.test_helpers import CONFIG

LIVE = {"DISPLAY": ":0"}
DEV = ["godot", "--", "--dev"]


def test_dev_run_is_recorded() -> None:
    decision = policy.decide(["godot", "--path", "/r", "--", "--dev"], LIVE, CONFIG)
    assert decision.record, decision.reason
    assert decision.reason == "dev play"


def test_exported_dev_build_is_recorded() -> None:
    assert policy.decide(["/b/game.x86_64", "--", "--dev", "--dev-tag=v01"], LIVE, CONFIG).record


@pytest.mark.parametrize("args", [["godot", "--"], ["godot", "--", "--no-dev", "--dev"]])
def test_no_dev_flag_means_no_recording(args: list[str]) -> None:
    decision = policy.decide(args, LIVE, CONFIG)
    assert not decision.record
    assert decision.reason == "not a --dev run"


@pytest.mark.parametrize(
    "marker", ["--autodrive=watch", "--result-file=/t/r", "--expect-window=1280x800", "--save-dir=/t"]
)
def test_each_bot_marker_blocks(marker: str) -> None:
    decision = policy.decide(["godot", "--", "--dev", marker], LIVE, CONFIG)
    assert not decision.record
    assert marker in decision.reason


@pytest.mark.parametrize(
    "engine",
    [["--headless"], ["--audio-driver", "Dummy"], ["--display-driver", "headless"]],
)
def test_headless_and_muted_engine_runs_block(engine: list[str]) -> None:
    decision = policy.decide(["godot", *engine, "--", "--dev"], LIVE, CONFIG)
    assert not decision.record
    assert decision.reason.startswith("headless or muted run")


def test_engine_flags_after_the_double_dash_are_the_games_own() -> None:
    assert policy.decide(["godot", "--", "--dev", "--headless"], LIVE, CONFIG).record


def test_engine_flag_without_a_value_or_with_another_value_does_not_block() -> None:
    assert policy.decide(["godot", "--audio-driver", "--dev"], LIVE, CONFIG).record
    assert policy.decide(["godot", "--audio-driver", "Pulse", "--dev"], LIVE, CONFIG).record
    assert policy.decide(["godot", "--audio-driver"], LIVE, CONFIG).reason == "not a --dev run"


def test_no_display_blocks() -> None:
    decision = policy.decide(DEV, {}, CONFIG)
    assert not decision.record
    assert decision.reason == "no DISPLAY"


@pytest.mark.parametrize(
    ("env", "reason"),
    [
        ({"DEMO_NO_RECORD": "1"}, "DEMO_NO_RECORD=1"),
        ({"DEMO_FEEDBACK_DIR": "/t"}, "DEMO_FEEDBACK_DIR is set"),
    ],
)
def test_env_opt_outs_block(env: dict[str, str], reason: str) -> None:
    decision = policy.decide(DEV, {**LIVE, **env}, CONFIG)
    assert not decision.record
    assert decision.reason == reason


def test_flag_set_to_zero_is_off() -> None:
    assert policy.decide(DEV, {**LIVE, "DEMO_NO_RECORD": "0"}, CONFIG).record


def test_another_games_env_prefix_does_not_block() -> None:
    assert policy.decide(DEV, {**LIVE, "OTHER_NO_RECORD": "1"}, CONFIG).record


def test_extra_blocking_flags_of_the_config_block() -> None:
    config = Config(binaries_dir="b", env_prefix="DEMO", extra_blocking_flags=("DEMO_CI",))
    assert policy.decide(DEV, {**LIVE, "DEMO_CI": "1"}, config).reason == "DEMO_CI=1"


def test_force_overrides_bot_rules_but_not_a_missing_display() -> None:
    args = ["godot", "--audio-driver", "Dummy", "--", "--dev", "--autodrive", "--save-dir=/t"]
    forced = policy.decide(args, LIVE, CONFIG, force=True)
    assert forced.record
    assert forced.reason == "forced"
    assert not policy.decide(args, {}, CONFIG, force=True).record


def test_the_reason_names_the_blocker() -> None:
    assert "--autodrive" in policy.decide(["godot", "--", "--dev", "--autodrive"], LIVE, CONFIG).reason


def test_session_and_feedback_dir_come_from_the_args() -> None:
    args = ["godot", "--", "--dev", "--session-id=abc", "--feedback-dir=/fb"]
    assert policy.arg_value(args, "--session-id=") == "abc"
    assert policy.arg_value(args, "--feedback-dir=") == "/fb"
    assert policy.arg_value(args, "--nope=") == ""
