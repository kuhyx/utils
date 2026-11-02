"""Git helpers: repo root, origin slug, HEAD sha and ``Todo:`` trailers."""

from __future__ import annotations

from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit

OWNER = "kuhyx"
_TRAILER_ID = re.compile(r"^[0-9a-fA-F][0-9a-fA-F-]{7,35}$")
_GIT_TIMEOUT = 15
_SLUG_PARTS = 2


def git(root: Path, *args: str) -> str | None:
    """Run git in `root`; stripped stdout, or None on any failure."""
    try:
        done = subprocess.run(
            ["git", *args],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT,
            stdin=subprocess.DEVNULL,
        )
    except OSError, subprocess.TimeoutExpired:
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def toplevel(cwd: Path) -> Path | None:
    out = git(cwd, "rev-parse", "--show-toplevel")
    return Path(out).resolve() if out else None


def _path_of(url: str) -> str:
    url = url.strip().rstrip("/").removesuffix(".git")
    if "://" in url:
        return urlsplit(url).path.strip("/")
    if ":" in url and not url.startswith("/"):
        return url.split(":", 1)[1].strip("/")
    return url


def parse_slug(url: str) -> tuple[str, str] | None:
    """(owner, name) from an scp-style, ssh:// or https:// remote URL."""
    if "://" not in url and (url.startswith("/") or ":" not in url):
        return None
    parts = [seg for seg in _path_of(url).split("/") if seg]
    return (parts[-2], parts[-1]) if len(parts) >= _SLUG_PARTS else None


def origin_url(root: Path) -> str | None:
    return git(root, "remote", "get-url", "origin")


def origin_slug(root: Path) -> tuple[str, str] | None:
    url = origin_url(root)
    return parse_slug(url) if url else None


def repo_name(root: Path) -> str:
    """Name from the origin URL; the checkout basename without a remote."""
    url = origin_url(root)
    name = _path_of(url).rsplit("/", 1)[-1] if url else ""
    return name or root.name


def expected_repo(root: Path) -> str:
    """The ``kuhyx/<name>`` value a task for this repository must carry."""
    return f"{OWNER}/{repo_name(root)}"


def head_sha(root: Path) -> str:
    return git(root, "rev-parse", "--short=7", "HEAD") or ""


def head_todo_ids(root: Path) -> list[str]:
    """Task ids from HEAD's ``Todo:`` trailers (first token, deduplicated)."""
    out = git(root, "log", "-1", "--format=%(trailers:key=Todo,valueonly)") or ""
    ids: list[str] = []
    for row in out.splitlines():
        token = row.split()[0] if row.strip() else ""
        if _TRAILER_ID.match(token) and token not in ids:
            ids.append(token)
    return ids
