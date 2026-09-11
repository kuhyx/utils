# Copyright (c) 2026 Krzysztof Rudnicki
"""``python -m music_theory`` entry point."""

from __future__ import annotations

import sys

from music_theory.cli import main

if __name__ == "__main__":
    sys.exit(main())
