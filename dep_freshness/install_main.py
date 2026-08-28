"""`python3 -m dep_freshness.install_main` — the installer's entrypoint.

Three lines for the same reason as `__main__.py`: an `if __name__` guard
inside install_cli.py would be a branch no test can enter, and the honest way
to hold full coverage is to have no untestable branch rather than suppress one.
"""

from dep_freshness.install_cli import main

raise SystemExit(main())
