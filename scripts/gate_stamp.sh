#!/bin/bash

# ============================================================================
# gate_stamp.sh — prove the tree being pushed passed the local gate, in ~1 s.
#
# The pre-push stage used to re-run every suite (clean-venv pytest, pre-commit
# --all-files, flutter/vitest coverage) on every push: 10+ minutes under the
# resource cap, and OOM-killed twice on 2026-09-20. All of that had already run
# minutes earlier in finish_auto.sh's gate. So the gate now leaves a receipt:
# the tree hash it passed on, in $GIT_DIR/gate-stamp. pre-push only compares
# the pushed commit's tree against that receipt and never runs anything heavy.
#
#   check              pre-push hook: exit 0 iff the pushed tree is stamped
#   write [--dirty-ok] record HEAD^{tree} — for finish_auto.sh, right after its
#                      gate + commit; refuses a dirty tree unless told the gate
#                      saw the working copy (narrow staging leaves other files)
#   full               run the repo's manual-stage hooks (the old pre-push set)
#                      on --all-files in ONE call, then write; >60 s in the
#                      bigger repos, so prefer the split form below
#   full --list        print the manual-stage hook ids, one per line
#   step <hook-id>     run one manual-stage hook on --all-files and record
#                      "<HEAD^{tree}> <id>" in $GIT_DIR/gate-steps; once every
#                      id from `full --list` is recorded for the current tree,
#                      write the stamp exactly as `write` does. Each call stays
#                      under the 60 s per-command cap:
#                        for id in $(gate_stamp.sh full --list); do
#                            gate_stamp.sh step "$id"; done   # one per call
#
# Manual-stage ids come from scripts/gate_stamp_hooks.py (PyYAML under
# /usr/bin/python3), which parses .pre-commit-config.yaml.
#
# The heavy suites still run in CI on every push; this only decides whether a
# tree may leave the machine, not whether it is fully green.
# ============================================================================

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
readonly SCRIPT_NAME
# Resolved before main() cd's to the toplevel, so a relative $0 still works.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
readonly HOOKS_HELPER="$SCRIPT_DIR/gate_stamp_hooks.py"

usage() {
    echo "Usage: $SCRIPT_NAME check | write [--dirty-ok] | full [--list] | step <hook-id>"
    exit 2
}

stamp_path() {
    printf '%s/gate-stamp\n' "$(git rev-parse --git-dir)"
}

steps_path() {
    printf '%s/gate-steps\n' "$(git rev-parse --git-dir)"
}

tree_of() {
    git rev-parse --verify --quiet "$1^{tree}"
}

# First field of the stamp is the tree hash; the rest is for humans.
stamped_tree() {
    local path
    path="$(stamp_path)"
    [[ -f "$path" ]] || return 0
    read -r tree _ < "$path"
    printf '%s\n' "$tree"
}

cmd_check() {
    # pre-commit consumes the hook's stdin and exports the ref being pushed;
    # a manual run has neither, so fall back to HEAD.
    local ref="${PRE_COMMIT_TO_REF:-HEAD}"
    local tree stamped
    tree="$(tree_of "$ref")" || {
        echo "$SCRIPT_NAME: cannot resolve $ref^{tree}" >&2
        exit 1
    }
    stamped="$(stamped_tree)"
    if [[ "$tree" == "$stamped" ]]; then
        echo "gate-stamp: tree ${tree:0:12} passed the local gate"
        return 0
    fi
    {
        echo "gate-stamp: tree ${tree:0:12} of $ref has NOT passed the local gate"
        if [[ -n "$stamped" ]]; then
            echo "  stamped tree is ${stamped:0:12} — something was committed after the gate"
        else
            echo "  no stamp in $(stamp_path)"
        fi
        echo "  Either: ~/.claude/scripts/finish_auto.sh   (gate + commit + push)"
        echo "  or:     scripts/check_gate_stamp.sh full --list   (manual-stage hook ids), then"
        echo "          scripts/check_gate_stamp.sh step <id>     once per id, one call each;"
        echo "          the last passing step stamps the tree, then push again"
    } >&2
    exit 1
}

