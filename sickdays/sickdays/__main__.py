# Copyright (c) 2026 Krzysztof Rudnicki
"""``python -m sickdays``: the same command as the ``sickdays`` script."""

from __future__ import annotations

import sys

from sickdays._cli import main

sys.exit(main())
