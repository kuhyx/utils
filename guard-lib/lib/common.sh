#!/bin/bash
# Shared helpers for guardctl subcommands. Sourced, never executed directly.

GUARD_LIB_CONF_DIR="${GUARD_LIB_CONF_DIR:-/etc/guard-lib}"
GUARD_LIB_TARGETS_DIR="$GUARD_LIB_CONF_DIR/targets"
GUARD_LIB_BLOCKS_DIR="$GUARD_LIB_CONF_DIR/blocks"
GUARD_LIB_LOG="${GUARD_LIB_LOG:-/var/log/guard-lib.log}"
GUARD_LIB_BIN="${GUARD_LIB_BIN:-/usr/local/bin/guardctl}"
GUARD_LIB_SYSTEMD_DIR="${GUARD_LIB_SYSTEMD_DIR:-/etc/systemd/system}"
GUARD_LIB_PACMAN_HOOKS_DIR="${GUARD_LIB_PACMAN_HOOKS_DIR:-/etc/pacman.d/hooks}"

die() {
    echo "guardctl: error: $*" >&2
    exit 1
}

require_root() {
    if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
        die "must be run as root"
    fi
}

log_hook() {
    # Best-effort log write; never fail the caller because logging failed.
    local msg="$1"
    mkdir -p "$(dirname "$GUARD_LIB_LOG")" 2>/dev/null || true
    printf '%s %s\n' "$(date -Is)" "$msg" >>"$GUARD_LIB_LOG" 2>/dev/null || true
}

require_name() {
    local name="$1"
    [[ -n "$name" ]] || die "instance name is required"
    [[ "$name" =~ ^[A-Za-z0-9._-]+$ ]] || die "instance name '$name' has invalid characters"
}

target_conf_path() {
    printf '%s/%s.conf' "$GUARD_LIB_TARGETS_DIR" "$1"
}

block_conf_path() {
    printf '%s/%s.conf' "$GUARD_LIB_BLOCKS_DIR" "$1"
}

# Populates TARGET, CANONICAL, BIND_MOUNT, PLUGIN, ALSO_WATCH from a target
# conf file. Fails loudly if the instance is not registered - callers must
# not silently no-op on a missing config, since that is exactly the
# silent-loss-of-protection failure mode this tool exists to avoid.
# Sets these as global output vars for callers in file_guard.sh - shellcheck
# can't see the cross-file usage, hence the disables below.
# shellcheck disable=SC2034
load_target_conf() {
    local name="$1"
    local conf
    conf="$(target_conf_path "$name")"
    [[ -f "$conf" ]] || die "no such file-guard instance: $name (missing $conf)"
    TARGET=""
    CANONICAL=""
    BIND_MOUNT="no"
    PLUGIN=""
    ALSO_WATCH=""
    # shellcheck source=/dev/null
    source "$conf"
    [[ -n "$TARGET" ]] || die "$conf did not set TARGET"
    [[ -n "$CANONICAL" ]] || CANONICAL="$GUARD_LIB_CONF_DIR/canonical/$name"
}

# Sets global output vars PACKAGE/LOCK_FILE/FILE_GUARD_NAME for callers in
# package_block.sh - same cross-file contract as load_target_conf above.
# shellcheck disable=SC2034
load_block_conf() {
    local name="$1"
    local conf
    conf="$(block_conf_path "$name")"
    [[ -f "$conf" ]] || die "no such package-block instance: $name (missing $conf)"
    PACKAGE=""
    LOCK_FILE=""
    FILE_GUARD_NAME=""
    # shellcheck source=/dev/null
    source "$conf"
    [[ -n "$PACKAGE" ]] || die "$conf did not set PACKAGE"
    [[ -n "$LOCK_FILE" ]] || die "$conf did not set LOCK_FILE"
}

# Runs a plugin function if the plugin script defines it. No-op otherwise.
plugin_call() {
    local fn="$1"
    if declare -f "$fn" >/dev/null 2>&1; then
        "$fn"
    fi
}

load_plugin() {
    local plugin="$1"
    if [[ -n "$plugin" ]]; then
        [[ -f "$plugin" ]] || die "plugin script not found: $plugin"
        # shellcheck source=/dev/null
        source "$plugin"
    fi
}

unlock_file() {
    local path="$1"
    [[ -e "$path" ]] || return 0
    chattr -i -a "$path" 2>/dev/null || true
}

lock_file() {
    local path="$1"
    [[ -e "$path" ]] || return 0
    chattr +i "$path" 2>/dev/null || log_hook "WARNING: chattr +i failed on $path (unsupported filesystem?)"
}

# Tears down a self-bind-mount read-only layer (see fg_bind_mount) so the
# underlying file becomes writable again. A read-only bind mount blocks
# writes and metadata changes (chattr included) at the VFS layer
# regardless of the inode's own permissions/attributes, so this must run
# before any write to a bind-mounted target - chattr alone is not enough.
collapse_bind_mount() {
    local path="$1"
    local i=0
    while mountpoint -q "$path" 2>/dev/null; do
        umount -l "$path" 2>/dev/null || break
        i=$((i + 1))
        ((i > 20)) && break
    done
    # A while loop that exits via its (now-false) condition returns
    # non-zero, which - combined with `set -e` and callers using
    # `[[ COND ]] && collapse_bind_mount ...` - would silently abort the
    # calling function right after a successful collapse. This is
    # best-effort teardown; always report success to the caller.
    return 0
}
