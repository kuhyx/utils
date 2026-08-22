#!/bin/bash
# ============================================================================
# vmbox: get a host repo into a sandbox.
#
# Two modes, because they answer different questions:
#   clone (default) -- reproducible: tests exactly what is committed at HEAD
#   worktree        -- tests what is on disk right now, uncommitted edits and
#                      all, which is usually what "does this script work?" means
#
# The host side is always mounted READ-ONLY, so nothing the guest does can
# reach the real repo.
# ============================================================================

# shellcheck source=common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
source "$(dirname "${BASH_SOURCE[0]}")/ssh.sh"

readonly GUEST_MOUNT="/mnt/hostrepo"

# $1 vm name, $2 host repo path, $3 mode (clone|worktree)
repo_sync() {
    local name="$1" src="$2" mode="${3:-clone}" repo_name
    require_vm "$name"
    [[ -d "$src" ]] || die "no such directory: $src"
    repo_name="$(basename "$src")"

    vm_is_running "$name" || die "sandbox '$name' is not running"

    # Warn about a dirty tree: another session's uncommitted work is a real
    # hazard, and it silently changes what a `clone` actually tests.
    if [[ -d "$src/.git" ]] && ! git -C "$src" diff --quiet 2>/dev/null; then
        warn "host repo has uncommitted changes"
        [[ "$mode" == clone ]] &&
            warn "  mode=clone tests HEAD, NOT those edits (use --worktree for them)"
    fi

    case "$mode" in
        clone)    _repo_clone "$name" "$src" "$repo_name" ;;
        worktree) _repo_rsync "$name" "$src" "$repo_name" ;;
        *) die "unknown repo mode '$mode' (use: clone | worktree)" ;;
    esac
}

_repo_clone() {
    local name="$1" src="$2" repo_name="$3"
    [[ -d "$src/.git" ]] || die "$src is not a git repo (use --worktree instead)"
    log "Cloning $repo_name into '$name' (HEAD, reproducible)"
    # --no-hardlinks: never link into the read-only host mount.
    vm_ssh_exec "$name" \
        "rm -rf ~/$repo_name && git clone --no-hardlinks -q $GUEST_MOUNT/$repo_name ~/$repo_name" ||
        die "clone failed"
    local head
    head="$(vm_ssh_exec "$name" "git -C ~/$repo_name rev-parse --short HEAD" 2>/dev/null)"
    ok "$repo_name cloned at $head (committed state)"
}

_repo_rsync() {
    local name="$1" src="$2" repo_name="$3"
    log "Copying $repo_name into '$name' (working tree, including uncommitted edits)"
    vm_ssh_exec "$name" \
        "rsync -a --exclude .git $GUEST_MOUNT/$repo_name/ ~/$repo_name/" ||
        die "rsync failed"
    ok "$repo_name copied (working-tree state)"
}
