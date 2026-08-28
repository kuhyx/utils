"""The toolchain versions a CI runner actually installs.

`.fvmrc` is a declaration nothing in this fleet reads; `subosito/flutter-action`
takes its own `flutter-version:`, and that is what the runner gets. When the
two disagree the failure is green-locally / red-in-CI with no diff to explain
it -- kuhylog's runner was on Flutter 3.44.9, which predates the
`@awaitNotRequired` annotation, so the same code was a violation there and
clean here.
"""

from __future__ import annotations

from dep_freshness import discover
from dep_freshness.parsers import workflow
from dep_freshness.tests.conftest import write

CI = """\
name: ci
on:
  push:
    branches: [main]
jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: subosito/flutter-action@v2
        with:
          flutter-version: 3.44.9
          channel: stable
      - uses: actions/setup-node@v4
        with:
          node-version: '24.18.0'
"""


def _path(repo):
    return repo / ".github/workflows/ci.yml"


def test_a_workflow_pin_is_a_toolchain_dependency(repo):
    deps = {
        d.name: d for d in workflow.parse(write(repo, ".github/workflows/ci.yml", CI))
    }
    assert deps["flutter"].pinned == "3.44.9"
    assert deps["flutter"].line == 12
    assert deps["node"].pinned == "24.18.0"
    assert deps["node"].ecosystem == "toolchain"


def test_a_channel_name_is_not_a_version(repo):
    body = CI.replace("flutter-version: 3.44.9", "flutter-version: stable")
    names = [
        d.name for d in workflow.parse(write(repo, ".github/workflows/ci.yml", body))
    ]
    assert "flutter" not in names, "a channel tells the gate nothing to compare"


def test_a_runtime_expression_is_skipped_rather_than_guessed(repo):
    body = CI.replace("flutter-version: 3.44.9", "flutter-version: ${{ env.FLUTTER }}")
    names = [
        d.name for d in workflow.parse(write(repo, ".github/workflows/ci.yml", body))
    ]
    assert "flutter" not in names


def test_an_unreadable_workflow_yields_nothing(repo):
    assert workflow.parse(repo / ".github/workflows/gone.yml") == []


def test_only_files_under_github_workflows_count(repo):
    assert workflow.is_workflow(_path(repo))
    assert workflow.is_workflow(repo / ".github/workflows/ci.yaml")
    assert not workflow.is_workflow(repo / ".github/ci.yml")
    assert not workflow.is_workflow(repo / "workflows/ci.yml")
    assert not workflow.is_workflow(repo / ".github/workflows/notes.md")


def test_discovery_routes_a_workflow_to_the_workflow_parser(repo):
    path = write(repo, ".github/workflows/ci.yml", CI)
    assert discover.is_manifest(path)
    assert {d.name for d in discover.parse_manifest(path)} == {"flutter", "node"}
    assert path in discover.find_manifests(repo)
