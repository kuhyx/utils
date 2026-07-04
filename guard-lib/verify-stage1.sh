#!/bin/bash
# Live root verification for guard-lib Stage 1: proves file-guard and
# package-block actually work against a real target and real pacman
# transactions before Stage 2 touches anything in /etc that matters
# (hosts, nsswitch, resolved). Must be run as root. Always cleans up
# after itself (throwaway target + test packages), whether checks pass
# or fail, so it is safe to re-run.
set -uo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "verify-stage1.sh must be run as root: sudo $0" >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_TARGET=/etc/guard-test-file
FG_NAME=dummy-test
PB_NAME=steam-test
PB_LOCK=/etc/guard-lib/blocks/steam-test-lock.json
HARMLESS_PKG=cowsay
BLOCKED_TEST_PKG=sl

PASS_COUNT=0
FAIL_COUNT=0
FAILURES=()
CLEANUP_DONE=0

step() {
    echo
    echo "=== $1 ==="
}

pass() {
    PASS_COUNT=$((PASS_COUNT + 1))
    echo "  PASS: $1"
}

fail() {
    FAIL_COUNT=$((FAIL_COUNT + 1))
    FAILURES+=("$1")
    echo "  FAIL: $1"
}

cleanup() {
    [[ "$CLEANUP_DONE" -eq 1 ]] && return
    CLEANUP_DONE=1
    step "Cleanup"
    guardctl package-block end "$PB_NAME" >/dev/null 2>&1 && echo "  ended package-block '$PB_NAME'" || true
    guardctl file-guard uninstall "$FG_NAME" >/dev/null 2>&1 && echo "  uninstalled file-guard '$FG_NAME'" || true
    rm -f "$TEST_TARGET"
    pacman -Qi "$BLOCKED_TEST_PKG" >/dev/null 2>&1 && pacman -R --noconfirm "$BLOCKED_TEST_PKG" >/dev/null 2>&1 || true
    pacman -Qi "$HARMLESS_PKG" >/dev/null 2>&1 && pacman -R --noconfirm "$HARMLESS_PKG" >/dev/null 2>&1 || true
    echo "  removed $TEST_TARGET, $HARMLESS_PKG, $BLOCKED_TEST_PKG"
}
trap cleanup EXIT INT TERM

step "1. Install guard-lib"
if "$SCRIPT_DIR/install.sh"; then
    pass "install.sh ran cleanly"
else
    fail "install.sh failed"
fi

step "2. Install file-guard on a throwaway target"
echo "hello" >"$TEST_TARGET"
if guardctl file-guard install "$FG_NAME" --target "$TEST_TARGET"; then
    pass "file-guard install succeeded"
else
    fail "file-guard install failed"
fi

attrs="$(lsattr "$TEST_TARGET" 2>/dev/null | awk '{print $1}')"
if [[ "$attrs" == *i* ]]; then
    pass "target is immutable after install (attrs: $attrs)"
else
    fail "target is NOT immutable after install (attrs: $attrs)"
fi

step "3. Tamper the target and confirm auto-revert"
chattr -i "$TEST_TARGET" 2>/dev/null || true
echo "TAMPERED" >"$TEST_TARGET"
sleep 2
content="$(cat "$TEST_TARGET" 2>/dev/null || echo '<missing>')"
if [[ "$content" == "hello" ]]; then
    pass "content auto-reverted to canonical after tamper"
else
    fail "content did NOT revert (got: '$content')"
fi

attrs="$(lsattr "$TEST_TARGET" 2>/dev/null | awk '{print $1}')"
if [[ "$attrs" == *i* ]]; then
    pass "target re-locked (immutable) after revert"
else
    fail "target NOT re-locked after revert (attrs: $attrs)"
fi

step "3b. file-guard unlock: legitimate edit updates canonical and survives re-enforce"
FAKE_EDITOR="$(mktemp)"
cat >"$FAKE_EDITOR" <<'EOF'
#!/bin/bash
echo "hello-edited" >"$1"
EOF
chmod +x "$FAKE_EDITOR"
if EDITOR="$FAKE_EDITOR" guardctl file-guard unlock "$FG_NAME" <<<"verify-stage1 test"; then
    pass "file-guard unlock completed"
else
    fail "file-guard unlock exited non-zero"
fi
content="$(cat "$TEST_TARGET" 2>/dev/null || echo '<missing>')"
if [[ "$content" == "hello-edited" ]]; then
    pass "unlock edit applied to target"
else
    fail "unlock edit NOT applied to target (got: '$content')"
fi
canonical_content="$(cat "$(guardctl file-guard canonical-path "$FG_NAME")" 2>/dev/null || echo '<missing>')"
if [[ "$canonical_content" == "hello-edited" ]]; then
    pass "unlock updated canonical to match edit"
else
    fail "canonical NOT updated after unlock (got: '$canonical_content') - legitimate edits would be reverted by the watcher"
fi
sleep 2
content_after_wait="$(cat "$TEST_TARGET" 2>/dev/null || echo '<missing>')"
if [[ "$content_after_wait" == "hello-edited" ]]; then
    pass "edit survives after re-enforce (not reverted)"
else
    fail "edit was reverted after unlock (got: '$content_after_wait')"
fi
rm -f "$FAKE_EDITOR"

step "4. Confirm a harmless pacman transaction still works (critical: generic hook must not brick pacman)"
echo "  (showing pacman's own output live - a slow mirror can take a minute or two, this is not a hang)"
if pacman -S --noconfirm --needed "$HARMLESS_PKG"; then
    pass "pacman -S $HARMLESS_PKG succeeded"
else
    fail "pacman -S $HARMLESS_PKG FAILED - the generic unlock-all/relock-all hook may be broken"
fi
if pacman -R --noconfirm "$HARMLESS_PKG"; then
    pass "pacman -R $HARMLESS_PKG succeeded (cleanup)"
else
    fail "pacman -R $HARMLESS_PKG failed (test package may be left installed)"
fi

step "5. package-block: block install of a throwaway package"
if guardctl package-block start "$PB_NAME" --package "$BLOCKED_TEST_PKG" --lock-file "$PB_LOCK" --days 1; then
    pass "package-block start succeeded"
else
    fail "package-block start failed"
fi

echo "  (expecting this install to be ABORTED by the package-block hook)"
if pacman -S --noconfirm "$BLOCKED_TEST_PKG"; then
    fail "pacman -S $BLOCKED_TEST_PKG succeeded while blocked (should have been aborted)"
else
    pass "pacman -S $BLOCKED_TEST_PKG was blocked as expected"
fi

step "6. package-block: end restores normal installs"
if guardctl package-block end "$PB_NAME"; then
    pass "package-block end succeeded"
else
    fail "package-block end failed"
fi

if pacman -S --noconfirm --needed "$BLOCKED_TEST_PKG"; then
    pass "pacman -S $BLOCKED_TEST_PKG succeeded after block ended"
else
    fail "pacman -S $BLOCKED_TEST_PKG FAILED after block ended (should be allowed now)"
fi

cleanup

echo
echo "=================================================="
echo "Stage 1 live verification: $PASS_COUNT passed, $FAIL_COUNT failed"
if [[ "$FAIL_COUNT" -gt 0 ]]; then
    echo "Failures:"
    for f in "${FAILURES[@]}"; do
        echo "  - $f"
    done
    exit 1
fi
echo "ALL STAGE 1 LIVE CHECKS PASSED"
exit 0
