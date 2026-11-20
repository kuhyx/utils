#!/bin/bash

# ============================================================================
# Lint of the kuhy_credit addon, demo and tests: gdlint (.gdlintrc, every check on)
# and gdformat --check. gdtoolkit is pinned in godot_dev_tools/requirements-dev.txt.
# ============================================================================

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly HERE

main() {
    local tool files=()
    for tool in gdlint gdformat; do
        command -v "$tool" >/dev/null || {
            echo "Error: $tool not found (pip install -r godot_dev_tools/requirements-dev.txt)" >&2
            exit 1
        }
    done
    mapfile -t files < <(find "$HERE/addons/kuhy_credit" "$HERE/demo" "$HERE/tests" -name '*.gd' -type f | sort)
    # One process per tool, not xargs -P: parallel gdtoolkit processes race to
    # create their grammar cache dir (os.makedirs EEXIST) on a cold cache and
    # report a file as unopenable.
    (cd "$HERE" && gdlint "${files[@]}" >/dev/null)
    gdformat --check "${files[@]}" >/dev/null 2>&1 || {
        gdformat --check "${files[@]}" 2>&1 | grep -v 'left unchanged' >&2 || true
        exit 1
    }
    echo "kuhy_credit godot lint: ${#files[@]} files ok"
}

main "$@"
