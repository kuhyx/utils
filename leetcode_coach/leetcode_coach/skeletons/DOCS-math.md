## Skeleton: Math and number theory (math)

Signal: divides its inputs (gcd); digits of a number; primes and divisors; closed-form formula.
Trap: JavaScript division gives a fraction, so floor it; stop trial division when d * d passes the limit, not at the limit.

```
// Peel the last figure off a number.
let rest: number = /* HOLE: the number to take apart */;
while (rest > 0) {
  const digit: number = rest % 10;
  /* HOLE: use digit */
  rest = Math.floor(rest / /* HOLE: divisor */);
}

// Euclid frame: the pair shrinks until one side is spent.
function fold(a: number, b: number): number {
  while (/* HOLE: when to stop */) {
    [a, b] = [b, /* HOLE: the next remainder */];
  }
  return /* HOLE: which of the two is left */;
}

// Trial division.
for (let d = 2; d * d <= /* HOLE: limit */; d++) {
  /* HOLE: what a divisor tells you */
}
```
