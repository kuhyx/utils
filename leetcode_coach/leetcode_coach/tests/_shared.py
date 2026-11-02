"""Fixtures shared by the coach tests: a two-sum statement and canned replies."""

from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Any

from leetcode_coach import local_backend

FIXTURE_TOOLBOX = Path(__file__).with_name("_toolbox_fixture.json")
"""Three entries and six properties: the toolbox every coach test runs on."""
STATEMENT = """# 1. Two Sum (Easy)
Return indices of two numbers adding up to target.

## Starter code (javascript)
```
var twoSum = function(nums, target) {
};
```
"""
LEAK = "Here:\n```js\nfor (const n of nums) seen.set(target - n, n)\n```\nTry it?"
SAFE = "What could you remember about each number you have already seen?"


def ollama_reply(text: str, tokens: int = 100) -> dict[str, Any]:
    """An Ollama /api/chat answer body."""
    return {"message": {"content": text}, "prompt_eval_count": tokens}


def completed(
    code: int, out: str = "", err: str = ""
) -> subprocess.CompletedProcess[str]:
    """A finished subprocess with the given exit code and output."""
    return subprocess.CompletedProcess([], code, out, err)


class FakeChat:
    """Returns scripted replies and records every prompt it was sent."""

    def __init__(self, *texts: str) -> None:
        self.texts = list(texts)
        self.prompts: list[list[dict[str, str]]] = []

    def __call__(self, messages: list[dict[str, str]]) -> local_backend.LocalReply:
        self.prompts.append(list(messages))
        return local_backend.LocalReply(self.texts.pop(0), 1.0, 10)