cmd_write() {
    local dirty_ok=0
    [[ "${1:-}" == "--dirty-ok" ]] && dirty_ok=1
    local dirty
    dirty="$(git status --porcelain --untracked-files=no)"
    if [[ -n "$dirty" && $dirty_ok -eq 0 ]]; then
        echo "$SCRIPT_NAME: working tree differs from HEAD — the gate ran on" >&2
        echo "  content that is not what HEAD holds. Commit first, then stamp." >&2
        exit 1
    fi
    local tree
    tree="$(tree_of HEAD)"
    printf '%s %s %s\n' "$tree" "$(date -Is)" "$SCRIPT_NAME" > "$(stamp_path)"
    echo "gate-stamp: recorded tree ${tree:0:12} for $(git rev-parse --short HEAD)"
    if [[ -n "$dirty" ]]; then
        echo "  (worktree also holds $(wc -l <<<"$dirty") uncommitted tracked change(s) the gate saw)"
    fi
}

manual_ids() {
    /usr/bin/python3 "$HOOKS_HELPER" .pre-commit-config.yaml
}

cmd_full() {
    if [[ "${1:-}" == "--list" ]]; then
        manual_ids
        return 0
    fi
    [[ $# -eq 0 ]] || usage
    echo "gate-stamp: hint: split this into <60 s calls with 'full --list' + 'step <hook-id>'"
    echo "gate-stamp: running the manual-stage hooks on all files (the old pre-push set)"
    pre-commit run --hook-stage manual --all-files
    cmd_write
}

# Refusals exit 2 (usage-class), unlike write's exit 1: nothing was run.
step_refuse() {
    echo "$SCRIPT_NAME step: $*" >&2
    exit 2
}

cmd_step() {
    [[ $# -eq 1 && -n "$1" ]] || usage
    local hook="$1" ids
    ids="$(manual_ids)"
    grep -Fxq -- "$hook" <<<"$ids" \
        || step_refuse "'$hook' is not a manual-stage hook (see: $SCRIPT_NAME full --list)"
    [[ -z "$(git status --porcelain --untracked-files=no)" ]] \
        || step_refuse "working tree differs from HEAD — commit first, then run steps."
    local tree
    tree="$(tree_of HEAD)"
    pre-commit run --hook-stage manual "$hook" --all-files
    [[ -z "$(git status --porcelain --untracked-files=no)" && "$(tree_of HEAD)" == "$tree" ]] \
        || step_refuse "'$hook' passed but the tree changed while it ran; not recorded."
    record_step "$tree" "$hook"
    local missing id
    missing="$(missing_steps "$tree" "$ids")"
    if [[ -z "$missing" ]]; then
        echo "gate-stamp: every manual-stage hook passed on tree ${tree:0:12}; stamping"
        cmd_write
    else
        echo "gate-stamp: '$hook' recorded for tree ${tree:0:12}; still missing:"
        while IFS= read -r id; do echo "  $id"; done <<<"$missing"
    fi
}

# Keep only the current tree's records: older trees can never be stamped
# again from here, and this bounds the file to one line per manual hook.
record_step() {
    local tree="$1" hook="$2" path kept
    path="$(steps_path)"
    kept="$(grep -s -- "^$tree " "$path" || true)"
    {
        [[ -n "$kept" ]] && printf '%s\n' "$kept"
        grep -Fxq -- "$tree $hook" <<<"$kept" || printf '%s %s\n' "$tree" "$hook"
    } > "$path.tmp"
    mv -f "$path.tmp" "$path"
}

missing_steps() {
    local tree="$1" ids="$2" path id
    path="$(steps_path)"
    while IFS= read -r id; do
        [[ -n "$id" ]] || continue
        grep -Fxqs -- "$tree $id" "$path" || printf '%s\n' "$id"
    done <<<"$ids"
}

main() {
    local cmd="${1:-}"
    [[ -n "$cmd" ]] || usage
    shift
    cd "$(git rev-parse --show-toplevel)"
    case "$cmd" in
        check) cmd_check "$@" ;;
        write) cmd_write "$@" ;;
        full)  cmd_full "$@" ;;
        step)  cmd_step "$@" ;;
        *) usage ;;
    esac
}

main "$@"
