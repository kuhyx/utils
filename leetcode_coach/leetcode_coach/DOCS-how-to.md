# The commands and the method, as the status app's Coach tab shows them

Quoted verbatim from `how_to.py`; `tests/test_how_to.py` fails if they differ.
SKILL.md section 3 is the full method; this is its one-line-per-step form.

Commands:

- `leetcode --cluster <name>` - Serve the next problem of a concept cluster (a due re-test comes first).
- `leetcode <url>` - Coach one problem, from its LeetCode URL or slug.
- `leetcode due` - List the cold re-tests that are due.
- `leetcode report` - One row per session: requirements before code, hint rung, reveal.

The command skips problems LeetCode already shows as Accepted, so it may serve a later one than listed here.

The method:

1. **Constraint** - Turn the hard constraint into a rule for the design.
2. **Requirements** - List what the operation must do, as properties, never by name.
3. **Toolbox** - Search the toolbox for an operation with those properties.
4. **Post-mortem** - Say which hint gave which requirement, then make the cards.
