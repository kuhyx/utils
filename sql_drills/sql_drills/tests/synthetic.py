"""Original statements in LeetCode's layout; real problem text is never stored."""

from __future__ import annotations

MONTHS = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
]

PIVOT = """# 9001. Pivot Shipments (Easy)
Tags: Database
Languages available: mysql, postgresql

Table: `Shipments`

```

+-------------+---------+
| Column Name | Type    |
+-------------+---------+
| id          | int     |
| weight      | int     |
| month       | varchar |
+-------------+---------+
(id, month) is the primary key of this table.
Each row is the weight a depot shipped in one month.
The month is one of ["Jan","Feb","Mar","Apr","May","Jun",
"Jul","Aug","Sep","Oct","Nov","Dec"].

```

Turn the table into one row per depot, with a weight column **for each month**.

Rows may come back in **any order**.

**Example 1:**

```

**Input:**
Shipments table:
+------+--------+-------+
| id   | weight | month |
+------+--------+-------+
| 1    | 400    | Jan   |
| 2    | 900    | Jan   |
| 3    | 150    | Feb   |
| 1    | 250    | Feb   |
| 1    | 70     | Mar   |
+------+--------+-------+
**Output:**
+------+------------+------------+------------+-----+------------+
| id   | Jan_Weight | Feb_Weight | Mar_Weight | ... | Dec_Weight |
+------+------------+------------+------------+-----+------------+
| 1    | 400        | 250        | 70         | ... | null       |
| 2    | 900        | null       | null       | ... | null       |
| 3    | null       | 150        | null       | ... | null       |
+------+------------+------------+------------+-----+------------+
**Explanation:** Depots ship nothing from Apr to Dec.

```

## Starter code (mysql)
```
# Write your MySQL query statement below
```
"""

ORDERS = """# 9002. Monthly Orders (Medium)
Tags: Database
Languages available: mysql, postgresql

Table: `Orders`

```

+---------------+---------+
| Column Name   | Type    |
+---------------+---------+
| id            | int     |
| region        | varchar |
| status        | enum    |
| total         | int     |
| placed_on     | date    |
+---------------+---------+
id is the primary key of this table.
The status column is an enum of type ["shipped", "returned"].

```

For each month and region, report the number of orders and their total, plus the
number of shipped orders and their total.

Rows may come back in **any order**.

**Example 1:**

```

**Input:**
Orders table:
+------+--------+----------+-------+------------+
| id   | region | status   | total | placed_on  |
+------+--------+----------+-------+------------+
| 121  | North  | shipped  | 1000  | 2018-12-18 |
| 122  | North  | returned | 2000  | 2018-12-19 |
| 123  | North  | shipped  | 2000  | 2019-01-01 |
| 124  | South  | shipped  | 2000  | 2019-01-07 |
+------+--------+----------+-------+------------+
**Output:**
+---------+--------+-------------+---------------+-------------+---------------+
| month   | region | order_count | shipped_count | order_total | shipped_total |
+---------+--------+-------------+---------------+-------------+---------------+
| 2018-12 | North  | 2           | 1             | 3000        | 1000          |
| 2019-01 | North  | 1           | 1             | 2000        | 2000          |
| 2019-01 | South  | 1           | 1             | 2000        | 2000          |
+---------+--------+-------------+---------------+-------------+---------------+

```

## Starter code (mysql)
```
# Write your MySQL query statement below
```
"""

PIVOT_GOOD_ROWS = [
    ["1", "400", "250", "70", *["NULL"] * 9],
    ["2", "900", *["NULL"] * 11],
    ["3", "NULL", "150", *["NULL"] * 10],
]
ORDERS_GOOD_ROWS = [
    ["2019-01", "South", "1", "1", "2000", "2000"],
    ["2018-12", "North", "2", "1", "3000.00", "1000"],
    ["2019-01", "North", "1", "1", "2000", "2000"],
]

PIVOT_SQL = (
    "SELECT id, "
    + ", ".join(
        f"SUM(CASE WHEN month = '{m}' THEN weight END) AS {m}_Weight" for m in MONTHS
    )
    + " FROM Shipments GROUP BY id"
)
ORDERS_SQL = {
    "mysql": "DATE_FORMAT(placed_on, '%Y-%m')",
    "postgresql": "TO_CHAR(placed_on, 'YYYY-MM')",
}
