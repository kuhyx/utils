"""A throwaway copy of a repo's working tree to run the site build in.

Why: kcd2-dice-solver (and personal-website) bind-mount `dist/` into the live
Caddy container, so a gate that ran `pnpm run build` in the repo emptied the
live site on every commit (Vite's emptyOutDir) and shipped the uncommitted
tree. Building in a copy means no build command, prerender step or outDir
setting can ever write the configured live `dist`.

The copy is the git working tree (tracked + untracked, minus ignored files, so
a stale `dist/` never leaks in) with `node_modules` symlinked, not copied.
Outside git (tests, a bare dir) everything but node_modules/.git is copied.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

SKIP = ("node_modules", ".git")


def _git_files(repo: Path) -> list[str]:
    """Working-tree files git would see: tracked + untracked, not ignored."""
    out = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-z", "--cached", "--others"]
        + ["--exclude-standard"],
        capture_output=True,
        check=True,
    ).stdout
    return sorted({f.decode() for f in out.split(b"\0") if f})


def populate(repo: Path, dest: Path) -> None:
    """Fill the empty dir `dest` with a build-ready copy of `repo`."""
    if (repo / ".git").exists():
        for rel in _git_files(repo):
            src = repo / rel
            if not src.is_file() or rel.split("/")[0] in SKIP:
                continue  # deleted in the worktree, or a submodule/dep dir
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target, follow_symlinks=False)
    else:
        shutil.copytree(
            repo,
            dest,
            symlinks=True,
            ignore=shutil.ignore_patterns(*SKIP),
            dirs_exist_ok=True,
        )
    if (repo / "node_modules").is_dir():
        (dest / "node_modules").symlink_to(repo / "node_modules")
