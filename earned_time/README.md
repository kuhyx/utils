# earned_time

Penalty-then-reward for gate apps: **one** table of what every gate earns in
gaming time and shutdown time, read by both consumers.

| consumer | applies | via |
|---|---|---|
| steam-backlog-enforcer | `Resolution.gaming_minutes` | `_budget_resolve.resolve_budget` |
| screen-locker | `Resolution.shutdown_minutes` | `_shutdown_base.reset_to_base_if_new_day` + live pass |

A gate (leetcode-guard, book-guard, ...) never touches either. It publishes a
fact — HMAC-signed `credit` rows in its ledger — and is registered here once.

## Adding a gate

1. The gate writes `{"entries": [...]}` to its ledger. Each row has
   `kind: "credit"`, a `detail` dict, and an `hmac` signed with
   `/etc/workout-locker/hmac.key` (`earned_time.entry_signature`, the same as
   gatelock's `log_integrity`).
2. Add an `Earner` to `earned_time/_policy.py` and to `EARNERS`:

   ```python
   ANKI = Earner(
       name="anki",                     # also screen-locker's "anki_bonus_date" stamp
       label="Anki",
       gaming_minutes=30,
       shutdown_minutes=30,
       penalty_from=date(2026, 10, 10), # base drops by the same 30/30 from then on
       ledger=".local/share/anki_guard/ledger.json",
       match=_anki_match,               # which verified credit rows count today
       missing_ledger_is_no=True,
   )
   ```

3. Bump the version, tag `earned-time-vX.Y.Z`, and bump the pin in both
   consumers. Neither needs code for a ledger-backed flat earner.

`penalty_from` is the gate's start date, so the base is never cut before the
reward that pays it back exists. The best case stays the same, because the
base drops by exactly what the new earner adds.

## Rules the consumers rely on

- **Minutes everywhere.** Shutdown is minutes after local midnight.
  screen-locker still stores whole hours and refuses (raises) a remainder
  rather than flooring it.
- **Paths are passed in.** `done_today(earner, ledger, key_file)` never
  resolves a real path itself; consumers' test suites redirect their own
  constants.
- **`None` is "could not check", never "no".** It earns nothing (fail closed),
  but consumers log it. A missing answer in `resolve()` is logged as well; an
  unknown earner name raises.
- **Stdlib only.** The gaming daemon imports this as root, headless.

## Install

```console
pip install --user "earned-time @ git+https://github.com/kuhyx/utils@earned-time-v0.1.0#subdirectory=earned_time"
```

The root `steam-backlog-enforcer.service` sets `HOME=/home/kuhy`, so it imports
from the same user site-packages.

## Test

```console
scripts/run_subproject_tests.sh earned_time
```
