# The coach's clients, gates and session log

Moved out of `SKILL.md` (250-line cap); none of it is coaching instruction.

The right client is `leetcode <url>` (this package's `leetcode` launcher,
symlinked from `~/.local/bin`): a print-mode loop on sonnet that also runs
the req-before-code gate and the session log (`leetcode report`). The Stop
hook (`stop_gate.py`) sends back a reply with a pasteable line or an early
toolbox name, but the TUI has already streamed it (2026-09-21: the blocked
`for` loop was visible above the rewrite); print mode waits. TUI: best-effort.

**Offline / out of quota.** `leetcode --local <url>` coaches on
`qwen3:30b-a3b-instruct-2507` via Ollama, and the REPL switches there by
itself, history intact, on "You've hit your ... limit". With no hooks there,
`local_coach.py` runs the same detectors on every draft; three leaky drafts
are withheld. Everything above `## Model and client` is its system prompt,
minus section 1. `python3 -m leetcode_coach.eval_local`: acceptance run.

## The req-before-code gate (TODO-coach.md decisions 4-8)

Both REPL paths run `phase.PhaseGate` on every block kuhy sends:

- `req: ...` is the requirement list. `req_check` judges it on
  `claude -p --model haiku` (no tools, hooks or session file), then on Ollama,
  and fails OPEN (`unverified`) when neither answers. It may only name
  missing properties from the `toolbox.json` vocabulary; anything else it says
  is dropped before kuhy sees it.
- A block that is code (regex first, the model only when the regex cannot
  tell, "not code" when nobody answers) is held back until a list passed, or
  was unverifiable, or came back incomplete three times (then the `code`
  event carries `req_incomplete: true`).
- Until the first `code` event, a reply naming a toolbox entry or alias is
  bounced (`leak.py`: the Stop hook on the Claude path, `local_coach` on the
  local one), except names kuhy already typed (not the statement: its tags
  and hints name the answer).
- Each reply's `<!-- rung:Hn -->` marker is logged and stripped.

Every step lands in `~/.local/share/leetcode-coach/sessions/<date>-<slug>.jsonl`
(`session_log.py`; `leetcode_guard._coach_log` reads the same contract). The
REPL exports the file as `LEETCODE_COACH_LOG`, which is how the Stop hook and
the card builder (`postmortem`) find it. `leetcode report` prints, per file,
req-before-code, highest rung, reveal and every req_check verdict.

Known gap: `~/.claude/hooks/status_tag_stop.py` wants the last line of a TUI
coaching reply to end in `?`; the rung line now comes after it. Print mode
(the REPL) is exempt from that hook.
