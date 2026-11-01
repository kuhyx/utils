"""Delta and table rendering for conformance reports (see conformance.py)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

Json = dict[str, Any]


def _num(value: object) -> float:
    """Numeric value from loosely typed JSON, 0 when absent."""
    return float(value) if isinstance(value, (int, float)) else 0.0


def load_previous(path: Path) -> Json:
    """Read an earlier ``--json`` report; ValueError if its shape is wrong."""
    data = json.loads(path.read_text(encoding="utf-8"))
    surfaces = data.get("surfaces") if isinstance(data, dict) else None
    ok = isinstance(surfaces, list) and isinstance(data.get("totals"), dict)
    if not ok or not all(isinstance(s, dict) and "name" in s for s in surfaces):
        msg = "not a conformance report"
        raise ValueError(msg)
    return data


def delta(current: Json, previous: Json) -> Json:
    """Per-surface and total change versus a previous report."""
    before = {str(s["name"]): s for s in previous["surfaces"]}
    rows: list[Json] = []
    entries = [*current["surfaces"], current["totals"]]
    prev_total = previous["totals"]
    for row in entries:
        old = prev_total if row["name"] == "TOTAL" else before.get(str(row["name"]), {})
        rows.append({
            "name": row["name"],
            "token_usages": _num(row["token_usages"]) - _num(old.get("token_usages")),
            "raw_literals": _num(row["raw_literals"]) - _num(old.get("raw_literals")),
            "conformance": None
            if row["conformance"] is None or old.get("conformance") is None
            else round(_num(row["conformance"]) - _num(old["conformance"]), 1),
        })
    return {"rows": rows}


def _fmt(value: object, signed: bool = False) -> str:
    """Table cell text for a count, percent or missing value."""
    if value is None:
        return "-"
    return f"{_num(value):+g}" if signed else f"{_num(value):g}"


def table(rep: Json, diff: Json | None) -> str:
    """Plain-text table, with delta columns when ``diff`` is given."""
    head = ["surface", "files", "tokens", "raw", "conf%"]
    if diff:
        head += ["d.tokens", "d.raw", "d.conf"]
    rows = [head]
    deltas = {str(r["name"]): r for r in diff["rows"]} if diff else {}
    for row in [*rep["surfaces"], rep["totals"]]:
        cells = [str(row["name"]), _fmt(row["files"]), _fmt(row["token_usages"]),
                 _fmt(row["raw_literals"]), _fmt(row["conformance"])]
        if diff:
            d = deltas.get(str(row["name"]), {})
            cells += [_fmt(d.get("token_usages", 0), True),
                      _fmt(d.get("raw_literals", 0), True),
                      _fmt(d.get("conformance"), True)]
        rows.append(cells)
    widths = [max(len(r[i]) for r in rows) for i in range(len(head))]
    return "\n".join(
        "  ".join(c.ljust(w) for c, w in zip(r, widths, strict=True)).rstrip()
        for r in rows
    )
