#!/bin/bash
# ============================================================================
# Runs INSIDE a sandbox as root, via `vm shim <name> <tool> [mode]`.
#
# Install a fake <tool> ahead of the real one on PATH (/usr/local/sbin is
# first for root and for systemd services), so scripts that shell out to
# hardware the guest does not have -- openrgb, nvidia-smi, amixer -- can be
# driven through a chosen behaviour instead of "command not found":
#
#   exit[:N]   return N immediately (default 0)
#   hang       never return (what openrgb 1.0-2 did on 2026-09-12)
#   sleep:S    return 0 after S seconds
#
# Every invocation is appended to /var/log/vmbox-shim/<tool>.log as
# "<epoch> <argv>", so the host can assert from the guest what was called,
# with which arguments, and in what order relative to other shims.
# ============================================================================

set -euo pipefail

TOOL="${1:?usage: shim.sh <tool> [exit[:N]|hang|sleep:S]}"
MODE="${2:-exit}"
# Overridable for the host-side bats tests, which must not write to /usr.
readonly SHIM_DIR="${VMBOX_SHIM_DIR:-/usr/local/sbin}"
readonly LOG_DIR="${VMBOX_SHIM_LOG_DIR:-/var/log/vmbox-shim}"

case "$TOOL" in
    */*|'') echo "shim: tool must be a bare command name, got '$TOOL'" >&2; exit 1 ;;
esac

behaviour=""
case "$MODE" in
    exit)     behaviour='exit 0' ;;
    exit:*)   behaviour="exit ${MODE#exit:}" ;;
    hang)     behaviour='exec sleep infinity' ;;
    sleep:*)  behaviour="sleep ${MODE#sleep:}; exit 0" ;;
    *) echo "shim: unknown mode '$MODE' (exit[:N] | hang | sleep:S)" >&2; exit 1 ;;
esac

install -d -m 755 "$LOG_DIR" "$SHIM_DIR"
cat > "$SHIM_DIR/$TOOL" <<SHIM
#!/bin/bash
# vmbox shim for ${TOOL} (mode: ${MODE}) -- installed by \`vm shim\`.
printf '%(%s)T %s\\n' -1 "\$*" >> "${LOG_DIR}/${TOOL}.log"
${behaviour}
SHIM
chmod 755 "$SHIM_DIR/$TOOL"
: > "$LOG_DIR/$TOOL.log"
echo "shim: $SHIM_DIR/$TOOL installed (mode: $MODE), log: $LOG_DIR/$TOOL.log"
