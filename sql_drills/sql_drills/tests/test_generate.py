"""``save_generated`` validates by running the reference on a fresh sandbox."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

import sql_drills as sd
from sql_drills import _paths

if TYPE_CHECKING:
    from sql_drills.tests.conftest import FakeMysql

_COLS = "emp\tid\nemp\tpay\n"


def _spec(**over: object) -> dict[str, Any]:
    base: dict[str, Any] = {
        "kind": "write",
        "topic": "window",
        "title": "Top earner",
        "task_md": "Return the best paid person.",
        "schema_sql": "CREATE TABLE emp (id INT, pay INT);",
        "reference_sql": "SELECT SECRET_REFERENCE;",
    }
    base.update(over)
    return base


def _wire(fake: FakeMysql, out: str = "2\n") -> None:
    fake.say("SECRET_REFERENCE", stdout=out)
    fake.say("information_schema", stdout=_COLS)
    fake.say("FROM `emp`", stdout="1\t5\n2\t9\n")


def test_valid_write_spec_is_saved_and_listed(fake_mysql: FakeMysql) -> None:
    _wire(fake_mysql)
    drill_id = sd.save_generated(_spec())
    assert drill_id.startswith("g-window-")
    meta = next(m for m in sd.list_drills() if m.id == drill_id)
    assert (meta.kind, meta.source, meta.topic, meta.title) == (
        "write",
        "generated",
        "window",
        "Top earner",
    )
    drill = sd.get_drill(drill_id)
    assert drill.expected_preview == [["2"]]
    assert drill.tables["emp"].rows == [["1", "5"], ["2", "9"]]
    assert drill.query is None


def test_reference_sql_is_never_written_to_disk(fake_mysql: FakeMysql) -> None:
    _wire(fake_mysql)
    drill_id = sd.save_generated(_spec())
    folder = _paths.data_dir() / "drills" / drill_id
    assert sorted(p.name for p in folder.iterdir()) == [
        "DOCS-task.md",
        "expected.txt",
        "meta.json",
        "schema.sql",
        "tables.json",
    ]
    assert all("SECRET_REFERENCE" not in p.read_text() for p in folder.iterdir())


def test_expected_is_the_reference_output_and_is_gradable(
    fake_mysql: FakeMysql,
) -> None:
    _wire(fake_mysql, "2\t9\n")
    drill_id = sd.save_generated(_spec())
    fake_mysql.say("my answer", stdout="2\t9\n", header="id\tpay")
    assert sd.run(drill_id, "my answer").match


def test_saving_twice_is_idempotent(fake_mysql: FakeMysql) -> None:
    _wire(fake_mysql)
    first = sd.save_generated(_spec())
    assert sd.save_generated(_spec()) == first
    assert len([m for m in sd.list_drills() if m.source == "generated"]) == 1


def test_spec_dataclass_is_accepted(fake_mysql: FakeMysql) -> None:
    _wire(fake_mysql)
    spec = sd.DrillSpec(**_spec())
    assert sd.save_generated(spec).startswith("g-window-")


def test_empty_reference_output_is_rejected(fake_mysql: FakeMysql) -> None:
    _wire(fake_mysql, "")
    with pytest.raises(sd.SpecError, match="empty"):
        sd.save_generated(_spec())
    assert not (_paths.data_dir() / "drills").exists() or not any(
        (_paths.data_dir() / "drills").iterdir()
    )


def test_erroring_reference_is_rejected(fake_mysql: FakeMysql) -> None:
    fake_mysql.say("SECRET_REFERENCE", stderr="ERROR 1064: syntax", rc=1)
    with pytest.raises(sd.SpecError, match=r"reference.*1064"):
        sd.save_generated(_spec())


def test_nondeterministic_reference_is_rejected(fake_mysql: FakeMysql) -> None:
    fake_mysql.say_seq("SECRET_REFERENCE", ["1\n", "2\n"])
    with pytest.raises(sd.SpecError, match="deterministic"):
        sd.save_generated(_spec())


@pytest.mark.parametrize(
    ("over", "msg"),
    [
        ({"topic": "cooking"}, "topic"),
        ({"kind": "chat"}, "kind"),
        ({"title": " "}, "title"),
        ({"reference_sql": ""}, "reference_sql"),
        ({"task_md": 5}, "task_md"),
        ({"expect_error": True}, "predict"),
    ],
)
def test_bad_specs_fail_before_touching_mysql(
    fake_mysql: FakeMysql, over: dict[str, Any], msg: str
) -> None:
    with pytest.raises(sd.SpecError, match=msg):
        sd.save_generated(_spec(**over))
    assert fake_mysql.calls == []


def test_missing_field_is_rejected(fake_mysql: FakeMysql) -> None:
    spec = _spec()
    del spec["schema_sql"]
    with pytest.raises(sd.SpecError, match="schema_sql"):
        sd.save_generated(spec)


def test_predict_spec_stores_the_query_and_hides_expected(
    fake_mysql: FakeMysql,
) -> None:
    _wire(fake_mysql, "2\n")
    drill_id = sd.save_generated(_spec(kind="predict"))
    drill = sd.get_drill(drill_id)
    assert drill.query == "SELECT SECRET_REFERENCE;"
    assert drill.expected_preview == []
    assert "Predict the exact output" in drill.task_md
    assert sd.check_prediction(drill_id, [["2"]]).match


def test_predict_spec_may_expect_an_error(fake_mysql: FakeMysql) -> None:
    fake_mysql.say("SECRET_REFERENCE", stderr="ERROR 1054 (42S22): Unknown", rc=1)
    drill_id = sd.save_generated(_spec(kind="predict", expect_error=True))
    res = sd.check_prediction(drill_id, [["ERROR"]])
    assert res.match
    assert res.error == "ERROR 1054 (42S22): Unknown"
    meta = json.loads(
        (_paths.data_dir() / "drills" / drill_id / "meta.json").read_text()
    )
    assert meta["error_code"] == 1054


def test_predict_error_without_flag_is_rejected(fake_mysql: FakeMysql) -> None:
    fake_mysql.say("SECRET_REFERENCE", stderr="ERROR 1054: x", rc=1)
    with pytest.raises(sd.SpecError, match="reference"):
        sd.save_generated(_spec(kind="predict"))


def test_expected_error_that_does_not_happen_is_rejected(fake_mysql: FakeMysql) -> None:
    _wire(fake_mysql)
    with pytest.raises(sd.SpecError, match="did not fail"):
        sd.save_generated(_spec(kind="predict", expect_error=True))


def test_expected_error_without_code_is_rejected(fake_mysql: FakeMysql) -> None:
    fake_mysql.say("SECRET_REFERENCE", stderr="odd failure", rc=1)
    with pytest.raises(sd.SpecError, match="error code"):
        sd.save_generated(_spec(kind="predict", expect_error=True))
