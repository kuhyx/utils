#!/bin/bash
# Editable user install so /usr/bin/python3 (the guards' user units) can
# `import holds`. Stdlib only; idempotent. The hold library is read by every gate
# from the system python, so it must import there without a venv.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_DIR
readonly SYSTEM_PYTHON="/usr/bin/python3"

"$SYSTEM_PYTHON" -m pip install --user --no-deps --break-system-packages -e "$REPO_DIR"
cd /
"$SYSTEM_PYTHON" -c 'import holds; print(holds.__file__)'
