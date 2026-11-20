"""yay-mcp TDQS judge: local decision engines vs the Claude judge.

No ground truth exists, so the Claude judge is run twice and its run-to-run
agreement is the ceiling. Every engine gets the judge's own rubric
(``TOOL_SYSTEM_PROMPT``) plus the same per-tool message as its state, and one
``score`` question per dimension. glama's deterministic gates are applied to
every source alike. The decision the script actually makes is "which
(tool, dimension) cells are below 5/5", so that agreement is the headline.

Run inside the tdqs venv (claude-agent-sdk; Max login, no API key):

    python -m system_one.bench.tdqs --claude-runs 2
    python -m system_one.bench.tdqs --engine kev-4b --base-url http://127.0.0.1:8018/v1
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

from system_one.bench.engines import make_engine

TDQS = Path.home() / "src" / "yay-mcp" / "scripts" / "tdqs_score.py"
OUT = Path.home() / "data" / "claude-scratch" / "system_one" / "tdqs"
LEVELS = {
    "purpose_clarity": [
        "missing or misleading",
        "tautology: restates the name/title",
        "vague purpose",
        "clear purpose but no sibling differentiation",
        "specific verb + resource, distinguishes it from siblings",
    ],
    "usage_guidelines": [
        "misleading",
        "no guidance",
        "implied usage only",
        "clear context, no exclusions",
        "explicit when / when-not / alternatives",
    ],
    "behavioral_transparency": [
        "contradicts annotations or discloses nothing",
        "barely any behaviour beyond annotations",
        "some behavioural context, clear gaps",
        "good behavioural context",
        "fully discloses side effects, auth, limits beyond annotations",
    ],
    "parameter_semantics": [
        "parameters unexplained and schema bare",
        "little meaning beyond the schema",
        "baseline: schema covers it, description adds nothing",
        "adds useful meaning beyond the schema",
        "fully explains every parameter's meaning and format",
    ],
    "conciseness_structure": [
        "bloated or unstructured",
        "wordy, buried lead",
        "adequate size, some filler",
        "concise and front-loaded",
        "every sentence earns its place, perfectly front-loaded",
    ],
    "contextual_completeness": [
        "badly incomplete",
        "major gaps",
        "minimum viable, clear gaps",
        "nearly complete",
        "complete for its complexity",
    ],
}


def load_tdqs() -> Any:
    """tdqs_score.py as a module (its prompts, gates and judge)."""
    spec = importlib.util.spec_from_file_location("tdqs_score", TDQS)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def tools() -> list[tuple[dict[str, Any], list[str]]]:
    """(tool, sibling names) for every exported tool."""
    servers = json.loads((OUT / "tools.json").read_text())
    return [(t, [x["name"] for x in ts]) for ts in servers.values() for t in ts]


def questions() -> dict[str, dict[str, Any]]:
    """One 1-5 score question per TDQS dimension."""
    return {
        dim: {
            "type": "score",
            "instructions": f"Rate the tool definition on {dim.replace('_', ' ')} (1-5).",
            "criteria": [f"{i + 1}: {d}" for i, d in enumerate(levels)],
        }
        for dim, levels in LEVELS.items()
    }


def run_claude(mod: Any, run: int) -> None:
    """One full Claude-judge pass (raw scores after gates)."""
    path = OUT / f"claude-run{run}.jsonl"
    done = (
        {json.loads(x)["name"] for x in path.read_text().splitlines()}
        if path.exists()
        else set()
    )
    with path.open("a") as fh:
        for tool, sibs in tools():
            if tool["name"] in done:
                continue
            res = asyncio.run(mod.score_tool(tool, sibs))
            fh.write(json.dumps({"name": tool["name"], "scores": res["scores"]}) + "\n")
            fh.flush()


def run_engine(mod: Any, name: str, base_url: str) -> None:
    """Score every tool with a local engine, gates applied like the judge."""
    pairs = tools()
    states = [
        mod.TOOL_SYSTEM_PROMPT + "\n\n" + mod.build_tool_message(t, s) for t, s in pairs
    ]
    engine = make_engine(name, base_url)
    with (OUT / f"{name}.jsonl").open("w") as fh:
        for (tool, _), dec in zip(
            pairs, engine.decide_many(states, questions()), strict=True
        ):
            scores = {
                dim: max(1, min(5, round(dec.answers[dim]["score"]) + 1))
                for dim in LEVELS
            }
            mod._apply_gates(tool, scores, contradiction=False)
            fh.write(
                json.dumps({"name": tool["name"], "scores": scores, "ms": dec.wall_ms})
                + "\n"
            )


def agreement(
    a: dict[str, dict[str, int]], b: dict[str, dict[str, int]]
) -> dict[str, float]:
    """Cell-level agreement of two score tables over their common tools."""
    cells = [(a[t][d], b[t][d]) for t in a if t in b for d in LEVELS]
    n = len(cells) or 1
    return {
        "cells": len(cells),
        "below5_agree": round(sum((x < 5) == (y < 5) for x, y in cells) / n, 3),
        "exact": round(sum(x == y for x, y in cells) / n, 3),
        "within1": round(sum(abs(x - y) <= 1 for x, y in cells) / n, 3),
        "mae": round(sum(abs(x - y) for x, y in cells) / n, 3),
    }


def table(path: Path) -> dict[str, dict[str, int]]:
    """name -> scores from a result file."""
    return {
        r["name"]: r["scores"] for r in map(json.loads, path.read_text().splitlines())
    }


def summary() -> None:
    """Every source vs Claude run 1."""
    ref = table(OUT / "claude-run1.jsonl")
    print(
        "| source | cells | below-5 agree | exact | within 1 | MAE |\n|---|---|---|---|---|---|"
    )
    for path in sorted(OUT.glob("*.jsonl")):
        if path.stem == "claude-run1":
            continue
        a = agreement(ref, table(path))
        print(
            f"| {path.stem} | {a['cells']} | {a['below5_agree']} | {a['exact']} | {a['within1']} | {a['mae']} |"
        )


def main(argv: list[str] | None = None) -> int:
    """CLI entry."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--claude-runs", type=int, default=0)
    ap.add_argument("--engine")
    ap.add_argument("--base-url", default="http://127.0.0.1:8018/v1")
    args = ap.parse_args(argv)
    mod = load_tdqs()
    for run in range(1, args.claude_runs + 1):
        run_claude(mod, run)
    if args.engine:
        run_engine(mod, args.engine, args.base_url)
    summary()
    return 0


if __name__ == "__main__":
    sys.exit(main())
