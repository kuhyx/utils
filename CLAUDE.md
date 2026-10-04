# utils

Monorepo of shared gates and libraries (dep_freshness, file_length, md_naming,
repo_contract, coverage_gaps, crdt-sync, gatelock, freedays, music_theory, ...).
Python packages with a root-level `<pkg>/tests` run with `PYTHONPATH=.`;
subprojects with their own `pyproject.toml` run via `scripts/run_subproject_tests.sh <dir>`.
`scripts/check_repo_contract.sh` is the REAL shared gate (not a shim): never
overwrite it with `repo_contract/templates/check_repo_contract.shim.sh`.

## Commands

- run: n/a: collection of gates and libraries, no single entry point
- test: `PYTHONPATH=. python -m pytest -q coverage_gaps/tests dep_freshness/tests file_length/tests home_paths/tests md_naming/tests repo_contract/tests`
- test-changed: `scripts/test_changed.sh`
- lint: `ruff check coverage_gaps repo_contract`
- coverage: `PYTHONPATH=. python -m pytest -q repo_contract/tests --cov=repo_contract --cov-branch --cov-report=xml --cov-fail-under=100`
- coverage-gaps: `coverage-gaps coverage.xml`
