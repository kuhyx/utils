"""`git ls-remote` as the one subprocess the registries share.

Deliberately not the GitHub REST API: that allows 60 unauthenticated requests
an hour, which ~20 consuming manifests would exhaust on a single `--all` run.
`ls-remote` is unmetered and answers tags and HEAD alike.
"""

from __future__ import annotations

import subprocess

from dep_freshness.registries.http import Offline, host_reachable


def ls_remote(remote: str, *args: str) -> list[str]:
    """Every `<sha>\\t<ref>` line `git ls-remote` prints for `remote`.

    `--options` go before the URL and ref patterns (`HEAD`) after it: git
    reads the first positional as the repository, so `ls-remote HEAD <url>`
    fails with "'HEAD' does not appear to be a git repository".
    """
    if not host_reachable(remote):
        raise Offline(remote)
    options = [a for a in args if a.startswith("-")]
    patterns = [a for a in args if not a.startswith("-")]
    try:
        result = subprocess.run(
            ["git", "ls-remote", *options, remote, *patterns],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise Offline(f"{remote}: {exc}") from exc
    if result.returncode != 0:
        raise Offline(f"{remote}: git ls-remote exit {result.returncode}")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]
