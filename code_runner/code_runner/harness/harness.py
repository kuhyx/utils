"""Runs inside the sandbox: call the solution once, write result.json."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import Any

PRELUDE = (
    "from typing import *\n"
    "import bisect, collections, functools, heapq, itertools, math\n"
    "import operator, re, string\n"
)
MAX_MESSAGE = 300


def describe(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:MAX_MESSAGE]


def write_result(root: Path, payload: dict[str, object]) -> None:
    # Unique name + rename: a symlink the solution planted at result.json is
    # replaced by this file, never followed.
    handle, name = tempfile.mkstemp(dir=root, prefix=".result-")
    with os.fdopen(handle, "w", encoding="utf-8") as out:
        json.dump(payload, out)
    Path(name).replace(root / "result.json")


def call(root: Path, spec: dict[str, Any]) -> object:
    namespace: dict[str, Any] = {"__name__": "solution"}
    exec(PRELUDE, namespace)
    source = (root / "solution.py").read_text(encoding="utf-8")
    exec(compile(source, "solution.py", "exec"), namespace)
    owner, name = spec["cls"], str(spec["fn"])
    if owner is None:
        target = namespace.get(name)
    else:
        cls = namespace.get(str(owner))
        target = getattr(cls() if cls else None, name, None)
    if target is None:
        message = f"name {owner or name!r} is not defined"
        raise NameError(message)
    return target(*spec["args"])


def main(directory: str) -> None:
    root = Path(directory)
    spec = json.loads((root / "input.json").read_text(encoding="utf-8"))
    started = time.perf_counter()
    try:
        value = call(root, spec)
        payload: dict[str, object] = {
            "ok": True,
            "value": json.loads(json.dumps(value)),
        }
    except BaseException as exc:
        payload = {"ok": False, "error": describe(exc)}
    payload["ms"] = (time.perf_counter() - started) * 1000
    sys.stdout.flush()
    write_result(root, payload)


if __name__ == "__main__":
    main(sys.argv[1])
