# LEFT JOIN anti-join and NULL handling

List customers who have never placed a valid order. An order is valid when
its status is not `cancelled`; a customer with only cancelled orders (or no
orders) qualifies.

Output columns (no header): `name`, `phone`, where a missing phone prints as
`n/a`.

- Order by `name` ascending.
- Trap: put the status condition in the `ON` clause, not in `WHERE`, or the
  cancelled-only customers vanish.
