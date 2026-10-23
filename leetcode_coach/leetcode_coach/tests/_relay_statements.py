"""Trimmed real statements (``fetch_problem.render``, fetched 2026-10-23).

Three shapes LeetCode uses for the examples: bold labels on plain lines
(missing-number), bold labels with the values in code spans (two-sum), and
bold labels inside a ``` fence (merge-intervals). The non-breaking-space
lines are copied as fetched.
"""

from __future__ import annotations

MISSING_NUMBER = """# 268. Missing Number (Easy)
Tags: Array, Hash Table, Math, Binary Search, Bit Manipulation, Sorting

Given an array `nums` containing `n` distinct numbers in the range `[0, n]`.

**Example 1:**

**Input:** nums = [3,0,1]

**Output:** 2

**Explanation:**

`n = 3` since there are 3 numbers, so all numbers are in the range `[0,3]`.

**Example 2:**

**Input:** nums = [0,1]

**Output:** 2

**Example 3:**

**Input:** nums = [9,6,4,2,3,5,7,0,1]

**Output:** 8

## Starter code (javascript)
```
/**
 * @param {number[]} nums
 * @return {number}
 */
var missingNumber = function(nums) {

};
```
"""

TWO_SUM = """# 1. Two Sum (Easy)
**Example 1:**
**Input:** `nums = [2,7,11,15], target = 9`
**Output:** `[0,1]`
**Explanation:**
The sum of `nums[0]` and `nums[1]` is `2 + 7 = 9`.
**Example 2:**
**Input:** `nums = [3,2,4], target = 6`
**Output:** `[1,2]`
**Example 3:**
**Input:** `nums = [3,3], target = 6`
**Output:** `[0,1]`
## Starter code (javascript)
```
var twoSum = function(nums, target) {
};
```
"""

MERGE_INTERVALS = """# 56. Merge Intervals (Medium)
**Example 1:**
```
**Input:** intervals = [[1,3],[2,6],[8,10],[15,18]]
**Output:** [[1,6],[8,10],[15,18]]
**Explanation:** Since intervals [1,3] and [2,6] overlap, merge them into [1,6].
```
**Example 2:**
```
**Input:** intervals = [[1,4],[4,5]]
**Output:** [[1,5]]
```
## Starter code (javascript)
```
var merge = function(intervals) {
};
```
"""
