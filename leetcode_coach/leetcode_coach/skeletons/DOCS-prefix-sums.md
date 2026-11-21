## Skeleton: Prefix sums (prefix-sums)

Signal: range query in O(1) after O(n) setup; keeps every prefix; handles negatives (a window breaks, a prefix does not).
Trap: the prefix array has one more slot than the input, and slot 0 is the empty prefix; an off-by-one here shifts every answer.

```
// Build.
const pre: number[] = new Array(seq.length + /* HOLE: extra slots */).fill(0);
for (let i = 0; i < seq.length; i++) {
  pre[/* HOLE: slot to fill */] = pre[/* HOLE: previous slot */] + seq[i];
}

// Query: seq[l..r] inclusive is one subtraction.
const span: number = pre[/* HOLE: slot for the r side */] - pre[/* HOLE: slot for the l side */];

// Prefix plus map: seed the empty prefix before the loop.
const firstSeen = new Map<number, number>([[0, /* HOLE: what the empty prefix stores */]]);
```
