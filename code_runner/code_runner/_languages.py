from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
import json
import os
from pathlib import Path
import shutil
from typing import TYPE_CHECKING

from code_runner._model import RunnerError
from code_runner._sandbox import WORK

if TYPE_CHECKING:
    from code_runner._starter import Entry

MEGABYTE = 1024 * 1024
_NODE_FLAGS = (
    "--permission",
    f"--allow-fs-read={WORK}",
    f"--allow-fs-write={WORK}",
    "--max-old-space-size=128",
)


@dataclass(frozen=True)
class Language:
    name: str
    solution_file: str
    harness_file: str
    program: str
    binary_env: str
    binary_default: str
    flags: tuple[str, ...]
    memory_bytes: int

    def resolve(self) -> Path:
        for candidate in (
            os.environ.get(self.binary_env),
            self.binary_default,
            shutil.which(self.program),
        ):
            if candidate and Path(candidate).is_file():
                return Path(candidate).resolve()
        msg = f"{self.program} not found (set {self.binary_env})"
        raise RunnerError(msg)

    def command(self, binary: Path) -> list[str]:
        return [str(binary), *self.flags, f"{WORK}/{self.harness_file}", WORK]

    def ro_binds(self, binary: Path) -> tuple[str, ...]:
        if binary.is_relative_to("/usr"):
            return ()
        return (str(binary.parent.parent),)

    def prepare(
        self, scratch: Path, code: str, entry: Entry, args: list[object]
    ) -> None:
        harness = resources.files("code_runner").joinpath("harness", self.harness_file)
        (scratch / self.harness_file).write_text(harness.read_text(encoding="utf-8"))
        text = code
        if self.name == "typescript":
            text += f"\nmodule.exports = {{ __entry: {entry.cls or entry.name} }};\n"
        (scratch / self.solution_file).write_text(text, encoding="utf-8")
        spec = {
            "cls": entry.cls,
            "fn": entry.name,
            "args": args,
            "typescript": self.name == "typescript",
        }
        (scratch / "input.json").write_text(json.dumps(spec), encoding="utf-8")


PYTHON = Language(
    "python3",
    "solution.py",
    "harness.py",
    "python3",
    "CODE_RUNNER_PYTHON",
    "/usr/bin/python3",
    ("-I", "-B"),
    512 * MEGABYTE,
)
JAVASCRIPT = Language(
    "javascript",
    "solution.js",
    "harness.js",
    "node",
    "CODE_RUNNER_NODE",
    "/usr/bin/node",
    _NODE_FLAGS,
    2048 * MEGABYTE,
)
TYPESCRIPT = Language(
    "typescript",
    "solution.cts",
    "harness.js",
    "node",
    "CODE_RUNNER_NODE",
    "/usr/bin/node",
    _NODE_FLAGS,
    2048 * MEGABYTE,
)
_BY_NAME = {
    "python3": PYTHON,
    "python": PYTHON,
    "javascript": JAVASCRIPT,
    "js": JAVASCRIPT,
    "typescript": TYPESCRIPT,
    "ts": TYPESCRIPT,
}


def get_language(name: str) -> Language:
    try:
        return _BY_NAME[name.lower()]
    except KeyError:
        msg = f"unsupported language {name!r}; use python3, javascript or typescript"
        raise RunnerError(msg) from None
