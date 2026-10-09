# Copyright (c) 2026 Krzysztof Rudnicki
"""What counts as a real credit, and failing closed when none is on record."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from typing import TYPE_CHECKING

import pytest

from earned_time import (
    ANKI,
    LEETCODE,
    READING,
    WORKOUT,
    maturity,
    real_credit,
)
from earned_time._evidence import credit_day
from earned_time.tests._maturity_rows import (
    KEY,
    TODAY,
    at,
    grant,
    ledger_file,
    signed,
    solve,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize(
    ("row", "real"),
    [
        (solve(TODAY), True),
        ({**solve(TODAY), "hmac": "forged"}, False),
        ("not a row", False),
        (signed({"kind": "charge", "entry_id": "x", "amount": 1}), False),
        (signed({"kind": "credit", "entry_id": "x", "detail": "flat"}), True),
        (signed({"kind": "credit", "entry_id": "x"}), True),
        (solve(TODAY, detail={"source": "manual"}), False),
        (solve(TODAY, detail={"source": "manual_grant"}), False),
        (solve(TODAY, entry="manual:2026-10-09"), False),
        (solve(TODAY, entry="manual_grant:anki:2026-10-09"), False),
        (solve(TODAY, amount=0), False),
        (solve(TODAY, amount=-3), False),
        (solve(TODAY, amount="5"), False),
        (solve(TODAY, amount=2.5), True),
        (grant(), True),
        (grant(amount=-1), False),
        (grant(amount="0"), False),
        (grant(source="manual_grant"), False),
        (grant(entry="manual_grant:session:a"), False),
        ({**grant(), "hmac": "forged"}, False),
        ({k: v for k, v in grant().items() if k != "hmac"}, False),
        (grant(grant_of=""), False),
        (grant(grant_of=7), False),
        (solve(TODAY, amount=0, detail="flat"), False),
    ],
)
def test_real_credit(row: object, real: object) -> None:
    assert real_credit(row, KEY) is real


def test_a_matcher_cannot_launder_a_manual_grant(
    tmp_path: Path, key_file: Path
) -> None:
    grant = signed(
        {
            "kind": "credit",
            "entry_id": "manual_grant:anki:2026-10-09",
            "amount": 0,
            "detail": {"anki_day": "2026-10-09", "source": "manual_grant"},
        }
    )
    assert ANKI.match is not None
    assert credit_day(ANKI, grant) == TODAY  # anki_match alone would count it
    verdict = maturity(ANKI, ledger_file(tmp_path, [grant]), key_file, TODAY)
    assert (verdict.level, verdict.credit_days, verdict.penalty_start) == (
        "new",
        0,
        None,
    )


def test_credit_day_asks_the_matcher_on_each_candidate_day() -> None:
    rest: dict[str, object] = {
        "kind": "credit",
        "entry_id": "rest_day:2026-10-09",
        "day": "2026-10-09",
        "created_at": f"{TODAY - timedelta(days=1)}T20:00:00+00:00",
        "detail": {"source": "rest_day", "declared_at": "1"},
    }
    assert credit_day(WORKOUT, rest) == TODAY  # by its ``day``, not created_at
    bare = {"kind": "credit", "entry_id": "x", "day": "soon", "detail": {}}
    assert credit_day(LEETCODE, bare) is None
    flat = {"kind": "credit", "entry_id": "x", "day": "soon", "detail": "flat"}
    assert credit_day(ANKI, flat) is None


def test_a_re_evaluation_grant_counts_its_day(tmp_path: Path, key_file: Path) -> None:
    session = signed(
        {
            "kind": "credit",
            "entry_id": "session:a",
            "amount": 17,
            "detail": {"bonus": "0", "ended_at": at(TODAY)},
        }
    )
    ledger = ledger_file(tmp_path, [session, grant()])
    verdict = maturity(READING, ledger, key_file, TODAY)
    assert (verdict.credit_days, verdict.credit_rows) == (1, 1)
    assert verdict.first_credit == TODAY


def test_unreadable_key_or_ledger_is_new(tmp_path: Path, key_file: Path) -> None:
    unconfirmed = replace(READING, confirmed_on=None)
    no_key = maturity(unconfirmed, ledger_file(tmp_path, []), tmp_path / "nokey", TODAY)
    assert not no_key.checked
    assert no_key.reasons[0].startswith("could not check: HMAC key")
    no_ledger = maturity(LEETCODE, tmp_path / "missing.json", key_file, TODAY)
    assert not no_ledger.checked
    assert no_ledger.reasons[0].startswith("could not check: ledger")
    for verdict in (no_key, no_ledger):
        assert (verdict.level, verdict.penalty_start, verdict.credit_rows) == (
            "new",
            None,
            0,
        )
    assert no_key.reasons[-1].startswith("never paid out: no penalty")


def test_a_confirmed_gate_fails_closed_when_it_cannot_be_checked(
    tmp_path: Path, key_file: Path
) -> None:
    assert READING.confirmed_on == date(2026, 10, 2)
    expected = date(2026, 10, 3)  # max(penalty_from 10-01, confirmed_on + 1)
    no_key = maturity(READING, ledger_file(tmp_path, []), tmp_path / "nokey", TODAY)
    locked = tmp_path / "locked.json"
    locked.write_text("{not json", encoding="utf-8")
    no_ledger = maturity(READING, locked, key_file, TODAY)
    for verdict in (no_key, no_ledger):
        assert not verdict.checked
        assert (verdict.level, verdict.penalty_start) == ("new", expected)
        assert verdict.reasons[-1] == (
            "could not check but confirmed_on 2026-10-02: "
            "fail closed, penalty from 2026-10-03"
        )


def test_deleting_a_confirmed_gates_ledger_lifts_nothing(
    tmp_path: Path, key_file: Path
) -> None:
    # READING's missing ledger is an honest "no" (missing_ledger_is_no), so
    # this is *checked* with no credit -- and still fails closed.
    verdict = maturity(READING, tmp_path / "missing.json", key_file, TODAY)
    assert verdict.checked
    assert verdict.reasons[0] == "no verified credit yet"
    assert verdict.penalty_start == date(2026, 10, 3)
    assert verdict.reasons[-1] == (
        "no verified credit but confirmed_on 2026-10-02: "
        "fail closed, penalty from 2026-10-03"
    )
    unconfirmed = replace(READING, confirmed_on=None)
    lenient = maturity(unconfirmed, tmp_path / "missing.json", key_file, TODAY)
    assert lenient.penalty_start is None
