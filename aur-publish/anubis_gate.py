"""Fetch an AUR URL from behind the Anubis anti-bot gate.

The AUR sits behind Anubis (https://anubis.techaro.lol/), which answers every
HTML request with a proof-of-work challenge page carrying HTTP **200**. A bare
`curl` therefore reports 200 for a page that is actually unreachable, which is
exactly how "is /register back up?" gets answered wrong.

This module solves the challenge and reports the status of the *real* page
behind it, so the caller can distinguish:

  * 200  -> genuinely available
  * 503  -> reached the site; that endpoint is disabled server-side
  * other-> whatever the app actually said

Exit codes mirror the HTTP status so shell callers can branch on them:
0 for 200, 1 for anything else, 2 for a local/transport failure.
"""

from __future__ import annotations

import argparse
import hashlib
import http.cookiejar
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://aur.archlinux.org"
UA = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
CHALLENGE_RE = re.compile(
    r'<script id="anubis_challenge" type="application/json">(.*?)</script>',
    re.S,
)
PASS_PATH = "/.within.website/x/cmd/anubis/api/pass-challenge"
# A solve at difficulty 4 takes ~0.01s; this ceiling only guards a server-side
# difficulty spike, so the poller degrades instead of spinning forever.
MAX_NONCE = 50_000_000


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Keep redirects visible instead of silently following them."""

    def redirect_request(self, *_args, **_kwargs):  # noqa: D102 - see class doc
        return None


def _opener() -> urllib.request.OpenerDirector:
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar), _NoRedirect
    )
    opener.addheaders = [
        ("User-Agent", UA),
        ("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
    ]
    return opener


def _solve(random_data: str, difficulty: int) -> tuple[int, str, float]:
    """Find a nonce whose sha256 digest starts with `difficulty` zero hex chars."""
    prefix = "0" * difficulty
    started = time.time()
    for nonce in range(MAX_NONCE):
        digest = hashlib.sha256(f"{random_data}{nonce}".encode()).hexdigest()
        if digest.startswith(prefix):
            return nonce, digest, time.time() - started
    raise RuntimeError(f"no nonce found below {MAX_NONCE} at difficulty {difficulty}")


def fetch(path: str, timeout: int = 30) -> tuple[int, str]:
    """Return (status, body) for `path`, clearing Anubis first if challenged."""
    opener = _opener()
    url = f"{BASE}{path}"

    try:
        with opener.open(url, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
            status = resp.status
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")

    match = CHALLENGE_RE.search(body)
    if not match:
        return status, body

    challenge = json.loads(match.group(1))["challenge"]
    nonce, digest, elapsed = _solve(
        challenge["randomData"], int(challenge["difficulty"])
    )
    query = urllib.parse.urlencode(
        {
            "id": challenge["id"],
            "response": digest,
            "nonce": str(nonce),
            "redir": path,
            "elapsedTime": str(int(elapsed * 1000)),
        }
    )
    try:
        opener.open(f"{BASE}{PASS_PATH}?{query}", timeout=timeout)
    except urllib.error.HTTPError:
        # A redirect or non-2xx here is fine; what matters is the cookie the
        # opener's jar just captured.
        pass

    try:
        with opener.open(url, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="AUR path, e.g. /register")
    parser.add_argument(
        "--print-body", action="store_true", help="write the page body to stdout"
    )
    args = parser.parse_args()

    try:
        status, body = fetch(args.path)
    except (urllib.error.URLError, RuntimeError, TimeoutError) as exc:
        print(f"transport error: {exc}", file=sys.stderr)
        return 2

    print(status)
    if args.print_body:
        sys.stdout.write(body)
    return 0 if status == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
