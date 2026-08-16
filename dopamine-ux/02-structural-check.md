Add a structural-token drift checker to CI

## findings (2, ranked by value over effort)

1. **Spacing, radius and type have never been drift-checked** — `palette_check.py`
   parses hex only, so three whole token categories can diverge across stacks
   while CI stays green. Motion inherits the same hole.
2. **`palette_map.py` points at a "scale check" that does not exist** — a
   comment describing a guarantee nobody wrote.

## what

`palette_check.py` guarantees the colour palette agrees across all stack copies.
It does **not** check anything else — verified 2026-08-16 by reading its four
parsers, every one of which requires a `#RRGGBB` value:

```python
parse_css : r"(--[a-z0-9-]+)\s*:\s*(#[0-9A-Fa-f]{6})\s*;"
parse_dart: r"static const Color (\w+) = Color\(0x[fF]{2}([0-9A-Fa-f]{6})\)"
parse_tk  : r'^\s{4}(\w+):\s*str\s*=\s*"(#[0-9A-Fa-f]{6})"'
parse_md  : r"^\|\s*`([a-z0-9-]+)`\s*\|\s*`(#[0-9A-Fa-f]{6})`"
```

So **spacing, radius and type have been silently unprotected all along**, and the
motion tokens added by prompt 01 inherit the same hole. A `--duration-fast: 120ms`
is invisible to every parser: CI passes while the stacks drift apart.

Worse, `scripts/palette_map.py:159` claims structural values are "checked by the
scale check" — **no such script exists anywhere in `~/utils`**. That comment
describes a check that was never written. This prompt writes it.

## where

Repo: `~/utils`.

**Create** `~/utils/unified-design-system/scripts/structural_check.py`.

**Edit** `~/utils/.github/workflows/palette-drift.yml` — add a step invoking it.
The workflow deliberately has no `paths:` filter; keep it that way.

**Fix** the stale comment at `~/utils/unified-design-system/scripts/palette_map.py`
(~:159) to name the real script.

Sources to compare (three code stacks + the prose freeze):

| Role | Path |
|---|---|
| prose freeze | `~/utils/unified-design-system/tokens.md` (spacing/radius/type) |
| motion freeze | `~/utils/unified-design-system/motion.md` (**created by prompt 01** — run it first) |
| web/React | `~/utils/web_ui/src/tokens.css` |
| Flutter/Dart | `~/utils/design_system/lib/src/tokens.dart` |
| Python/Tkinter | `~/utils/gatelock/gatelock/_window.py` (`class LockConfig`) |

## must

- Cover **motion** (durations, easing) **and** the already-unprotected
  **spacing, radius and type** scales, in one checker.
- Mirror `palette_check.py`'s two-halves design, because it is the part that
  actually works:
  1. **Agreement** — for each mapped token, resolve it in every non-`n/a` stack
     and fail if values disagree.
  2. **Completeness, bidirectional** — every structural value parsed out of any
     source must be mapped, or explicitly exempted. This is what catches
     "added it to one stack, forgot the others".
- Support an explicit **`n/a` per stack**, and require a reason string. Tkinter
  has no animation framework; a duration legitimately does not exist there. An
  honest `n/a` with a reason is correct — a fabricated constant is not.
- **Adjudicate with exit codes.** Exit non-zero on drift with a message naming
  the token and the disagreeing files. No warnings-only mode.
- Keep every file ≤ **250 lines** (`~/utils/file_length/config.py`). Note
  `palette_check.py` is 231 and `palette_map.py` is 162 — that pair was split
  precisely to stay under the cap. **Split yours the same way from the start**
  (`structural_check.py` + `structural_map.py`) rather than discovering the
  problem at 251 lines.
- Ruff-clean under the repo's config. No `# noqa`, no `type: ignore`.

- **Expect it to fail on first run.** Spacing/radius/type have never been
  compared; there may be real pre-existing drift. That is the point of writing
  it. Fix whatever it surfaces, in the stack copy that is wrong, and say in the
  session summary what drifted.
- must not: weaken the checker, add an exemption, or narrow its scope to make it
  green. If a token genuinely differs per stack for a good reason, encode it as
  an `n/a`/variant **with the reason recorded**, not as a silent skip.
- must not: modify `palette_check.py`. It works; it is simply colour-only. The
  two scripts run side by side.
- must not: change any token *value* to resolve a disagreement without saying so
  explicitly — that is a design change, and `tokens.md` is a freeze. Surface it
  and let kuhy decide which value is canonical.

- optional: teach it the shadow tier too, if that falls out cheaply.

## done

1. `python3 ~/utils/unified-design-system/scripts/structural_check.py` exits 0,
   and exits non-zero when you deliberately break one stack copy (**test both
   directions** — a checker that never fails is not a checker).
2. It is wired into `~/utils/.github/workflows/palette-drift.yml` and the
   workflow passes.
3. `palette_map.py`'s "scale check" comment names the real script.
4. `~/utils/scripts/check_file_length.sh --all` reports no new violations.
5. The session summary states what drift, if any, the first run found.

## verify

Desktop. Run the script, paste the output. Then prove it fails: change one
spacing or duration value in **one** stack copy, re-run, paste the non-zero exit
and the message, and revert. Both halves of that demonstration are required —
the passing run alone proves nothing.

## read first

- `~/utils/unified-design-system/scripts/palette_check.py` — the design to
  mirror. Read `NON_COLOUR_CSS`: it is the regex that currently *excludes*
  spacing/radius/type/shadow from the colour check, and therefore the precise
  list of what you are now covering.
- `~/utils/unified-design-system/scripts/palette_map.py` — the `PALETTE` tuple of
  `Token(canonical, md, css, dart, tk, why)` rows. Your map wants the same shape,
  including the `why` field.
- `~/utils/.github/workflows/palette-drift.yml` — how `palette_check.py` and
  `ramp_check.py` are invoked; add your step alongside.
- `~/utils/unified-design-system/motion.md` — what prompt 01 created.
- `~/utils/unified-design-system/tokens.md` — the spacing/radius/type tables.
  **Do not edit it**; it is 260 lines and already over the cap.

## context you would otherwise rediscover

- The four "stack copies" are really **three code stacks plus a prose freeze**.
  There is no fourth code stack; do not hunt for one.
- `~/dufs-cloud/app/lib/ui/theme.dart` is a **fifth, uncompared copy** of the
  palette (the Flutter app has no `design_system` dependency and hand-restates
  every hex). It is out of scope here — prompt 07 wires it up properly. Do not
  add it as a source to this checker; wait until 07 has removed it.
- Three Flutter apps (diet-guard, workout_app, wake_alarm) similarly
  hand-transcribe tokens into local `lib/ui/theme.dart` files. Those are
  deliberately outside the checker's scope for now — bringing them in is a much
  larger job than this prompt.
- `~/utils/gatelock/` is a package inside this monorepo, not a separate repo.
