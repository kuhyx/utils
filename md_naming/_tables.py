"""Exemption tables and namespace rules for the markdown-naming convention.

The data half: which basenames are reserved by external tooling, which
directory trees are exempt, and the literal marker every TODO file carries.
:mod:`md_naming.rules` holds the predicates that read these, and
:mod:`md_naming.config` re-exports both as the public surface.

Deliberately built on top of :mod:`file_length._tables` for the shared notions
of "excluded dir", "third-party repo" and "vendored tree". Restating those
here is exactly what lets two gates disagree about the same file.
"""

from __future__ import annotations

import re

#: The four namespaces. A markdown file in a kuhy-owned repo must match one.
#:
#: README  -- what this directory is and how to run it.
#: CLAUDE* -- instructions Claude must read.
#: DOCS*   -- reference, findings, design records. Permanent.
#: TODO*   -- outstanding work. Carries MARKER; deleted when the work lands.
ALLOWED_PATTERN = re.compile(r"^(README|CLAUDE.*|DOCS.*|TODO.*)\.(md|markdown)$")

#: The literal every TODO file must contain, and that no other file may.
#: CI greps this exact string, so it cannot be paraphrased.
MARKER = "REMOVE ME AFTER FINISH"

#: Prefix identifying a task file, for the reverse check (marker => TODO*).
TODO_PREFIX = "TODO"

#: A TODO older than this many days gets a CI ::warning::. Never a failure:
#: no machine can prove a task is finished, so the honest mechanism is a nudge.
STALE_DAYS = 90

#: Basenames owned by external tooling. Renaming these breaks the tool, so
#: they are exempt from the namespace rule rather than migrated.
#:
#: SKILL.md          -- the skill loader requires the literal filename.
#: CLAUDE/AGENTS     -- auto-loaded by the harness.
#: copilot-*         -- read by GitHub Copilot.
HARNESS_NAMES = frozenset(
    {
        "SKILL.md",
        "CLAUDE.md",
        "AGENTS.md",
        "copilot-instructions.md",
    }
)

#: Community-health and license-compliance names. GitHub keys off these exact
#: filenames to surface contributing/security UI; CREDITS and ATTRIBUTION also
#: back the standing "always attribute assets" rule, so renaming them would
#: quietly weaken an unrelated guarantee.
COMMUNITY_NAMES = frozenset(
    {
        "CONTRIBUTING.md",
        "SECURITY.md",
        "CODE_OF_CONDUCT.md",
        "CHANGELOG.md",
        "NOTICE.md",
        "CREDITS.md",
        "ATTRIBUTION.md",
        "THIRD_PARTY_NOTICES.md",
        "LICENSE.md",
        "ISSUE_TEMPLATE.md",
        "PULL_REQUEST_TEMPLATE.md",
        "BRANCH_PROTECTION.md",
    }
)

#: Directory fragments whose markdown is machine-managed or vendored, wherever
#: they appear. `.github/` holds templates GitHub names itself; the rest are
#: agent-memory and skill-bundle trees dropped in from elsewhere.
EXEMPT_SUBPATHS = (
    "/.github/",
    "/.projectmem/",
    "/.hippo/",
    "/.agents/",
    "/.claude/",
    "/ios/Runner/",
    "/android/app/src/",
)

#: Repos under ~ that are clones of other people's work, in addition to the
#: shared THIRD_PARTY_REPOS list. A dated backup clone is not a live repo.
EXTRA_THIRD_PARTY = frozenset(
    {
        # Dotfile clones of other people's projects. These live outside ~/*/
        # so a survey that walks only project dirs misses them -- the 2026-08-24
        # migration renamed 5 files in nvm and ohmyzsh before this was added.
        ".nvm",
        ".oh-my-zsh",
        ".cargo",
        ".rustup",
        ".pyenv",
        ".fzf",
        ".tmux",
        "screen-locker-backup-20260705-200741",
        "flax-editor",
        "flax-mcp-test",
        "diet-guard-peer-backup",
        "claude_refactor_staging",
    }
)
