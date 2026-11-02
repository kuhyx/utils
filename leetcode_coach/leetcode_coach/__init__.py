"""The /leetcode coach: Claude skill, print-mode REPL, offline coach, card builder.

Moved here from ``~/.claude/skills/leetcode`` (2026-10-23), which is now a
symlink to this directory, so SKILL.md still loads from the old path.

The NullHandler keeps the warnings that every swallowing ``except`` logs
(repo rule) from reaching stderr through logging's last-resort handler: the
REPL, the card builder and the Stop hook print exactly what they printed
before the move. A caller that configures logging still sees them.
"""

import logging

logging.getLogger(__name__).addHandler(logging.NullHandler())
