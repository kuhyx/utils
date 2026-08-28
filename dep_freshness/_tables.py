"""Static data for the dependency-freshness gate.

Every tunable lives here so `config.py` stays a re-export surface and the
ecosystem modules stay pure logic. Changing a registry URL, a TTL or the Node
release channel is a one-line edit in this file and nowhere else.
"""

from __future__ import annotations

from typing import Final

# --- Ecosystems -------------------------------------------------------------

PUB: Final = "pub"
PYPI: Final = "pypi"
NPM: Final = "npm"
CARGO: Final = "cargo"
GOMOD: Final = "gomod"
GITTAG: Final = "gittag"
TOOLCHAIN: Final = "toolchain"
# The constraint a workflow parser writes for a version MATRIX. Standing
# decision (kuhy, 2026-08-28): one toolchain version per repo, always newest,
# so a matrix is a finding to delete rather than a range to satisfy.
MATRIX: Final = "matrix"

ECOSYSTEMS: Final = (PUB, PYPI, NPM, CARGO, GOMOD, GITTAG, TOOLCHAIN)

# --- Registry endpoints -----------------------------------------------------

PUB_API: Final = "https://pub.dev/api/packages/{name}"
PYPI_API: Final = "https://pypi.org/simple/{name}/"
NPM_API: Final = "https://registry.npmjs.org/{name}"
CRATES_API: Final = "https://crates.io/api/v1/crates/{name}"
GOPROXY_API: Final = "https://proxy.golang.org/{name}/@latest"
FLUTTER_RELEASES: Final = (
    "https://storage.googleapis.com/flutter_infra_release/releases/"
    "releases_linux.json"
)
NODE_RELEASES: Final = "https://nodejs.org/dist/index.json"
UTILS_TAG_REMOTE: Final = "https://github.com/kuhyx/utils"

# pnpm 11 quarantines packages younger than this before it will install them,
# to blunt the window in which a compromised publish is live. The gate matches
# it: reporting a repo as behind a version its package manager refuses to
# install is a failure nobody can act on. Its default is 1440 minutes.
NPM_QUARANTINE_HOURS: Final = 24

# crates.io 403s without one; npm/PyPI want a contactable agent too.
USER_AGENT: Final = "kuhyx-dependency-freshness (+https://github.com/kuhyx/utils)"

# PyPI's modern index; the legacy JSON `info.version` leaks pre-releases.
PYPI_ACCEPT: Final = "application/vnd.pypi.simple.v1+json"
NPM_ACCEPT: Final = "application/vnd.npm.install-v1+json"

# --- Cache ------------------------------------------------------------------

CACHE_PATH_ENV: Final = "DEP_FRESHNESS_CACHE"
DEFAULT_CACHE_DIR: Final = "~/.cache/dep-freshness"
CACHE_FILE: Final = "registry.json"
TTL_SECONDS: Final = 6 * 3600
TTL_GITTAG_SECONDS: Final = 24 * 3600
HTTP_TIMEOUT: Final = 10.0
PROBE_TIMEOUT: Final = 2.0
MAX_WORKERS: Final = 8

# --- Toolchain targets ------------------------------------------------------

# Q2 read literally points at Node Current; this machine and every repo build
# against LTS, so the gate targets LTS. One-line switch to "current".
NODE_CHANNEL: Final = "lts"

# The interpreter is pacman-managed here. A gate satisfiable only by fighting
# the distro gets disabled, so Python is compared to what is INSTALLED.
PYTHON_SOURCE: Final = "installed"

# --- Manifest discovery -----------------------------------------------------

MANIFEST_GLOBS: Final = (
    "pubspec.yaml",
    "pyproject.toml",
    "package.json",
    "Cargo.toml",
    "go.mod",
    ".fvmrc",
    ".nvmrc",
    ".python-version",
)
REQUIREMENTS_PATTERN: Final = r"^requirements.*\.txt$"

# `.utils` is where every CI workflow checks the shared gate out, INSIDE the
# repo being checked. Without it `--all` walks utils' own manifests and fails
# the consuming repo for staleness in a directory that repo does not own --
# which is exactly how punchme's first green local run turned red in CI.
EXCLUDED_DIRS: Final = frozenset({
    ".git", "node_modules", "build", "dist", ".dart_tool", ".venv", "venv",
    "__pycache__", "target", "vendor", ".gradle", "ios", "macos", "windows",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "coverage", "htmlcov",
    ".idea", ".vscode", "Pods", ".fvm", ".utils",
})

# --- Constraint policy ------------------------------------------------------

# Q13: these resolve from the Flutter/Dart SDK or are lint packages coupled to
# it, so a caret range is allowed. An exact pin is still checked for staleness.
PUB_CARET_ALLOWED: Final = frozenset({
    "flutter", "flutter_test", "flutter_localizations", "flutter_driver",
    "flutter_web_plugins", "integration_test", "sky_engine",
    "flutter_lints", "very_good_analysis", "lints",
})

# Packages that ship with the Flutter SDK: no registry version exists.
PUB_SDK_PACKAGES: Final = frozenset({
    "flutter", "flutter_test", "flutter_localizations", "flutter_driver",
    "flutter_web_plugins", "integration_test", "sky_engine",
})

# `dependency_overrides` is an unpinned dependency wearing a disguise.
PUB_OVERRIDE_KEY: Final = "dependency_overrides"

ALLOWLIST_FILE: Final = "dependency-freshness.allowlist.yaml"

# A blocker like "typescript-eslint does not support TS 7" holds in EVERY repo
# that pins typescript, so a repo-only allowlist would mean hand-copying one
# entry into eight files that then all rot independently -- the four-way fork
# of the 250-line cap, in the mechanism built to avoid it. The shared file in
# ~/utils is inherited; a repo entry for the same package overrides it.
SHARED_ALLOWLIST_ENV: Final = "DEP_FRESHNESS_SHARED_ALLOWLIST"
ALLOWLIST_MAX_DAYS: Final = 90
TRANSITIVE_PREFIX: Final = "transitive:"
