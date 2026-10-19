# Copyright (c) 2026 Krzysztof Rudnicki
"""Whether a locker's X grab is ACTUALLY held, on disk, for any reader.

A claim is published *before* its window grabs, and leetcode-guard's study
mode releases the grab while the claim lives on -- so "a live claim exists" is
not "input is locked". :attr:`gatelock.Claim.grab_held` is the second answer,
and this module is how it is written and read.

**Rewritten in place, never replaced.** Liveness is the ``flock`` the owner
holds on its open claim file (see :mod:`gatelock._arbiter`). A temp file plus
``os.replace`` would swap in a fresh inode nobody has locked, and the next
reader would take its lock and reap it as dead. So the flip overwrites the
same inode through the owner's own descriptor: ``O_APPEND`` (the handle was
opened ``a+``) is cleared so ``pwrite`` lands at offset 0, and the new text is
space-padded to the current size so the file never shrinks -- a reader sees
the old document or the new one, never an empty or truncated one. JSON allows
trailing whitespace, so the padding parses.

**Never raises.** The flip runs inside grab and study-mode transitions; an
exception there would roll a lock back. A failed write is logged and the
in-memory claim still changes.
"""

from __future__ import annotations

import fcntl
import logging
import os
from typing import IO, TYPE_CHECKING, Final

from gatelock._claims import default_runtime_dir, live_claims

if TYPE_CHECKING:
    from pathlib import Path

    from gatelock._claims import Claim

_logger = logging.getLogger(__name__)

CLAIMS_DIRNAME: Final = "claims"


def rewrite_in_place(handle: IO[str] | None, text: str) -> bool:
    """Overwrite the flock-held file behind `handle` with `text`, same inode.

    Args:
        handle: The owner's open (and locked) claim or holder handle; None
            when the arbiter never published or has released.
        text: The new JSON document.

    Returns:
        Whether the file was rewritten.
    """
    if handle is None:
        return False
    try:
        handle.flush()
        fd = handle.fileno()
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, flags & ~os.O_APPEND)
        data = text.encode("utf-8")
        os.pwrite(fd, data.ljust(os.fstat(fd).st_size, b" "), 0)
    except (OSError, ValueError) as exc:
        _logger.warning("could not rewrite claim file in place: %s", exc)
        return False
    return True


def held_grabs(claims_dir: Path | None = None) -> tuple[Claim, ...]:
    """Every live claim whose X grab is actually held right now.

    Readable by root: the enforcer runs as root, where ``XDG_RUNTIME_DIR`` is
    unset and the default below resolves to root's own (empty) dir -- so root
    callers must pass the user's dir, ``/run/user/1000/gatelock/claims``.
    Dead owners' claims are reaped as a side effect, as in
    :func:`gatelock._claims.live_claims`.

    Args:
        claims_dir: Directory holding claim files; defaults to the one
            :class:`gatelock.Arbiter` publishes into for this user.

    Returns:
        Live claims with ``grab_held`` and a declared grab other than "none",
        in arbitration order.
    """
    directory = (
        claims_dir if claims_dir is not None else default_runtime_dir() / CLAIMS_DIRNAME
    )
    return tuple(c for c in live_claims(directory) if c.grab_held and c.grab != "none")
