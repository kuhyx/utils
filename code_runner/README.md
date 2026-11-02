# code_runner

Runs a learner's solution (Python 3, JavaScript, TypeScript) against a problem statement's examples inside bubblewrap: no network, read-only `/usr`, scratch dir, CPU/memory/process/file/time limits.

```python
import code_runner as cr

statement = ...  # markdown from ~/.claude/skills/leetcode/fetch_problem.py
results = cr.run("python3", code, cr.extract_starter(statement), cr.parse_examples(statement))
```

`run(lang, code, starter, examples) -> list[CaseResult]` with `n, input, expected, actual, ok, stdout, error, ms`. One sandbox process per example. TypeScript runs through node's type stripping (no type check, no enums). Needs `bwrap`, `prlimit`, `/usr/bin/python3`, node >= 22.18. Install: `./install.sh`.
