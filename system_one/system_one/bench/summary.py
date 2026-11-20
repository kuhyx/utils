"""Threshold-free comparison of every engine run by ``bench.task_size``.

Per-half thresholds on ~50 rows are noisy, so this ranks engines by ROC-AUC on
the model-decided rows (continuation-rule rows are identical for everyone and
left out) and by precision at Haiku's own recall over all 181 rows. Haiku's
signal is its ``est_calls``; the zero-cost ``heuristic`` is the floor.

    python -m system_one.bench.summary
"""

from __future__ import annotations

import sys
from typing import Any

from system_one.bench.metrics import confusion
from system_one.bench.task_size import OUT, SCRATCH, eval_rows, jl, load_live


def auc(pos: list[float], neg: list[float]) -> float:
    """P(score of a random positive > random negative), ties count half."""
    if not pos or not neg:
        return 0.0
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return round(wins / (len(pos) * len(neg)), 3)


def precision_at_recall(values: list[float], truth: list[bool], recall: float) -> float:
    """Best precision among cuts that reach ``recall``."""
    best = 0.0
    for thr in sorted(set(values)):
        c = confusion(truth, [v >= thr for v in values])
        if c["recall"] >= recall:
            best = max(best, c["precision"])
    return best


def signals(live: Any) -> dict[str, dict[str, float]]:
    """Engine/signal name -> session -> value."""
    out: dict[str, dict[str, float]] = {}
    haiku = jl(SCRATCH / "results-v3-single.jsonl")
    out["haiku est_calls"] = {r["session"]: float(r["est_calls"]) for r in haiku}
    for path in sorted(OUT.glob("*.jsonl")):
        rows = jl(path)
        out[f"{path.stem} p_big"] = {r["session"]: r["p_big"] for r in rows}
        out[f"{path.stem} size"] = {r["session"]: r["size"] for r in rows}
        out[f"{path.stem} p50_ms"] = {
            "_": sorted(r["ms"] for r in rows)[len(rows) // 2]
        }
    del live
    return out


def main() -> int:
    """Print a markdown table."""
    live = load_live()
    rows, _ = eval_rows(live)
    model_rows = [r for r in rows if live.rule(r["prompt"]) is None]
    sig = signals(live)
    sig["heuristic score"] = {
        r["session"]: live.heuristic_score(r["prompt"]) for r in rows
    }
    haiku = sig["haiku est_calls"]
    truth_all = [r["hit_gate"] for r in rows]
    haiku_recall = confusion(
        truth_all,
        [
            live.rule(r["prompt"]) is not None
            or haiku.get(r["session"], 0) >= live.TOO_BIG_AT
            for r in rows
        ],
    )["recall"]
    print(
        f"rows={len(rows)} model-decided={len(model_rows)} haiku recall={haiku_recall}\n"
    )
    print(
        "| signal | AUC (model rows) | precision @ Haiku recall (all rows) | p50 ms |"
    )
    print("|---|---|---|---|")
    for name, vals in sig.items():
        if name.endswith("p50_ms") or not vals:
            continue
        pos = [
            vals[r["session"]]
            for r in model_rows
            if r["hit_gate"] and r["session"] in vals
        ]
        neg = [
            vals[r["session"]]
            for r in model_rows
            if not r["hit_gate"] and r["session"] in vals
        ]
        allv = [
            99e9 if live.rule(r["prompt"]) is not None else vals.get(r["session"], 0.0)
            for r in rows
        ]
        engine = name.rsplit(" ", 1)[0]
        ms = sig.get(f"{engine} p50_ms", {}).get("_", "")
        if engine == "haiku":
            ms = sorted(h["ms"] for h in jl(SCRATCH / "results-v3-single.jsonl"))[70]
        print(
            f"| {name} | {auc(pos, neg)} | {precision_at_recall(allv, truth_all, haiku_recall)} | {ms} |"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
