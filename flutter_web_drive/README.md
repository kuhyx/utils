# flutter_web_drive

Headless, LLM-friendly driver for Flutter web apps. An agent can navigate and
test a desktop app (a Flutter web build in a Chrome `--app` window, the way
kartka and todo ship) **without touching the real screen, mouse or keyboard**.

- A long-lived **headless** chromium runs as a `systemd-run --user` unit with a
  persistent profile. It has to be a unit because `setsid` children die with
  the calling Bash scope.
- Each CLI verb attaches over CDP, does one thing and exits. **The exit code
  is the verdict.** On failure it prints one stderr line naming the step that
  failed.
- Widgets are addressed through Flutter's **semantics tree**. Flutter paints
  to a canvas, so the accessibility mirror (`[id^=flt-semantic-node-]`) is the
  only addressable view. The driver switches it on by clicking
  `flt-semantics-placeholder`. The app's `lib/` needs no changes.

## Spike result (2026-10-24, chromium 155, Flutter 3.47.8 CanvasKit)

`--headless=new` + CDP `Page.captureScreenshot` **renders CanvasKit frames
correctly**. (The old `--headless` `--screenshot` path was blank.) **No Xvfb
is needed**, and none is used.

Other findings from the spike:
- Semantics enabled once stay enabled across later CDP connections.
- Console messages and exceptions are replayed on `Runtime.enable` /
  `Log.enable`, so `console` works from a fresh attach.
- The viewport is smaller than `--window-size`: 1400x1000 gives 1400x879.
  `start` reports the real viewport.

## Safety

- Every attach reads `/json/version`. It **refuses any browser that is not
  `HeadlessChrome`** (exit 4). For example, Steam's CEF listens on 9222 on
  this PC. Never point the driver at 9222.
- The unit unsets `DISPLAY`/`WAYLAND_DISPLAY`. `--password-store=basic` keeps
  chromium away from the desktop keyring, which could prompt on :0.
  `--disable-extensions` drops the Claude extension that chromium-flags.conf
  loads.
- `start` refuses a CDP port that some other browser already answers on.
- Secrets go through `text --stdin` / `text --file PATH` (MCP: `from_file`),
  never argv. `tree` shows password fields as `*`.

## CLI

```bash
export PYTHONPATH=~/src/utils
D="python3 -m flutter_web_drive --app myapp"   # --app namespaces state/artefacts
$D start --url http://127.0.0.1:47392/ --profile ~/.local/share/myapp-agent/profile \
         --cdp-port 9342 [--unit fwd-myapp] [--size 1400x1000]
$D tree [--filter TEXT] [--row LABEL] [--all]
$D tap "Browse" [--contains]          # exact label or one line of it
$D tap-xy 40 100
$D text "hello" | $D text --stdin | $D text --file ~/.config/x/password
$D key Enter                          # Escape Tab Backspace Delete Space Arrow* Home End PageUp PageDown
$D scroll 0 600 [--at X Y]
$D wait "Sync now" [--timeout S<=50] [--contains] [--gone] [--flag current] [--row LABEL]
$D shot [OUT.png] [--min-colours 16]  # prints "path WxH colours=N stddev=S"
$D eval "location.href"
$D console [--limit 20] [--warnings] [--fail-on-error]
$D stop
```

`tree` prints one line per node:

```
#5 button "Browse | Tab 2 of 4" [tap,current] @0,75 80x67
#73 textbox "Sync account email" = "me@example.com" [focused] @16,203 1368x48
```

- `[tags]`: `tap` (tappable), `current`, `selected`, `checked`, `mixed`,
  `pressed`, `expanded`, `disabled`, `focused`.
- `= value` is the field value, `aria-valuenow` or `aria-description`. For
  example, an ExpansionTile reads `"Collapsed"`.
- `--row LABEL` keeps the nodes inside the row of that label, e.g. a chapter
  row's "Mark unread" button: `wait "Mark unread" --row "Chapter 5"`.
- `tap` prefers tappable matches and says when there were several. When
  nothing matches, it lists what is tappable.

Exit codes: `0` ok, `1` the step's check failed (not found, timeout, page
exception, blank shot), `2` usage, `3` no driver browser (not started or
crashed), `4` the CDP port belongs to a non-headless browser.

Artefacts (screenshots, `state.json`) go to `~/data/claude-scratch/e2e/<app>/`
(override with `$FWD_ARTEFACTS`), never to /tmp. A `wait` timeout saves
`wait-timeout-*.png` and names it in the error.

## MCP server

`mcp_server.py` is a thin stdio server (mcp 2.x `MCPServer`). Its tools match
the verbs: `start stop shot tree tap tap_xy text key scroll wait eval_js
console`, each taking `app`. Every tool is one `Driver` call, so no logic is
duplicated. Register it (user scope):

```bash
claude mcp add flutter-web-drive -s user -e PYTHONPATH=$HOME/src/utils \
  -- python3 -m flutter_web_drive.mcp_server
```

## Layout

| file | role |
|---|---|
| `cdp.py` | websocket session, page discovery, headless check |
| `semantics.py` | the JS snippets, `Node`, matching, row scoping, tree format |
| `actions.py` / `keys.py` | verbs on one attached page |
| `browser.py` / `state.py` | chromium argv, `systemd-run` unit, per-app state |
| `api.py` | `Driver`: the verbs the CLI and the MCP server share |
| `cli.py` / `mcp_server.py` | the two front ends |

Tests (`tests/`, 100 % branch, no network or browser) use a fake CDP page.
The real-browser check is a consumer flow, e.g.
`~/src/kartka/tools/agent/flows/f0_smoke.sh`.

```bash
PYTHONPATH=. python -m pytest -q flutter_web_drive/tests \
  --cov=flutter_web_drive --cov-branch --cov-fail-under=100
ruff check flutter_web_drive && ruff format --check flutter_web_drive
pip install --user -r flutter_web_drive/requirements.txt
```
