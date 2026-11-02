#!/bin/bash
# Install + enable the focus_project harvester units (systemd --user).
# Run as the desktop user (never sudo). Idempotent. Needs focus_project
# importable by /usr/bin/python3 (see install.sh).
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_DIR
readonly UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
readonly DATA_DIR="${FOCUS_PROJECT_DATA:-$HOME/.local/share/focus_project}"
readonly UNITS=(focus-project-harvest.service focus-project-harvest.path focus-project-harvest.timer)

if [[ "$(id -u)" -eq 0 ]]; then
    echo "run as your own user, not root" >&2
    exit 1
fi
(cd / && /usr/bin/python3 -c 'import focus_project') ||
    {
        echo "focus_project not importable: run $REPO_DIR/install.sh first" >&2
        exit 1
    }

# The .path unit watches files inside this directory.
mkdir -p "$DATA_DIR" "$UNIT_DIR"
for unit in "${UNITS[@]}"; do
    install -m 0644 "$REPO_DIR/systemd/$unit" "$UNIT_DIR/$unit"
done
systemctl --user daemon-reload
systemctl --user enable --now focus-project-harvest.path focus-project-harvest.timer
for unit in "${UNITS[@]}"; do
    diff -q "$REPO_DIR/systemd/$unit" "$UNIT_DIR/$unit"
done
echo "focus-project-harvest units installed and enabled"
