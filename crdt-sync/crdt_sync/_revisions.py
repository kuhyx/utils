"""The revision string a device publishes alongside its log.

Split from :mod:`crdt_sync._sync` so both the push and pull halves can import
it without importing each other. Pure: a revision is a function of the encoded
log and nothing else, which is what lets two devices agree on whether they are
looking at the same bytes.

Re-exported from :mod:`crdt_sync._sync`, so existing imports keep working.
"""

from __future__ import annotations

import hashlib

def revision_of(encoded_log: str) -> str:
    """Return the revision of a serialized log: a content hash.

    A hash rather than the log's maximum HLC because merging a peer's *older*
    record changes the content without raising the maximum -- with three
    devices in one namespace (diet-guard has ``pc``, ``phone`` and
    ``desktop``) a clock-based revision can miss a peer's merged state. It is
    also the same value used to suppress no-op pushes, so the two
    optimisations share one mechanism.

    Parameters
    ----------
    encoded_log : str
        The serialized log, exactly as it would be pushed.

    Returns:
    -------
    str
        A hex SHA-256 digest.

    """
    return hashlib.sha256(encoded_log.encode("utf-8")).hexdigest()
