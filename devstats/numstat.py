"""One `git log --numstat -z` pass per repo, parsed into commits and file changes.

Record layout (git 2.x): `\\x1e<sha>\\x1f<committer ts>\\x1f<author email>\\x1f<author ts>\\x1f<subject>\\0`,
then a newline before the first entry, then per file either
`ins\\tdel\\tpath\\0` or, for a rename, `ins\\tdel\\t\\0old\\0new\\0`.
Binaries report `-` for both counts.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from devstats.gitcmd import git

FORMAT = "%x1e%H%x1f%ct%x1f%ae%x1f%at%x1f%s"


@dataclass(frozen=True)
class FileChange:
    """Line counts for one path in one commit."""

    path: str
    ins: int
    dels: int
    binary: bool


@dataclass(frozen=True)
class Commit:
    """One non-merge commit: committer timestamp, lowercased author email, files.

    `author_ts` + `subject` survive history rewrites (filter-repo splits, forks),
    so together with the email they identify the same work across repos.
    """

    sha: str
    ts: int
    email: str
    files: tuple[FileChange, ...]
    author_ts: int = 0
    subject: str = ""

    @property
    def identity(self) -> tuple[str, int, str]:
        """Key that is equal for a commit and its rewritten copy in another repo."""
        return (self.email, self.author_ts, self.subject)

    @property
    def churn(self) -> int:
        """Changed lines (ins+del) over all files."""
        return sum(f.ins + f.dels for f in self.files)


def _parse_files(tokens: list[str]) -> tuple[FileChange, ...]:
    """Turn the NUL-split numstat tokens of one commit into FileChanges."""
    files: list[FileChange] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i].lstrip("\n")
        i += 1
        if not tok:
            continue
        ins, dels, path = tok.split("\t", 2)
        if not path:  # rename: old and new path follow as their own tokens
            path = tokens[i + 1]
            i += 2
        binary = ins == "-"
        files.append(FileChange(path, 0 if binary else int(ins), 0 if binary else int(dels), binary))
    return tuple(files)


def parse_log(raw: bytes) -> list[Commit]:
    """Parse the output of `git log --numstat -z --format=FORMAT`."""
    commits: list[Commit] = []
    for record in raw.decode(errors="replace").split("\x1e")[1:]:
        header, _, body = record.partition("\0")
        sha, ts, email, author_ts, subject = header.split("\x1f", 4)
        files = _parse_files(body.split("\0"))
        commits.append(Commit(sha, int(ts), email.lower(), files, int(author_ts), subject))
    return commits


def read_commits(repo: Path, refs: Sequence[str], since_ts: int) -> list[Commit]:
    """Non-merge commits reachable from any of `refs`, committed at or after `since_ts`."""
    since = datetime.fromtimestamp(since_ts, UTC).isoformat()
    raw = git(repo, "log", *refs, "--no-merges", f"--since={since}", "--numstat", "-z",
              f"--format={FORMAT}", "--")
    return [c for c in parse_log(raw) if c.ts >= since_ts]
