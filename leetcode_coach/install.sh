#!/bin/bash
# Editable user install so /usr/bin/python3 (the tutor server, the CLI, the
# Stop hook) can `import leetcode_coach` straight from this checkout.
# leetcode-guard installs the TAGGED copy instead (its pyproject pin); run
# this only to develop the coach against live callers. Idempotent.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_DIR
readonly SYSTEM_PYTHON="/usr/bin/python3"

"$SYSTEM_PYTHON" -m pip install --user --no-deps --break-system-packages -e "$REPO_DIR"
cd /
"$SYSTEM_PYTHON" -P -c 'import leetcode_coach; print(leetcode_coach.__file__)'
