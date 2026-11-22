# /leetcode review [slug]: name the one cause of a slow solve

Claude Code only; `leetcode --local` does not run this.

A review looks at a solve the guard flagged: LeetCode accepted it, but kuhy
spent more than 20 active minutes on it although the unit's theory was already
taught. You find the one cause, log it, and that starts the cold re-test clock
(+3 and +10 days). You do not coach the problem again.

**Never print a solution**, a corrected line or a rewrite of kuhy's code.
`reveal` does not apply in a review.

## The flow

1. **Pick the solve.** Run:
   ```bash
   python3 -m leetcode_coach.review_cli review-list
   ```
   - No slug in the arguments: show kuhy the lines as printed and ask which
     solve he wants to review.
   - A slug in the arguments: go on only if one line starts with that slug.
   - `nothing to review`, or his slug is not on the list: say so in one line
     and stop. Only flagged solves can be reviewed.
   - `could not check: ...` (exit 2): the guard gave no report. Show the line
     and stop. Never report it as "nothing to review".
2. **Show the evidence.** Quote the solve's line and say what it means:
   `active` is the time the problem page was on screen, `span` runs from the
   day's first heartbeat to Accepted, `failed` counts the failed submissions
   by verdict, `first submit` is the active time before the first submission,
   `tabs` splits the active time by page tab, `theory` is the unit's tutor
   state at the solve.
3. **Ask for his accepted code.** kuhy pastes it. Do not fetch it and do not
   rewrite it.
4. **Ask at most 3 questions**, one per message, each about something the
   evidence or the code shows ("12 minutes passed before your first submit:
   what did you do in them?"). Stop asking once the cause is clear.
5. **Name exactly ONE cause** in one or two sentences that cite the evidence.
   If two fit, pick the one that cost more minutes. kuhy may correct you: his
   word decides.

   | cause id | what happened |
   |---|---|
   | `statement` | He misread the statement or missed a part of it. |
   | `missing-idea` | He did not have the idea the solution needs. Name the unit that teaches it (`--module`). |
   | `idea-to-code` | He had the idea early and could not turn it into code. |
   | `debugging` | The code was nearly right; the time went into finding a bug (debugging process). |
   | `interruption` | He was away or distracted; the minutes are not work on the problem. |

   Then close the review:
   ```bash
   python3 -m leetcode_coach.review_cli review-finish <slug> --cause <cause> [--module <unit>]
   ```
   `--module <unit>` goes with `missing-idea` and with no other cause. The
   unit is a curriculum unit id: `scans`, `hashing`, `math`, `bits`,
   `sorting-greedy`, `pointers-window`, `prefix-sums`, `stack-queue`,
   `binary-search`, `lists-recursion`, `trees`, `heap-dp`, `sql`, `js-pandas`.

   Read its output; it says exactly what it wrote:
   - exit 0, `review logged: ...` and `ledger row: written`: the solve is no
     longer flagged, and the re-test falls due 3 and 10 days from today
     (`leetcode --retest <slug>`).
     The same write adds a `progress` row (`progress:<day>:<done>:<target>`),
     so a review pays its share of the day's bonus: the target is how many
     solves were flagged when that day's first review finished and does not
     change after it.
   - `refused: ...` (exit 1): the slug is not flagged or an argument is
     wrong. Nothing was written.
   - `could not check: ...` (exit 2): nothing was written. Tell kuhy; do not
     retry in a loop.
   - `nothing written: no signed ledger row ...` (exit 3): the signing key is
     unreadable. Nothing was written and the solve stays flagged. Tell kuhy.
   - `ledger row written, review event NOT logged ...` (exit 3): run the same
     command again.
6. **Card, for two causes only.** `missing-idea` and `idea-to-code` get ONE
   property -> operation card for the toolbox entry his accepted code relies
   on, built the post-mortem way (SKILL.md section 5b, steps 2 to 4):
   ```bash
   python3 -m leetcode_coach.toolbox_cards cards "<entry>" \
     | ~/.claude/skills/leetcode/make_cards.py -
   ```
   `statement`, `debugging` and `interruption` get no card: the `review`
   event is their whole record. No cause writes to the tutor or changes a
   price.
7. **End.** Tell kuhy the cause and the two re-test dates, then stop.

**An abandoned review writes nothing.** If kuhy stops before a cause is named,
run no command: the solve stays flagged and he can review it later.

## Skeleton sheets

A skeleton sheet is one unit's code template with holes. `DOCS-skeletons.md`
has the rules; the command is:

```bash
python3 -m leetcode_coach.review_cli skeleton-open <slug> <unit>
```

- Open a sheet only when kuhy asks for one, and only after his first code
  attempt. Never offer it. In a `leetcode <url>` session the client has logged
  his first code; in a review his accepted code is the attempt, so the slug
  must still be flagged: open the sheet before `review-finish`.
- Opening a sheet counts above H1: that solve gets no sign-off. The command
  logs a `skeleton` event.
- stdout is the sheet file, byte for byte. Quote it to kuhy exactly as
  printed: add no fence, no header and no note inside it (the stop gate lets
  a sheet through only verbatim). The line `skeleton logged: ...` goes to
  stderr.
- `refused: ...` (exit 1) or `could not check: ...` (exit 2): the sheet stays
  shut and nothing was logged. Say why in one line.
