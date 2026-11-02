# Pivot text attributes with MAX(CASE WHEN)

`person_attrs` stores one attribute per row (`email`, `phone`, `city`) in a
text column. Turn it into one row per person.

Output columns (no header): `person`, `email`, `phone`, `city`.

- A missing attribute prints as `NULL`.
- Order by `person` ascending.
- Hint: `SUM` cannot pivot text; think about which aggregate can.
