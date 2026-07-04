#!/bin/bash
# guardctl file-guard subcommands. Sourced by guardctl, never executed directly.

restore_from_canonical() {
    local name="$1"
    [[ -e "$CANONICAL" ]] || return 1
    # shellcheck disable=SC2153 # BIND_MOUNT set by load_target_conf, not a typo
    [[ "$BIND_MOUNT" == "yes" ]] && collapse_bind_mount "$TARGET"
    unlock_file "$TARGET"
    mkdir -p "$(dirname "$TARGET")"
    cp --preserve=mode,ownership,timestamps "$CANONICAL" "$TARGET"
    log_hook "file-guard $name: restored $TARGET from canonical (drift/missing detected)"
}

snapshot_canonical() {
    local name="$1"
    mkdir -p "$(dirname "$CANONICAL")"
    unlock_file "$CANONICAL"
    cp --preserve=mode,ownership,timestamps "$TARGET" "$CANONICAL"
    lock_file "$CANONICAL"
    log_hook "file-guard $name: snapshotted $TARGET as new canonical"
}

fg_ensure_templates_installed() {
    for unit in guard-file@.path guard-file@.service guard-bind-mount@.service; do
        [[ -f "$GUARD_LIB_SYSTEMD_DIR/$unit" ]] || \
            die "missing $GUARD_LIB_SYSTEMD_DIR/$unit - run guard-lib's install.sh first"
    done
}

fg_install() {
    local name="$1"
    shift
    require_name "$name"
    local target="" canonical="" bind_mount="no" plugin="" also_watch=()
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --target) target="$2"; shift 2 ;;
            --canonical) canonical="$2"; shift 2 ;;
            --bind-mount) bind_mount="yes"; shift ;;
            --plugin) plugin="$2"; shift 2 ;;
            --also-watch) also_watch+=("$2"); shift 2 ;;
            *) die "file-guard install: unknown argument '$1'" ;;
        esac
    done
    [[ -n "$target" ]] || die "file-guard install: --target is required"
    target="$(realpath -m "$target")"
    [[ -n "$plugin" ]] && plugin="$(realpath -m "$plugin")"
    require_root
    fg_ensure_templates_installed

    local conf
    conf="$(target_conf_path "$name")"
    [[ -f "$conf" ]] && die "file-guard instance '$name' already installed (uninstall it first)"
    [[ -n "$canonical" ]] || canonical="$GUARD_LIB_CONF_DIR/canonical/$name"

    mkdir -p "$GUARD_LIB_TARGETS_DIR" "$(dirname "$canonical")"
    cat >"$conf" <<EOF
TARGET="$target"
CANONICAL="$canonical"
BIND_MOUNT="$bind_mount"
PLUGIN="$plugin"
ALSO_WATCH="${also_watch[*]}"
EOF

    TARGET="$target"
    CANONICAL="$canonical"
    if [[ ! -e "$canonical" ]]; then
        [[ -e "$target" ]] || die "file-guard install: target '$target' does not exist and no canonical to seed from"
        snapshot_canonical "$name"
    fi

    mkdir -p "$GUARD_LIB_SYSTEMD_DIR/guard-file@$name.path.d"
    {
        echo "[Path]"
        echo "PathModified=$target"
        for w in "${also_watch[@]}"; do
            echo "PathModified=$w"
        done
    } >"$GUARD_LIB_SYSTEMD_DIR/guard-file@$name.path.d/override.conf"

    systemctl daemon-reload
    systemctl enable --now "guard-file@$name.path"

    if [[ "$bind_mount" == "yes" ]]; then
        systemctl enable --now "guard-bind-mount@$name.service"
    fi

    fg_enforce "$name"
    log_hook "file-guard $name: installed (target=$target bind_mount=$bind_mount)"
    echo "installed file-guard '$name' for $target"
}

fg_enforce() {
    local name="$1"
    load_target_conf "$name"
    # shellcheck disable=SC2153 # PLUGIN is set by load_target_conf, not a typo of local `plugin`
    load_plugin "$PLUGIN"

    plugin_call pre_action

    if [[ ! -e "$TARGET" ]]; then
        restore_from_canonical "$name" || die "cannot restore $TARGET: no canonical copy exists"
    fi

    local validated=1
    if declare -f validate >/dev/null 2>&1; then
        if ! validate "$TARGET"; then
            validated=0
            if [[ -e "$CANONICAL" ]]; then
                restore_from_canonical "$name"
            else
                plugin_call emergency_fix
            fi
            plugin_call post_restore_action
        fi
    fi

    if [[ "$validated" -eq 1 ]]; then
        if [[ -e "$CANONICAL" ]]; then
            if ! cmp -s "$TARGET" "$CANONICAL"; then
                restore_from_canonical "$name"
                plugin_call post_restore_action
            fi
        else
            snapshot_canonical "$name"
        fi
    fi

    # Collapse before the final chattr dance too, not just for restores:
    # if this instance is bind-mounted and already mounted read-only
    # (e.g. every time enforce runs with no drift to restore), chattr
    # itself fails against a read-only mount - silently leaving the
    # target with no immutable flag at all.
    [[ "$BIND_MOUNT" == "yes" ]] && collapse_bind_mount "$TARGET"
    unlock_file "$TARGET"
    lock_file "$TARGET"
    [[ "$BIND_MOUNT" == "yes" ]] && _reapply_bind_mount "$name"
    log_hook "file-guard $name: enforce ok"
}

