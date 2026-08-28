"""Shared dependency-freshness gate: every dep on newest stable, mechanically.

Entry point is `scripts/check_dependency_freshness.sh`; the logic lives here so
the gate, the CI workflow and the SessionStart hook all read one implementation
instead of hand-replicated copies (see the four-way fork of the 250-line cap).
"""
