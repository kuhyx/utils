"""Fail-closed checks on what may be sent to free (logging, maybe training) providers.

A file may go out only if it lives in a PUBLIC GitHub repo, or under /tmp or
/var/log, and is not a secret-shaped file. Every text is scanned for credential
patterns; that scan has no override.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from fnmatch import fnmatch
from pathlib import Path

CACHE = Path.home() / ".cache/omniroute_offload/visibility.json"
CACHE_TTL_S = 86400
SCRATCH_ROOTS = (Path("/tmp"), Path("/var/log"))
DENIED_HOME_DIRS = (".ssh", ".config", ".gnupg", ".aws", ".claude")
DENIED_NAMES = (
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "id_rsa*",
    "id_ed25519*",
    "id_ecdsa*",
    "*secret*",
    "*credential*",
    "*.p12",
    "*.pfx",
    "*.keystore",
    "*.jks",
    ".netrc",
)
SECRET_PATTERNS = re.compile(
    r"sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{20,}"
    r"|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|AIza[0-9A-Za-z_-]{35}"
    r"|xox[abprs]-[A-Za-z0-9-]{10,}"
)
GITHUB_REMOTE = re.compile(r"github\.com[:/]([^/\s]+/[^/\s]+?)(?:\.git)?/?$")


def secret_refusal(text: str) -> str | None:
    """Reason to refuse when the text contains something credential-shaped."""
    hit = SECRET_PATTERNS.search(text)
    return f"looks like a credential ({hit.group()[:8]}...)" if hit else None


def path_refusal(path: Path, *, home: Path) -> str | None:
    """Reason to refuse by file name or location alone (repo visibility aside)."""
    if any(fnmatch(path.name, pattern) for pattern in DENIED_NAMES):
        return f"{path}: secret-shaped file name"
    for sub in DENIED_HOME_DIRS:
        if path.is_relative_to(home / sub):
            return f"{path}: under ~/{sub}"
    if _repo_root(path) or any(path.is_relative_to(root) for root in SCRATCH_ROOTS):
        return None
    return f"{path}: not in a public repo, /tmp or /var/log"


def file_refusal(path: Path, *, home: Path) -> str | None:
    """Check one file; inside any repo (even under /tmp) its visibility decides."""
    path = path.resolve()
    reason = path_refusal(path, home=home)
    root = _repo_root(path)
    if reason or root is None:
        return reason
    return repo_refusal(root)


def github_slug(remote: str) -> str | None:
    """owner/repo of a GitHub remote URL, else None."""
    match = GITHUB_REMOTE.search(remote.strip())
    return match.group(1) if match else None


def repo_refusal(root: Path) -> str | None:
    """Reason to refuse unless the repo's GitHub origin is PUBLIC (cached a day)."""
    remote = _git(root, "remote", "get-url", "origin")
    slug = github_slug(remote) if remote else None
    if slug is None:
        return f"{root}: repo has no GitHub origin"
    visibility = _cached_visibility(slug)
    if visibility == "PUBLIC":
        return None
    return f"{root}: {slug} is {visibility or 'unknown (gh failed)'}"


def _cached_visibility(slug: str) -> str | None:
    try:
        cache = json.loads(CACHE.read_text())
    except OSError, ValueError:
        cache = {}
    entry = cache.get(slug)
    if entry and time.time() - entry["at"] < CACHE_TTL_S:
        return str(entry["visibility"])
    visibility = _gh_visibility(slug)
    if visibility is None:
        return None
    cache[slug] = {"visibility": visibility, "at": time.time()}
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache))
    return visibility


def _gh_visibility(slug: str) -> str | None:
    try:
        done = subprocess.run(
            ["gh", "repo", "view", slug, "--json", "visibility"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except OSError, subprocess.TimeoutExpired:
        return None
    if done.returncode:
        return None
    return str(json.loads(done.stdout)["visibility"])


def _repo_root(path: Path) -> Path | None:
    start = path if path.is_dir() else path.parent
    while not start.exists():
        start = start.parent
    top = _git(start, "rev-parse", "--show-toplevel")
    return Path(top) if top else None


def _git(cwd: Path, *args: str) -> str | None:
    done = subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=False
    )
    return done.stdout.strip() if not done.returncode and done.stdout.strip() else None


def check_dir_main(argv: list[str] | None = None) -> int:
    """free-llm-check-dir <dir>: exit 0 if its files may go to free models, else 2."""
    args = sys.argv[1:] if argv is None else argv
    target = Path(args[0] if args else ".").resolve()
    reason = file_refusal(target, home=Path.home())
    if reason:
        print(f"refused: {reason}", file=sys.stderr)
        return 2
    return 0
