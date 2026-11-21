## Skeleton: Stack and queue (stack-queue)

Signal: last-in-first-out; next-greater lookup; brackets; amortized O(n).
Trap: pop only after you check the stack is not empty; keep INDEXES on the stack when you need distances; shift() on a long array is slow.

```
// Monotonic stack: each element is pushed once and popped at most once.
const waiting: number[] = [];
for (let i = 0; i < seq.length; i++) {
  while (waiting.length > 0 && /* HOLE: the last waiting element is settled by seq[i] */) {
    const last: number = waiting.pop() as number;
    /* HOLE: record what seq[i] settles for last */
  }
  waiting.push(/* HOLE: the index or the value that keeps waiting */);
}
/* HOLE: what happens to elements still waiting at the end */

// Queue: take from the front.
const front: number = lineup.shift() as number;
```
