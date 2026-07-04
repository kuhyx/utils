#!/bin/bash
# PostTransaction hook script: re-enforce every registered file-guard
# instance (restores drift if pacman legitimately rewrote the file, then
# re-locks it). Same fail-open discipline as guard-lib-unlock-all.sh - a
# single broken instance logs a warning and the loop continues.
set -uo pipefail

TARGETS_DIR="${GUARD_LIB_TARGETS_DIR:-/etc/guard-lib/targets}"
GUARDCTL="${GUARD_LIB_BIN:-/usr/local/bin/guardctl}"

if [[ -d "$TARGETS_DIR" ]]; then
    for conf in "$TARGETS_DIR"/*.conf; do
        [[ -e "$conf" ]] || continue
        name="$(basename "$conf" .conf)"
        "$GUARDCTL" file-guard pacman-relock "$name" 2>/dev/null || \
            echo "guard-lib: WARNING failed to re-lock '$name' after transaction (continuing)" >&2
    done
fi

exit 0
