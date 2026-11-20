"""Task-size estimator: local decision engines vs the shipped Haiku verdicts.

Replicates REEVAL-v3-2026-10-04's rows exactly (``run_eval_v3.py``): hook-
evaluated rows of ``samples-v3.jsonl`` minus the few-shot sessions, 300k-peak
label ``hit_gate``. Continuation-rule rows are TOO BIG for every engine (the
rule needs no model). Every engine gets the live estimator's own prompt text
(rubric + few-shot + query) as its state; the hash is recorded.

Thresholds are fitted on the ``split_of`` train half (lowest p whose recall
still matches Haiku's train recall: kuhy prefers recall) and reported on the
test half, next to Haiku on the same test rows. Runs offline; no Claude call.

    python -m system_one.bench.task_size --engine kev-4b --base-url http://127.0.0.1:8018/v1
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

from system_one.bench.engines import Engine, make_engine
from system_one.bench.metrics import confusion, fit_threshold

SCRATCH = Path.home() / "data" / "claude-scratch" / "task-size"
OUT = SCRATCH / "system_one"
LIVE = Path.home() / ".claude" / "scripts" / "task_size_estimate.py"
QUESTIONS: dict[str, dict[str, Any]] = {
    "too_big": {
        "type": "noul",
        "instructions": "Will this task overflow one coding-agent session, i.e. "
        "need more than 300k tokens of context (roughly more than 180 tool calls)?",
    },
    "size": {
        "type": "score",
        "instructions": "How many tool calls will this task really take?",
        "criteria": [
            "under 40 tool calls: a question or a one-line fix",
            "40 to 150 tool calls: a bug that needs investigation",
            "150 to 300 tool calls: a feature with tests and verification",
            "over 300 tool calls: a migration, sweep, new app or multi-item list",
        ],
    },
}


def jl(path: Path) -> list[dict[str, Any]]:
    """Read a jsonl file ([] if absent)."""
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def load_live() -> Any:
    """The live estimator, pointed at the v3 few-shot pool like run_eval_v3."""
    spec = importlib.util.spec_from_file_location("live_est", LIVE)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.SAMPLES = SCRATCH / "samples-pool-v3.jsonl"
    return mod


def eval_rows(live: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(rows, shots): run_eval_v3's scored rows and the few-shot pick."""
    shots = live.pick_examples(live.load_samples())
    excl = {s["session"] for s in shots}
    old = {r["session"] for r in jl(SCRATCH / "results-2026-10-04.jsonl")}
    rows = [
        r
        for r in jl(SCRATCH / "samples-v3.jsonl")
        if r["hook_evaluates"] and r["session"] not in excl and r["session"] in old
    ]
    return rows, shots


def run_engine(
    engine: Engine, live: Any, rows: list[dict[str, Any]], shots: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Ask the engine about every model-decided row; cached + resumable."""
    cache = OUT / f"{engine.name}.jsonl"
    done = {r["session"]: r for r in jl(cache)}
    todo = [
        r for r in rows if live.rule(r["prompt"]) is None and r["session"] not in done
    ]
    states = [live.build_prompt(r["prompt"], r["cwd"], shots) for r in todo]
    OUT.mkdir(parents=True, exist_ok=True)
    with cache.open("a") as fh:
        for row, state, out in zip(
            todo, states, engine.decide_many(states, QUESTIONS), strict=True
        ):
            rec = {
                "session": row["session"],
                "p_big": out.answers["too_big"]["noul"],
                "size": out.answers["size"]["score"],
                "ms": out.wall_ms,
                "truncated": bool(out.raw.get("truncated")),
                "state_sha256": hashlib.sha256(state.encode()).hexdigest()[:16],
            }
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            done[row["session"]] = rec
    return done


def report(
    engine_name: str,
    live: Any,
    rows: list[dict[str, Any]],
    got: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Fit on train, score on test; Haiku (pessimistic, est>=150) alongside."""
    haiku = {r["session"]: r for r in jl(SCRATCH / "results-v3-single.jsonl")}

    def haiku_big(r: dict[str, Any]) -> bool:
        if live.rule(r["prompt"]) is not None:
            return True
        return haiku.get(r["session"], {}).get("est_calls", 0) >= live.TOO_BIG_AT

    halves = {
        h: [r for r in rows if live.split_of(r["session"]) == h]
        for h in ("train", "test")
    }
    out: dict[str, Any] = {"engine": engine_name, "n": len(rows)}
    for signal in ("p_big", "size"):

        def value(r: dict[str, Any], sig: str = signal) -> float:
            return (
                99.0
                if live.rule(r["prompt"]) is not None
                else float(got[r["session"]][sig])
            )

        train = halves["train"]
        target = confusion(
            [r["hit_gate"] for r in train], [haiku_big(r) for r in train]
        )["recall"]
        thr = fit_threshold(
            [value(r) for r in train], [r["hit_gate"] for r in train], target
        )
        test = halves["test"]
        out[signal] = {
            "threshold": thr,
            "test": confusion(
                [r["hit_gate"] for r in test], [value(r) >= thr for r in test]
            ),
            "all": confusion(
                [r["hit_gate"] for r in rows], [value(r) >= thr for r in rows]
            ),
        }
    out["haiku_test"] = confusion(
        [r["hit_gate"] for r in halves["test"]], [haiku_big(r) for r in halves["test"]]
    )
    out["haiku_all"] = confusion(
        [r["hit_gate"] for r in rows], [haiku_big(r) for r in rows]
    )
    ms = sorted(v["ms"] for v in got.values())
    out["p50_ms"] = ms[len(ms) // 2] if ms else None
    out["haiku_p50_ms"] = sorted(h["ms"] for h in haiku.values())[len(haiku) // 2]
    out["truncated"] = sum(v["truncated"] for v in got.values())
    return out


def main(argv: list[str] | None = None) -> int:
    """CLI entry."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--engine",
        required=True,
        help="kev-0.8b | kev-4b | kev-9b | laya | semif-4b ...",
    )
    ap.add_argument("--base-url", default="http://127.0.0.1:8018/v1")
    args = ap.parse_args(argv)
    live = load_live()
    rows, shots = eval_rows(live)
    got = run_engine(make_engine(args.engine, args.base_url), live, rows, shots)
    rep = report(args.engine, live, rows, got)
    (OUT / f"report-{args.engine}.json").write_text(json.dumps(rep, indent=1))
    json.dump(rep, sys.stdout, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
