# kuhy_credit

One "Created by kuhy" credit for every kuhy repo. The user sees the M1 logo. A
click or tap opens a small panel with the logo and the words "Created by kuhy".
A click or tap on the panel opens https://kuhy.duckdns.org in the system
browser. Escape, a click outside the panel and a second logo click close it.
Nothing loads over the network and nothing opens without a click.

## Where the data lives

- `credit.json` holds the URL, the text and the paths of the two sources it
  reads: the M1 art (`unified-design-system/logo/final/kuhy.svg`) and the
  design tokens (`web_ui/src/tokens.css`).
- `generator/generate.py` writes each stack's data file from those sources.
  Never edit a generated file by hand:

  | Stack    | Generated file                            |
  | -------- | ----------------------------------------- |
  | python   | `kuhy_credit/_data.py`                    |
  | web      | `web/src/credit-data.js`                  |
  | flutter  | `flutter/lib/src/credit_data.g.dart`      |
  | godot    | `godot/addons/kuhy_credit/credit_data.gd` |
  | terminal | `terminal/kuhy-credit.sh`                 |

- `python -m generator.generate --check` (from `kuhy_credit/`) fails and names
  every stack whose file differs from the sources. CI runs it on every push.

## Decisions (change them here if you disagree)

- Placement: web footer, Flutter about screen, Godot main-menu corner. The
  panel opens above the logo, aligned to its end edge; each stack has a
  "below" and a "start" option.
- Lockers and gate windows get no credit. The Tk widget ships but no locker
  uses it.
- Distribution: a git dependency pinned to the tag `kuhy-credit-v<version>`
  (version in `pyproject.toml`, `web/package.json` and
  `flutter/pubspec.yaml`, kept equal). Never copy the files into a repo by hand.

## Web (plain HTML, Astro, React/Vite)

```jsonc
// package.json
"@kuhyx/kuhy-credit": "github:kuhyx/utils#kuhy-credit-v0.1.0&path:kuhy_credit/web"
```

```html
<script type="module">import "@kuhyx/kuhy-credit";</script>
<footer><kuhy-credit></kuhy-credit></footer>
```

In Astro, put the same `import` in a `<script>` tag of the layout. In React
19, call `import "@kuhyx/kuhy-credit";` once and render `<kuhy-credit />`;
the `.d.ts` adds the JSX type. Attributes: `placement="below"`,
`align="start"`, `theme="light|dark"` (default: follow the page). The size
comes from `--kuhy-credit-size` (default 48px). Colours come from the page's
`tokens.css` variables when they exist, else from the generated token values.

Demo: `python3 -m http.server -d . 8765` from the repo root, then open
http://127.0.0.1:8765/kuhy_credit/web/demo/index.html (`?theme=light` forces
the light theme).

## Flutter (Android and web)

```yaml
dependencies:
  kuhy_credit:
    git:
      url: https://github.com/kuhyx/utils
      ref: kuhy-credit-v0.1.0
      path: kuhy_credit/flutter
```

```dart
import 'package:kuhy_credit/kuhy_credit.dart';

const KuhyCredit() // e.g. at the bottom of the about screen
```

The widget opens the site with `url_launcher` (a new tab on web, the browser
app on Android). Back closes an open panel. Demo: `flutter/example`.

## Godot 4.7

```bash
cache="$(mktemp -d)"
git clone --depth 1 --branch kuhy-credit-v0.1.0 https://github.com/kuhyx/utils "$cache"
cp -r "$cache/kuhy_credit/godot/addons/kuhy_credit" addons/
```

```gdscript
var credit: Control = preload("res://addons/kuhy_credit/kuhy_credit.tscn").instantiate()
credit.light = false  # true on a light menu
$MainMenu.add_child(credit)  # then place it in a corner
```

The script opens the site with `OS.shell_open`. Demo:
`godot --path kuhy_credit/godot` (`-- --light` for the light theme).

## Python / Tkinter

```bash
pip install "kuhy-credit @ git+https://github.com/kuhyx/utils@kuhy-credit-v0.1.0#subdirectory=kuhy_credit"
```

```python
from kuhy_credit.tk import KuhyCredit

KuhyCredit(root, theme="dark").place(relx=1, rely=1, x=-16, y=-16, anchor="se")
```

The widget opens the site with `webbrowser` (a new tab). Tk has no rounded
corners and no accessibility tree, so those two parts of the design do not
apply there. Demo: `python -m kuhy_credit.demo [--light]`.

## Terminal programs

```bash
kuhy-credit                          # after the pip install above
bash kuhy_credit/terminal/kuhy-credit.sh   # no Python needed
```

```python
from kuhy_credit import credit_line
print(credit_line())  # Created by kuhy https://kuhy.duckdns.org
```

## Tests

| Stack           | Command (from `kuhy_credit/`)                                   |
| --------------- | --------------------------------------------------------------- |
| python + drift  | `xvfb-run -a python -m pytest` (100% branch coverage)           |
| web             | `cd web && pnpm install && pnpm coverage` (100%)                |
| web E2E         | `PYTHONPATH=.. python3 e2e/web_e2e.py`                          |
| flutter         | `cd flutter && flutter test --coverage` (100% lines)            |
| flutter web E2E | build `flutter/example` for web, then `python3 e2e/flutter_web_e2e.py` |
| godot + E2E     | `godot/test.sh` (GUT; `tests/test_demo_e2e.gd` is the E2E)      |
| Tk E2E          | part of the pytest run: `tests/test_tk_e2e.py`                  |

Every E2E clicks the logo, then the panel, and checks the URL the stubbed
browser launch received.
