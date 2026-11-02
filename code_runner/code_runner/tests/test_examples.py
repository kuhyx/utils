from code_runner._examples import parse_examples
from code_runner._model import Example

TWO_SUM = """# 1. Two Sum (Easy)
Tags: Array, Hash Table

Return indices.

You can return the answer in any order.

**Example 1:**

**Input:** `nums = [2,7,11,15], target = 9`

**Output:** `[0,1]`

**Explanation:** 2 + 7.

**Example 2:**

**Input:** `nums = [3,2,4], target = 6`

**Output:** `[1,2]`

## Starter code (python3)
```
class Solution:
    def twoSum(self, nums, target):
```
"""

FENCED = """# 5. Pal

Output order does not matter.

**Example 1:**
```
Input: s = "a,b", flag = true
Output: "b"
Explanation: Output: not an example
```
**Example 2:**
```
Input: s = 'x', flag = false
Output: None
```
"""

THREE_SUM = """# 15. 3Sum
Notice that the order of the output and the order of the triplets does not matter.
**Example 1:**
**Input:** nums = [-1,0,1,2,-1,-4]
**Output:** [[-1,-1,2],[-1,0,1]]
"""

SKIPPED = """# 2. Add Two Numbers
**Example 1:**
**Input:** l1 = 1->2
**Output:** [1,2]
**Example 2:**
**Input:** a = 1, b = 2
**Output:** 3.00000
**Example 3:**
**Input:** a = 1
**Output:** 1->2
**Example 4:**
**Input:** a
**Output:** 1
"""


def test_two_sum_examples_are_typed_and_ordered_any() -> None:
    found = parse_examples(TWO_SUM)
    assert found == [
        Example(1, {"nums": [2, 7, 11, 15], "target": 9}, [0, 1], "any"),
        Example(2, {"nums": [3, 2, 4], "target": 6}, [1, 2], "any"),
    ]


def test_fenced_examples_and_python_literals() -> None:
    found = parse_examples(FENCED)
    assert [e.args for e in found] == [
        {"s": "a,b", "flag": True},
        {"s": "x", "flag": False},
    ]
    assert [e.expected for e in found] == ["b", None]
    assert {e.order for e in found} == {"exact"}


def test_triplets_sentence_means_deep_order() -> None:
    assert parse_examples(THREE_SUM)[0].order == "deep"


def test_unparseable_examples_are_skipped_but_numbering_is_kept() -> None:
    found = parse_examples(SKIPPED)
    assert found == [Example(2, {"a": 1, "b": 2}, 3.0, "exact")]


def test_output_without_input_and_empty_statement() -> None:
    assert parse_examples("**Output:** 1\n") == []
    assert parse_examples("") == []


def test_starter_section_is_never_scanned() -> None:
    text = "# t\n## Starter code (python3)\n```\nInput: a = 1\nOutput: 2\n```\n"
    assert parse_examples(text) == []
