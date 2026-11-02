# Thousands separators with FORMAT

`invoices` has one row per invoice.

Output columns (no header), per customer:

1. `customer`
2. total amount with thousands separators and 2 decimals (`35,200.59`)
3. average amount with thousands separators and 0 decimals

- Order by the numeric total descending (not the formatted text).
- Trap: `FORMAT` returns text, so sort on the `SUM`, and `FORMAT(x, 0)` is
  not the same string as `ROUND(x)` (no separators).
