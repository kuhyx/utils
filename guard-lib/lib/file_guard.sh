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
