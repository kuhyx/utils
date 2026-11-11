# Copyright (c) 2026 Krzysztof Rudnicki
"""Which X windows are known system credential prompts.

Incident 2026-11-11: at login the GNOME Keyring unlock prompt (``gcr-prompter``)
took the X keyboard and pointer grab ~1 s before a lock armed. The lock's
override-redirect windows then covered the prompt, so the grab could never be
taken and nothing on screen could be clicked. Yielding to *these* windows --
and only these -- is the one deliberate exception to "the lock is always on
top"; anything else holding the grab (a fullscreen game) stays covered.
"""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterable

SYSTEM_PROMPT_CLASSES: Final = (
    "gcr-prompter",
    "pinentry*",
    "polkit-gnome-authentication-agent-1",
    "lxpolkit",
    "ssh-askpass*",
    "x11-ssh-askpass",
    "ksshaskpass",
    "gnome-ssh-askpass",
)
"""``fnmatch`` patterns, lowercase, matched against WM_CLASS instance or class."""


@dataclass(frozen=True)
class PromptWindow:
    """A mapped system prompt: the client and the ancestor below the root.

    Attributes:
        window_id: The client window that carries the WM_CLASS.
        toplevel_id: Its ancestor that is a direct child of the root. Under a
            reparenting window manager (i3) that is the WM's frame, and it is
            the window whose stacking position matters.
        wm_class: The ``(instance, class)`` pair.
    """

    window_id: int
    toplevel_id: int
    wm_class: tuple[str, str]

    @property
    def name(self) -> str:
        """The WM_CLASS instance, for log lines."""
        return self.wm_class[0]


def is_system_prompt(wm_class: Iterable[str]) -> bool:
    """Whether a WM_CLASS (instance or class, any case) is an allowlisted prompt."""
    return any(
        fnmatchcase(part.lower(), pattern)
        for part in wm_class
        for pattern in SYSTEM_PROMPT_CLASSES
    )
