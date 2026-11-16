#!/bin/bash

# ============================================================================
# GUT tests of the dev_tools addon against the stub host project in this
# folder, headless and muted, one run under 60 s.
#   godot_dev_tools/test.sh            the whole suite
#   godot_dev_tools/test.sh -gselect=test_annotator    one file
# GUT is fetched at the pinned tag into addons/gut (gitignored): no third-party
# code is committed. user:// and the feedback dir point at a throwaway folder,
# so no test ever writes where a real game saves.
# Fail closed: green only with exit 0, no SCRIPT ERROR, no failing test, at
# least one test and tests == passing + pending. Prints one summary line.
# ============================================================================

set -euo pipefail

readonly GUT_TAG="v9.7.1"
readonly RUN_TIMEOUT=50
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly HERE
TMP=""

cleanup() {
    [[ -z "$TMP" ]] || rm -rf "$TMP"
}

# Fetches GUT at GUT_TAG into addons/gut unless that version is already there.
ensure_gut() {
    local gut_dir="$HERE/addons/gut" tmp
    if [[ -f "$gut_dir/plugin.cfg" ]] && grep -q "\"${GUT_TAG#v}\"" "$gut_dir/plugin.cfg"; then
        return
    fi
    tmp="$(mktemp -d)"
    git -c advice.detachedHead=false clone -q --depth 1 --branch "$GUT_TAG" \
        https://github.com/bitwes/Gut "$tmp/gut"
    rm -rf "$gut_dir"
    mv "$tmp/gut/addons/gut" "$gut_dir"
    rm -rf "$tmp"
}

# Value of a GUT totals row ("Tests 59", "Passing Tests 59"...), 0 when absent.
total_of() {
    local row="$1" out="$2"
    awk -v row="$row" 'index($0, row) == 1 { v = $NF } END { print v + 0 }' <<<"$out"
}

# Runs godot under the resource cap kuhy's machine has, else plainly.
run_capped() {
    local capped="$HOME/.claude/scripts/capped.sh"
    if [[ -x "$capped" ]]; then
        "$capped" "$@"
    else
        "$@"
    fi
}

main() {
    command -v godot >/dev/null || {
        echo "Error: godot 4.7.2 not on PATH" >&2
        exit 1
    }
    ensure_gut
    TMP="$(mktemp -d)"
    trap cleanup EXIT
    export XDG_DATA_HOME="$TMP/xdg"
    export DEV_FEEDBACK_DIR="$TMP/feedback"
    mkdir -p "$XDG_DATA_HOME" "$DEV_FEEDBACK_DIR"
    # GUT's own class_names need a class cache before a script run.
    run_capped timeout 40 godot --headless --path "$HERE" --import >/dev/null 2>&1 || true
    local out code=0 start="$SECONDS"
    out="$(run_capped timeout -k 3 "$RUN_TIMEOUT" godot --headless --audio-driver Dummy \
        --path "$HERE" -s addons/gut/gut_cmdln.gd -gexit "$@" 2>&1)" || code=$?
    local tests passing failing pending why=""
    tests="$(total_of Tests "$out")"
    passing="$(total_of "Passing Tests" "$out")"
    failing="$(total_of "Failing Tests" "$out")"
    pending="$(total_of "Risky/Pending" "$out")"
    if [[ "$code" -eq 124 || "$code" -eq 137 || "$code" -eq 143 ]]; then
        why="timed out or killed after ${RUN_TIMEOUT}s (exit $code)"
    elif grep -qE 'SCRIPT ERROR|Failing Tests' <<<"$out" || ((failing > 0)); then
        why="failing tests or a script error"
    elif ((code != 0)); then
        why="exit code $code"
    elif ((tests == 0)); then
        why="no tests ran"
    elif ((tests != passing + pending)); then
        why="tests $tests != passing $passing + pending $pending"
    fi
    local line="$tests tests, $passing pass, $failing fail, $pending pending, $((SECONDS - start))s"
    if [[ -n "$why" ]]; then
        echo "$out" | tail -60 >&2
        echo "godot_dev_tools: FAILED ($why; $line)" >&2
        exit 1
    fi
    echo "godot_dev_tools: green ($line)"
}

main "$@"
