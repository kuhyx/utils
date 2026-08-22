#!/bin/bash
# ============================================================================
# vmbox installer: installs host dependencies and links `vm` onto PATH.
#
# Deliberately NOT run as root: vmbox is designed to need no root at all
# (user-mode + multicast networking, qcow2 overlays, no bridge, no libvirt).
# Only the pacman step escalates, and only when something is missing.
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
readonly SCRIPT_DIR
readonly LINK_DIR="${LINK_DIR:-$HOME/.local/bin}"

# xorriso ships in libisoburn -- there is no package named "xorriso".
readonly -a PACKAGES=(qemu-base libisoburn openssh python)

if [[ $EUID -eq 0 ]]; then
    echo "Do not run install.sh as root: it links into \$HOME and would" >&2
    echo "create root-owned files there. It escalates on its own if needed." >&2
    exit 1
fi

echo "==> Checking host dependencies ..."
missing=()
for pkg in "${PACKAGES[@]}"; do
    pacman -Qq "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
done

if (( ${#missing[@]} )); then
    echo "==> Installing: ${missing[*]}"
    sudo pacman -S --needed --noconfirm "${missing[@]}"
else
    echo "    all present: ${PACKAGES[*]}"
fi

# KVM is what makes this usable rather than glacial; a missing /dev/kvm is a
# hard stop, not a warning, because the fallback is ~20x slower.
[[ -c /dev/kvm ]] || {
    echo "error: /dev/kvm missing -- enable virtualization (SVM/VT-x) in firmware" >&2
    exit 1
}
[[ -r /dev/kvm && -w /dev/kvm ]] || {
    echo "error: /dev/kvm not read/writable by $USER -- add yourself to the 'kvm' group" >&2
    exit 1
}

echo "==> Linking vm -> $LINK_DIR/vm"
install -d -m 755 "$LINK_DIR"
ln -sfn "$SCRIPT_DIR/bin/vm" "$LINK_DIR/vm"

case ":$PATH:" in
    *":$LINK_DIR:"*) ;;
    *) echo "    note: $LINK_DIR is not on your PATH" ;;
esac

echo
echo "Installed. Next: vm build     (builds the golden image, once)"
