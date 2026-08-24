"""Classify each legacy markdown file as a task (TODO) or a record (DOCS).

Filename alone is not a reliable signal and neither is directory: this corpus
contains `docs/todo/workstream-d-scoping-findings.md`, which lives under
`docs/todo/` and is explicitly a findings record ("No code was written or
modified in any repo for this pass"), and `INSTALLER_FIX_TASK.md`, which reads
as pending but shipped in commit 4c426eae.

So the audited files carry an explicit verdict here, sourced from three
Explore audits cross-checked against exit codes where one exists. Anything not
listed falls back to a conservative heuristic and is reported for review rather
than renamed silently.
"""

from __future__ import annotations

#: Files the audits proved are still outstanding work -> TODO*, marker added.
TASKS: dict[str, str] = {
    # 250-line cap refactors. Verified by running the shared gate per repo:
    # every one of these exits 1 with violations still present.
    "atomichabits/refactor_claude_todo.md": "TODO-file-length-250.md",
    "CV/refactor_claude_todo.md": "TODO-file-length-250.md",
    "dufs-cloud/refactor_claude_todo.md": "TODO-file-length-250.md",
    "epopeja_karta/refactor_claude_todo.md": "TODO-file-length-250.md",
    "europe-county-map/refactor_claude_todo.md": "TODO-file-length-250.md",
    "habit_stack/refactor_claude_todo.md": "TODO-file-length-250.md",
    "home_inventory/refactor_claude_todo.md": "TODO-file-length-250.md",
    "i3wm-mcp/refactor_claude_todo.md": "TODO-file-length-250.md",
    "konbini-67/refactor_claude_todo.md": "TODO-file-length-250.md",
    "kuhytrack/refactor_claude_todo.md": "TODO-file-length-250.md",
    "leetcode-guard/refactor_claude_todo.md": "TODO-file-length-250.md",
    "macro-cam/refactor_claude_todo.md": "TODO-file-length-250.md",
    "mcp-servers/refactor_claude_todo.md": "TODO-file-length-250.md",
    "opengameart-mcp/refactor_claude_todo.md": "TODO-file-length-250.md",
    "screen-locker/refactor_claude_todo.md": "TODO-file-length-250.md",
    "steam-backlog-enforcer/refactor_claude_todo.md": "TODO-file-length-250.md",
    "steam-game-installer/refactor_claude_todo.md": "TODO-file-length-250.md",
    "wake-alarm/refactor_claude_todo.md": "TODO-file-length-250.md",
    "wiki-kb/refactor_claude_todo.md": "TODO-file-length-250.md",
    "yay-mcp/refactor_claude_todo.md": "TODO-file-length-250.md",
    # Design audits with violations the audit re-confirmed still present.
    "habit_stack/DESIGN_AUDIT_TODO.md": "TODO-design-audit.md",
    "todo/DESIGN_AUDIT_TODO.md": "TODO-design-audit.md",
    "testsAndMisc/DESIGN_AUDIT_TODO.md": "TODO-design-audit.md",
    # dopamine-ux programme: 00-INDEX records 8 of 9 "not started".
    "diet-guard/prompts/dopamine-ux-diet-guard.md": "TODO-dopamine-ux-diet-guard.md",
    "dufs-cloud/prompts/dopamine-ux-07-theme.md": "TODO-dopamine-ux-07-theme.md",
    "dufs-cloud/prompts/dopamine-ux-08-motion.md": "TODO-dopamine-ux-08-motion.md",
    "screen-locker/prompts/dopamine-ux-04-screen-locker.md": "TODO-dopamine-ux-04-screen-locker.md",
    "screen-locker/prompts/dopamine-ux-05-workout-app.md": "TODO-dopamine-ux-05-workout-app.md",
    "todo/prompts/dopamine-ux-todo.md": "TODO-dopamine-ux-todo.md",
    "wake-alarm/prompts/dopamine-ux-wake-alarm.md": "TODO-dopamine-ux-wake-alarm.md",
    "utils/prompts/dopamine-ux-02-structural-check.md": "TODO-dopamine-ux-02-structural-check.md",
    # pylint-to-ten: measured 8.53 and 8.77 against a target of 10.00.
    "leetcode-guard/prompts/pylint-to-ten.md": "TODO-pylint-to-ten.md",
    "steam-backlog-enforcer/prompts/pylint-to-ten.md": "TODO-pylint-to-ten.md",
    "utils/gatelock/prompts/pylint-to-ten.md": "TODO-pylint-to-ten.md",
    "steam-backlog-enforcer/prompts/refactor-250-continue.md": "TODO-refactor-250-continue.md",
    "screen-locker/todo_fix_pylint_10_prompt.md": "TODO-pylint-to-ten.md",
    "screen-locker/todo_finish_dart_250_prompt.md": "TODO-finish-dart-250.md",
    # Other confirmed-outstanding work.
    "europe-county-map/docs/toDo.md": "TODO-deferred-mechanics.md",
    "lyricanki/NEXT_SESSION.md": "TODO-second-song-and-language.md",
    "osu-automapper/NEXT_SESSION.md": "TODO-sweep-writeup.md",
    "screen-locker/docs/android-ui-automation-task.md": "TODO-android-ui-mcp-wrapper.md",
    "utils/vmbox/DISCOVERY_TEST.md": "TODO-discovery-test.md",
    "roadside-assistance/TODO.md": "TODO.md",
}

