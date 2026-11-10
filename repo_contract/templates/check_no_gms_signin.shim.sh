#!/bin/bash

# ============================================================================
# Fail if this app links Google's non-free sign-in (google_sign_in,
# play-services-auth, googleid) instead of google_account_token.
#
# Thin delegate to the shared gate in ~/src/utils, which owns the package
# list and the fix message. Copy this file to scripts/check_no_gms_signin.sh
# in a repo; never copy the shared gate itself.
# ============================================================================

set -euo pipefail

readonly SHARED_GATE="${UTILS_ROOT:-$HOME/src/utils}/scripts/check_no_gms_signin.sh"

main() {
    if [[ ! -x "$SHARED_GATE" ]]; then
        echo "Error: shared no-gms-signin gate not found at $SHARED_GATE" >&2
        echo "       Clone github.com/kuhyx/utils to ~/src/utils, or set" >&2
        echo "       UTILS_ROOT to where it lives." >&2
        exit 1
    fi

    exec bash "$SHARED_GATE" "$@"
}

main "$@"
