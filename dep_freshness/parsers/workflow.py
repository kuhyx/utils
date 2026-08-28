"""`.github/workflows/*.yml` -> the toolchain versions CI actually builds with.

`.fvmrc` declares the SDK, but nothing in this fleet reads it: `subosito/
flutter-action` takes its own `flutter-version:`, and that pin is what the
runner really installs. The two drift silently, and the failure mode is the
worst kind -- green locally, red in CI, with no diff to explain it. kuhylog
went red on `discarded_futures` for exactly this reason: the runner was on
Flutter 3.44.9, which predates the `@awaitNotRequired` annotation that makes
the same `unawaited(...)` call a violation on 3.47.2.

`actions/setup-python` is the same story and cost testsAndMisc a red run on
2026-08-28: `python-tests.yml` still said `python-version: "3.11"` while the
repo's pins had moved to `numpy 2.5.2`, which requires >=3.12. Nothing local
could see it -- the gate judged the interpreter in the shell, not the one the
runner installs.

So the CI pin is a dependency like any other, judged against the same latest
stable. Keeping both honest that way needs no separate "these must agree"
rule: two values both required to equal latest already agree.

**A version MATRIX is a finding, not a support range.** Standing decision
(kuhy, 2026-08-28): every repo runs EXACTLY ONE toolchain version and it is
always the newest. `python-version: ["3.10", "3.11", "3.12"]` is three answers
to a question that has one, and the two oldest are guaranteed to be behind. It
is reported so it gets deleted, not bumped.

Two things are skipped rather than guessed: a `${{ ... }}` expression, which
resolves at run time, and a wildcard like `3.x`, which `setup-python` already
resolves to the newest stable and therefore cannot drift. `3.x` is what the
fleet standardised on, so the common case makes zero registry calls.
"""

from __future__ import annotations

import re
from pathlib import Path

from dep_freshness._tables import MATRIX, TOOLCHAIN
from dep_freshness.models import Dep
from dep_freshness.versions import exact_pin

WORKFLOW_DIR = ".github/workflows"

# `flutter-version: 3.47.2`, `node-version: '24.18.0'`, quoted or not, and the
# inline-mapping form `with: {python-version: "3.12"}` that build_your_x uses.
_PIN = re.compile(
    r"""(?:^|[{,])\s*(?P<tool>flutter|node|python)-version:(?P<rest>.*)$"""
)
# A channel name is not a version, and `.fvmrc` already reports that case.
_NOT_A_VERSION = frozenset({"stable", "beta", "master", "main", "dev", "lts", "latest"})
# `3.x`, `24.x`, bare `x`: already "newest", so there is nothing to compare.
_WILDCARD = re.compile(r"^\d+(\.\d+)*\.x$|^x$")


def is_workflow(path: Path) -> bool:
    """True for a file inside a repo's `.github/workflows` directory."""
    return (
        path.suffix in (".yml", ".yaml")
        and path.parent.name == "workflows"
        and path.parent.parent.name == ".github"
    )


def _scalar(rest: str) -> str:
    """The bare version out of everything that can follow the colon.

    Handles the quoting, a trailing `}` from an inline mapping, and a trailing
    `# comment`. Returns "" when the line declares no value at all, which in
    YAML means a block list follows -- i.e. a matrix written the long way.
    """
    text = rest.split("#", 1)[0].strip().rstrip("}").strip()
    return text.strip("\"'")


def _dep(tool: str, value: str, path: Path, number: int) -> Dep | None:
    """The `Dep` for one `<tool>-version:` line, or None when unjudgeable."""
    if value.startswith("${{") or value in _NOT_A_VERSION or _WILDCARD.match(value):
        return None
    # An inline `[...]` list, or an empty value with a block list beneath it.
    matrix = value.startswith("[") or value == ""
    return Dep(
        ecosystem=TOOLCHAIN,
        name=tool,
        constraint=MATRIX if matrix else value,
        path=path,
        line=number,
        pinned=None if matrix else exact_pin(value),
    )


def parse(path: Path) -> list[Dep]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    deps: list[Dep] = []
    for number, line in enumerate(text.splitlines(), start=1):
        match = _PIN.search(line)
        if not match:
            continue
        dep = _dep(match.group("tool"), _scalar(match.group("rest")), path, number)
        if dep is not None:
            deps.append(dep)
    return deps
