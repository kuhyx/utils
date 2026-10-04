#!/bin/bash

# ============================================================================
# Run only the tests related to files changed vs HEAD (staged, unstaged and
# untracked). Quiet: failures plus a one-line summary. Maps a change to its
# top-level directory: `<dir>/tests` runs with PYTHONPATH=., a subproject with
# its own pyproject.toml runs via scripts/run_subproject_tests.sh. Anything
# unmappable falls back to the shared-gate suites.
# ============================================================================

set -euo pipefail

cd "$(git rev-parse --show-toplevel)"
CHANGED=()
while IFS= read -r f; do
    [[ -n "$f" && -e "$f" ]] && CHANGED+=("$f")
done < <({ git diff --name-only HEAD 2>/dev/null || true; git ls-files --others --exclude-standard; } | sort -u)

readonly GATES=(coverage_gaps dep_freshness file_length home_paths md_naming repo_contract)
dirs=()
unmapped=0
for f in "${CHANGED[@]}"; do
    d="${f%%/*}"
    case "$f" in
        *.py | *.sh | *.yaml | *.yml | *.toml | *.json) ;;
        *) continue ;;
    esac
    if [[ "$d" == "$f" ]]; then unmapped=1; continue; fi
    if [[ -d "$d/tests" || -f "$d/pyproject.toml" ]]; then dirs+=("$d"); else unmapped=1; fi
done
mapfile -t dirs < <(printf '%s\n' "${dirs[@]}" | sort -u)

if [[ ${#CHANGED[@]} -eq 0 ]]; then echo "no changes vs HEAD: nothing to test"; exit 0; fi
if [[ ${#dirs[@]} -eq 0 && $unmapped -eq 0 ]]; then echo "no code changes: nothing to test"; exit 0; fi

rc=0
if [[ ${#dirs[@]} -eq 0 ]]; then
    echo "no mapped tests: running shared-gate suites"
    dirs=("${GATES[@]}")
fi
for d in "${dirs[@]}"; do
    if [[ -f "$d/pyproject.toml" ]]; then
        scripts/run_subproject_tests.sh "$d" -q --tb=short || rc=$?
    elif [[ -d "$d/tests" ]]; then
        PYTHONPATH=. python3 -m pytest -q --tb=short "$d/tests" || rc=$?
    fi
done
exit $rc
