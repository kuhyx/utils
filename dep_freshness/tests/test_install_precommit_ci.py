"""The fourth install piece: teaching an existing pre-commit workflow the gate.

These assertions are about a failure that is invisible locally -- the delegate
resolves through `~/utils` on this machine and through nothing at all on a
runner -- so they check the runner-visible facts: that the shared repo is
checked out, that `UTILS_ROOT` points at it, and that the insert lands after
the workflow's own checkout rather than before it.
"""

from __future__ import annotations

import pytest

from dep_freshness import install as installer
from dep_freshness import install_precommit_ci as ci
from dep_freshness.tests.conftest import write

BARE_WORKFLOW = """\
name: pre-commit

on: [push]

jobs:
  pre-commit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - uses: pre-commit/action@v3.0.1
"""


def test_a_repo_with_no_precommit_workflow_is_left_alone(repo):
    assert ci.needs_patch(repo) is False
    assert ci.patch(repo) is False
    assert not (repo / ci.PRECOMMIT_WORKFLOW).exists()


def test_a_bare_workflow_gains_the_checkout_and_the_env_var(repo):
    write(repo, str(ci.PRECOMMIT_WORKFLOW), BARE_WORKFLOW)

    assert ci.needs_patch(repo) is True
    assert ci.patch(repo) is True

    body = (repo / ci.PRECOMMIT_WORKFLOW).read_text(encoding="utf-8")
    assert "repository: kuhyx/utils" in body
    assert "path: .utils" in body
    assert "UTILS_ROOT=$GITHUB_WORKSPACE/.utils" in body


def test_the_insert_lands_after_the_workflows_own_checkout(repo):
    write(repo, str(ci.PRECOMMIT_WORKFLOW), BARE_WORKFLOW)
    ci.patch(repo)

    lines = (repo / ci.PRECOMMIT_WORKFLOW).read_text(encoding="utf-8").split("\n")
    own = lines.index("      - uses: actions/checkout@v4")
    shared = lines.index("      - name: Check out the shared gates")
    action = lines.index("      - uses: pre-commit/action@v3.0.1")
    assert own < shared < action, "$GITHUB_WORKSPACE must exist before .utils lands"


def test_a_second_run_writes_nothing(repo):
    write(repo, str(ci.PRECOMMIT_WORKFLOW), BARE_WORKFLOW)
    ci.patch(repo)
    once = (repo / ci.PRECOMMIT_WORKFLOW).read_text(encoding="utf-8")

    assert ci.needs_patch(repo) is False
    assert ci.patch(repo) is False
    assert (repo / ci.PRECOMMIT_WORKFLOW).read_text(encoding="utf-8") == once


def test_a_workflow_with_no_checkout_refuses_rather_than_guessing(repo):
    write(
        repo,
        str(ci.PRECOMMIT_WORKFLOW),
        "name: pre-commit\njobs:\n  pre-commit:\n    steps:\n"
        "      - uses: pre-commit/action@v3.0.1\n",
    )
    with pytest.raises(ValueError, match="no `- uses: actions/checkout@v4` step"):
        ci.patch(repo)


def test_the_installer_reports_the_patch_as_a_fourth_piece(repo):
    write(repo, str(ci.PRECOMMIT_WORKFLOW), BARE_WORKFLOW)

    expected = f"{ci.PRECOMMIT_WORKFLOW} (shared-gate checkout)"
    assert expected in installer.plan(repo)
    assert expected in installer.install(repo)
    assert installer.install(repo) == []
