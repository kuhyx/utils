## Skeleton: Two pointers and sliding window (pointers-window)

Signal: two moving indexes; from both ends (needs sorted input); window moves right (monotone condition).
Trap: decide whether the loop is lo < hi or lo <= hi before you write the body, and move at least one index every turn.

```
// From both ends.
let lo: number = 0;
let hi: number = /* HOLE: last index */;
while (lo < hi) {
  /* HOLE: look at seq[lo] and seq[hi] */
  if (/* HOLE: which end is wrong */) {
    lo++;
  } else {
    hi--;
  }
}

// Window: the right end grows every turn, the left end only repairs.
let from: number = 0;
for (let to = 0; to < seq.length; to++) {
  /* HOLE: add seq[to] to the window state */
  while (/* HOLE: the window is invalid */) {
    /* HOLE: remove seq[from] from the window state */
    from++;
  }
  /* HOLE: the window is valid here; record what you need */
}
```