fg_unlock() {
    local name="$1"
    require_root
    load_target_conf "$name"
    # shellcheck disable=SC2153 # PLUGIN set by load_target_conf, not a typo
    load_plugin "$PLUGIN"
    echo "About to unlock file-guard '$name' ($TARGET) for editing."
    read -rp "Reason for unlocking: " reason
    [[ -n "$reason" ]] || die "a reason is required"
    log_hook "file-guard $name: UNLOCK requested by ${SUDO_USER:-$(whoami)}: $reason"
    echo "Unlocking in 45s (Ctrl-C to abort)..."
    sleep 45
    # Stop the watcher before unlocking: chattr alone (no content write)
    # fires PathModified, and the resulting enforce pass unconditionally
    # re-locks the target even with no drift - which would silently
    # re-lock this file out from under the editor. Confirmed live during
    # the shutdown-schedule migration (see guard-lib project notes).
    systemctl stop "guard-file@${name}.path" 2>/dev/null || true
    # shellcheck disable=SC2153 # BIND_MOUNT set by load_target_conf, not a typo
    [[ "$BIND_MOUNT" == "yes" ]] && collapse_bind_mount "$TARGET"
    unlock_file "$TARGET"
    log_hook "file-guard $name: unlocked for editing"

    local before after
    before="$(sha256sum "$TARGET" 2>/dev/null | awk '{print $1}')"
    # Deliberately unquoted: $EDITOR commonly carries arguments (e.g.
    # "code --wait", "emacsclient -t") that must be word-split.
    ${EDITOR:-vi} "$TARGET"
    after="$(sha256sum "$TARGET" 2>/dev/null | awk '{print $1}')"

    if [[ "$before" != "$after" ]]; then
        if declare -f validate >/dev/null 2>&1 && ! validate "$TARGET"; then
            echo "New content fails this instance's validate() check - reverting your edit; canonical unchanged." >&2
            log_hook "file-guard $name: edit REJECTED (failed validate), reverting to canonical"
            [[ -e "$CANONICAL" ]] && cp --preserve=mode,ownership,timestamps "$CANONICAL" "$TARGET"
        else
            # Update canonical to match: without this, re-locking below
            # fires the watcher, which would see the new content as
            # "drift" against the stale canonical and silently revert
            # this legitimate edit.
            log_hook "file-guard $name: content changed, updating canonical"
            unlock_file "$CANONICAL"
            cp --preserve=mode,ownership,timestamps "$TARGET" "$CANONICAL"
            lock_file "$CANONICAL"
        fi
    else
        log_hook "file-guard $name: no content change"
    fi

    lock_file "$TARGET"
    # shellcheck disable=SC2153 # BIND_MOUNT set by load_target_conf, not a typo
    [[ "$BIND_MOUNT" == "yes" ]] && _reapply_bind_mount "$name"
    systemctl start "guard-file@${name}.path" 2>/dev/null || true
    log_hook "file-guard $name: re-locked after edit"
    echo "Re-locked '$name'."
}

fg_uninstall() {
    local name="$1"
    shift
    local keep_canonical=0
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --keep-canonical) keep_canonical=1; shift ;;
            *) die "file-guard uninstall: unknown argument '$1'" ;;
        esac
    done
    require_root
    load_target_conf "$name"
    systemctl disable --now "guard-file@$name.path" 2>/dev/null || true
    systemctl disable --now "guard-bind-mount@$name.service" 2>/dev/null || true
    rm -rf "${GUARD_LIB_SYSTEMD_DIR:?}/guard-file@$name.path.d"
    systemctl daemon-reload
    # shellcheck disable=SC2153 # BIND_MOUNT set by load_target_conf, not a typo
    [[ "$BIND_MOUNT" == "yes" ]] && collapse_bind_mount "$TARGET"
    unlock_file "$TARGET"
    if [[ "$keep_canonical" -eq 0 ]]; then
        unlock_file "$CANONICAL"
        rm -f "$CANONICAL"
    fi
    rm -f "$(target_conf_path "$name")"
    log_hook "file-guard $name: uninstalled (keep_canonical=$keep_canonical)"
    echo "uninstalled file-guard '$name'"
}

fg_status() {
    local name="$1"
    load_target_conf "$name"
    echo "name: $name"
    echo "target: $TARGET"
    echo "canonical: $CANONICAL"
    # shellcheck disable=SC2153 # BIND_MOUNT/PLUGIN/ALSO_WATCH set by load_target_conf, not typos
    echo "bind_mount: $BIND_MOUNT"
    echo "plugin: ${PLUGIN:-<none>}"
    echo "also_watch: ${ALSO_WATCH:-<none>}"
    if [[ -e "$TARGET" ]]; then
        local attrs
        attrs="$(lsattr "$TARGET" 2>/dev/null | awk '{print $1}')"
        echo "target attrs: ${attrs:-unknown}"
    else
        echo "target: MISSING"
    fi
    local unit_state
    unit_state="$(systemctl is-active "guard-file@$name.path" 2>/dev/null || true)"
    echo "path unit: ${unit_state:-unknown}"
}

