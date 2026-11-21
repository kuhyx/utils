## Skeleton: Heap and dynamic programming (heap-dp)

Signal: O(log n) push and pop-min (a heap, partial order); an answer built from answers to smaller inputs (a DP table or a memo).
Trap: name what ONE cell of the table means before you fill it, and size the table for the base case; JavaScript has no built-in heap, so keep one in an array.

```
// Bottom-up table.
const cell: number[] = new Array(/* HOLE: how many states, base state included */).fill(0);
cell[0] = /* HOLE: the base state */;
for (let i = 1; i < cell.length; i++) {
  cell[i] = /* HOLE: from cell[i - 1], cell[i - 2], ... */;
}
const answer: number = cell[/* HOLE: which state is the answer */];

// Heap kept in a plain list: the parent of slot i is (i - 1) >> 1.
function siftUp(h: number[], i: number): void {
  while (i > 0) {
    const up: number = (i - 1) >> 1;
    if (/* HOLE: parent already in order */) { break; }
    /* HOLE: swap h[i] and h[up] */
    i = up;
  }
}
```
