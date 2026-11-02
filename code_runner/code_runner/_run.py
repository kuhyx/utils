from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
import json
import os
from pathlib import Path
import stat
import tempfile

from code_runner._compare import TooDeepError, matches, too_deep
from code_runner._languages import Language, get_language
from code_runner._model import MAX_CAPTURE, CaseResult, Example, Limits
from code_runner._sandbox import BoxResult, execute
from code_runner._starter import Entry, parse_starter

Box = Callable[[list[str], Path, Limits, int, tuple[str, ...]], BoxResult]
_OUT_OF_MEMORY = ("out of memory", "allocation failed")
_MAX_ERROR = 200
# Everything hostile JSON can raise on the host: deep nesting, huge numbers.
_HOSTILE = (ValueError, TypeError, RecursionError, MemoryError, OverflowError)


def _positional(example: Example, entry: Entry) -> list[object]:
    if set(example.args) == set(entry.params):
        return [example.args[name] for name in entry.params]
    if len(example.args) == len(entry.params):
        return list(example.args.values())
    given, wanted = len(example.args), len(entry.params)
    msg = f"ArgumentError: example gives {given} arguments, {entry.name} takes {wanted}"
    raise ValueError(msg)


def _read_result(scratch: Path) -> dict[str, object] | None:
    # The scratch dir is the solution's: never follow a link it planted there.
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    try:
        fd = os.open(scratch / "result.json", flags)
    except OSError:
        return None
    with os.fdopen(fd, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            return None
        raw = handle.read(MAX_CAPTURE * 16)
    try:
        payload = json.loads(raw)
    except _HOSTILE:  # ValueError, or RecursionError on "[" * 200000
        return None
    if not isinstance(payload, dict) or "ok" not in payload:
        return None
    return None if too_deep(payload) else payload


def _crash(box: BoxResult) -> str:
    low = box.stderr.lower()
    if any(marker in low for marker in _OUT_OF_MEMORY):
        return "MemoryLimitExceeded"
    return f"Crashed (exit {box.returncode})"


def _took(ms: object, fallback: float) -> float:
    if isinstance(ms, bool) or not isinstance(ms, int | float):
        return fallback
    try:
        return float(ms)
    except OverflowError:  # an int too big for a float
        return fallback


def _outcome(scratch: Path, box: BoxResult) -> tuple[object, str | None, float]:
    if box.timed_out:
        return None, "TimeLimitExceeded", box.elapsed_ms
    payload = _read_result(scratch)
    if payload is None:
        return None, _crash(box), box.elapsed_ms
    took = _took(payload.get("ms"), box.elapsed_ms)
    if payload["ok"] is True:
        return payload.get("value"), None, took
    return None, str(payload.get("error", "Error"))[:_MAX_ERROR], took


@dataclass(frozen=True)
class _Job:
    language: Language
    binary: Path
    code: str
    entry: Entry
    limits: Limits
    box: Box


def _case(job: _Job, example: Example) -> CaseResult:
    try:
        args = _positional(example, job.entry)
    except ValueError as exc:
        return CaseResult(
            example.n, example.args, example.expected, None, ok=False, error=str(exc)
        )
    language = job.language
    with tempfile.TemporaryDirectory(prefix="code-runner-") as tmp:
        scratch = Path(tmp)
        language.prepare(scratch, job.code, job.entry, args)
        done = job.box(
            language.command(job.binary),
            scratch,
            job.limits,
            language.memory_bytes,
            language.ro_binds(job.binary),
        )
        actual, error, ms = _outcome(scratch, done)
    ok = False
    if error is None:
        try:
            ok = matches(example.expected, actual, example.order)
        except (TooDeepError, RecursionError, MemoryError) as exc:
            actual, error = None, f"InvalidResult: {type(exc).__name__}"
    return CaseResult(
        example.n, example.args, example.expected, actual, ok, done.stdout, error, ms
    )


def run(
    lang: str,
    code: str,
    starter: str,
    examples: Sequence[Example],
    *,
    limits: Limits | None = None,
    box: Box = execute,
) -> list[CaseResult]:
    language = get_language(lang)
    entry = parse_starter(language.name, starter)
    job = _Job(language, language.resolve(), code, entry, limits or Limits(), box)
    return [_case(job, example) for example in examples]
