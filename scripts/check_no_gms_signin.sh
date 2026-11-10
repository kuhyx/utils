#!/bin/bash

# ============================================================================
# Fail if a Flutter/Android app links Google's non-free sign-in stack.
#
# Every app signs in through kuhy's FOSS plugin google_account_token
# (utils/google_account_token, Android AccountManager). google_sign_in pulls
# google_sign_in_android, which links play-services-auth / googleid into the
# APK. Nine apps were migrated off it on 2026-11-02 and four more on
# 2026-11-10; nothing else stops a later session from re-adding it.
#
# Lockfile mode (default) reads pubspec.lock package keys, plus the gradle
# files under each lock's sibling android/ dir. Web-only pieces
# (google_sign_in_web, google_sign_in_platform_interface and their transitive
# google_identity_services_web) are allowed while google_sign_in_android is
# absent: kartka's web build uses them for the GIS button and they never
# reach an APK. APK mode looks for the GMS auth library marker files in the
# built APK, the ground truth when a dependency arrives some other way.
#
# Usage: check_no_gms_signin.sh [pubspec.lock | dir ...]
#        check_no_gms_signin.sh --apk app.apk
#   A dir is searched for pubspec.lock files (build/, .dart_tool/ pruned).
#   With no arguments, checks ./pubspec.lock (passes if there is none).
# Exit: 0 clean | 1 non-free sign-in found | 2 usage error
# ============================================================================

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
readonly SCRIPT_NAME
readonly BANNED=(google_sign_in google_sign_in_android google_sign_in_ios)
readonly WEB_ONLY=(google_sign_in_web google_sign_in_platform_interface
    google_identity_services_web)
# Maven coordinates (and split-form catalog names) of the GMS sign-in stack.
# Anchored so com.google.gms:google-services (Firebase) and
# play-services-auth-api-phone do not trip it.
readonly GRADLE_PATTERN='com\.google\.android\.gms:play-services-(auth|identity-credentials)([^-[:alnum:]]|$)|com\.google\.android\.libraries\.identity\.googleid|androidx\.credentials:credentials-play-services-auth|name[[:space:]]*=[[:space:]]*"(play-services-auth|play-services-identity-credentials|credentials-play-services-auth|googleid)"'
# APK mode: library marker files AGP copies to the APK root (or META-INF),
# one per linked artifact. Dex strings are not used: play-services-base and
# -basement reference GoogleSignInAccount without linking play-services-auth.
# play-services-fido (passkeys) is deliberately allowed.
readonly APK_MARKERS=(
    googleid.properties
    play-services-auth.properties
    play-services-auth-base.properties
    play-services-auth-api-phone.properties
    play-services-auth-blockstore.properties
    play-services-identity-credentials.properties
    META-INF/androidx.credentials_credentials-play-services-auth.version
)
readonly PRUNE=(-name build -o -name .dart_tool -o -name .git -o -name .gradle -o -name .claude
    -o -name node_modules)

usage() {
    echo "Usage: $SCRIPT_NAME [pubspec.lock | dir ...]"
    echo "       $SCRIPT_NAME --apk app.apk"
    echo "  Fails when an app links Google's non-free sign-in (GMS auth)."
    exit 0
}

fix_hint() {
    echo "       Use google_account_token instead (FOSS, AccountManager):" >&2
    echo "         google_account_token:" >&2
    echo "           git:" >&2
    echo "             url: https://github.com/kuhyx/utils" >&2
    echo "             ref: google_account_token-v0.1.0" >&2
    echo "             path: google_account_token" >&2
    echo "       See utils/google_account_token/README.md." >&2
}

# Package keys of a pubspec.lock: the 2-space keys under `packages:`.
lock_packages() {
    awk '
        /^packages:[[:space:]]*$/ { in_packages = 1; next }
        /^[^[:space:]]/          { in_packages = 0; next }
        in_packages && /^  [A-Za-z0-9_]+:[[:space:]]*$/ {
            sub(/^  /, ""); sub(/:.*/, ""); print
        }
    ' "$1"
}

