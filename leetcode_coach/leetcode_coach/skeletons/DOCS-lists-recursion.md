## Skeleton: Linked lists and recursion (lists-recursion)

Signal: follow a chain of next links; cycle; reverse or merge in place; a problem that repeats on a smaller copy of itself.
Trap: save cur.next in a variable before you overwrite it; every recursion needs its base case written first and a call on a strictly smaller case.

```
// Walk a chain, rewiring as you go.
function walk(start: ListNode | null): ListNode | null {
  let prev: ListNode | null = null;
  let cur: ListNode | null = start;
  while (cur !== null) {
    const after: ListNode | null = cur.next;
    /* HOLE: rewire cur.next */
    prev = /* HOLE: the new previous */;
    cur = after;
  }
  return /* HOLE: the new front of the chain */;
}

// Recursion frame.
function dive(depth: number): number {
  if (/* HOLE: base case */) { return /* HOLE: base value */; }
  const below: number = dive(/* HOLE: a strictly smaller case */);
  return /* HOLE: combine below with this level */;
}
```
