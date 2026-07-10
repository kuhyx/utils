#!/bin/bash
# Installs guard-lib: guardctl to /usr/local/bin, its lib/ to
# /usr/local/lib/guard-lib, systemd unit templates, and the generic
# unlock-all/relock-all pacman hooks. Safe to re-run (idempotent copy).
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "install.sh must be run as root (it writes to /usr/local, /etc/systemd, /etc/pacman.d)" >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

for tool in jq chattr lsattr systemctl; do
    command -v "$tool" >/dev/null 2>&1 || {
        echo "install.sh: required tool '$tool' not found on PATH" >&2
        exit 1
    }
done

echo "Installing guardctl to /usr/local/bin ..."
install -m 755 "$SCRIPT_DIR/guardctl" /usr/local/bin/guardctl

echo "Installing lib/ to /usr/local/lib/guard-lib ..."
install -d -m 755 /usr/local/lib/guard-lib
install -m 644 "$SCRIPT_DIR"/lib/*.sh /usr/local/lib/guard-lib/

echo "Installing systemd unit templates ..."
install -m 644 "$SCRIPT_DIR"/systemd/guard-file@.path /etc/systemd/system/
install -m 644 "$SCRIPT_DIR"/systemd/guard-file@.service /etc/systemd/system/
install -m 644 "$SCRIPT_DIR"/systemd/guard-bind-mount@.service /etc/systemd/system/
systemctl daemon-reload

echo "Installing generic pacman unlock-all/relock-all hooks ..."
install -d -m 755 /etc/guard-lib/pacman-hooks
install -m 755 "$SCRIPT_DIR/pacman-hooks/guard-lib-unlock-all.sh" /etc/guard-lib/pacman-hooks/
install -m 755 "$SCRIPT_DIR/pacman-hooks/guard-lib-relock-all.sh" /etc/guard-lib/pacman-hooks/
install -d -m 755 /etc/pacman.d/hooks
install -m 644 "$SCRIPT_DIR/pacman-hooks/10-guard-lib-unlock-all.hook" /etc/pacman.d/hooks/
install -m 644 "$SCRIPT_DIR/pacman-hooks/90-guard-lib-relock-all.hook" /etc/pacman.d/hooks/

install -d -m 755 /etc/guard-lib/targets /etc/guard-lib/blocks /etc/guard-lib/canonical

echo "guard-lib installed. Try: guardctl file-guard install dummy-test --target /etc/guard-test-file"
