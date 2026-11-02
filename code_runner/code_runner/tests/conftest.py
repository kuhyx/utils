"""Shared fixtures: real-sandbox tests are skipped where bubblewrap cannot run."""

from __future__ import annotations

import shutil

import pytest

from code_runner._model import Example, RunnerError
from code_runner._sandbox import check_sandbox


def _bwrap_works() -> bool:
    try:
        check_sandbox()
    except RunnerError:
        return False
    return True


needs_sandbox = pytest.mark.skipif(not _bwrap_works(), reason="bwrap/userns unusable")
needs_node = pytest.mark.skipif(
    not _bwrap_works() or not shutil.which("node"), reason="node or bwrap missing"
)

TWO_SUM_STARTER = {
    "python3": "class Solution:\n    def twoSum(self, nums: list[int], target: int) -> list[int]:\n",
    "javascript": "var twoSum = function(nums, target) {\n\n};",
    "typescript": "function twoSum(nums: number[], target: number): number[] {\n};",
}
TWO_SUM_CODE = {
    "python3": (
        "class Solution:\n"
        "    def twoSum(self, nums, target):\n"
        "        seen = {}\n"
        "        for i, n in enumerate(nums):\n"
        "            if target - n in seen:\n"
        "                return [i, seen[target - n]]\n"
        "            seen[n] = i\n"
    ),
    "javascript": (
        "var twoSum = function(nums, target) {\n"
        "  const seen = new Map();\n"
        "  for (let i = 0; i < nums.length; i++) {\n"
        "    if (seen.has(target - nums[i])) return [i, seen.get(target - nums[i])];\n"
        "    seen.set(nums[i], i);\n"
        "  }\n"
        "};"
    ),
    "typescript": (
        "function twoSum(nums: number[], target: number): number[] {\n"
        "  const seen = new Map<number, number>();\n"
        "  for (let i = 0; i < nums.length; i++) {\n"
        "    const j = seen.get(target - nums[i]);\n"
        "    if (j !== undefined) return [i, j];\n"
        "    seen.set(nums[i], i);\n"
        "  }\n"
        "  return [];\n"
        "}"
    ),
}


@pytest.fixture
def two_sum_examples() -> list[Example]:
    return [
        Example(1, {"nums": [2, 7, 11, 15], "target": 9}, [0, 1], "any"),
        Example(2, {"nums": [3, 2, 4], "target": 6}, [1, 2], "any"),
        Example(3, {"nums": [3, 3], "target": 6}, [0, 1], "any"),
    ]
