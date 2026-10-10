#!/usr/bin/env bats
# ============================================================================
# vmbox: host-side unit tests for guest/shim.sh, the fake hardware tools.
#
# The shim runs on the host against a temp PATH under the per-test VMBOX_HOME
# from test_helper.bash; nothing is installed system-wide.
# ============================================================================

load test_helper

_shim() {
    VMBOX_SHIM_DIR="$VMBOX_TEST_HOME/sbin" VMBOX_SHIM_LOG_DIR="$VMBOX_TEST_HOME/shimlog" \
        bash "$REPO_ROOT/guest/shim.sh" "$@"
}

@test "shim: exit mode returns 0 and logs the argv with an epoch" {
    run _shim openrgb exit
    [ "$status" -eq 0 ]
    run "$VMBOX_TEST_HOME/sbin/openrgb" --mode static --color 000000
    [ "$status" -eq 0 ]
    run cat "$VMBOX_TEST_HOME/shimlog/openrgb.log"
    [[ "$output" =~ ^[0-9]{9,}\ --mode\ static\ --color\ 000000$ ]]
}

@test "shim: exit:N returns N" {
    _shim nvidia-smi exit:3
    run "$VMBOX_TEST_HOME/sbin/nvidia-smi" -pl 100
    [ "$status" -eq 3 ]
}

@test "shim: hang mode never returns (the 2026-09-12 openrgb)" {
    _shim openrgb hang
    run timeout 1 "$VMBOX_TEST_HOME/sbin/openrgb"
    [ "$status" -eq 124 ]
    run cat "$VMBOX_TEST_HOME/shimlog/openrgb.log"
    [ "${#lines[@]}" -eq 1 ]
}

@test "shim: an unknown mode or a path is refused" {
    run _shim openrgb explode
    [ "$status" -eq 1 ]
    run _shim /usr/bin/openrgb exit
    [ "$status" -eq 1 ]
}
