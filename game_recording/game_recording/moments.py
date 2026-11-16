# Copyright (c) 2026 Krzysztof Rudnicki
"""Which telemetry entries are moments worth a timestamp, and the derived ones.

Direct moments map one entry to one moment (the game's dev telemetry writes
them). Derived moments need several entries: a burst of hitches is one moment.
Moments carry `ms` (the entry's game clock); timeline.py turns it into `t`.
What counts is the game's `MomentMap` (config.py); this module only applies it.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from game_recording.config import Moment, MomentMap, Row

# Fields every entry carries; never part of a passthrough moment's payload.
ENVELOPE = ("session", "time", "frame", "tag", "event", "seq", "ms")
ANNOTATION = "annotation"
NEVER_MS = -(10**12)


def event_name(row: Row) -> str:
    """The entry's event name, "" when it has none."""
    return str(row.get("event", ""))


def moment(row: Row, kind: str, label: str, **extra: object) -> Moment:
    """A moment at the entry's game clock; custom rules build theirs with this."""
    out: Moment = {
        "kind": kind,
        "label": label,
        "event": event_name(row),
        "seq": row.get("seq"),
        "ms": row["ms"],
    }
    if row.get("game"):
        out["game"] = row["game"]
    out.update(extra)
    return out


def _keep(row: Row, keys: tuple[str, ...]) -> Row:
    return {k: row[k] for k in keys if k in row}


def _words(value: object) -> str:
    """A field value as label text: a list reads as a,b,c."""
    if isinstance(value, list):
        return ",".join(str(v) for v in value)
    return str(value)


def _direct(row: Row, moment_map: MomentMap) -> Moment | None:
    name = event_name(row)
    if name not in moment_map.direct:
        return None
    extra = _keep(row, moment_map.direct[name])
    detail = " ".join(_words(v) for v in extra.values() if v not in ("", None))
    return moment(
        row,
        name,
        f"{name} {row.get('game', '')} {detail}".replace("  ", " ").strip(),
        **extra,
    )


def _game_end(row: Row, moment_map: MomentMap) -> Moment | None:
    if event_name(row) != "game_end":
        return None
    extra = _keep(row, moment_map.game_end_fields)
    return moment(row, "game_end", f"game_end {row.get('outcome', '')}".strip(), **extra)


def _annotation(row: Row, _moment_map: MomentMap) -> Moment | None:
    if event_name(row) != ANNOTATION:
        return None
    return moment(
        row,
        ANNOTATION,
        "F12 annotation",
        png=row.get("image", ""),
        marks=row.get("marks"),
    )


def _engine_error(row: Row, moment_map: MomentMap) -> Moment | None:
    if event_name(row) != "engine_error" or row.get("kind") not in moment_map.error_kinds:
        return None
    text = str(row.get("message", ""))[:60]
    extra = _keep(row, ("message", "file", "line"))
    return moment(row, "engine_error", f"engine_error {text}", error_kind=row["kind"], **extra)


def _passthrough(row: Row, moment_map: MomentMap) -> Moment | None:
    name = event_name(row)
    if not (moment_map.passthrough_prefixes and name.startswith(moment_map.passthrough_prefixes)):
        return None
    extra = {k: v for k, v in row.items() if k not in ENVELOPE}
    return moment(row, name, name, **extra)


_BUILT_IN: tuple[Callable[[Row, MomentMap], Moment | None], ...] = (
    _direct,
    _game_end,
    _annotation,
    _engine_error,
    _passthrough,
)


def _one(row: Row, moment_map: MomentMap) -> Moment | None:
    for classifier in moment_map.classifiers:
        found = classifier(row)
        if found is not None:
            return found
    for rule in _BUILT_IN:
        found = rule(row, moment_map)
        if found is not None:
            return found
    return None


def classify(rows: list[Row], moment_map: MomentMap) -> list[Moment]:
    """The direct moments of a session's entries."""
    return [m for m in (_one(r, moment_map) for r in rows) if m is not None]


def derive(rows: list[Row], moment_map: MomentMap) -> list[Moment]:
    """The moments that need more than one entry."""
    out = _hitches(rows, moment_map.hitch_merge_s)
    for session_rule in moment_map.session_rules:
        out += session_rule(rows)
    return out


def _hitches(rows: list[Row], merge_s: float) -> list[Moment]:
    """A burst of `hitch` entries closer than `merge_s` is one moment."""
    out: list[Moment] = []
    last_ms = NEVER_MS
    for row in rows:
        if event_name(row) != "hitch":
            continue
        dur = row.get("dur_ms", 0)
        if out and row["ms"] - last_ms <= merge_s * 1000:
            out[-1]["count"] += 1
            out[-1]["max_ms"] = max(out[-1]["max_ms"], dur)
        else:
            out.append(
                moment(
                    row,
                    "hitch",
                    "",
                    count=1,
                    max_ms=dur,
                    cause=row.get("cause", ""),
                    derived=True,
                )
            )
        out[-1]["label"] = f"hitch x{out[-1]['count']} max {out[-1]['max_ms']} ms"
        last_ms = row["ms"]
    return out
