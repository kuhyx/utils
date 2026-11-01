# utils

Monorepo of shared gates and libraries (dep_freshness, file_length, md_naming,
repo_contract, coverage_gaps, crdt-sync, gatelock, freedays, sickdays, earned_time, music_theory,
flutter_web_drive (headless Flutter-web E2E driver + MCP), ...).
Python packages with a root-level `<pkg>/tests` run with `PYTHONPATH=.`;
subprojects with their own `pyproject.toml` run via `scripts/run_subproject_tests.sh <dir>`.
`scripts/check_repo_contract.sh` is the REAL shared gate (not a shim): never
overwrite it with `repo_contract/templates/check_repo_contract.shim.sh`.

## Commands

- run: n/a: collection of gates and libraries, no single entry point
- test: `PYTHONPATH=. python -m pytest -q agent_ready/tests coverage_gaps/tests dep_freshness/tests file_length/tests flutter_web_drive/tests home_paths/tests md_naming/tests repo_contract/tests scripts/tests unified-design-system/tests`
- test-changed: `scripts/test_changed.sh`
- lint: `ruff check agent_ready coverage_gaps flutter_web_drive repo_contract`
- coverage: `PYTHONPATH=. python -m pytest -q agent_ready/tests flutter_web_drive/tests repo_contract/tests unified-design-system/tests --cov=agent_ready --cov=flutter_web_drive --cov=repo_contract --cov=conformance --cov=conformance_diff --cov-branch --cov-report=xml --cov-fail-under=100`
- coverage-gaps: `coverage-gaps coverage.xml`
