"""Shared pytest fixtures for crdt_sync's test suite."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from crdt_sync import Hlc
from crdt_sync._remote import RemoteSyncError

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.fixture
def make_hlc() -> Callable[..., Hlc]:
    """Return a factory for deterministic Hlc values."""

    def _make(wall_time_ms: int, counter: int = 0, node_id: str = "node-a") -> Hlc:
        return Hlc(wall_time_ms=wall_time_ms, counter=counter, node_id=node_id)

    return _make


class FakeStore:
    """An in-memory remote: records its traffic, and can be told to fail.

    One class rather than a near-copy per test module. It is the union of
    what those copies needed -- ``reads``/``writes`` for asserting on traffic
    rather than only on results, and ``failing`` for driving the error paths
    -- because the shared half was the fiddly part (the prefix slicing in
    :meth:`list_directory` and :meth:`get_string_map`) and two copies of that
    is where they drift.
    """

    def __init__(
        self,
        files: dict[str, str] | None = None,
        *,
        failing: bool = False,
    ) -> None:
        """Start holding ``files``, failing every call if ``failing``."""
        self.files = dict(files or {})
        self.failing = failing
        self.reads: list[str] = []
        self.writes: list[str] = []

    def _guard(self, what: str) -> None:
        if self.failing:
            msg = f"{what} failed"
            raise RemoteSyncError(msg)

    def list_directory(self, path: str) -> list[str]:
        """Return the distinct first segments under ``path``."""
        self._guard("list")
        prefix = f"{path}/"
        return sorted(
            {
                key[len(prefix) :].split("/")[0]
                for key in self.files
                if key.startswith(prefix)
            }
        )

    def get_file_text(self, path: str) -> str | None:
        """Return the stored text, recording the read."""
        self._guard("read")
        self.reads.append(path)
        return self.files.get(path)

    def put_file_text(self, path: str, text: str, *, message: str) -> None:
        """Store ``text``, recording the write."""
        del message
        self._guard("write")
        self.writes.append(path)
        self.files[path] = text

    def get_string_map(self, path: str) -> dict[str, str]:
        """Return the direct children of ``path`` as a flat map."""
        self._guard("map read")
        prefix = f"{path}/"
        return {
            key[len(prefix) :]: value
            for key, value in self.files.items()
            if key.startswith(prefix)
        }

    def delete_file(self, path: str, *, message: str = "") -> None:
        """Remove ``path`` if present."""
        del message
        self._guard("delete")
        self.files.pop(path, None)

    def can_access_remote(self) -> bool:
        """Report health, which ``failing`` inverts."""
        return not self.failing


class FakeStoreWithoutBulkRead:
    """A store with no bulk-map read, standing in for GitHub.

    Composes rather than subclasses :class:`FakeStore`, because a subclass
    would inherit ``get_string_map`` -- the capability this fake must lack.
    """

    def __init__(self, files: dict[str, str] | None = None) -> None:
        """Wrap a plain :class:`FakeStore` holding ``files``."""
        self._inner = FakeStore(files)

    @property
    def files(self) -> dict[str, str]:
        """The wrapped store's contents."""
        return self._inner.files

    @property
    def reads(self) -> list[str]:
        """The wrapped store's recorded reads."""
        return self._inner.reads

    @property
    def writes(self) -> list[str]:
        """The wrapped store's recorded writes."""
        return self._inner.writes

    def list_directory(self, path: str) -> list[str]:
        """Delegate to the wrapped store."""
        return self._inner.list_directory(path)

    def get_file_text(self, path: str) -> str | None:
        """Delegate to the wrapped store."""
        return self._inner.get_file_text(path)

    def put_file_text(self, path: str, text: str, *, message: str) -> None:
        """Delegate to the wrapped store."""
        self._inner.put_file_text(path, text, message=message)

    def delete_file(self, path: str, *, message: str = "") -> None:
        """Delegate to the wrapped store."""
        self._inner.delete_file(path, message=message)

    def can_access_remote(self) -> bool:
        """Delegate to the wrapped store."""
        return self._inner.can_access_remote()
