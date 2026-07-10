#!/bin/bash
# guardctl package-block subcommands. Sourced by guardctl, never executed directly.

pb_hook_path() {
    printf '%s/guard-lib-block-%s.hook' "$GUARD_LIB_PACMAN_HOOKS_DIR" "$1"
}

pb_start() {
    local name="$1"
    shift
    require_name "$name"
    local package="" lock_file="" days="" bind_mount_args=()
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --package) package="$2"; shift 2 ;;
            --lock-file) lock_file="$2"; shift 2 ;;
            --days) days="$2"; shift 2 ;;
            --bind-mount) bind_mount_args=(--bind-mount); shift ;;
            *) die "package-block start: unknown argument '$1'" ;;
        esac
    done
    [[ -n "$package" ]] || die "package-block start: --package is required"
    [[ -n "$lock_file" ]] || die "package-block start: --lock-file is required"
    [[ "$days" =~ ^[0-9]+$ ]] || die "package-block start: --days must be a positive integer"
    require_root

    local conf
    conf="$(block_conf_path "$name")"
    [[ -f "$conf" ]] && die "package-block instance '$name' already active (end it first)"

    lock_file="$(realpath -m "$lock_file")"
    local started_at until
    started_at="$(date +%s)"
    until=$((started_at + days * 86400))

    mkdir -p "$(dirname "$lock_file")"
    jq -n --argjson started_at "$started_at" --argjson until "$until" --argjson days "$days" \
        '{started_at: $started_at, until: $until, days: $days}' >"$lock_file"

    local fg_name="${name}-lock"
    fg_install "$fg_name" --target "$lock_file" "${bind_mount_args[@]}"

    mkdir -p "$GUARD_LIB_BLOCKS_DIR"
    cat >"$conf" <<EOF
PACKAGE="$package"
LOCK_FILE="$lock_file"
FILE_GUARD_NAME="$fg_name"
EOF

    mkdir -p "$GUARD_LIB_PACMAN_HOOKS_DIR"
    cat >"$(pb_hook_path "$name")" <<EOF
[Trigger]
Operation = Install
Operation = Upgrade
Type = Package
Target = $package

[Action]
Description = guard-lib: package-block '$name' guarding $package
When = PreTransaction
Exec = $GUARD_LIB_BIN package-block check $name
AbortOnFail
EOF

    log_hook "package-block $name: started, blocking '$package' until $(date -d "@$until" -Is)"
    echo "package-block '$name' active: '$package' blocked until $(date -d "@$until")"
}

pb_check() {
    local name="$1"
    local conf
    conf="$(block_conf_path "$name")"
    if [[ ! -f "$conf" ]]; then
        log_hook "package-block $name: WARNING check ran with no registered instance, allowing (fail-open)"
        return 0
    fi
    load_block_conf "$name"
    # shellcheck disable=SC2153 # LOCK_FILE/PACKAGE set by load_block_conf, not typos
    if [[ ! -f "$LOCK_FILE" ]]; then
        log_hook "package-block $name: WARNING lock file missing, allowing (fail-open)"
        return 0
    fi
    local until
    until="$(jq -r '.until // empty' "$LOCK_FILE" 2>/dev/null)"
    if [[ ! "$until" =~ ^[0-9]+$ ]]; then
        log_hook "package-block $name: WARNING lock file malformed, allowing (fail-open)"
        return 0
    fi
    local now
    now="$(date +%s)"
    if [[ "$now" -lt "$until" ]]; then
        # shellcheck disable=SC2153 # PACKAGE set by load_block_conf, not a typo
        echo "guard-lib: '$PACKAGE' is blocked by package-block '$name' until $(date -d "@$until")." >&2
        echo "guard-lib: this is intentional and cannot be lifted by a pacman transaction." >&2
        log_hook "package-block $name: BLOCKED transaction against $PACKAGE (until $until)"
        return 1
    fi
    log_hook "package-block $name: lock expired ($until <= $now), allowing"
    return 0
}

pb_status() {
    local name="$1"
    load_block_conf "$name"
    echo "name: $name"
    echo "package: $PACKAGE"
    echo "lock file: $LOCK_FILE"
    if [[ -f "$LOCK_FILE" ]]; then
        local until now
        until="$(jq -r '.until // empty' "$LOCK_FILE" 2>/dev/null)"
        now="$(date +%s)"
        if [[ "$until" =~ ^[0-9]+$ ]]; then
            if [[ "$now" -lt "$until" ]]; then
                echo "status: active, blocked until $(date -d "@$until")"
            else
                echo "status: expired at $(date -d "@$until") (run 'package-block end $name' to clean up)"
            fi
        else
            echo "status: lock file malformed"
        fi
    else
        echo "status: lock file missing"
    fi
}

pb_end() {
    local name="$1"
    require_root
    load_block_conf "$name"
    rm -f "$(pb_hook_path "$name")"
    fg_uninstall "$FILE_GUARD_NAME"
    rm -f "$LOCK_FILE"
    rm -f "$(block_conf_path "$name")"
    log_hook "package-block $name: ended (package=$PACKAGE)"
    echo "package-block '$name' ended; '$PACKAGE' is no longer blocked by guard-lib"
}

package_block_main() {
    local sub="$1"
    shift || true
    case "$sub" in
        start) pb_start "$@" ;;
        check) pb_check "$@" ;;
        status) pb_status "$@" ;;
        end) pb_end "$@" ;;
        *) die "package-block: unknown subcommand '$sub' (expected start|check|status|end)" ;;
    esac
}
