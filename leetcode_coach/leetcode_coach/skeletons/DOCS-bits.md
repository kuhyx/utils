## Skeleton: Bit manipulation (bits)

Signal: works per bit; self-inverse (XOR cancels pairs); isolates one bit; O(1) extra space.
Trap: JavaScript bit operators work on signed 32-bit integers; use >>> 0 when the sign bit must not count as negative.

```
// Fold with one bit operator.
let acc: number = /* HOLE: neutral start for the operator */;
for (let i = 0; i < seq.length; i++) {
  acc = acc /* HOLE: the operator: ^, & or | */ seq[i];
}

// Visit every bit position.
for (let b = 0; b < /* HOLE: width of the integer */; b++) {
  const bit: number = (x >> /* HOLE: position */) & /* HOLE: mask for one bit */;
  /* HOLE: use bit */
}

// Clear or keep one bit.
x = x /* HOLE: operator */ (/* HOLE: expression built from x */);
```
