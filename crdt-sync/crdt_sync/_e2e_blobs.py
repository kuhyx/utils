# Copyright (c) 2026 Krzysztof Rudnicki
"""Read every text blob under an old (plaintext) prefix, for the e2e copy."""

from __future__ import annotations

from typing import TYPE_CHECKING

from crdt_sync._sync import default_revs_path

if TYPE_CHECKING:
    from crdt_sync._remote import RemoteStore


def blobs(store: RemoteStore, root: str) -> dict[str, str]:
    """Every text blob under ``root`` (flat leaves and ``<dir>/<file>``)."""
    skip = {default_revs_path(root), f"{root}/e2e", f"{root}/revs"}
    out: dict[str, str] = {}
    for name in store.list_directory(root):
        full = f"{root}/{name}"
        if full in skip:
            continue
        children = store.list_directory(full)
        if not children:
            text = store.get_file_text(full)
            if text is not None:
                out[name] = text
            continue
        for child in children:
            text = store.get_file_text(f"{full}/{child}")
            if text is not None:
                out[f"{name}/{child}"] = text
    return out
