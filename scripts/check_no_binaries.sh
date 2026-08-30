#!/bin/bash

# ============================================================================
# Block binary and image files from being committed.
#
# Promoted here from testsAndMisc/meta/scripts so every repo gets the same
# answer to "may this file be committed?". signal-bot is a public repository
# that had three binary SQLite files in its history before this existed, and
# it also holds a private message database one `git add -f` away from the
# same fate -- so the rule wants enforcing everywhere, not per repo.
#
# Exceptions live in .binary-allowlist in the repo root, one glob per line.
# ============================================================================

set -euo pipefail

readonly ALLOWLIST_FILE=".binary-allowlist"

readonly BLOCKED_EXTENSIONS=(
	# Images
	png jpg jpeg gif webp svg ico bmp tiff tif psd
	# Audio/Video
	mp3 mp4 wav avi mkv flac ogg wma aac m4a mov wmv flv
	# Archives
	zip tar gz tgz bz2 xz 7z rar
	# Documents
	pdf doc docx xls xlsx ppt pptx
	# Fonts
	ttf woff woff2 eot otf
	# Compiled / binary
	o so a exe dll dylib pyc pyo class
	# Data. sqlite3-wal and -shm are spelled out because a live database is
	# three files, and blocking only the first one blocks nothing useful.
	apkg bin flat db sqlite sqlite3 sqlite3-wal sqlite3-shm
)

allowed_patterns=()

build_pattern() {
	local pattern="" ext
	for ext in "${BLOCKED_EXTENSIONS[@]}"; do
		if [[ -z "$pattern" ]]; then
			pattern="\\.(${ext}"
		else
			pattern="${pattern}|${ext}"
		fi
	done
	printf '%s)$' "$pattern"
}

load_allowlist() {
	[[ -f "$ALLOWLIST_FILE" ]] || return 0
	local line
	while IFS= read -r line; do
		[[ "$line" =~ ^[[:space:]]*# ]] && continue
		[[ -z "${line// /}" ]] && continue
		allowed_patterns+=("$line")
	done <"$ALLOWLIST_FILE"
}

is_allowed() {
	local file="$1" pat
	for pat in "${allowed_patterns[@]+"${allowed_patterns[@]}"}"; do
		# shellcheck disable=SC2254
		case "$file" in
		$pat) return 0 ;;
		esac
	done
	return 1
}

main() {
	local pattern found=0 file
	pattern="$(build_pattern)"
	load_allowlist

	for file in "$@"; do
		# Untracked or deleted paths are not this gate's business.
		git ls-files --error-unmatch "$file" >/dev/null 2>&1 || continue
		grep -qiE "$pattern" <<<"$file" || continue
		is_allowed "$file" && continue
		echo "BLOCKED: $file"
		found=1
	done

	if [[ "$found" -eq 1 ]]; then
		echo ""
		echo "ERROR: binary/image files must not be committed."
		echo "Options:"
		echo "  1. Keep them outside the repo (preferred)."
		echo "  2. Add a glob to $ALLOWLIST_FILE, for genuinely essential files."
		exit 1
	fi
}

main "$@"
