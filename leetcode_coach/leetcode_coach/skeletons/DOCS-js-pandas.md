## Skeleton: JavaScript closures, promises and pandas (js-pandas)

Signal: a function that returns a function, a timer or a delayed result, an async call (JavaScript); a table of rows to filter, join, group or reshape (pandas).
Trap: a closure keeps the variable, not a copy; await only works inside async; setTimeout takes milliseconds and returns the handle you cancel with; in pandas keep a plain assignment per step, and reset_index after a groupby.

```
// Closure, timer and promise frame.
function make(start) {
  let state = /* HOLE: private value kept between calls */;
  return function () { /* HOLE: update state, then read it */ };
}
const handle = setTimeout(() => { /* HOLE: what runs later */ }, /* HOLE: delay in milliseconds */);
clearTimeout(handle);
async function load(ms) {
  const wait = new Promise((resolve, reject) => { /* HOLE: call resolve or reject, when */ });
  const first = await /* HOLE: a promise */;
  const all = await Promise.all(/* HOLE: list of promises started together */);
}
```

```
import pandas as pd

# One transformation per line; the final step is yours.
out = (
    frame
    .merge(/* HOLE: other frame */, on=/* HOLE: key column */, how=/* HOLE: join kind */)
    .query(/* HOLE: filter expression */)
    .groupby(/* HOLE: key columns */, as_index=False)
    .agg(/* HOLE: named aggregations */)
    .sort_values(/* HOLE: column */, ascending=/* HOLE: True or False */)
)
```
