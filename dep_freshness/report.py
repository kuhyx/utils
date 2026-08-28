"""Human and machine output. No decisions are made here.

The loud exception block prints on success *as well as* failure (Q17): an
exception the user stops seeing is a suppression, and the whole point of the
allowlist is that every not-latest pin stays visible.
"""

from __future__ import annotations

from datetime import date, datetime
import json
from pathlib import Path
import sys

from dep_freshness.models import Exception_, Finding, Severity

def _err(stream):
    """Resolve stderr at call time.

    A `stream=sys.stderr` default binds the stream at import, which silently
    bypasses anything that replaces it later -- pytest's capture, and any
    caller redirecting output.
    """
    return sys.stderr if stream is None else stream


_HEADLINE = {
    Severity.STALE: "behind latest stable",
    Severity.UNPINNED: "not exact-pinned",
    Severity.LOCK_MISMATCH: "manifest and lockfile disagree",
    Severity.OVERRIDE: "dependency override",
    Severity.UNKNOWN: "could not be determined",
}


def _where(finding: Finding, root: Path) -> str:
    try:
        rel = finding.dep.path.relative_to(root)
    except ValueError:
        rel = finding.dep.path
    return f"{rel}:{finding.dep.line}" if finding.dep.line else str(rel)


def _days_left(expires: str) -> int | None:
    try:
        return (datetime.strptime(expires, "%Y-%m-%d").date() - date.today()).days
    except ValueError:
        return None


def exceptions_block(
    entries: list[Exception_], still_blocking: dict[str, bool], stream=None
) -> None:
    """The always-printed banner naming every exception currently in force."""
    if not entries:
        return
    stream = _err(stream)
    print(f"\n⚠️  DEPENDENCY EXCEPTION IN USE — {len(entries)} active", file=stream)
    for entry in entries:
        print(f"  {entry.package} {entry.pinned} ({entry.ecosystem})", file=stream)
        if entry.transitive:
            state = "still blocking" if still_blocking.get(
                f"{entry.ecosystem}:{entry.package}", True) else "CLEARED"
            print(f"    blocked_by: {entry.blocked_by}  [{state}]", file=stream)
        else:
            left = _days_left(entry.expires or "")
            suffix = f"expires in {left} days" if left is not None else "expires"
            print(f"    blocked_by: {entry.blocked_by}   {suffix}", file=stream)
        print(f"    reason: {entry.reason}", file=stream)


def machine_lines(entries: list[Exception_]) -> list[str]:
    """Plain-ASCII `[DEP-EXCEPTION]` lines for the SessionStart hook and CI logs."""
    out = []
    for entry in entries:
        head = (f"[DEP-EXCEPTION] {entry.ecosystem}:{entry.package} {entry.pinned}")
        if entry.latest_known:
            head += f" < {entry.latest_known}"
        if entry.transitive:
            out.append(f"{head} blocked_by={entry.blocked_by} [still blocking]")
        else:
            left = _days_left(entry.expires or "")
            days = f" ({left}d)" if left is not None else ""
            out.append(f"{head} expires {entry.expires}{days}")
    return out


def violations(findings: list[Finding], root: Path, stream=None) -> None:
    """The failure body: every finding, grouped by why it failed."""
    stream = _err(stream)
    print(
        f"\nDependency-freshness gate FAILED: {len(findings)} finding(s)\n",
        file=stream,
    )
    for severity in Severity:
        group = [f for f in findings if f.severity is severity]
        if not group:
            continue
        print(f"  {_HEADLINE[severity]}:", file=stream)
        for finding in sorted(group, key=lambda f: (str(f.dep.path), f.dep.name)):
            current = finding.dep.pinned or finding.dep.constraint
            latest = f" -> {finding.latest}" if finding.latest else ""
            print(
                f"    {finding.dep.ecosystem}:{finding.dep.name} "
                f"{current}{latest}   {_where(finding, root)}",
                file=stream,
            )
            if finding.detail:
                print(f"        {finding.detail}", file=stream)
        print("", file=stream)
    print(
        "Bump them to latest stable, or record an exception in "
        "dependency-freshness.allowlist.yaml with reason + blocked_by.",
        file=stream,
    )


def degraded(reasons: list[str], stream=None) -> None:
    stream = _err(stream)
    print(
        "\nDEGRADED: dependency freshness unverified (offline) — "
        f"{len(reasons)} lookup(s) served from cache or skipped.",
        file=stream,
    )
    for reason in reasons[:5]:
        print(f"  {reason}", file=stream)


def as_json(
    findings: list[Finding], entries: list[Exception_], exit_code: int
) -> str:
    payload = {
        "exit_code": exit_code,
        "findings": [
            {
                "ecosystem": f.dep.ecosystem,
                "package": f.dep.name,
                "severity": f.severity.value,
                "current": f.dep.pinned or f.dep.constraint,
                "latest": f.latest,
                "path": str(f.dep.path),
                "line": f.dep.line,
                "detail": f.detail,
                "excused": f.excused,
            }
            for f in findings
        ],
        "exceptions": [
            {
                "ecosystem": e.ecosystem,
                "package": e.package,
                "pinned": e.pinned,
                "blocked_by": e.blocked_by,
                "expires": e.expires,
                "reason": e.reason,
                "transitive": e.transitive,
            }
            for e in entries
        ],
    }
    return json.dumps(payload, indent=2)
