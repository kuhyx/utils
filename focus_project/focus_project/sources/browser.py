# Copyright (c) 2026 Krzysztof Rudnicki
"""Browser evidence: active window/URL time on the project's sites.

Reads the kuhytrack activity server (read-only GETs, the same data the PC
watcher and the phone bridge write): ``currentwindow`` buckets give
``{app, title[, url]}`` spans, ``afkstatus`` buckets of the same host trim
them to time the user was present. A host without an AFK bucket (the phone)
is taken as present.

Matching is case-insensitive. A ``site_patterns`` entry such as
``leetcode.com`` matches as-is in the url/title/app, or, when the window is
a browser, by its stem (``leetcode``) in the title: Chrome-family titles
carry the page name, not the host. Stems under four characters are ignored.

Failure modes (named): no tracker config -> inactive, 0 minutes; tracker
unreachable or broken -> raises, so the registry logs it and counts 0; an
AFK bucket with no events that day -> 0 for that host (fail closed).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from focus_project.sources import Interval, day_bounds

if TYPE_CHECKING:
    from focus_project._model import Project

_LOG = logging.getLogger(__name__)
# Long window events start before midnight; ask a little earlier.
LOOKBACK_S = 3600
TIMEOUT_S = 5
MIN_STEM = 4
BROWSERS = (
    "helium",
    "librewolf",
    "firefox",
    "chrom",
    "brave",
    "vivaldi",
    "opera",
    "msedge",
    "zen",
)
_ENV_DEFAULT = "~/.config/kuhytrack/env"
_urlopen = urlopen


@dataclass(frozen=True)
class Config:
    """Where the tracker listens and the bearer token (may be empty)."""

    url: str
    token: str


def _config() -> Config | None:
    """The tracker's own ``KT_URL``/``KT_TOKEN`` env file, or None if absent."""
    path = Path(os.environ.get("KUHYTRACK_ENV", _ENV_DEFAULT)).expanduser()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    values: dict[str, str] = {}
    for line in lines:
        key, sep, value = line.strip().partition("=")
        if sep and not key.startswith("#"):
            values[key.strip()] = value.strip().strip("'\"")
    url = values.get("KT_URL", "")
    return Config(url.rstrip("/"), values.get("KT_TOKEN", "")) if url else None


def _get_json(cfg: Config, path: str, params: dict[str, str] | None = None) -> Any:  # noqa: ANN401
    """One authenticated GET returning parsed JSON."""
    url = cfg.url + path + (f"?{urlencode(params)}" if params else "")
    request = Request(url)  # noqa: S310 (operator-configured http URL)
    if cfg.token:
        request.add_header("Authorization", f"Bearer {cfg.token}")
    with _urlopen(request, timeout=TIMEOUT_S) as response:
        return json.load(response)


def _merge(spans: list[Interval]) -> list[Interval]:
    """Sorted, non-overlapping union of ``spans``."""
    out: list[Interval] = []
    for start, end in sorted(spans):
        if out and start <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], end))
        else:
            out.append((start, end))
    return out


def _intersect(left: list[Interval], right: list[Interval]) -> list[Interval]:
    """Overlap of two merged span lists."""
    out: list[Interval] = []
    for a0, a1 in left:
        for b0, b1 in right:
            lo, hi = max(a0, b0), min(a1, b1)
            if hi > lo:
                out.append((lo, hi))
    return out


def _needles(patterns: tuple[str, ...]) -> tuple[list[str], list[str]]:
    """``(full, stems)``: lowercase host patterns and their page-title stems."""
    full: list[str] = []
    stems: list[str] = []
    for raw in patterns:
        pattern = raw.strip().lower().removeprefix("www.")
        if not pattern:
            continue
        full.append(pattern)
        stem = pattern.split(".", 1)[0]
        if "." in pattern and len(stem) >= MIN_STEM:
            stems.append(stem)
    return full, stems


def _matches(data: dict[str, Any], full: list[str], stems: list[str]) -> bool:
    fields = {
        k: str(data.get(k, "")).lower() for k in ("url", "title", "app", "package")
    }
    text = " ".join(fields.values()).replace("www.", "")
    if any(needle in text for needle in full):
        return True
    if any(b in fields["app"] for b in BROWSERS):
        return any(stem in fields["title"] for stem in stems)
    return False


def _epoch(stamp: str) -> float:
    return datetime.fromisoformat(stamp).timestamp()


def _spans(events: list[dict[str, Any]]) -> list[Interval]:
    out: list[Interval] = []
    for event in events:
        start = _epoch(event["timestamp"])
        out.append((start, start + float(event.get("duration") or 0)))
    return out


def intervals(day: date, project: Project) -> list[Interval]:
    """Present time on the project's sites; see the module docstring."""
    full, stems = _needles(project.site_patterns)
    if not full:
        return []
    cfg = _config()
    if cfg is None:
        _LOG.info("browser source: no kuhytrack config (inactive)")
        return []
    lo, hi = day_bounds(day)
    stamp = "%Y-%m-%dT%H:%M:%S.000Z"
    params = {
        "start": datetime.fromtimestamp(lo - LOOKBACK_S, UTC).strftime(stamp),
        "end": datetime.fromtimestamp(hi, UTC).strftime(stamp),
    }

    def events(bucket: dict[str, Any]) -> list[dict[str, Any]]:
        return list(_get_json(cfg, f"/api/0/buckets/{bucket['id']}/events", params))

    buckets = list(_get_json(cfg, "/api/0/buckets").values())
    present: dict[str, list[Interval]] = {}
    for bucket in buckets:
        if bucket["type"] == "afkstatus":
            live = [e for e in events(bucket) if e["data"].get("status") == "not-afk"]
            present.setdefault(bucket["hostname"], []).extend(_spans(live))
    on_site: dict[str, list[Interval]] = {}
    for bucket in buckets:
        if bucket["type"] == "currentwindow":
            hits = [e for e in events(bucket) if _matches(e["data"], full, stems)]
            on_site.setdefault(bucket["hostname"], []).extend(_spans(hits))
    out: list[Interval] = []
    for host, spans in on_site.items():
        merged = _merge(spans)
        out.extend(
            _intersect(merged, _merge(present[host])) if host in present else merged
        )
    return out
