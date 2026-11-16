#!/bin/bash

# ============================================================================
# Lint of the dev_tools addon and its tests: gdlint (.gdlintrc, every check on)
# and gdformat --check. gdtoolkit is pinned in requirements-dev.txt
# (pip install -r godot_dev_tools/requirements-dev.txt, or uv tool install).
# ============================================================================

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly HERE

main() {
    local tool files=()
    for tool in gdlint gdformat; do
        command -v "$tool" >/dev/null || {
            echo "Error: $tool not found (pip install -r $HERE/requirements-dev.txt)" >&2
            exit 1
        }
    done
    mapfile -t files < <(find "$HERE/addons/dev_tools" "$HERE/tests" -name '*.gd' -type f | sort)
    # One process per tool, not xargs -P: parallel gdtoolkit processes race to
    # create their grammar cache dir (os.makedirs EEXIST) on a cold cache and
    # report a file as unopenable.
    (cd "$HERE" && gdlint "${files[@]}" >/dev/null)
    gdformat --check "${files[@]}" >/dev/null 2>&1 || {
        gdformat --check "${files[@]}" 2>&1 | grep -v 'left unchanged' >&2 || true
        exit 1
    }
    echo "godot_dev_tools lint: ${#files[@]} files ok"
}

main "$@"
