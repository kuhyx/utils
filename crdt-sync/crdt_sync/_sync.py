"""Domain-agnostic pull/merge/push sync orchestration.

Generalizes diet_guard's original ``_sync.py`` (pull every other device's
pushed log, merge with the local one, push this device's own merged result
back up) so any app can reuse the loop while keeping its own on-disk JSON
shape via the ``encode``/``decode`` callbacks -- this module has no opinion
on what a ``Record``'s fields actually mean.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from crdt_sync._log import merge_logs

if TYPE_CHECKING:
    from collections.abc import Callable

    from crdt_sync._github import GitHubSyncClient
    from crdt_sync._log import Log

_logger = logging.getLogger(__name__)

_DEFAULT_FILENAME = "log.json"


def _pull_remote_logs(
    client: GitHubSyncClient,
    device_id: str,
    path_prefix: str,
    filename: str,
    decode: Callable[[str], Log],
) -> list[Log]:
    """Return every other device's last-pushed log, skipping this one.

    A device whose pushed file is corrupt or unparsable (e.g. an interrupted
    push) is logged and skipped, same as one that has never pushed at all --
    GitHub is an external system boundary, and one bad device's file must not
    stall merging in every other device's.
    """
    remote_logs: list[Log] = []
    for other_device_id in client.list_directory(path_prefix):
        if other_device_id == device_id:
            continue
        text = client.get_file_text(f"{path_prefix}/{other_device_id}/{filename}")
        if text is None:
            continue
        try:
            remote_logs.append(decode(text))
        except (ValueError, KeyError, TypeError):
            _logger.warning(
                "Unparsable log pushed by device %r, skipping",
                other_device_id,
            )
    return remote_logs


def sync_log(
    *,
    client: GitHubSyncClient,
    device_id: str,
    path_prefix: str,
    local_log: Log,
    encode: Callable[[Log], str],
    decode: Callable[[str], Log],
    filename: str = _DEFAULT_FILENAME,
    commit_message: str = "crdt_sync: update log",
) -> Log:
    """Run one full sync tick: pull every other device's log, merge, push.

    Pulls from ``<path_prefix>/<other-device-id>/<filename>`` for every
    device directory GitHub reports under ``path_prefix``, merges each into
    ``local_log`` with :func:`crdt_sync.merge_logs`, then pushes this
    device's own merged result to ``<path_prefix>/<device_id>/<filename>``.

    Args:
        client: An authenticated :class:`GitHubSyncClient`.
        device_id: This device's identifier; also the directory name its own
            log is pushed under.
        path_prefix: The repo-relative directory holding one subdirectory
            per device (e.g. ``"devices"``).
        local_log: This device's current full log (including tombstones).
        encode: Serializes a merged log for pushing.
        decode: Parses a remote device's pushed text back into a log.
            Raising ``ValueError``, ``KeyError``, or ``TypeError`` is treated
            as a corrupt/unparsable push, and that device is skipped for
            this tick rather than aborting the whole sync.
        filename: The file name each device pushes its log as.
        commit_message: The commit message used for this device's push.

    Returns:
        The merged log, as pushed.
    """
    merged = dict(local_log)
    for remote_log in _pull_remote_logs(
        client, device_id, path_prefix, filename, decode
    ):
        merged = merge_logs(merged, remote_log)

    client.put_file_text(
        f"{path_prefix}/{device_id}/{filename}",
        encode(merged),
        message=commit_message,
    )
    return merged
