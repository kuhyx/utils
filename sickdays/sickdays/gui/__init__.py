# Copyright (c) 2026 Krzysztof Rudnicki
"""The Tk sick-day picker, and the switch panel other apps embed.

Kept out of :mod:`sickdays` on purpose: every headless gate imports
``sickdays`` once a minute, and none of them may pull in tkinter. Import
this module only from the ``sickdays gui`` command or an app that already
draws with Tk::

    from sickdays.gui import KeepPanel

    panel = KeepPanel(surface, today, on_saved=lambda entry: panel.destroy())
    panel.pack()

:class:`KeepPanel` is a plain ``tk.Frame`` (no root, no mainloop, no grab),
so it works in-process under another window's X grab. See its docstring for
what ``on_saved`` receives. :func:`run` opens the whole window.
"""

from __future__ import annotations

from sickdays.gui._panel import KeepPanel
from sickdays.gui._window import SickDaysApp, run

__all__ = ["KeepPanel", "SickDaysApp", "run"]
