"""HTTP calls to the gateway: liveness, a real chat probe, admin provider state."""

from __future__ import annotations

import http.cookiejar
import json
import urllib.error
import urllib.request
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from omniroute_offload._gw_config import Config

type Json = Any

COMBO = "free-best"
CHAT_TIMEOUT_S = 90


class ApiError(RuntimeError):
    """The gateway answered with an error or not at all."""


def _request(
    url: str, body: object, method: str | None, headers: dict[str, str]
) -> urllib.request.Request:
    data = None if body is None else json.dumps(body).encode()
    hdrs = {"content-type": "application/json", **headers}
    return urllib.request.Request(url, data=data, method=method, headers=hdrs)


def _send(
    req: urllib.request.Request,
    timeout: float,
    opener: urllib.request.OpenerDirector | None = None,
) -> Json:
    open_ = opener.open if opener else urllib.request.urlopen
    try:
        with open_(req, timeout=timeout) as resp:
            raw = resp.read()
    except (urllib.error.URLError, TimeoutError, OSError) as err:
        msg = f"{req.full_url}: {err}"
        raise ApiError(msg) from err
    try:
        return json.loads(raw) if raw else {}
    except json.JSONDecodeError as err:
        msg = f"{req.full_url}: not JSON"
        raise ApiError(msg) from err


def call(
    url: str,
    body: dict[str, Any] | None = None,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 15,
) -> Json:
    """Send JSON (POST when body is given), return decoded JSON; ApiError on failure."""
    return _send(_request(url, body, None, headers or {}), timeout)


def alive(cfg: Config) -> bool:
    """Return True when the web server answers its auth-status endpoint."""
    try:
        call(f"{cfg.base_url}/api/auth/status", timeout=5)
    except ApiError:
        return False
    return True


def chat(cfg: Config, key: str) -> str:
    """One real completion through the combo; returns its text or raises ApiError."""
    reply = call(
        f"{cfg.base_url}/v1/chat/completions",
        {
            "model": COMBO,
            "max_tokens": 300,
            "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
        },
        headers={"authorization": f"Bearer {key}"},
        timeout=CHAT_TIMEOUT_S,
    )
    try:
        text = str(reply["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError) as err:
        msg = f"unexpected reply: {str(reply)[:200]}"
        raise ApiError(msg) from err
    if not text:
        msg = "empty completion"
        raise ApiError(msg)
    return text


class Admin:
    """Cookie session on the admin API."""

    def __init__(self, cfg: Config, password: str) -> None:
        """Log in; ApiError when the password is refused."""
        self.base = cfg.base_url
        jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(jar)
        )
        self._call("/api/auth/login", {"password": password})

    def _call(self, path: str, body: object = None, method: str | None = None) -> Json:
        return _send(_request(self.base + path, body, method, {}), 15, self.opener)

    def providers(self) -> list[dict[str, Any]]:
        """Return every provider connection."""
        got = self._call("/api/providers")
        return list(got.get("connections", got) if isinstance(got, dict) else got)

    def combo_members(self, name: str = COMBO) -> set[str]:
        """Return provider ids the combo routes to (empty when it is missing)."""
        got = self._call("/api/combos")
        combos = got.get("combos", got) if isinstance(got, dict) else got
        return {
            str(m.get("providerId") or str(m.get("model", "")).split("/", 1)[0])
            for c in combos
            if c.get("name") == name
            for m in c.get("models", [])
            if isinstance(m, dict)
        }

    def reactivate(self, conn_id: str) -> None:
        """Mark a connection active again (the PUT merges; keys are kept)."""
        self._call(f"/api/providers/{conn_id}", {"testStatus": "active"}, "PUT")

    def upsert_combo(self, name: str, models: list[str]) -> None:
        """Create or replace a priority combo."""
        got = self._call("/api/combos")
        combos = got.get("combos", got) if isinstance(got, dict) else got
        body = {"name": name, "models": models, "strategy": "priority"}
        ids = [c["id"] for c in combos if c.get("name") == name]
        if ids:
            self._call(f"/api/combos/{ids[0]}", body, "PUT")
        else:
            self._call("/api/combos", body)


def cooldown_until(conn: dict[str, Any]) -> datetime | None:
    """Return the latest cooldown end of a connection (top level or per key)."""
    stamps = [conn.get("rateLimitedUntil")]
    health = (conn.get("providerSpecificData") or {}).get("apiKeyHealth") or {}
    stamps += [k.get("cooldownUntil") for k in health.values() if isinstance(k, dict)]
    parsed = [_parse(s) for s in stamps if isinstance(s, str)]
    valid = [p for p in parsed if p is not None]
    return max(valid) if valid else None


def _parse(stamp: str) -> datetime | None:
    try:
        return datetime.fromisoformat(stamp)
    except ValueError:
        return None
