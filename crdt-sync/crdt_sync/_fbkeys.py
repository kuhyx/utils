"""Escaping arbitrary strings into Firebase Realtime Database keys.

Split from :mod:`crdt_sync._firebase`, which keeps the client. RTDB forbids
``.``, ``$``, ``#``, ``[``, ``]`` and ``/`` in a key, but the app stores
record ids and file paths that contain them, so every key is escaped on the
way in and unescaped on the way out. The pair has to round-trip exactly or a
device silently stops seeing its own writes.

Re-exported from :mod:`crdt_sync._firebase`, so existing imports keep working.
"""

from __future__ import annotations

# Characters Realtime Database forbids in a key, plus ``~`` itself because it
# is this module's escape character. ``/`` is absent deliberately: it is the
# path separator, handled by splitting into segments before escaping.
_ESCAPES = {
    "~": "~7E",
    ".": "~2E",
    "$": "~24",
    "#": "~23",
    "[": "~5B",
    "]": "~5D",
}
_UNESCAPES = {escape: char for char, escape in _ESCAPES.items()}
_ESCAPE_LENGTH = 3


def encode_key(segment: str) -> str:
    """Escape one path segment into a legal Realtime Database key.

    RTDB rejects ``. $ # [ ] /`` in keys, and the REST API's trailing
    ``.json`` is a *format suffix* rather than part of the path -- so a
    filename like ``log.json`` cannot be stored verbatim. The mapping is a
    reversible ``~XX`` escape (``log.json`` -> ``log~2Ejson``) rather than a
    lossy "strip the extension", because callers see these names again:
    todo-app lists *filenames*, not device directories, and must keep getting
    ``<uuid>.json`` back.

    ``~`` is the escape character because it is legal in RTDB keys and
    unreserved in URLs, so the escaped form needs no percent-encoding --
    which the server would otherwise decode back into the illegal character.

    Parameters
    ----------
    segment : str
        One path segment, with no ``/`` in it.

    Returns:
    -------
    str
        The escaped key.

    """
    return "".join(_ESCAPES.get(char, char) for char in segment)


def decode_key(key: str) -> str:
    """Reverse :func:`encode_key`.

    Parameters
    ----------
    key : str
        An escaped Realtime Database key.

    Returns:
    -------
    str
        The original segment.

    """
    out: list[str] = []
    index = 0
    while index < len(key):
        escape = key[index : index + _ESCAPE_LENGTH]
        char = _UNESCAPES.get(escape)
        if char is None:
            out.append(key[index])
            index += 1
        else:
            out.append(char)
            index += _ESCAPE_LENGTH
    return "".join(out)


def encode_path(path: str) -> str:
    """Escape every segment of a ``/``-separated logical path.

    Parameters
    ----------
    path : str
        A logical path such as ``"todo-sync/notes/abc.json"``.

    Returns:
    -------
    str
        The path with each segment escaped, empty segments dropped.

    """
    return "/".join(encode_key(part) for part in path.split("/") if part)
