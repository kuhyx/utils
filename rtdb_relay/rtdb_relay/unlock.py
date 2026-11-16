# Copyright (c) 2026 Krzysztof Rudnicki. MIT License.
"""The E2E key from the shared crdt-sync passphrase (header made on first use)."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from crdt_sync import (
    Argon2Params,
    E2eHeaderError,
    E2eKey,
    E2eLayout,
    E2eLockedError,
    E2eWrongPassphraseError,
    unlock_e2e,
)

from rtdb_relay.seal import dumps

if TYPE_CHECKING:
    from collections.abc import Coroutine

    from rtdb_relay.rtdb import Rtdb


class HeaderStore:
    """crdt_sync's sync ``RemoteStore``, just enough for ``unlock_e2e``.

    ``unlock_e2e`` runs in a worker thread (Argon2id must not block the
    loop); each call hops back to the loop that owns the async client.
    The header is one JSON string leaf, as the Flutter side writes it.
    """

    def __init__(self, raw: Rtdb, loop: asyncio.AbstractEventLoop) -> None:
        """Read and write through ``raw`` (an unsealed client on ``""``)."""
        self._raw = raw
        self._loop = loop

    def _run[T](self, coro: Coroutine[Any, Any, T]) -> T:
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()

    def list_directory(self, path: str) -> list[str]:
        """Nothing: only the header is read through here."""
        del path
        return []

    def get_file_text(self, path: str) -> str | None:
        """The header text, or ``None``; a non-string value comes back as JSON."""
        value = self._run(self._raw.get(path))
        if value is None or isinstance(value, str):
            return value
        return dumps(value)  # not ours: E2eHeaderError, never overwritten

    def put_file_text(self, path: str, text: str, *, message: str) -> None:
        """Write the header as one string leaf."""
        del message
        self._run(self._raw.put(path, text))

    def delete_file(self, path: str, *, message: str = "") -> None:
        """Refused: the header is never deleted."""
        del path, message
        msg = "the relay never deletes the e2e header"
        raise NotImplementedError(msg)

    def can_access_remote(self) -> bool:
        """Always: a failing call raises on its own."""
        return True


async def unlock(
    rtdb: Rtdb,
    passphrase: str,
    layout: E2eLayout,
    params: Argon2Params | None = None,
) -> E2eKey:
    """The key of ``layout`` (``E2eLayout.of("<app>/v1")``) from ``passphrase``.

    Raises:
        E2eLockedError: No passphrase, a wrong one, or an unreadable header.

    """
    if not passphrase:
        msg = "no crdt-sync passphrase on this PC"
        raise E2eLockedError(msg)
    store = HeaderStore(rtdb.at(""), asyncio.get_running_loop())
    try:
        return await asyncio.to_thread(
            unlock_e2e,
            store,
            path_prefix=layout.prefix,
            passphrase=passphrase,
            params=params,
            e2e_path=layout.e2e_path,
        )
    except (E2eWrongPassphraseError, E2eHeaderError) as exc:
        raise E2eLockedError(str(exc) or type(exc).__name__) from exc
