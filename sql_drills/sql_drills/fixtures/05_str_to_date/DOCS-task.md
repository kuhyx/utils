# Parse text dates with STR_TO_DATE

`signups.signup_text` stores a timestamp as text in the US layout
`MM/DD/YYYY HH:MM` (for example `03/14/2022 18:45`).

Output columns (no header): `id`, then the signup date as `YYYY-MM-DD`.

- Keep only signups on or after 2022-03-01 (compare real dates, not text).
- Order by the parsed timestamp ascending.
- Trap: ordering the raw text sorts by month first, across years.
