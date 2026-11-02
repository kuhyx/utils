# LAG and DATEDIFF: find long gaps between logins

`logins` has one row per user per day they logged in. Find every pair of
consecutive logins by the same user that are 7 or more days apart.

Output columns (no header): `user_name`, previous login date, login date,
gap in days.

- Order by `user_name`, then login date ascending.
- Window functions cannot appear in `WHERE`; wrap them in a CTE or subquery.
