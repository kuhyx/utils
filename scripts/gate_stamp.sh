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
#                      on --all-files, then write; the on-demand heavy gate
#
# The heavy suites still run in CI on every push; this only decides whether a
# tree may leave the machine, not whether it is fully green.
# ============================================================================

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
readonly SCRIPT_NAME

usage() {
    echo "Usage: $SCRIPT_NAME check | write [--dirty-ok] | full"
    exit 2
}

stamp_path() {
    printf '%s/gate-stamp\n' "$(git rev-parse --git-dir)"
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
        echo "  or:     scripts/check_gate_stamp.sh full    (old pre-push suites, then push again)"
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

cmd_full() {
    echo "gate-stamp: running the manual-stage hooks on all files (the old pre-push set)"
    pre-commit run --hook-stage manual --all-files
    cmd_write
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
        *) usage ;;
    esac
}

main "$@"
