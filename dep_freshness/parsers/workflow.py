"""`.github/workflows/*.yml` -> the toolchain versions CI actually builds with.

`.fvmrc` declares the SDK, but nothing in this fleet reads it: `subosito/
flutter-action` takes its own `flutter-version:`, and that pin is what the
runner really installs. The two drift silently, and the failure mode is the
worst kind -- green locally, red in CI, with no diff to explain it. kuhylog
went red on `discarded_futures` for exactly this reason: the runner was on
Flutter 3.44.9, which predates the `@awaitNotRequired` annotation that makes
the same `unawaited(...)` call a violation on 3.47.2.

So the CI pin is a dependency like any other, judged against the same latest
stable. Keeping both honest that way needs no separate "these must agree"
rule: two values both required to equal latest already agree.

A `${{ ... }}` expression is skipped -- it resolves at run time, and guessing
is worse than saying nothing.
"""

from __future__ import annotations

import re
from pathlib import Path

from dep_freshness._tables import TOOLCHAIN
from dep_freshness.models import Dep
from dep_freshness.versions import exact_pin

WORKFLOW_DIR = ".github/workflows"

# `flutter-version: 3.47.2`, `node-version: '24.18.0'`, quoted or not.
_PIN = re.compile(
    r"""^\s*(?P<tool>flutter|node)-version:\s*["']?(?P<value>[^"'#\s]+)["']?"""
)
# A channel name is not a version, and `.fvmrc` already reports that case.
_NOT_A_VERSION = frozenset({"stable", "beta", "master", "main", "dev", "lts", "latest"})


def is_workflow(path: Path) -> bool:
    """True for a file inside a repo's `.github/workflows` directory."""
    return (
        path.suffix in (".yml", ".yaml")
        and path.parent.name == "workflows"
        and path.parent.parent.name == ".github"
    )


def parse(path: Path) -> list[Dep]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    deps: list[Dep] = []
    for number, line in enumerate(text.splitlines(), start=1):
        match = _PIN.match(line)
        if not match:
            continue
        value = match.group("value")
        if value.startswith("${{") or value in _NOT_A_VERSION:
            continue
        deps.append(
            Dep(
                ecosystem=TOOLCHAIN,
                name=match.group("tool"),
                constraint=value,
                path=path,
                line=number,
                pinned=exact_pin(value),
            )
        )
    return deps
