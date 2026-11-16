# Copyright (c) 2026 Krzysztof Rudnicki. MIT License.
"""Sealing: the tutor's contract vectors still open and classify the same."""

from __future__ import annotations

import asyncio
import json

from crdt_sync import E2eCipher
import pytest

from rtdb_relay import sse
from rtdb_relay.layout import E2eLayoutError, Layout, parts_of
from rtdb_relay.seal import SEALED, Sealer, dumps
from rtdb_relay.tests._fake_rtdb import ROOT, FakeRtdb
from rtdb_relay.tests._layouts import TUTOR, VECTORS


def _sealer() -> Sealer:
    return Sealer(E2eCipher(bytes.fromhex(VECTORS["key_hex"])), TUTOR)


def test_vectors_pin_the_rules_and_open() -> None:
    assert VECTORS["root"] == TUTOR.root == "tutor/v1-e2e"
    assert VECTORS["sealed_key"] == SEALED
    for rule in VECTORS["rules"]:
        assert TUTOR.classify(parts_of(rule["path"])).kind == rule["kind"], rule
    s = _sealer()
    for unit in VECTORS["units"]:
        assert s.open(unit["path"], unit["stored"]) == unit["value"]
        assert set(unit["stored"]) - {SEALED} <= {"created", "at", "seen", "beat"}


def test_sealed_bytes_are_the_cipher_over_compact_json_at_the_full_path() -> None:
    """Differential: our seal == crdt_sync's cipher on the vectors' format."""
    cipher = E2eCipher(bytes.fromhex(VECTORS["key_hex"]))
    s = Sealer(cipher, TUTOR)
    for unit in VECTORS["units"]:
        ours = s.seal(unit["path"], unit["value"])
        assert isinstance(ours, dict)
        assert isinstance(unit["stored"], dict)
        clear = {k: v for k, v in unit["stored"].items() if k != SEALED}
        assert {k: v for k, v in ours.items() if k != SEALED} == clear
        aad = f"{TUTOR.root}/{unit['path']}"
        text = cipher.open(ours[SEALED], path=aad)
        value = unit["value"]
        rest = (
            {k: v for k, v in value.items() if k not in clear}
            if isinstance(value, dict)
            else value
        )
        assert text == dumps(rest)
        # And the vector's own blob opens to the same plaintext bytes.
        assert cipher.open(unit["stored"][SEALED], path=aad) == text


def test_seal_refuses_unknown_and_inside_unit_writes() -> None:
    s = _sealer()
    with pytest.raises(E2eLayoutError):
        s.seal("secrets", {"a": 1})
    with pytest.raises(E2eLayoutError):
        s.seal("sessions", "flat")  # a scalar where a tree belongs
    with pytest.raises(E2eLayoutError):
        s.seal_patch("sessions/s/msgs/m0001", {"text": "x"})
    with pytest.raises(E2eLayoutError):
        s.open("stats/today/x", 1)
    assert s.unit_path("stats/today/x") == "stats/today"
    assert s.unit_path("stats/today") is None
    assert s.seal("live", {"a": None}) is None  # pruned to nothing
    assert s.seal("meta/x", 1) == 1
    assert s.seal_patch("prefs", {"a": None}) == {"a": None}


def test_open_drops_a_moved_or_tampered_unit_and_keeps_plaintext() -> None:
    s = _sealer()
    sealed = s.seal("prefs/current_subject", "car")
    assert s.open("prefs", {"current_subject": sealed}) == {"current_subject": "car"}
    assert s.open("prefs", {"other": sealed}) == {}
    assert s.open("prefs", {"current_subject": {SEALED: "AQ=="}}) == {}
    assert s.open("prefs/current_subject", "car") == "car"
    assert s.open("sessions", [{"x": 1}]) == [{"x": 1}]
    assert s.open("meta", {"a": 1}) == {"a": 1}


def test_root_override_changes_the_aad() -> None:
    layout = Layout(root="app/v1-e2e", clear=(), units={"x": frozenset()})
    cipher = E2eCipher(bytes(range(32)))
    blob = Sealer(cipher, layout).seal("x", 1)
    assert Sealer(cipher, layout, root="other").open("x", blob) is None
    assert Sealer(cipher, layout).open("x", blob) == 1


def test_rtdb_reads_below_a_unit_and_streams_open() -> None:
    fake = FakeRtdb()
    fake.set(f"{ROOT}/stats/today", {"new_cap": 25})

    async def go() -> None:
        db = fake.rtdb()
        assert await db.get("stats/today/new_cap") == 25
        assert await db.get("stats/today/nope/deeper") is None
        stream = sse.listen(db, "stats")
        first = await anext(stream)
        assert first.data == {"today": {"new_cap": 25}}
        await db.patch("stats", {"days": {"2026-11-12": {"m": 3}}})
        second = await anext(stream)
        assert second.kind == "patch"
        assert second.data == {"days": {"2026-11-12": {"m": 3}}}
        await stream.aclose()
        await db.aclose()

    asyncio.run(go())
    assert "new_cap" not in json.dumps(fake.raw)
