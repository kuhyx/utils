#!/bin/bash
# Install the evening-gates user unit. Idempotent; never enables or starts it:
# root's shutdown check starts it on demand (see evening_chain.py).
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_DIR
readonly UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
readonly SYSTEM_PYTHON="/usr/bin/python3"

fail() {
    echo "install_evening_gates: $*" >&2
    exit 1
}

main() {
    [[ $EUID -ne 0 ]] || fail "run as kuhy, not root (it is a user unit)"
    "$SYSTEM_PYTHON" -c "import gatelock.evening_chain, earned_time, freedays, sickdays" \
        || fail "the system python cannot import gatelock.evening_chain and its readers"
    mkdir -p "$UNIT_DIR"
    install -m 644 "$REPO_DIR/systemd/evening-gates.service" "$UNIT_DIR/"
    systemctl --user daemon-reload
    systemd-analyze --user verify "$UNIT_DIR/evening-gates.service" \
        || fail "evening-gates.service does not verify"
    echo "installed $UNIT_DIR/evening-gates.service (not enabled, not started)"
}

main "$@"
