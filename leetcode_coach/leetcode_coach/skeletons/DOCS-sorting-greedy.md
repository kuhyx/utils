## Skeleton: Sorting and greedy (sorting-greedy)

Signal: makes equal values adjacent; overlaps become adjacent; earliest end first; greedy commits and never revisits; needs a majority.
Trap: sort() without a comparator compares as strings ([10, 9, 1] becomes [1, 10, 9]); and sort() reorders the array you pass it.

```
// Sort a copy, then one pass that commits to the locally best choice.
const order: number[] = seq.slice().sort(/* HOLE: comparator; negative puts the first argument first */);
let chosen: number = /* HOLE: start state */;
for (let i = 0; i < order.length; i++) {
  if (/* HOLE: can order[i] be taken given what is already chosen */) {
    /* HOLE: commit to order[i], never undo it */
  }
}

// Candidate and streak (majority vote).
let pick: number | undefined = undefined;
let streak: number = 0;
for (let i = 0; i < seq.length; i++) {
  if (streak === 0) {
    pick = /* HOLE: the new candidate */;
  }
  streak += /* HOLE: up or down, and when */;
}
```