fg_canonical_path() {
    # Machine-readable single-value output: the canonical path for an
    # instance, so consumers with bespoke unlock flows (that can't go
    # through `unlock`/`enforce` directly) don't have to hardcode or
    # duplicate guard-lib's canonical-path convention.
    local name="$1"
    load_target_conf "$name"
    echo "$CANONICAL"
}

fg_pacman_unlock() {
    # Quiet, non-interactive unlock used only by the generic pacman
    # PreTransaction hook - no typed reason, no editor. The pacman
    # transaction itself is the sanctioned reason.
    #
    # Stops the path unit, not just chattr -i's the target: chattr alone
    # fires PathModified, and if the watcher's enforce pass wins the race
    # against pacman's own write, it silently re-locks the file before
    # pacman gets to it, breaking the very transaction this hook exists
    # to allow. Matches the pre-existing hosts-guard pacman hooks, which
    # stop hosts-guard.path/nsswitch-guard.path/resolved-guard.path for
    # the same reason.
    local name="$1"
    load_target_conf "$name"
    systemctl stop "guard-file@${name}.path" 2>/dev/null || true
    # shellcheck disable=SC2153 # BIND_MOUNT set by load_target_conf, not a typo
    [[ "$BIND_MOUNT" == "yes" ]] && collapse_bind_mount "$TARGET"
    unlock_file "$TARGET"
    log_hook "file-guard $name: pacman-unlock (pre-transaction)"
}

fg_pacman_relock() {
    # Counterpart to fg_pacman_unlock, used only by the generic pacman
    # PostTransaction hook: re-enforce (drift-restore + chattr +i, and -
    # if this instance is bind-mounted - re-establish the read-only
    # bind mount, since fg_enforce does that itself now) then restart
    # the path unit that pacman-unlock stopped.
    local name="$1"
    fg_enforce "$name"
    systemctl start "guard-file@${name}.path" 2>/dev/null || true
    log_hook "file-guard $name: pacman-relock (post-transaction)"
}

fg_sync_canonical() {
    # Counterpart to fg_pacman_unlock for callers that legitimately EDITED
    # the target (not pacman's own hook flow, which wants drift reverted).
    # Adopts the target's current content as the new canonical, instead of
    # fg_enforce's drift-check-and-revert - which would otherwise silently
    # undo the very edit the caller just made. Assumes the watcher was
    # already stopped by a prior fg_pacman_unlock; does not stop it itself.
    local name="$1"
    load_target_conf "$name"
    snapshot_canonical "$name"
    # shellcheck disable=SC2153 # BIND_MOUNT set by load_target_conf, not a typo
    [[ "$BIND_MOUNT" == "yes" ]] && collapse_bind_mount "$TARGET"
    unlock_file "$TARGET"
    lock_file "$TARGET"
    [[ "$BIND_MOUNT" == "yes" ]] && _reapply_bind_mount "$name"
    systemctl start "guard-file@${name}.path" 2>/dev/null || true
    log_hook "file-guard $name: synced canonical to current content"
}

# Self-bind-mounts TARGET over itself, then remounts that layer
# read-only. This is a mount-level lock independent of chattr: even a
# successful `chattr -i` bypass still can't write through a read-only
# mount. Deliberately does NOT bind CANONICAL over TARGET - that would
# merge them onto the same inode, so chattr/writes to either would hit
# both and "restore from canonical" would become meaningless.
_reapply_bind_mount() {
    local name="$1"
    if mountpoint -q "$TARGET" 2>/dev/null; then
        return 0
    fi
    mount --bind "$TARGET" "$TARGET"
    mount -o remount,ro,bind "$TARGET"
    log_hook "file-guard $name: bind-mounted $TARGET read-only"
}

fg_bind_mount() {
    local name="$1"
    require_root
    load_target_conf "$name"
    _reapply_bind_mount "$name"
}

file_guard_main() {
    local sub="$1"
    shift || true
    case "$sub" in
        install) fg_install "$@" ;;
        enforce) fg_enforce "$@" ;;
        unlock) fg_unlock "$@" ;;
        pacman-unlock) fg_pacman_unlock "$@" ;;
        uninstall) fg_uninstall "$@" ;;
        status) fg_status "$@" ;;
        canonical-path) fg_canonical_path "$@" ;;
        bind-mount) fg_bind_mount "$@" ;;
        pacman-relock) fg_pacman_relock "$@" ;;
        sync) fg_sync_canonical "$@" ;;
        *) die "file-guard: unknown subcommand '$sub' (expected install|enforce|unlock|pacman-unlock|pacman-relock|sync|uninstall|status|canonical-path|bind-mount)" ;;
    esac
}
