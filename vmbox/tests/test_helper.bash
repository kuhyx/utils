# ============================================================================
# vmbox: shared bats fixture for the host-side unit tests (load test_helper).
#
# VMBOX_HOME is redirected to a per-test temp dir. Nothing here may touch the
# real ~/.local/share/vmbox: these tests create and delete VM state, and a
# stray write there would clobber a live sandbox's overlay or pidfile.
# ============================================================================

setup() {
    VMBOX_TEST_HOME="$(mktemp -d)"
    export VMBOX_HOME="$VMBOX_TEST_HOME"
    REPO_ROOT="$(cd "$BATS_TEST_DIRNAME/.." && pwd -P)"
    export REPO_ROOT

    # common.sh guards against double-sourcing with a readonly flag, and bats
    # runs every test in a fresh subshell, so a plain source is safe here.
    source "$REPO_ROOT/lib/common.sh"
    source "$REPO_ROOT/lib/verdict.sh"

    install -d "$VMBOX_VMS_DIR"
}

teardown() {
    [[ -n "${VMBOX_TEST_HOME:-}" && -d "$VMBOX_TEST_HOME" ]] && rm -rf "$VMBOX_TEST_HOME"
}

# Create a fake VM directory without booting anything.
_fake_vm() {
    install -d "$(vm_dir "$1")"
}
