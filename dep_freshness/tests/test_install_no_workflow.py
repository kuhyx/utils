"""The per-repo opt-out from the CI workflow (`.dep-freshness-no-workflow`).

A repo that runs the gate only locally (teatr-pw: no GitHub Actions minutes)
deletes `.github/workflows/dependency-freshness.yml` on purpose. Without an
opt-out the next fleet sweep puts it back, so the marker must stop the
installer from creating OR rewriting it -- and must not stop anything else.
"""

from __future__ import annotations

from dep_freshness import install as installer
from dep_freshness.tests.conftest import write

MARKER = ".dep-freshness-no-workflow"
WORKFLOW = ".github/workflows/dependency-freshness.yml"


def test_the_marker_path_is_the_documented_one():
    assert str(installer.NO_WORKFLOW_MARKER) == MARKER


def test_an_opted_out_repo_gets_the_local_pieces_but_no_workflow(repo):
    write(repo, MARKER, "# no GitHub Actions here\n")

    assert installer.install(repo) == [
        "scripts/check_dependency_freshness.sh",
        ".pre-commit-config.yaml (dependency-freshness hook)",
    ]
    assert not (repo / WORKFLOW).exists()
    assert not (repo / ".github").exists()


def test_plan_does_not_report_the_workflow_as_missing(repo):
    write(repo, MARKER, "")

    assert WORKFLOW not in installer.plan(repo)
    installer.install(repo)
    assert installer.plan(repo) == []
    assert installer.install(repo) == []


def test_an_existing_drifted_workflow_is_left_as_it_is(repo):
    """Opted out means hands off: no create, no rewrite, no delete."""
    write(repo, MARKER, "")
    write(repo, WORKFLOW, "name: kept by hand\n")

    assert WORKFLOW not in installer.install(repo)
    assert (repo / WORKFLOW).read_text(encoding="utf-8") == "name: kept by hand\n"


def test_without_the_marker_the_workflow_is_still_installed(repo):
    assert WORKFLOW in installer.install(repo)
    assert (repo / WORKFLOW).is_file()
