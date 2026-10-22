"""Two backends behind one ``get(path)``: a build directory and a live site.

DirSite answers like a plain static host (index.html for ``/x/``, a 404 for
anything missing), so the find/read checks are written once for both modes.
"""

from __future__ import annotations

import http.client
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

from agent_ready.report import Undeterminable

DEFAULT_UA = "Claude-User/1.0 (+agentready-check)"
MAX_BODY = 5 * 1024 * 1024
_EXT_MIME = {
    ".html": "text/html",
    ".md": "text/markdown",
    ".txt": "text/plain",
    ".xml": "application/xml",
    ".json": "application/json",
}


@dataclass(frozen=True)
class Response:
    """A fetched resource: final status, bare media type, headers, body."""

    status: int
    ctype: str
    body: bytes
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def text(self) -> str:
        """Body decoded as UTF-8 (lenient)."""
        return self.body.decode("utf-8", "replace")


class Site:
    """Common URL handling; subclasses implement ``_fetch``."""

    live = False

    def __init__(self, origin: str) -> None:
        self.origin = origin.rstrip("/")
        self._cache: dict[tuple[str, str], Response | Undeterminable] = {}
        self._lock = threading.Lock()

    def to_path(self, url: str, base: str = "/") -> str | None:
        """Site path for a URL or relative href; None when off-site."""
        absolute = urljoin(self.origin + base, url.strip())
        parts = urlsplit(absolute)
        if (
            parts.scheme not in ("http", "https")
            or parts.netloc != urlsplit(self.origin).netloc
        ):
            return None
        return parts.path or "/"

    def get(self, path: str, ua: str = DEFAULT_UA) -> Response:
        """Fetch ``path`` (memoized, including network failures)."""
        key = (path, ua)
        with self._lock:
            hit = self._cache.get(key)
        if hit is None:
            try:
                hit = self._fetch(path, ua)
            except Undeterminable as exc:
                hit = exc
            with self._lock:
                self._cache[key] = hit
        if isinstance(hit, Undeterminable):
            raise hit
        return hit

    def prefetch(self, paths: list[str], uas: tuple[str, ...] = (DEFAULT_UA,)) -> None:
        """Warm the cache for every (path, ua) pair; parallel for live sites."""
        if not self.live:
            return
        pairs = [(p, ua) for p in dict.fromkeys(paths) for ua in uas]
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda pair: self._safe_get(*pair), pairs))

    def _safe_get(self, path: str, ua: str) -> None:
        try:
            self.get(path, ua)
        except Undeterminable:
            pass

    def _fetch(self, path: str, ua: str) -> Response:
        raise NotImplementedError


class DirSite(Site):
    """A build output directory served the way a static host serves it."""

    def __init__(self, root: Path) -> None:
        super().__init__("https://dist.invalid")
        self.root = root.resolve()

    def file_for(self, path: str) -> Path | None:
        """The file a static host would serve for ``path``."""
        rel = unquote(path.split("?", 1)[0]).lstrip("/")
        base = (self.root / rel).resolve()
        if not base.is_relative_to(self.root):
            return None
        cands = (
            [base / "index.html"]
            if path.endswith("/") or not rel
            else [base, base.with_name(base.name + ".html"), base / "index.html"]
        )
        return next((c for c in cands if c.is_file()), None)

    def _fetch(self, path: str, ua: str) -> Response:
        target = self.file_for(path)
        if target is None:
            fallback = self.root / "404.html"
            body = fallback.read_bytes() if fallback.is_file() else b""
            return Response(404, "text/html", body)
        return Response(
            200,
            _EXT_MIME.get(target.suffix, "application/octet-stream"),
            target.read_bytes(),
        )


class HttpSite(Site):
    """A live site. Follows redirects; HTTP errors are responses, not raises."""

    live = True

    def __init__(self, base: str, timeout: float = 8.0, budget: float = 45.0) -> None:
        parts = urlsplit(base)
        super().__init__(f"{parts.scheme}://{parts.netloc}")
        self.timeout = timeout
        self.deadline = time.monotonic() + budget

    def _remaining(self) -> float:
        left = self.deadline - time.monotonic()
        if left < 1:
            raise Undeterminable("overall time budget used up")
        return min(self.timeout, left)

    def _fetch(self, path: str, ua: str) -> Response:
        return self.request(path, ua)

    def request(
        self,
        path: str,
        ua: str = DEFAULT_UA,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> Response:
        """Uncached GET (or POST when ``data`` is given)."""
        req = urllib.request.Request(
            self.origin + path,
            data=data,
            headers={"User-Agent": ua, "Accept": "*/*", **(headers or {})},
        )
        try:
            with urllib.request.urlopen(req, timeout=self._remaining()) as resp:
                return _response(resp.status, resp.headers, resp.read(MAX_BODY))
        except urllib.error.HTTPError as exc:
            return _response(exc.code, exc.headers, exc.read(MAX_BODY))
        except (
            urllib.error.URLError,
            TimeoutError,
            OSError,
            http.client.HTTPException,
        ) as exc:
            raise Undeterminable(f"{path}: {getattr(exc, 'reason', exc)}") from exc


def _response(status: int, headers: http.client.HTTPMessage, body: bytes) -> Response:
    """Normalise headers: lowercase keys, repeated headers joined by ', '."""
    flat: dict[str, str] = {}
    for key in set(headers.keys()):
        flat[key.lower()] = ", ".join(headers.get_all(key) or [])
    ctype = flat.get("content-type", "").split(";", 1)[0].strip().lower()
    return Response(status, ctype, body, flat)
