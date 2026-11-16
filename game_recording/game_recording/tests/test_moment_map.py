# Copyright (c) 2026 Krzysztof Rudnicki
"""A second, made-up game adopts the package by configuration alone."""

import pytest

from game_recording import moments
from game_recording.config import COMMON_DIRECT, Config, Moment, MomentMap, Row
from game_recording.tests.test_helpers import entry


def boss_hit(row: Row) -> Moment | None:
    if row.get("event") != "boss_hit":
        return None
    return moments.moment(row, "boss", "hit the boss", dmg=row.get("dmg"))


def never(_row: Row) -> Moment | None:
    return None


def hijack_buy(row: Row) -> Moment | None:
    return moments.moment(row, "hijacked", "custom") if row.get("event") == "buy" else None


def second(_row: Row) -> Moment | None:
    return moments.moment({"ms": 1}, "second", "second")


def ammo_low(rows: list[Row]) -> list[Moment]:
    return [moments.moment(r, "ammo_low", "ammo low") for r in rows if r.get("ammo", 99) < 5]


def classify(rows: list[Row], moment_map: MomentMap) -> list[Moment]:
    return moments.classify(rows, moment_map)


def test_default_map_has_only_the_common_events() -> None:
    plain = MomentMap()
    assert plain.direct is COMMON_DIRECT
    assert plain.passthrough_prefixes == ()
    assert classify([entry("hub_open", 1)], plain)[0]["kind"] == "hub_open"
    assert classify([entry("buy", 1)], plain) == []


def test_a_game_adds_its_own_direct_events() -> None:
    game = MomentMap(direct={**COMMON_DIRECT, "loot": ("item",)})
    found = classify([entry("loot", 5, 1, game="g", item="axe")], game)
    assert found[0]["label"] == "loot g axe"
    assert found[0]["item"] == "axe"


def test_empty_passthrough_prefixes_pass_nothing_through() -> None:
    assert classify([entry("evt_x", 1), entry("", 2)], MomentMap()) == []


def test_set_passthrough_prefixes_pass_matching_events() -> None:
    game = MomentMap(passthrough_prefixes=("quest_",))
    found = classify([entry("quest_done", 1, 1, stars=3), entry("evt_x", 2)], game)
    assert [m["kind"] for m in found] == ["quest_done"]
    assert found[0]["stars"] == 3


def test_game_end_fields_are_configurable() -> None:
    game = MomentMap(game_end_fields=("score",))
    m = classify([entry("game_end", 1, 1, outcome="win", score=9, elapsed_s=4)], game)[0]
    assert m["score"] == 9
    assert "elapsed_s" not in m
    assert m["label"] == "game_end win"


def test_game_end_without_an_outcome_has_a_bare_label() -> None:
    assert classify([entry("game_end", 1)], MomentMap())[0]["label"] == "game_end"


def test_error_kinds_are_configurable() -> None:
    game = MomentMap(error_kinds=frozenset({"stderr"}))
    assert classify([entry("engine_error", 1, kind="stderr", message="x")], game)[0]["error_kind"] == "stderr"
    assert classify([entry("engine_error", 1, kind="script_error", message="x")], game) == []


def test_hitch_merge_s_override_changes_the_burst() -> None:
    rows = [entry("hitch", 1000, 1, dur_ms=1), entry("hitch", 1500, 2, dur_ms=2)]
    assert len(moments.derive(rows, MomentMap(hitch_merge_s=0.1))) == 2
    assert len(moments.derive(rows, MomentMap(hitch_merge_s=5.0))) == 1
    assert MomentMap().hitch_merge_s == 2.0


def test_classifier_hook_makes_a_moment_the_built_ins_do_not() -> None:
    game = MomentMap(classifiers=(boss_hit,))
    found = classify([entry("boss_hit", 7, 1, dmg=12), entry("hub_open", 8, 2)], game)
    assert [m["kind"] for m in found] == ["boss", "hub_open"]
    assert found[0]["dmg"] == 12


def test_classifier_hooks_run_before_built_ins() -> None:
    game = MomentMap(direct={**COMMON_DIRECT, "buy": ()}, classifiers=(hijack_buy,))
    assert classify([entry("buy", 1)], game)[0]["kind"] == "hijacked"


def test_first_non_none_classifier_wins() -> None:
    game = MomentMap(classifiers=(never, boss_hit, second))
    assert classify([entry("boss_hit", 1, 1)], game)[0]["kind"] == "boss"
    assert classify([entry("other", 1, 1)], game)[0]["kind"] == "second"


def test_session_rule_hook_moments_join_the_hitch_burst() -> None:
    game = MomentMap(session_rules=(ammo_low,))
    rows = [entry("hitch", 1000, 1, dur_ms=5), entry("shot", 2000, 2, ammo=3), entry("shot", 3000, 3, ammo=40)]
    found = moments.derive(rows, game)
    assert [m["kind"] for m in found] == ["hitch", "ammo_low"]
    assert moments.derive(rows, MomentMap()) == found[:1]


def test_moment_builder_fields() -> None:
    row = entry("evt_x", 42, 9, game="g")
    m = moments.moment(row, "kind", "label", extra=1)
    assert m == {"kind": "kind", "label": "label", "event": "evt_x", "seq": 9, "ms": 42, "game": "g", "extra": 1}


def test_moment_builder_omits_an_empty_game() -> None:
    assert "game" not in moments.moment(entry("evt_x", 42), "k", "l")


def test_config_env_names_use_the_prefix() -> None:
    cfg = Config(binaries_dir="b", env_prefix="ZED")
    assert cfg.env_name("NO_RECORD") == "ZED_NO_RECORD"
    assert cfg.blocking_flags == ("ZED_NO_RECORD",)
    assert cfg.moments == MomentMap()


def test_extra_blocking_flags_follow_the_no_record_flag() -> None:
    cfg = Config(binaries_dir="b", env_prefix="ZED", extra_blocking_flags=("ZED_CI",))
    assert cfg.blocking_flags == ("ZED_NO_RECORD", "ZED_CI")


@pytest.mark.parametrize(("override", "expected"), [("", "ZED_BINARIES"), ("MY_BINS", "MY_BINS")])
def test_binaries_var_defaults_and_overrides(override: str, expected: str) -> None:
    assert Config(binaries_dir="b", env_prefix="ZED", binaries_env=override).binaries_var == expected
