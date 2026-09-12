# Copyright (c) 2026 Krzysztof Rudnicki
"""Loading the optional ``python-xlib`` dependency, in one place.

``python-xlib`` is optional: without it, output detection falls back to Tk
``<Configure>`` events plus ``xrandr`` polling. The fallback is the path that
must stay tested, and a module-scope ``try/except ImportError`` would resolve
it once at import time, leaving the ``except`` arm permanently unreachable for
branch coverage. So the modules are loaded on demand, through :mod:`importlib`,
by the two call sites that need them.
"""

from __future__ import annotations

import importlib
from types import ModuleType


def load_xlib(*names: str) -> tuple[ModuleType, ...] | None:
    """Import the named ``Xlib`` modules, or None if python-xlib is unavailable.

    Args:
        names: Fully-qualified module names, e.g. ``"Xlib.display"``.

    Returns:
        The modules in the order asked for, or None on the first ImportError.
    """
    try:
        return tuple(importlib.import_module(name) for name in names)
    except ImportError:
        return None
