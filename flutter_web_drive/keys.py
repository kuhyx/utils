"""Named keys the ``key`` verb can press."""

from __future__ import annotations

# name -> (key, code, windowsVirtualKeyCode, text). Text makes chromium emit
# the char event Flutter's text input listens for (Enter submits a field).
KEYS: dict[str, tuple[str, str, int, str]] = {
    "Enter": ("Enter", "Enter", 13, "\r"),
    "Escape": ("Escape", "Escape", 27, ""),
    "Tab": ("Tab", "Tab", 9, ""),
    "Backspace": ("Backspace", "Backspace", 8, ""),
    "Delete": ("Delete", "Delete", 46, ""),
    "Space": (" ", "Space", 32, " "),
    "ArrowUp": ("ArrowUp", "ArrowUp", 38, ""),
    "ArrowDown": ("ArrowDown", "ArrowDown", 40, ""),
    "ArrowLeft": ("ArrowLeft", "ArrowLeft", 37, ""),
    "ArrowRight": ("ArrowRight", "ArrowRight", 39, ""),
    "Home": ("Home", "Home", 36, ""),
    "End": ("End", "End", 35, ""),
    "PageUp": ("PageUp", "PageUp", 33, ""),
    "PageDown": ("PageDown", "PageDown", 34, ""),
}