#: Files the audits found are records, findings or settled decisions.
#: Permanent, no marker. Includes the three that read as pending but are not.
RECORDS: dict[str, str] = {
    "macro-cam/STAGE0_FINDINGS.md": "DOCS-stage0-findings.md",
    "macro-cam/PIXEL_BUDGET.md": "DOCS-pixel-budget.md",
    "testsAndMisc/RESTRUCTURE_HANDOFF.md": "DOCS-restructure-handoff.md",
    "testsAndMisc/INSTALLER_FIX_TASK.md": "DOCS-installer-fix.md",
    "testsAndMisc/docs/restructure-live-state.md": "DOCS-restructure-live-state.md",
    "testsAndMisc/docs/dns-filtering-parked.md": "DOCS-dns-filtering-parked.md",
    "screen-locker/docs/todo/workstream-d-scoping-findings.md": "DOCS-workstream-d-scoping-findings.md",
    "screen-locker/docs/todo/workstream-c-github-sync-workout-data.md": "DOCS-workstream-c-github-sync.md",
    "screen-locker/docs/todo/workstream-d-shared-crdt-transport.md": "DOCS-workstream-d-shared-crdt-transport.md",
    "utils/vmbox/SESSION_RESULTS.md": "DOCS-session-results.md",
    "utils/vmbox/NEXT_SESSION_PROMPT.md": "DOCS-vmbox-session-jobs.md",
    "dufs-cloud/SUBTITLE_INVESTIGATION.md": "DOCS-subtitle-investigation.md",
    "leetcode-guard/INCIDENT-2026-08-05-no-way-to-solve.md": "DOCS-incident-2026-08-05.md",
    "yay-mcp/docs/register.md": "DOCS-register.md",
    "europe-county-map/RESEARCH.md": "DOCS-research.md",
    "roadside-assistance/PLAN.md": "DOCS-plan.md",
    "diet-guard/prompts/crdt-sync-session-reuse.md": "DOCS-crdt-sync-session-reuse.md",
}

#: Audited as DONE. Deleted only where an exit code proves it; the rest are
#: reported for the user to confirm, never removed on a model's say-so.
PROVEN_DONE = (
    "todo/refactor_claude_todo.md",
    "utils/refactor_claude_todo.md",
    "testsAndMisc/refactor_claude_todo.md",
    "testsAndMisc/refactor_claude_todo_resume.md",
)

#: Claimed DONE by audit but with no exit code to prove it. Needs confirmation.
CLAIMED_DONE = (
    "dufs-cloud/DESIGN_AUDIT_TODO.md",
    "personal-website/DESIGN_AUDIT_TODO.md",
    "steam-backlog-enforcer/DESIGN_AUDIT_TODO.md",
    "wake-alarm/DESIGN_AUDIT_TODO.md",
    "diet-guard/DESIGN_AUDIT_TODO.md",
    "screen-locker/DESIGN_AUDIT_TODO.md",
    "screen-locker/HANDOFF_2026-08-24.md",
    "screen-locker/NEXT_SESSION_PROMPT.md",
    "todo/MIGRATION.md",
    "wake-alarm/MIGRATION.md",
)
