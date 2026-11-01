"""Make ``scripts/`` importable: the folder name has a hyphen, so no package."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
