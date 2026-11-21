## Skeleton: SQL queries (sql)

Signal: a table schema and a question about rows; joins, group-by, a filter before or after grouping.
Trap: clauses run in this order: FROM, JOIN, WHERE, GROUP BY, HAVING, SELECT, ORDER BY, LIMIT; WHERE cannot see an aggregate or a select alias, HAVING can see the aggregate; a filter on the right table of a LEFT JOIN belongs in ON, not WHERE.

```
SELECT /* HOLE: columns, or an aggregate over each group */
FROM /* HOLE: main table */ AS a
LEFT JOIN /* HOLE: other table */ AS b
  ON /* HOLE: join condition */
WHERE /* HOLE: row filter: runs before grouping, no aggregates */
GROUP BY /* HOLE: every selected column that is not aggregated */
HAVING /* HOLE: group filter: aggregates allowed */
ORDER BY /* HOLE: sort keys, ASC or DESC */
LIMIT /* HOLE: how many rows */;
```
