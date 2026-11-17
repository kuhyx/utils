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
"rtdb-relay @ git+https://github.com/kuhyx/utils@rtdb-relay-v0.1.1#subdirectory=rtdb_relay"
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

## Dart API (the Flutter client, `dart/`)

```yaml
rtdb_relay:
  git:
    url: https://github.com/kuhyx/utils
    ref: rtdb-relay-v0.2.0
    path: rtdb_relay/dart
```

`import 'package:rtdb_relay/rtdb_relay.dart';` The tutor app uses it since
v0.2.0 (`lib/sync/*.dart` there are thin tutor bindings: a worked example).
A request is written by the app and answered by the worker; the app never
writes `claim` or `result`.

- `RelayLayout(String base, {required List<String> clear, required
  Map<String, Set<String>> units})`: the tree rules, same patterns as the
  Python `Layout`. `root` is crdt_sync's e2e prefix of `base`
  (`todoimpl/v1` -> `todoimpl/v1-e2e`); the passphrase header lives at
  `<base>/e2e`. Start from `kRelayClear` + `kRelayUnits` (claim clear;
  `requests/*/req` keeps `created`, `requests/*/result` keeps `at`,
  `presence/workers/*` keeps `beat`). `classify(parts) -> E2eRule`,
  `unitPath(rel) -> String?`, `rel(path) -> String?`. Unknown paths throw
  `E2eLayoutError` on write.
- `RelaySealer(E2eCipher cipher, {required RelayLayout layout, String?
  root})`: `seal(rel, value)`, `sealPatch(rel, body)`, `open(rel, value)`.
  `E2eGate` makes one for you; build it by hand only in tests.
- `RtdbClient({required RelayLayout layout, required String databaseUrl,
  required IdTokenSource idToken, http.Client? httpClient, String?
  namespace, RelaySealer? sealer, bool sealRequired = false})`:
  `get(path, {query})`, `keys(path)`, `getTagged(path) -> Tagged`,
  `put(path, value)`, `putIfMatch(path, value, etag) -> ConditionalResult`,
  `deleteIfMatch(path, etag)`, `patch(path, Map)`, `delete(path)`,
  `close()`. Paths are full (`<root>/requests/<rid>/req`). Errors are
  `RtdbError` (`isAuth`, `isTransient`); with `sealRequired` nothing under
  the root is sent before the key is unlocked. `keyRangeQuery(startAt)`
  gives the `$key`-ordered range query (the only index the rules allow).
- `RtdbStream(RtdbClient client, {Sleep? sleep})`: `listen(path, {query})
  -> Stream<RtdbEvent>` (SSE, reconnects with backoff, opens sealed
  units; events `RtdbPut`, `RtdbPatch`, `RtdbConnected`,
  `RtdbDisconnected`, ...). `applyEvent(tree, event)`, `getAt(tree, path)`
  and `setAt(tree, path, value)` keep a local copy of a streamed node.
- `RequestHub(RtdbStream stream, String requestsPath)`: one ranged listen
  for every request in flight. `watch(rid) -> Stream<Object?>` yields the
  `requests/<rid>` node (`req`, `claim`, `result`) each time it changes;
  `inFlight` counts the followed requests. To send: `put('<root>/requests/
  <rid>/req', {'kind': k, 'dev': deviceId, 'created': {'.sv':
  'timestamp'}, 'sent_at': ms, 'body': {...}})` with a fresh ULID `rid`,
  then `watch(rid)` until `result` appears (`ok`, or `code`/`error`/`retry`).
- `RevWatcher(RtdbStream stream, String path, {WidgetsBinding? binding,
  ValueListenable<int>? yieldTo})`: `changesOf(key) -> Stream<int>` emits
  real moves of `rev/<key>` only; pauses while the app is hidden and while
  `yieldTo` (pass `RequestHub.inFlight`) is above 0. `revOf(rev, key)`,
  `foregroundFor(state)`.
- `E2eGate({required RtdbClient client, FlutterSecureStorage storage,
  Argon2Params params})`: `unlock() -> Future<bool>` opens the key from the
  keystore passphrase (crdt_sync_flutter) and sets `client.sealer`;
  `locked`, `reason`.
- `RelayFirebaseConfig({apiKey, databaseUrl, syncUid, serverClientId})`
  (const; keep the values in a gitignored generated file) and
  `RelayAuth({required RelayFirebaseConfig config, required
  GoogleTokenFetcher googleToken, required FirebaseCredentialStore store,
  http.Client? httpClient, DateTime Function()? clock, Future<bool>
  Function()? adopt})`: `hasSession()`, `signInWithGoogle({tokenFetcher})
  -> SignInOutcome` (refuses a Google account whose uid is not
  `syncUid`), `idToken()` (pass `auth.idToken` to `RtdbClient`),
  `signOut()`. `googleToken`: crdt_sync_flutter's `googleIdToken`.
  `secureCredentialStore(String key)` is the keystore-backed store.
- Desktop (web in a Chrome `--app` window): `adoptWrapperCredentials(base:,
  client:, store:, expectedUid:)` takes the PC server's seeded session once
  from `<base>sync-credentials`; pass it as `RelayAuth.adopt`.

Develop: `cd dart && fvm flutter test --coverage &&
scripts/check_coverage.sh coverage/lcov.info 100`; `fvm flutter analyze`.
`test/data/e2e_vectors.json` (the tutor's contract vectors) and
`test/differential_test.dart` (the tutor's pre-extraction sealer, frozen in
`test/support/`) pin the wire format.

## Develop (Python)

`uv venv --python 3.15 .venv && uv pip install -e . pytest==9.2.0
pytest-cov==7.1.0 ruff==0.17.4 mypy==2.4.1`, then `scripts/run_subproject_tests.sh rtdb_relay`
from the repo root (100 % branch coverage), `ruff check .` and `mypy rtdb_relay`.
