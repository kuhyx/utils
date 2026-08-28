"""The toolchain versions a CI runner actually installs.

`.fvmrc` is a declaration nothing in this fleet reads; `subosito/flutter-action`
takes its own `flutter-version:`, and that is what the runner gets. When the
two disagree the failure is green-locally / red-in-CI with no diff to explain
it -- kuhylog's runner was on Flutter 3.44.9, which predates the
`@awaitNotRequired` annotation, so the same code was a violation there and
clean here. `actions/setup-python` did the same to testsAndMisc on 2026-08-28.
"""

from __future__ import annotations

from dep_freshness import discover
from dep_freshness._tables import MATRIX
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


def _parse(repo, body):
    return workflow.parse(write(repo, ".github/workflows/ci.yml", body))


def _names(repo, body):
    return [d.name for d in _parse(repo, body)]


def test_a_workflow_pin_is_a_toolchain_dependency(repo):
    deps = {d.name: d for d in _parse(repo, CI)}
    assert deps["flutter"].pinned == "3.44.9"
    assert deps["flutter"].line == 12
    assert deps["node"].pinned == "24.18.0"
    assert deps["node"].ecosystem == "toolchain"


def test_a_channel_name_is_not_a_version(repo):
    body = CI.replace("flutter-version: 3.44.9", "flutter-version: stable")
    assert "flutter" not in _names(repo, body), "a channel gives nothing to compare"


def test_a_runtime_expression_is_skipped_rather_than_guessed(repo):
    body = CI.replace("flutter-version: 3.44.9", "flutter-version: ${{ env.FLUTTER }}")
    assert "flutter" not in _names(repo, body)


def test_a_setup_python_pin_is_a_toolchain_dependency(repo):
    """testsAndMisc went red because its runner was still on 3.11.

    Its pins had moved to numpy 2.5.2, which declares >=3.12. Nothing local
    could see it: the gate judged the interpreter in the shell, never the one
    `actions/setup-python` installs.
    """
    body = CI + '          python-version: "3.11"\n'
    deps = {d.name: d for d in _parse(repo, body)}
    assert deps["python"].pinned == "3.11"
    assert deps["python"].ecosystem == "toolchain"


def test_a_wildcard_has_nothing_to_compare(repo):
    """`3.x` already resolves to newest stable, so it cannot drift behind."""
    for value in ('"3.x"', '"24.x"', '"x"'):
        body = CI + f"          python-version: {value}\n"
        assert "python" not in _names(repo, body), value


def test_an_inline_matrix_is_reported_rather_than_bumped(repo):
    """One version per repo, always newest: a matrix is deleted, not raised."""
    body = CI + '        python-version: ["3.10", "3.11", "3.12"]\n'
    deps = {d.name: d for d in _parse(repo, body)}
    assert deps["python"].constraint == MATRIX
    assert deps["python"].pinned is None


def test_a_block_list_matrix_is_caught_too(repo):
    """The long form declares no value on the line; the list is beneath it."""
    body = CI + "        python-version:\n          - '3.10'\n          - '3.11'\n"
    deps = {d.name: d for d in _parse(repo, body)}
    assert deps["python"].constraint == MATRIX


def test_an_inline_mapping_pin_is_found(repo):
    """build_your_x writes `with: {python-version: "3.12"}` on one line."""
    body = CI + '        with: {python-version: "3.12"}\n'
    deps = {d.name: d for d in _parse(repo, body)}
    assert deps["python"].pinned == "3.12"


def test_a_trailing_comment_is_not_part_of_the_version(repo):
    body = CI + '          python-version: "3.12"  # oldest supported\n'
    deps = {d.name: d for d in _parse(repo, body)}
    assert deps["python"].pinned == "3.12"


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
