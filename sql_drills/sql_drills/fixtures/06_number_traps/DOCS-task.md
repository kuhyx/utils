# Number traps: AVG scale, ROUND, CAST AS DECIMAL

`team_results` has one row per team per season.

Output columns (no header), per team:

1. `team`
2. average wins, `ROUND`ed to 2 decimals
3. average games, NOT rounded (print whatever MySQL gives you)
4. win percentage `100 * SUM(wins) / SUM(games)` as `DECIMAL(5,1)`
   via `CAST`

- Order by `team` ascending.
- Trap: `AVG()` of an integer column returns 4 decimals (`2.5000`), and
  `/` is decimal division in MySQL (use `DIV` for the integer kind).
