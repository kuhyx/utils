#!/bin/bash

# ============================================================================
# Register every com.kuhy.* / dev.kuhy.* Android app in the kuhy-syncs Firebase
# project and attach both signing fingerprints to each.
#
# Google sign-in on Android needs an Android OAuth client whose (package name,
# SHA-1) pair matches the installed APK. Getting either wrong surfaces as
# `ApiException: 10 / DEVELOPER_ERROR`, which names neither -- so this does it
# from one verified list instead of five console visits.
#
# Both fingerprints go on every app: the release key signs what CI publishes,
# the debug key signs a local `flutter build apk`. Omitting the debug one means
# sign-in works from CI builds and mysteriously fails from your own.
#
# Idempotent: existing apps are reused and existing hashes skipped, so this is
# safe to re-run after adding an app or rotating a key.
#
# Requires: firebase-tools, and `firebase login` already done (browser flow).
# ============================================================================

set -euo pipefail

readonly PROJECT="kuhy-syncs"

# Fingerprints, read from the keystores rather than pasted, so a rotated key
# cannot silently leave this script registering a stale hash.
readonly DEBUG_KEYSTORE="$HOME/.android/debug.keystore"
readonly RELEASE_KEYSTORE="$HOME/.android/release/kuhy-release.jks"

# "<display name>:<package name>" -- the package must match applicationId in
# each app's build.gradle exactly. Note todo is dev.kuhy.*, the rest com.kuhy.*.
readonly APPS=(
    "todo:dev.kuhy.todo"
    "workout_app:com.kuhy.workout_app"
    "diet_guard_app:com.kuhy.diet_guard_app"
    "home_inventory:com.kuhy.home_inventory"
    "wake_alarm_sync:com.kuhy.wake_alarm_sync"
)

usage() {
    echo "Usage: $(basename "$0") [--dry-run]"
    echo "  Registers the Android apps and their SHA-1s in $PROJECT."
    echo "  Run 'firebase login' first."
    exit 0
}

DRY_RUN=0

require_login() {
    if ! firebase login:list 2>&1 | grep -qi 'logged in'; then
        echo "Error: not logged in. Run: firebase login" >&2
        echo "       (browser flow -- this script cannot do it for you)" >&2
        exit 1
    fi
}

# Prints the SHA-1 of a keystore alias, or exits with a message naming the file.
sha1_of() {
    local keystore="$1" alias="$2" storepass="$3"
    if [[ ! -f "$keystore" ]]; then
        echo "Error: keystore not found: $keystore" >&2
        exit 1
    fi
    local out
    out="$(keytool -list -v -keystore "$keystore" -alias "$alias" \
        -storepass "$storepass" 2>/dev/null | grep -m1 'SHA1:' || true)"
    if [[ -z "$out" ]]; then
        echo "Error: no SHA1 for alias '$alias' in $keystore" >&2
        exit 1
    fi
    # "	 SHA1: AA:BB:..." -> "AA:BB:..."
    echo "${out##*SHA1: }"
}

# Looks up an appId by package name, via --json.
#
# Deliberately not parsing `apps:list`'s default output: that is a rendered
# table carrying ANSI colour codes, and it shows the *display name* rather than
# the package -- so a name/package mismatch silently found nothing. The JSON
# form carries packageName explicitly.
app_id_for() {
    local package="$1"
    firebase apps:list ANDROID --project "$PROJECT" --json 2>/dev/null \
        | python3 -c "
import json, sys
package = sys.argv[1]
try:
    apps = json.load(sys.stdin).get('result') or []
except ValueError:
    sys.exit(0)
for app in apps:
    if app.get('packageName') == package:
        print(app.get('appId', ''))
        break
" "$package"
}

# Returns the appId for a package name, creating the app when absent.
ensure_app() {
    local display="$1" package="$2" existing
    existing="$(app_id_for "$package")"
    if [[ -n "$existing" ]]; then
        echo "$existing"
        return
    fi
    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "WOULD-CREATE"
        return
    fi
    firebase apps:create ANDROID "$display" \
        --package-name "$package" --project "$PROJECT" >&2
    app_id_for "$package"
}

# Adds a fingerprint unless the app already carries it.
ensure_sha() {
    local app_id="$1" sha="$2" label="$3"
    if [[ "$app_id" == "WOULD-CREATE" ]]; then
        echo "    would add $label SHA-1"
        return
    fi
    # Compare without separators and case-insensitively: the API echoes hashes
    # unseparated and lowercased, while keytool prints AA:BB:CC uppercase, so a
    # literal match would re-add an existing hash on every run.
    local normalized="${sha//:/}"
    if firebase apps:android:sha:list "$app_id" --project "$PROJECT" --json 2>/dev/null \
        | tr -d '\n' | grep -qi "${normalized}"; then
        echo "    $label SHA-1 already present"
        return
    fi
    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "    would add $label SHA-1"
        return
    fi
    firebase apps:android:sha:create "$app_id" "$sha" --project "$PROJECT" >/dev/null
    echo "    added $label SHA-1"
}

main() {
    local debug_sha release_sha
    debug_sha="$(sha1_of "$DEBUG_KEYSTORE" androiddebugkey android)"

    # The release store password lives in a key.properties committed nowhere;
    # any app's copy will do since they share one keystore.
    local props="$HOME/home_inventory/android/key.properties"
    if [[ ! -f "$props" ]]; then
        echo "Error: $props not found; needed for the release keystore password" >&2
        exit 1
    fi
    local storepass alias
    storepass="$(grep '^storePassword=' "$props" | cut -d= -f2-)"
    alias="$(grep '^keyAlias=' "$props" | cut -d= -f2-)"
    release_sha="$(sha1_of "$RELEASE_KEYSTORE" "$alias" "$storepass")"

    echo "Project:  $PROJECT"
    echo "release:  $release_sha"
    echo "debug:    $debug_sha"
    echo

    [[ "$DRY_RUN" -eq 0 ]] && require_login

    for entry in "${APPS[@]}"; do
        local display="${entry%%:*}" package="${entry#*:}"
        echo "$display ($package)"
        local app_id
        app_id="$(ensure_app "$display" "$package")"
        if [[ -z "$app_id" ]]; then
            echo "    Error: could not resolve an appId" >&2
            exit 1
        fi
        echo "    appId: $app_id"
        ensure_sha "$app_id" "$release_sha" release
        ensure_sha "$app_id" "$debug_sha" debug
    done

    echo
    echo "Done. Next: enable Google sign-in, then read the Web client id with"
    echo "  firebase apps:sdkconfig WEB --project $PROJECT"
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run) DRY_RUN=1; shift ;;
        -h|--help) usage ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

main
