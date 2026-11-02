# Top-N per group with DENSE_RANK

Show employees whose salary is among the two highest DISTINCT salaries in
their department (ties share a rank, so more than two people can appear).

Output columns (no header): `dept`, `name`, `salary`, the dense rank.

- Order by `dept`, then rank, then `name` ascending.
- `RANK()` would skip numbers after ties; this drill wants `DENSE_RANK()`.
