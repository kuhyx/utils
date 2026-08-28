"""Give a repo's `pre-commit` CI workflow the shared-gate checkout it needs.

The fourth piece of the install, and the one that is easy to forget because
nothing local reveals it: `.pre-commit-config.yaml` gains a hook that execs
`scripts/check_dependency_freshness.sh`, which delegates to `~/utils`. That
path exists on this machine and does not exist on a runner, so a repo whose
`pre-commit` workflow runs `pre-commit/action` against a bare checkout goes red
with "shared gate not found at /home/runner/utils/..." -- green locally, red in
CI, with no diff that explains it. screen-locker, wake-alarm and diet-guard
each hit it and each got the same twelve lines pasted in by hand.

Only repos that HAVE such a workflow are touched; the dedicated
`dependency-freshness.yml` already carries its own checkout.
"""

from __future__ import annotations

from pathlib import Path

PRECOMMIT_WORKFLOW = Path(".github/workflows/pre-commit.yml")
MARKER = "UTILS_ROOT"
CHECKOUT = "- uses: actions/checkout@v4"

PATCH = """\

      # Hooks here delegate to the shared gates in kuhyx/utils. Without this
      # checkout they exit 1 with "shared gate not found at
      # /home/runner/utils/..." -- green locally, red on every runner.
      - name: Check out the shared gates
        uses: actions/checkout@v4
        with:
          repository: kuhyx/utils
          path: .utils
      - name: Point the delegates at that checkout
        run: echo "UTILS_ROOT=$GITHUB_WORKSPACE/.utils" >> "$GITHUB_ENV"\
"""


def needs_patch(repo: Path) -> bool:
    """True when a pre-commit workflow exists and cannot find the shared gate."""
    target = repo / PRECOMMIT_WORKFLOW
    if not target.is_file():
        return False
    return MARKER not in target.read_text(encoding="utf-8")


def patch(repo: Path) -> bool:
    """Insert the checkout after the workflow's own `actions/checkout`.

    Inserting after the repo's own checkout rather than at the top of `steps:`
    keeps `$GITHUB_WORKSPACE` populated before `.utils` lands inside it, and
    leaves every surrounding comment intact -- a YAML round-trip would drop
    the ones explaining why each hook is there.
    """
    if not needs_patch(repo):
        return False
    target = repo / PRECOMMIT_WORKFLOW
    lines = target.read_text(encoding="utf-8").split("\n")
    anchors = [n for n, line in enumerate(lines) if line.strip() == CHECKOUT]
    if not anchors:
        raise ValueError(
            f"{target} has no `{CHECKOUT}` step to insert after; "
            "add the shared-gate checkout by hand, then re-run"
        )
    lines[anchors[0] + 1 : anchors[0] + 1] = PATCH.split("\n")
    target.write_text("\n".join(lines), encoding="utf-8")
    return True
