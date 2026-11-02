"""run_code: kuhy's JavaScript against the statement's examples (decision 8).

The contract (DOCS-coach-relay.md section 2) allows exactly one subprocess
shape here: ``node`` with a fixed argv, never a shell. kuhy's code is embedded
in a generated harness as a JSON string literal and compiled with
``new Function``, so a syntax error is told apart from a crash; the examples
are JSON literals this module generates from the statement. The process runs
in a fresh temporary directory under node's permission model: it may read
that directory and nothing else, spawns no child, opens no worker.

The answer carries printed values only, never node's stderr or a stack trace:
a thrown error becomes ``error: <ClassName>``. The harness silences
``console`` and ``process.stdout.write`` before kuhy's code loads and marks its
own result lines with a per-run random token, so whatever kuhy's code prints
cannot pose as a result. Output is cut at ``MAX_OUTPUT`` bytes before it is
read, and one value is shown in at most ``MAX_SHOWN`` characters.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import tempfile
from typing import TYPE_CHECKING, Any, Final

from leetcode_coach.relay import examples

if TYPE_CHECKING:
    from collections.abc import Callable

_logger: Final = logging.getLogger(__name__)

NODE_ENV: Final = "LEETCODE_NODE_BIN"
DEFAULT_NODE: Final = "/usr/bin/node"
TIMEOUT_S: Final = 5.0
MAX_OUTPUT: Final = 64 * 1024
MAX_SHOWN: Final = 200
NO_RESULT: Final = "no result"
_FIELDS: Final = 4  # mark, n, ok|err, value
_ERROR_NAME: Final = re.compile(r"[A-Za-z]{1,40}")

_HARNESS: Final = """const __mark = "{mark}";
const __write = process.stdout.write.bind(process.stdout);
for (const k of ["log", "error", "warn", "info", "debug", "trace", "dir", "table"]) {{
  console[k] = () => {{}};
}}
process.stdout.write = () => true;
process.stderr.write = () => true;
const __say = (line) => __write(__mark + " " + line + "\\n");
const __name = (e) =>
  e && typeof e.name === "string" && /^[A-Za-z]{{1,40}}$/.test(e.name)
    ? e.name
    : "Error";
const __examples = {examples};
let __load;
try {{
  __load = new Function(
    {code} + "\\n;return typeof {name} === 'function' ? {name} : undefined;"
  );
}} catch (e) {{
  __say("syntax");
  process.exit(0);
}}
let __fn;
let __failed = null;
try {{
  __fn = __load();
}} catch (e) {{
  __failed = __name(e);
}}
if (__failed === null && typeof __fn !== "function") __failed = "ReferenceError";
for (const ex of __examples) {{
  if (__failed !== null) {{
    __say(ex.n + " err " + __failed);
    continue;
  }}
  try {{
    const r = __fn(...ex.args);
    __say(ex.n + " ok " + (r === undefined ? "undefined" : JSON.stringify(r)));
  }} catch (e) {{
    __say(ex.n + " err " + __name(e));
  }}
}}
"""


def node_bin() -> str:
    """``LEETCODE_NODE_BIN``, else ``node`` from PATH, else ``/usr/bin/node``."""
    return os.environ.get(NODE_ENV) or shutil.which("node") or DEFAULT_NODE


def _canonical(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def _shown(text: str) -> str:
    return text if len(text) <= MAX_SHOWN else text[:MAX_SHOWN] + "..."


def harness(code: str, name: str, found: list[examples.Example], mark: str) -> str:
    """The generated ``run.js``: every interpolated value is a JSON literal."""
    cases = [{"n": ex.n, "args": list(ex.args)} for ex in found]
    return _HARNESS.format(
        mark=mark,
        examples=json.dumps(cases),
        code=json.dumps(code),
        name=name,
    )


def _results(stdout: bytes, mark: str) -> dict[int, tuple[str, str]] | None:
    """``{n: (ok|err, value)}`` from the marked lines; None on a syntax error."""
    text = stdout[:MAX_OUTPUT].decode("utf-8", errors="replace")
    found: dict[int, tuple[str, str]] = {}
    for line in text.splitlines():
        parts = line.split(" ", 3)
        if parts[0] != mark:
            continue
        if parts[1:] == ["syntax"]:
            return None
        if len(parts) == _FIELDS and parts[1].isdigit() and parts[2] in {"ok", "err"}:
            found[int(parts[1])] = (parts[2], parts[3])
    return found


def _row(ex: examples.Example, result: tuple[str, str] | None) -> dict[str, Any]:
    expected = _canonical(ex.expected)
    row: dict[str, Any] = {"n": ex.n, "ok": False, "expected": _shown(expected)}
    if result is None:
        return {**row, "got": NO_RESULT}
    kind, value = result
    if kind == "err":
        name = value if _ERROR_NAME.fullmatch(value) else "Error"
        return {**row, "got": f"error: {name}"}
    try:
        got = _canonical(json.loads(value))
    except ValueError:
        _logger.warning("example %d printed a value that is not JSON", ex.n)
        return {**row, "got": _shown(value)}
    return {**row, "ok": got == expected, "got": _shown(got)}


def _failed(error: str) -> dict[str, Any]:
    return {"examples": [], "error": error}


def run(
    code: str,
    statement: str,
    *,
    node: str | None = None,
    timeout_s: float = TIMEOUT_S,
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
) -> dict[str, Any]:
    """Run ``code`` on every parsed example; the contract's ``run_code`` data."""
    name, found = examples.parse(statement)
    if name is None or not found:
        return _failed("no_examples")
    mark = secrets.token_hex(16)
    with tempfile.TemporaryDirectory(prefix="leetcode-run-") as tmp:
        script = Path(tmp) / "run.js"
        script.write_text(harness(code, name, found, mark), encoding="utf-8")
        argv = [
            node or node_bin(),
            "--permission",
            f"--allow-fs-read={tmp}",
            "--max-old-space-size=128",
            str(script),
        ]
        try:
            proc = runner(
                argv,
                cwd=tmp,
                env={"PATH": "/usr/bin:/bin"},
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired:
            _logger.warning("run_code: node ran past %.0f s and was killed", timeout_s)
            return _failed("timeout")
        except OSError as exc:
            _logger.warning("run_code: node could not start: %s", exc)
            return _failed("node_missing")
    results = _results(proc.stdout, mark)
    if results is None:
        return _failed("syntax")
    rows = [_row(ex, results.get(ex.n)) for ex in found]
    return {"examples": rows, "error": None}
