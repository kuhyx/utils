# Predict: NULL needs IS NULL

The same filter, now with an explicit NULL branch. How many rows, and why does it differ from the plain `!=` version?

Predict the exact output of the query before running it: one grid row per
result row, `NULL` for SQL NULL, no header. If the query fails, type `ERROR`
in the first cell.
