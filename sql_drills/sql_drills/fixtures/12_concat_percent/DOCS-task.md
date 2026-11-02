# CONCAT and percentage formatting

`poll_votes` has the vote count per option for several polls. For each
option print its share of its own poll's votes with one decimal.

Output columns (no header): `poll_id`, then text like `Red: 42.9%`.

- Order by `poll_id`, then votes descending, then option name ascending.
- A share of exactly 50 prints `50.0%` and zero prints `0.0%`.
- Trap: `ROUND(x, 1)` keeps the trailing `.0` only on a DECIMAL, so do the
  arithmetic in decimal, not by dividing integers with `DIV`.
