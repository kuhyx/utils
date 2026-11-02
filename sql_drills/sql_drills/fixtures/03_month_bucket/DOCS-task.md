# Month buckets with DATE_FORMAT and conditional aggregation

`orders` has one row per order with a status of `shipped`, `pending` or
`cancelled`. Summarise per calendar month.

Output columns (no header): `month` (as `YYYY-MM`), total orders, shipped
orders, cancelled orders, revenue of shipped orders only.

- Revenue is `0.00` for a month with no shipped orders.
- Only months that have at least one order appear.
- Order by `month` ascending.
