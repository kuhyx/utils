"""This device's stable sync identity.

Every device that pushes into a namespace needs an id that is *its own*: it
is the directory segment its log is pushed under
(``<path_prefix>/<device_id>/<filename>``), the revision key, and the node
component baked into every HLC stamp it writes (``<iso>-<counter>-<id>``).

Two devices sharing an id overwrite each other's pushed file on every tick,
so the id must be per-*install*, not per-role: a fixed ``"pc"``/``"phone"``
constant silently collides the moment a second machine takes the same role,
and a reinstall inherits the previous install's CRDT identity.

A migration from a role constant to a persisted uuid cannot rewrite history.
Stamps already written keep the old id, and the old path keeps the log that
was pushed under it -- so a device that has just switched ids must still
recognise its *former* id as itself. That is what [legacy_id] carries, and
why [DeviceIdentity.own_ids] exists: skip-own-writes has to test membership
of that set rather than equality with one id, or the device re-downloads and
re-merges its own pre-migration history as though a peer had written it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
import uuid

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class DeviceIdentity:
    """This device's current sync id, plus the id it used to push under.

    Attributes:
        device_id: The id to push, stamp and key revisions under from now on.
        legacy_id: The id this device pushed under before the migration to
            persisted uuids, or ``None`` once its old path has been reclaimed.
    """

    device_id: str
    legacy_id: str | None = None

    @property
    def own_ids(self) -> frozenset[str]:
        """Every id that means "this device", for skip-own-writes checks."""
        if self.legacy_id is None:
            return frozenset({self.device_id})
        return frozenset({self.device_id, self.legacy_id})

    def is_own(self, other_device_id: str) -> bool:
        """Return whether [other_device_id] is one of this device's own ids."""
        return other_device_id in self.own_ids


def load_device_identity(path: Path, *, legacy_id: str | None = None) -> DeviceIdentity:
    """Return the id persisted at [path], creating it on first call.

    The file holds exactly one uuid4 and is written once; every later call
    returns the same value, which is what makes the id stable across restarts
    (and is why it must live in durable state, not a temp dir).

    Args:
        path: File holding this device's uuid. Parent dirs are created.
        legacy_id: The role constant this device pushed under before
            migrating, recorded on the returned identity so skip-own-writes
            still recognises the old path as this device's own. Pass ``None``
            once that path has been reclaimed.

    Returns:
        This device's [DeviceIdentity].
    """
    try:
        existing = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        existing = ""
    if existing:
        return DeviceIdentity(device_id=existing, legacy_id=legacy_id)

    # Deliberately not guarded: if the state directory cannot be created the
    # id cannot be persisted, and returning an unpersisted one would mint a
    # fresh uuid on every restart, stranding a device directory each time.
    minted = str(uuid.uuid4())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{minted}\n", encoding="utf-8")
    return DeviceIdentity(device_id=minted, legacy_id=legacy_id)
