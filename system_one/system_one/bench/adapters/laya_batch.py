"""Run inside the Laya venv: TypeSafe-shaped JSONL requests in, answers out.

    laya_batch.py [--model NAME] [--max-len N] IN.jsonl OUT.jsonl

Each output row is ``{"answers", "ms", "truncated", "model"}``. Truncation is
reported when the state alone is longer than the checkpoint's token limit,
because Laya's English checkpoint reads only 512 tokens.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from laya import Router  # type: ignore[import-not-found]


def main() -> None:
    """CLI entry."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--model")
    ap.add_argument("--max-len", type=int)
    ap.add_argument("src", type=Path)
    ap.add_argument("dst", type=Path)
    args = ap.parse_args()
    router = Router(device="cuda")
    kwargs = {}
    if args.model:
        kwargs["model"] = args.model
    if args.max_len:
        kwargs["max_len"] = args.max_len
    with args.dst.open("w") as out:
        for line in args.src.read_text().splitlines():
            req = json.loads(line)
            t0 = time.monotonic()
            res = router.predict(req["state"], req["questions"], **kwargs)
            ms = int((time.monotonic() - t0) * 1000)
            routing = res.get("routing", {})
            row = {
                "answers": res["answers"],
                "ms": ms,
                "model": routing.get("model"),
                "truncated": bool(res.get("truncated") or routing.get("truncated")),
            }
            out.write(json.dumps(row) + "\n")
            out.flush()


if __name__ == "__main__":
    main()
