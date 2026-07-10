#!/bin/bash
# PreTransaction hook script: quiet-unlock every registered file-guard
# instance so pacman can write through to files it legitimately manages
# (e.g. nsswitch.conf on a glibc upgrade, resolved.conf on a systemd
# upgrade). Deliberately never aborts: one broken instance config must not
# block every pacman transaction on the system, which is a much worse
# outcome than a guarded file briefly going unprotected mid-transaction
# (relock-all in PostTransaction restores it).
set -uo pipefail

TARGETS_DIR="${GUARD_LIB_TARGETS_DIR:-/etc/guard-lib/targets}"
GUARDCTL="${GUARD_LIB_BIN:-/usr/local/bin/guardctl}"

if [[ -d "$TARGETS_DIR" ]]; then
    for conf in "$TARGETS_DIR"/*.conf; do
        [[ -e "$conf" ]] || continue
        name="$(basename "$conf" .conf)"
        "$GUARDCTL" file-guard pacman-unlock "$name" 2>/dev/null || \
            echo "guard-lib: WARNING failed to unlock '$name' before transaction (continuing)" >&2
    done
fi

exit 0
