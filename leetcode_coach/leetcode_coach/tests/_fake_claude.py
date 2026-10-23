#!/usr/bin/env python3
"""A scripted stand-in for `claude -p`, reached through LEETCODE_CLAUDE_BIN.

Reads ``$FAKE_CLAUDE_DIR/script.json``: ``{"haiku": [...], "coach": [...]}``.
A call made with ``--model haiku`` is the checker; any other is the coach.
Each call takes the next answer of its kind -- ``{"result": "..."}`` is printed
the way ``--output-format json`` prints it, ``{"exit": n, "stderr": "..."}``
fails -- and appends ``{"kind", "args", "prompt"}`` to ``calls.jsonl`` so a
test can prove what did and did not reach the model.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys


def main() -> int:
    """Answer one scripted call."""
    root = Path(os.environ["FAKE_CLAUDE_DIR"])
    args = sys.argv[1:]
    model = args[args.index("--model") + 1] if "--model" in args else ""
    kind = "haiku" if model == "haiku" else "coach"
    with (root / "calls.jsonl").open("a", encoding="utf-8") as fh:
        record = {"kind": kind, "args": args[:-1], "prompt": args[-1]}
        fh.write(json.dumps(record) + "\n")
    counter = root / f"{kind}.used"
    used = int(counter.read_text(encoding="utf-8")) if counter.exists() else 0
    counter.write_text(str(used + 1), encoding="utf-8")
    script = json.loads((root / "script.json").read_text(encoding="utf-8"))
    answer = script[kind][used]
    if "exit" in answer:
        sys.stderr.write(answer.get("stderr", ""))
        return int(answer["exit"])
    sys.stdout.write(json.dumps({"result": answer["result"], "session_id": "fake"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
