"""A remote store that writes to two backends and reads from both.

Exists for the GitHub -> Firebase cutover: each app can move to Firebase
while still mirroring to the old repo, so rolling back is a constructor
change rather than a data recovery.

Mirrors ``crdt_sync_dart``'s ``lib/src/mirror_store.dart``; keep the two in
step.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, TypeVar

from crdt_sync._remote import RemoteSyncError

if TYPE_CHECKING:
    from collections.abc import Callable

    from crdt_sync._remote import RemoteStore

_logger = logging.getLogger(__name__)

# PEP 695 type parameters need Python 3.12; this package targets 3.10.
_T = TypeVar("_T")


class MirrorSyncClient:
    """Writes to both backends; reads from both, preferring the primary.

    **Reads consult both on purpose.** Each app spans two devices, and they
    cut over one at a time. If reads were primary-only, a migrated PC would
    never see an un-migrated phone's writes while still mirroring its own
    back -- silent one-directional convergence, with no error raised. Because
    :func:`crdt_sync.merge_logs` is commutative and idempotent, a union read
    costs nothing semantically and makes the cutover order irrelevant.

    Write asymmetry is deliberate too: the primary is authoritative, so a
    primary failure fails the tick (fail-closed), while a mirror failure is
    reported and otherwise tolerated. Once the mirror is retired, the old
    backend going away must not break sync.

    **Reads are resilient on BOTH sides; writes are not.** A read is only
    fail-closed when neither backend can answer. Reads used to call the
    primary unguarded, so a Firebase outage produced no data at all and the
    mirror was never consulted -- the union read silently degraded to nothing,
    contradicting the paragraph above. Writes keep the asymmetry: a write the
    primary did not accept has not happened, so it must fail the tick.
    """

    def __init__(
        self,
        primary: RemoteStore,
        mirror: RemoteStore,
        *,
        on_mirror_failure: Callable[[str, Exception], None] | None = None,
    ) -> None:
        """Wrap ``primary`` (authoritative) and ``mirror`` (best effort).

        Args:
            primary: The backend whose failures fail the tick.
            mirror: The backend kept in step but never allowed to fail a tick.
            on_mirror_failure: Notified when the mirror misbehaves. Defaults
                to a warning log -- a silent mirror failure would let the
                fallback rot unnoticed until the day it was needed.
        """
        self.primary = primary
        self.mirror = mirror
        self._on_mirror_failure = on_mirror_failure or _log_mirror_failure

    def list_directory(self, path: str) -> list[str]:
        """Return the union of both backends' entries under ``path``.

        A reachable primary that lists nothing is a real answer; a primary
        that *raises* is not. Reads are the half of this class that exists to
        be resilient, so a primary failure degrades to the mirror's entries
        rather than failing the read -- returning nothing because one side is
        down breaks the union promise exactly when the fallback is most
        needed. Only a failure on BOTH sides propagates, since then there is
        genuinely no answer to give.
        """
        primary_names = self._try_primary_read(
            f"list_directory {path}", lambda: self.primary.list_directory(path)
        )
        mirror_names = self._try_mirror(
            f"list_directory {path}", lambda: self.mirror.list_directory(path)
        )
        if primary_names is None and mirror_names is None:
            self._raise_both_failed(f"list_directory {path}")
        names = list(primary_names or [])
        seen = set(names)
        for name in mirror_names or []:
            if name not in seen:
                seen.add(name)
                names.append(name)
        return names

    def get_file_text(self, path: str) -> str | None:
        """Return ``path``'s text from the primary, else from the mirror.

        Absent from the primary means "this device has not migrated yet",
        not "no data" -- so it falls through rather than reporting nothing.
        A primary that *raises* falls through for the same reason (see
        :meth:`list_directory`); only a failure on both sides propagates.
        """
        try:
            text = self.primary.get_file_text(path)
        except RemoteSyncError as error:
            self._on_primary_read_failure(f"get_file_text {path}", error)
            mirror_text = self._try_mirror(
                f"get_file_text {path}", lambda: self.mirror.get_file_text(path)
            )
            if mirror_text is None:
                self._raise_both_failed(f"get_file_text {path}")
            return mirror_text
        if text is not None:
            return text
        return self._try_mirror(
            f"get_file_text {path}", lambda: self.mirror.get_file_text(path)
        )

    def put_file_text(self, path: str, text: str, *, message: str) -> None:
        """Write to the primary, then best-effort to the mirror.

        Raises:
            RemoteSyncError: If the *primary* write fails.
        """
        self.primary.put_file_text(path, text, message=message)
        self._try_mirror(
            f"put_file_text {path}",
            lambda: self.mirror.put_file_text(path, text, message=message),
        )

    def delete_file(self, path: str, *, message: str = "crdt_sync: delete") -> None:
        """Delete from the primary, then best-effort from the mirror.

        Raises:
            RemoteSyncError: If the *primary* delete fails.
        """
        self.primary.delete_file(path, message=message)
        self._try_mirror(
            f"delete_file {path}",
            lambda: self.mirror.delete_file(path, message=message),
        )

    def can_access_remote(self) -> bool:
        """Return whether the **primary** is reachable.

        Only the primary: a settings "Test connection" button must not report
        success because the backend being retired happens to answer.
        """
        return self.primary.can_access_remote()

    def get_string_map(self, path: str) -> dict[str, str]:
        """Merge both backends' revision maps, primary winning on conflict.

        A device that has not migrated publishes revisions only to the
        mirror; without this it would look revision-less and be
        re-downloaded every tick for the whole trial period.

        Like the other reads, a primary failure degrades to the mirror rather
        than failing the tick: revisions are a cache, and losing them re-reads
        data rather than losing it.
        """
        merged: dict[str, str] = {}
        mirror_read = getattr(self.mirror, "get_string_map", None)
        # A mirror that CANNOT do bulk reads contributes nothing, but that is
        # not a failure -- it has no revisions to give, which is a real answer.
        # Only a mirror that tried and threw leaves the read with no answer,
        # and only then can a failing primary make this raise.
        mirror_answered = mirror_read is None
        if mirror_read is not None:
            mirror_map = self._try_mirror(
                f"get_string_map {path}", lambda: mirror_read(path)
            )
            mirror_answered = mirror_map is not None
            merged.update(mirror_map or {})
        primary_read = getattr(self.primary, "get_string_map", None)
        if primary_read is not None:
            primary_map = self._try_primary_read(
                f"get_string_map {path}", lambda: primary_read(path)
            )
            if primary_map is None and not mirror_answered:
                self._raise_both_failed(f"get_string_map {path}")
            merged.update(primary_map or {})
        return merged

    def _try_mirror(self, operation: str, run: Callable[[], _T]) -> _T | None:
        """Run a mirror operation, reporting rather than propagating failure."""
        try:
            return run()
        except RemoteSyncError as error:
            self._on_mirror_failure(operation, error)
            return None

    def _try_primary_read(self, operation: str, run: Callable[[], _T]) -> _T | None:
        """Run a primary READ, reporting rather than propagating failure.

        Reads only -- writes stay fail-closed, since a write the primary did
        not accept has not happened and must fail the tick.
        """
        try:
            return run()
        except RemoteSyncError as error:
            self._on_primary_read_failure(operation, error)
            return None

    def _on_primary_read_failure(self, operation: str, error: Exception) -> None:
        """Warn that a read fell back to the mirror."""
        _logger.warning(
            "Primary backend failed during %s: %s — falling back to the mirror",
            operation,
            error,
        )

    def _raise_both_failed(self, operation: str) -> None:
        """Raise when neither backend could answer a read.

        Fail closed rather than returning an empty result: an empty read is
        indistinguishable from "no data", and callers act on that by treating
        remote state as absent.
        """
        msg = f"both primary and mirror backends failed during {operation}"
        raise RemoteSyncError(msg)


def _log_mirror_failure(operation: str, error: Exception) -> None:
    """Warn loudly, so a rotting fallback is visible before it is needed."""
    _logger.warning("Mirror backend failed during %s: %s", operation, error)
