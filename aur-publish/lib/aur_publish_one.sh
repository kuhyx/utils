#!/bin/bash

# ============================================================================
# Building, verifying and pushing one package to the AUR.
#
# Sourced by publish.sh, never executed: these functions read the readonly
# config (AUR_HOST, AUR_ROOT, DRY_RUN, PUBLISHED, FAILED) that the entry script declares, and
# a `readonly` re-run inside a twice-sourced lib would abort under `set -e`.
# ============================================================================

set -euo pipefail

publish_one() {
    local pkg="$1" repo="$2" wrapper="$3" binary="$4" expected="$5"
    local dir="$AUR_ROOT/$pkg"
    local version

    log "$pkg"

    [[ -d "$repo" ]] || { warn "$pkg: no repo at $repo"; return 1; }
    [[ -f "$dir/PKGBUILD" ]] || { warn "$pkg: no PKGBUILD at $dir"; return 1; }

    version="$(newest_tag "$repo")"
    [[ -n "$version" ]] || { warn "$pkg: no vX.Y.Z tag on the remote"; return 1; }
    info "newest release tag: v$version"

    cd "$dir"
    sed -i -E "s/^pkgver=.*/pkgver=$version/" PKGBUILD
    # The tarball for a tag contains the PKGBUILD, so the checksum can only be
    # computed after the tag exists — never committed ahead of time.
    updpkgsums >/dev/null 2>&1 || { warn "$pkg: updpkgsums failed (tag missing?)"; return 1; }

    info "building"
    if ! env PATH=/usr/bin:/bin:/usr/local/bin makepkg -Cf --noconfirm >/dev/null 2>&1; then
        warn "$pkg: makepkg failed"
        return 1
    fi

    local built
    built="$(find . -maxdepth 1 -name "$pkg-$version-*.pkg.tar.zst" | head -1)"
    [[ -n "$built" ]] || { warn "$pkg: no package produced"; return 1; }

    # namcap's "ELF files outside of a valid path ('opt/')" is a false positive
    # for /opt-installed apps, so only genuinely new errors are worth failing on.
    local findings
    findings="$(namcap "$built" 2>&1 | grep -E ' E: ' | grep -v "outside of a valid path" || true)"
    if [[ -n "$findings" ]]; then
        warn "$pkg: namcap errors:"
        printf '      %s\n' "$findings"
        return 1
    fi

    info "installing and launching"
    sudo pacman -U --noconfirm "$built" >/dev/null 2>&1 \
        || { warn "$pkg: pacman -U failed"; return 1; }
    verify_installed "$binary" "$expected" "$wrapper" || { warn "$pkg: launch check failed"; return 1; }

    # Generated before the rule check, which verifies it matches the PKGBUILD.
    makepkg --printsrcinfo > .SRCINFO
    check_aur_rules "$pkg" || return 1

    # The AUR repo is a separate remote living alongside the build dir; adding
    # it here (rather than cloning into a fresh path) keeps the verified
    # PKGBUILD and the thing being pushed byte-identical.
    if [[ ! -d .git ]]; then
        git init -q -b master .
        git remote add origin "ssh://aur@$AUR_HOST/$pkg.git"
    fi
    git remote get-url origin >/dev/null 2>&1 \
        || git remote add origin "ssh://aur@$AUR_HOST/$pkg.git"

    # Fetch first: an existing AUR package must be built on, not overwritten.
    if git fetch -q origin master 2>/dev/null; then
        git reset -q --soft FETCH_HEAD 2>/dev/null || true
    fi

    cat > .gitignore <<'EOF'
# Build products; the AUR tracks only the recipe.
*.pkg.tar.zst
*.tar.gz
src/
pkg/
EOF

    git add PKGBUILD .SRCINFO .gitignore
    if git diff --cached --quiet; then
        info "already up to date on the AUR; nothing to push"
        PUBLISHED+=("$pkg v$version (unchanged)")
        return 0
    fi

    git -c user.name='Krzysztof Rudnicki' \
        -c user.email='krzysztofrudnicki0@gmail.com' \
        commit -q -m "$pkg $version-1"

    if ((DRY_RUN)); then
        info "DRY RUN — not pushing"
        PUBLISHED+=("$pkg v$version (dry run)")
        return 0
    fi

    info "pushing to the AUR"
    git push -q origin master 2>&1 | tail -3 || { warn "$pkg: push failed"; return 1; }
    PUBLISHED+=("$pkg v$version")
    return 0
}

