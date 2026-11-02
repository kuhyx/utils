SQL drill engine (MySQL 8.0.33 + PostgreSQL 18.6, one container each): `import sql_drills as sd`.
Drills: `sd.run(id, sql, dialect)`. LeetCode examples: `sd.run_problem(slug_or_statement, sql, dialect)`.
Data: `$SQL_DRILLS_DATA`. Install: `./install.sh`.
Root password: random, `~/.config/sql_drills/root_password` (0600); learner SQL runs as a per-run user, client commands (`\!`) refused.
