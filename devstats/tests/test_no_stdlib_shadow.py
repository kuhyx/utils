"""No devstats module may share a stdlib module's name.

`python -m devstats` run from inside `devstats/` puts that dir first on
sys.path, so a `devstats/html.py` replaced the stdlib `html` for every import.
"""

from __future__ import annotations

import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]


def test_no_module_shadows_the_stdlib() -> None:
    clashes = sorted(p.name for p in PACKAGE.glob("*.py") if p.stem in sys.stdlib_module_names)
    assert clashes == []
