# GROUP BY with WHERE versus HAVING

`tickets` holds support tickets with hours spent. Ignoring `low` priority
tickets, find teams with at least 3 tickets AND at least 10 total hours.

Output columns (no header): `team`, ticket count, total hours.

- Order by total hours descending, then `team` ascending.
- Row filters (`priority`) go in `WHERE`; aggregate filters in `HAVING`.
