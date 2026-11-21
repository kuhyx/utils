## Skeleton: Binary search (binary-search)

Signal: O(log n) per query; sorted input, or a yes/no question that flips once as the guess grows.
Trap: pick one range style, [lo, hi] or [lo, hi), and keep the loop test, both updates and the return consistent with it; a mismatch loops forever.

```
let lo: number = 0;
let hi: number = /* HOLE: last index, or length: match the loop test */;
while (lo /* HOLE: < or <= */ hi) {
  const pivot: number = lo + Math.floor((hi - lo) / 2);
  if (/* HOLE: invariant: what is true at pivot when the answer is at pivot or to its left */) {
    hi = /* HOLE: pivot or pivot - 1 */;
  } else {
    lo = /* HOLE: pivot + 1 or pivot */;
  }
}
return /* HOLE: lo or hi, and a range check if the answer may not exist */;
```
