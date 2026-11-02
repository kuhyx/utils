#!/bin/bash
# Editable user install so /usr/bin/python3 (the tutor server, the CLI) can
# `import sql_drills`. Stdlib only; idempotent.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_DIR
readonly SYSTEM_PYTHON="/usr/bin/python3"

"$SYSTEM_PYTHON" -m pip install --user --no-deps --break-system-packages -e "$REPO_DIR"
cd /
"$SYSTEM_PYTHON" -c 'import sql_drills; print(sql_drills.__file__)'
