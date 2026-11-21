## Skeleton: Hashing and counting (hashing)

Signal: O(1) lookup; stores a value per key; presence only; arbitrary keys (a Map) or a bounded key range (an array).
Trap: a Map returns undefined for a new key, so give it a default with ?? before you do arithmetic.

```
// Map frame: ask first, then store.
function tally(seq: string[]): number {
  const seen = new Map<string, number>();
  for (let i = 0; i < seq.length; i++) {
    const item: string = seq[i];
    const before: number = seen.get(item) ?? /* HOLE: default for a new item */;
    /* HOLE: decide with before; the answer may be ready already */
    seen.set(item, /* HOLE: what to store for this item */);
  }
  return /* HOLE: what the map says at the end */;
}

// Bounded keys (26 letters): a plain list indexed by key.
const slots: number[] = new Array(/* HOLE: size of the key range */).fill(0);
slots[seq[i].charCodeAt(0) - /* HOLE: code of the first key */] += /* HOLE: step */;
```
