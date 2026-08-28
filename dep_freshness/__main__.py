"""`python3 -m dep_freshness` — the entrypoint the shell wrapper calls.

Kept to three lines on purpose: a `if __name__ == "__main__"` guard inside
check.py is a branch no test can enter, and the honest way to keep the gate at
full coverage is to have no untestable branch rather than to suppress one.
"""

from dep_freshness.check import main

raise SystemExit(main())
