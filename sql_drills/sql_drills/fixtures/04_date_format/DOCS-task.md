# Date formatting: %i is minutes, %M is the month name

`events` has a `DATETIME` column. Print each event in two display formats.

Output columns (no header): `id`, then the start as
`Friday, 05 March 2021 09:07` (weekday name, 2-digit day, month name, year,
24-hour `HH:MM`), then the 12-hour time as `09:07 AM`.

- Order by `id` ascending.
- Trap: mixing up `%i` (minutes) with `%M` (month name), and `%h` (12-hour)
  with `%H` (24-hour).