# Prints the offending packages of one lock, one per line.
lock_offenders() {
    local -A present=()
    local name
    while IFS= read -r name; do
        present["$name"]=1
    done < <(lock_packages "$1")
    for name in "${BANNED[@]}"; do
        [[ -n "${present[$name]:-}" ]] && echo "$name"
    done
    if [[ -n "${present[google_sign_in_android]:-}" ]]; then
        for name in "${WEB_ONLY[@]}"; do
            [[ -n "${present[$name]:-}" ]] && echo "$name"
        done
    fi
    return 0
}

# Prints file:line:text for every non-comment GMS sign-in coordinate under
# the lock's sibling android/ dir.
gradle_offenders() {
    local android_dir="$1/android" file
    [[ -d "$android_dir" ]] || return 0
    while IFS= read -r -d '' file; do
        grep -nE "$GRADLE_PATTERN" "$file" \
            | grep -vE '^[0-9]+:[[:space:]]*(//|#|\*|/\*)' \
            | sed "s|^|$file:|" || true
    done < <(find "$android_dir" \( "${PRUNE[@]}" \) -prune -o -type f \
        \( -name 'build.gradle*' -o -name '*.versions.toml' \) -print0)
}

indent() {
    local line
    while IFS= read -r line; do
        echo "         $line"
    done
}

check_lock() {
    local lock="$1" offenders gradle
    offenders="$(lock_offenders "$lock")"
    gradle="$(gradle_offenders "$(dirname "$lock")")"
    [[ -z "$offenders" && -z "$gradle" ]] && return 0
    if [[ -n "$offenders" ]]; then
        echo "Error: $lock links Google's non-free sign-in:" >&2
        indent <<<"$offenders" >&2
    fi
    if [[ -n "$gradle" ]]; then
        echo "Error: gradle names the GMS sign-in stack:" >&2
        indent <<<"$gradle" >&2
    fi
    return 1
}

check_apk() {
    local apk="$1" entries found=()
    local marker
    [[ -f "$apk" ]] || { echo "Error: no such APK: $apk" >&2; exit 2; }
    entries="$(unzip -Z1 "$apk")"
    for marker in "${APK_MARKERS[@]}"; do
        grep -qxF -- "$marker" <<<"$entries" && found+=("$marker")
    done
    [[ "${#found[@]}" -eq 0 ]] && return 0
    echo "Error: $apk bundles Google's non-free sign-in libraries:" >&2
    printf '         %s\n' "${found[@]}" >&2
    fix_hint
    return 1
}

# Expands the arguments into pubspec.lock paths, NUL-separated.
collect_locks() {
    local arg
    for arg in "$@"; do
        if [[ -d "$arg" ]]; then
            find "$arg" \( "${PRUNE[@]}" \) -prune -o -type f \
                -name pubspec.lock -print0
        else
            printf '%s\0' "$arg"
        fi
    done
}

main() {
    case "${1:-}" in
        -h|--help) usage ;;
        --apk)
            [[ $# -eq 2 ]] || { echo "Usage: $SCRIPT_NAME --apk app.apk" >&2; exit 2; }
            check_apk "$2"
            return
            ;;
    esac
    if [[ $# -eq 0 ]]; then
        [[ -f pubspec.lock ]] || return 0
        set -- pubspec.lock
    fi

    local -a locks=()
    local arg lock failed=0
    # Validated up front: collect_locks runs in a process substitution, whose
    # exit status would be lost, and a typo'd path must not pass silently.
    for arg in "$@"; do
        [[ -e "$arg" ]] || { echo "Error: no such file or directory: $arg" >&2; exit 2; }
    done
    mapfile -d '' locks < <(collect_locks "$@")
    for lock in "${locks[@]}"; do
        check_lock "$lock" || failed=1
    done
    [[ "$failed" -eq 0 ]] || fix_hint
    return "$failed"
}

main "$@"
