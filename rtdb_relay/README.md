# rtdb_relay

A sealed request relay over Firebase RTDB: a phone app writes a request, a
worker on the PC answers it. No VPN, no open port: both sides talk only to
RTDB over HTTPS. Access needs the one Google account the RTDB rules allow,
and every value is sealed end to end with the shared crdt-sync passphrase.

Extracted from `kuhyx/tutor` (`tutor/relay/`), whose phone app has used this
wire format since 2026-10. The tutor's contract vectors
(`rtdb_relay/tests/data/e2e_vectors.json`) pin the byte format; the tests
check that the package seals and opens exactly those bytes.

Python 3.14+ (tested on 3.15.2). Install from a release tag:

```toml
"rtdb-relay @ git+https://github.com/kuhyx/utils@rtdb-relay-v0.1.0#subdirectory=rtdb_relay"
```

## Wire format (under the app's root, e.g. `todoimpl/v1-e2e`)

| Path | Who writes | Value |
|---|---|---|
| `requests/{rid}/req` | client | sealed `{kind, dev, created, sent_at, body}`; `created` clear |
| `requests/{rid}/claim` | worker | clear `{by, lease_until, attempt, phase, at}` (ms) |
| `requests/{rid}/result` | worker | sealed `{ok, kind, ...data}` or `{ok: false, kind, code, error, retry}`; `at` clear |
| `presence/workers/{worker}` | worker | sealed `{host, version}`; `beat` clear (server time) |
| `<root minus -e2e>/e2e` | first unlock | the Argon2id key header (crdt_sync) |

`rid` is a ULID (`[0-9A-HJKMNP-TV-Z]{26}`); any other key is never used in
a path. A sealed unit is `{"_e2e": <XChaCha20-Poly1305 blob>, <clear
siblings>}`, the blob being crdt_sync's `E2eCipher` over compact JSON with the
unit's full path (`<root>/<path>`) as AAD, so a blob moved elsewhere does not
open.

## Python API (the PC worker)

```python
from crdt_sync import E2eCipher, E2eLayout
from rtdb_relay.layout import Layout, Rule, E2eLayoutError, parts_of
from rtdb_relay.seal import Sealer, SEALED
from rtdb_relay.rtdb import Rtdb, RtdbError, ConflictError, SERVER_TIME
from rtdb_relay.unlock import unlock
from rtdb_relay.server import RequestServer, RequestError
from rtdb_relay import presence, sse, mirror
```

- `Layout(root: str, clear: tuple[str, ...], units: dict[str, frozenset[str]])`:
  the tree rules. `*` matches one segment; a `clear` pattern covers its
  subtree; a unit maps to the clear fields it keeps. A write to a path with
  no rule raises `E2eLayoutError` (fail closed). A relay app needs at least
  `clear=("requests/*/claim",)` and units `requests/*/req: {"created"}`,
  `requests/*/result: {"at"}`, `presence/workers/*: {"beat"}`.
  `layout.classify(parts) -> Rule`, `layout.unit_path(path) -> str | None`.
- `Rtdb(database_url: str, token: Callable[[], Awaitable[str]], client:
  httpx.AsyncClient | None = None, *, root: str, sealer: Sealer | None = None)`:
  `get(path, params=None)`, `get_etag(path)`, `put(path, value)`,
  `put_etag(path, value, if_match)`, `patch(path, dict)`, `delete(path,
  if_match=None)`, `open_stream(path, params=None)`, `at(root) -> Rtdb` (raw,
  unsealed), `aclose()`. Errors never contain the URL or the token.
- `await unlock(raw_rtdb, passphrase: str, layout: E2eLayout, params:
  Argon2Params | None = None) -> E2eKey`: makes the header on first use;
  raises `E2eLockedError` on a missing or wrong passphrase. Then
  `Sealer(E2eCipher(key.master), layout)` and `Rtdb(..., root=layout.root,
  sealer=sealer)`.
- `RequestServer(rtdb: Rtdb, worker: str, handlers: Mapping[str, Handler],
  now: Callable[[], float] = time.time)` with `Handler = Callable[[dict[str,
  Any]], Awaitable[dict[str, Any]]]` (request `body` in, result data out).
  `await server.run()` watches `requests` until cancelled; `await
  server.answer(rid, raw_node)` serves one. A handler refuses with
  `raise RequestError(code, message, retry=False)`. Guards: unknown kind ->
  `unknown_kind`; unsealed or undecryptable `req` -> `unsealed`; a handler
  bug -> `internal` (logged); long handlers renew the lease every 60 s.
- `await presence.beat_forever(rtdb, worker, version)`: a beat every 30 s.
- `sse.listen(rtdb, path) -> AsyncGenerator[sse.Event]` (reconnects with
  backoff, opens sealed units); `mirror.apply(tree, event) -> dict` keeps a
  local copy of a streamed node. To publish a sealed snapshot node, `await
  rtdb.put("<unit path>", value)`.

## Dart API (the Flutter client)

Not extracted yet: the tutor app's `lib/sync/` and `lib/relay/` still hold
the client half. Until it moves here, a new client follows the wire format
above (`requests/{rid}/req` sealed with crdt_sync's Dart `E2eCipher`, then
listen on `requests/{rid}/result`).

## Develop

`uv venv --python 3.15 .venv && uv pip install -e . pytest==9.2.0
pytest-cov==7.1.0 ruff==0.17.4 mypy==2.4.1`, then `scripts/run_subproject_tests.sh rtdb_relay`
from the repo root (100 % branch coverage), `ruff check .` and `mypy rtdb_relay`.
