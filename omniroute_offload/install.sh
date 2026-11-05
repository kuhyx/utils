#!/bin/bash
# Install free-llm (stdlib-only, system python, editable) and link claude-free into ~/.local/bin.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_DIR
readonly SYSTEM_PYTHON="/usr/bin/python3"
readonly BIN_DIR="${HOME}/.local/bin"

"${SYSTEM_PYTHON}" -m pip install --user --no-deps --break-system-packages -q -e "${REPO_DIR}"
mkdir -p "${BIN_DIR}"
ln -sf "${REPO_DIR}/bin/claude-free" "${BIN_DIR}/claude-free"
command -v free-llm free-llm-read-hook free-llm-check-dir claude-free
