"""Find the merged pull requests of a commit through the ``gh`` CLI."""

from __future__ import annotations

from dataclasses import dataclass
import json
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

GH_TIMEOUT = 20.0


class GhError(Exception):
    """gh missing, offline, failing or answering nonsense."""


class GhNotFound(GhError):
    """GitHub does not know the commit (HTTP 404/422), e.g. an unpushed sha."""


@dataclass(frozen=True)
class PullRequest:
    """A pull request GitHub links to a commit."""

    number: int
    body: str
    merged: bool


def run_gh(args: list[str]) -> str:
    """Run ``gh <args>``; stdout, or GhError on any failure."""
    try:
        done = subprocess.run(
            ["gh", *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=GH_TIMEOUT,
            stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError as err:
        msg = "gh not installed"
        raise GhError(msg) from err
    except subprocess.TimeoutExpired as err:
        msg = "gh timed out"
        raise GhError(msg) from err
    if done.returncode != 0:
        message = done.stderr.strip() or f"gh exit {done.returncode}"
        if "(HTTP 404)" in message or "(HTTP 422)" in message:
            raise GhNotFound(message)
        raise GhError(message)
    return done.stdout


def merged_prs(
    owner: str,
    name: str,
    sha: str,
    run: Callable[[list[str]], str] | None = None,
) -> list[PullRequest]:
    """Pull requests GitHub links to commit `sha`."""
    reply = (run or run_gh)(["api", f"repos/{owner}/{name}/commits/{sha}/pulls"])
    try:
        data = json.loads(reply)
        return [
            PullRequest(
                int(pr["number"]), pr.get("body") or "", bool(pr.get("merged_at"))
            )
            for pr in data
        ]
    except (ValueError, TypeError, KeyError) as err:
        msg = "unparseable gh output"
        raise GhError(msg) from err
