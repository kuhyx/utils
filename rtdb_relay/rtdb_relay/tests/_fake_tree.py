# Copyright (c) 2026 Krzysztof Rudnicki. MIT License.
"""Tree and wire helpers of the fake RTDB (``_fake_rtdb``)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import httpx


def _parts(path: str) -> list[str]:
    return [p for p in path.strip("/").split("/") if p]


def etag(value: object) -> str:
    if value is None:
        return "null_etag"
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _event(kind: str, path: str, data: Any) -> str:
    return f"event: {kind}\ndata: {json.dumps({'path': path, 'data': data})}\n\n"


def _assign(node: dict[str, Any], parts: list[str], value: Any) -> None:
    for part in parts[:-1]:
        if not isinstance(node.get(part), dict):
            node[part] = {}
        node = node[part]
    node[parts[-1]] = value


def _prune(node: Any) -> Any:
    """RTDB keeps no empty objects."""
    if not isinstance(node, dict):
        return node
    out = {k: _prune(v) for k, v in node.items()}
    return {k: v for k, v in out.items() if v is not None and v != {}} or None


def _reply(
    status: int, value: Any, headers: dict[str, str] | None = None
) -> httpx.Response:
    """A JSON response; ``httpx.Response(json=None)`` would send no body at all."""
    return httpx.Response(
        status, content=json.dumps(value).encode(), headers=headers or {}
    )
