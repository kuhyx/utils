# Pivot quarters into columns with SUM(CASE WHEN)

`shop_sales` holds one row per sale. Report the total amount per region with
one column per quarter.

Output columns (no header): `region`, `Q1`, `Q2`, `Q3`, `Q4`.

- A region with no sales in a quarter shows `0`, never `NULL`.
- Order by `region` ascending.
