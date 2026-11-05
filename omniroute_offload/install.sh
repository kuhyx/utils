#!/bin/bash
# Install free-llm + omniroute-gateway (system python, editable), claude-free, and the gateway timers.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_DIR
readonly SYSTEM_PYTHON="/usr/bin/python3"
readonly BIN_DIR="${HOME}/.local/bin"
readonly UNIT_DIR="${HOME}/.config/systemd/user"

"${SYSTEM_PYTHON}" -m pip install --user --no-deps --break-system-packages -q -e "${REPO_DIR}"
mkdir -p "${BIN_DIR}" "${UNIT_DIR}"
ln -sf "${REPO_DIR}/bin/claude-free" "${BIN_DIR}/claude-free"
command -v free-llm free-llm-read-hook free-llm-check-dir claude-free omniroute-gateway

install -m644 "${REPO_DIR}"/systemd/omniroute-* "${UNIT_DIR}/"
systemctl --user daemon-reload
systemctl --user enable --now omniroute-health.timer omniroute-update.timer
systemctl --user list-timers 'omniroute-*' --no-pager
