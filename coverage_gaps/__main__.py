"""`python3 -m coverage_gaps` -- the entrypoint the `coverage-gaps` wrapper calls."""

from coverage_gaps.cli import main

raise SystemExit(main())
