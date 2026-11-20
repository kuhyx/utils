"""Decision engines behind one interface, all answering TypeSafe-shaped questions.

- ``kev-*``: HTTP to a local ``kev.serve`` (TypeSafe API, loopback only).
- ``laya`` / ``laya-ml8k``: Laya's Router in its own venv, batch subprocess.
- ``semif-4b``: SemIf's direct scorer in its own venv, batch subprocess.

Laya and SemIf each pin their own torch, so they never share Kev's venv; the
benches only exchange JSONL with them.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from system_one.client import Decision, Questions, decide

VENVS = Path.home() / ".local" / "share" / "system_one" / "venvs"
ADAPTERS = Path(__file__).parent / "adapters"
SEMIF_MODEL = ("Qwen/Qwen3.5-4B", "851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a")


class Engine(Protocol):
    """Anything that answers the same questions about many states."""

    name: str

    def decide_many(
        self, states: list[str], questions: Questions
    ) -> Iterator[Decision]:
        """One decision per state, in order."""
        ...


@dataclass
class KevEngine:
    """A running kev.serve (any checkpoint) on a loopback port."""

    name: str
    base_url: str

    def decide_many(
        self, states: list[str], questions: Questions
    ) -> Iterator[Decision]:
        """One HTTP request per state."""
        for state in states:
            yield decide(state, questions, base_url=self.base_url, timeout_s=120)


def _run_batch(
    argv: list[str], requests: list[dict[str, Any]], flags: tuple[str, str] | None = None
) -> list[dict[str, Any]]:
    """Write requests as JSONL, run ``argv IN OUT`` (or ``argv --in IN --out OUT``), read back."""
    with tempfile.TemporaryDirectory(prefix="system_one-") as tmp:
        src, dst = Path(tmp) / "in.jsonl", Path(tmp) / "out.jsonl"
        src.write_text("".join(json.dumps(r) + "\n" for r in requests))
        io = [flags[0], str(src), flags[1], str(dst)] if flags else [str(src), str(dst)]
        subprocess.run([*argv, *io], check=True)
        return [json.loads(x) for x in dst.read_text().splitlines() if x.strip()]


@dataclass
class LayaEngine:
    """Laya Router; ``model``/``max_len`` pin a checkpoint (None = auto route)."""

    name: str
    model: str | None = None
    max_len: int | None = None

    def decide_many(
        self, states: list[str], questions: Questions
    ) -> Iterator[Decision]:
        """One batch subprocess for all states."""
        argv = [
            str(VENVS / "laya" / "bin" / "python"),
            "-I",
            str(ADAPTERS / "laya_batch.py"),
        ]
        if self.model:
            argv += ["--model", self.model]
        if self.max_len:
            argv += ["--max-len", str(self.max_len)]
        reqs = [{"state": s, "questions": questions} for s in states]
        for out in _run_batch(argv, reqs):
            yield Decision(out["answers"], int(out["ms"]), out)


def _semif_rows(states: list[str], questions: Questions) -> list[dict[str, Any]]:
    """Explode each (state, question) into one SemIf row with explicit options."""
    rows = []
    for i, state in enumerate(states):
        for qid, q in questions.items():
            if q["type"] == "noul":
                opts = [
                    {"id": "no", "description": "No."},
                    {"id": "yes", "description": "Yes."},
                ]
            elif q["type"] == "score":
                opts = [
                    {"id": str(k), "description": d}
                    for k, d in enumerate(q["criteria"])
                ]
            else:
                opts = [{"id": k, "description": d} for k, d in q["criteria"].items()]
            rows.append(
                {
                    "id": f"{i}|{qid}",
                    "state": state,
                    "question": q["instructions"],
                    "options": opts,
                }
            )
    return rows


def _semif_answer(qtype: str, row: dict[str, Any]) -> dict[str, Any]:
    probs = dict(zip(row["option_ids"], row["probabilities"], strict=True))
    if qtype == "noul":
        return {"type": "noul", "noul": probs["yes"]}
    if qtype == "score":
        return {"type": "score", "score": sum(int(k) * p for k, p in probs.items())}
    return {
        "type": "choice",
        "choice": max(probs, key=probs.__getitem__),
        "probabilities": probs,
    }


@dataclass
class SemIfEngine:
    """SemIf direct typed-logit scoring of a frozen Qwen3.5-4B (no fine-tune)."""

    name: str

    def decide_many(
        self, states: list[str], questions: Questions
    ) -> Iterator[Decision]:
        """One batch CLI run; model load is paid once for the whole bench."""
        model, rev = SEMIF_MODEL
        argv = [
            str(VENVS / "semif" / "bin" / "semif-score"),
            "--mode",
            "direct",
            "--model",
            model,
            "--revision",
            rev,
        ]
        t0 = time.monotonic()
        rows = (
            _run_batch(argv, _semif_rows(states, questions), ("--input", "--output"))
            if states
            else []
        )
        del t0
        by_state: dict[int, dict[str, Any]] = {}
        secs: dict[int, float] = {}
        for row in rows:
            i_str, qid = row["id"].split("|", 1)
            i = int(i_str)
            by_state.setdefault(i, {})[qid] = _semif_answer(questions[qid]["type"], row)
            secs[i] = secs.get(i, 0.0) + float(row["total_seconds"])
        for i in range(len(states)):
            yield Decision(by_state[i], int(secs[i] * 1000), {"truncated": False})


def make_engine(name: str, base_url: str) -> Engine:
    """Engine by bench name."""
    if name.startswith("kev"):
        return KevEngine(name, base_url)
    if name == "laya":
        return LayaEngine(name)
    if name == "laya-ml8k":
        return LayaEngine(name, model="multilingual", max_len=8192)
    if name == "semif-4b":
        return SemIfEngine(name)
    msg = f"unknown engine {name!r}"
    raise ValueError(msg)
