# godot_dev_tools

The dev feedback mode of kuhy's Godot games, as one addon every game mounts at
a pinned tag. Press F12 in a `--dev` run: the frame freezes, you draw red marks
over it (rect, arrow, circle, pen, text label, select a game object), type an
optional note, press Enter, and a bundle folder lands in the game's feedback
folder. `feedback_inbox` (this repo) turns each bundle into a todo task.

First written by kuhy for one of his Godot games, generalised here into a host
interface.

Godot 4.7.2, GDScript. Version in `addons/dev_tools/dev_tools.cfg`; the tag is
`godot-dev-tools-v<version>`.

## Layout

| Path | Holds |
|---|---|
| `addons/dev_tools/` | the addon: the only folder a game mounts |
| `tests/` | GUT tests and a stub host (`tests/stub_host.gd`) |
| `project.godot` | the stub host project the tests run in |
| `test.sh` | fetches GUT at its pinned tag, runs the tests headless (about 2 s) |
| `lint.sh` | gdlint + gdformat --check (gdtoolkit pinned in `requirements-dev.txt`) |

The addon scripts have no `class_name` (they stay out of the global class cache,
so a game that excludes the folder from exports loses nothing) and reach each
other by relative `preload`, so the mount path is yours to choose, under
`Dev`-prefixed aliases (a game's own `class_name` Style or Frame cannot shadow them). They name no
class of any game, ship no image or sound (the icons are vector shapes), and
show no text: every icon-only control carries an `accessibility_name`, and the
only words on screen are the ones the developer types.

## Mount it in a game

Pin the tag, never copy the folder and never use a submodule. Fetch the repo at
the tag (shallow), then link or copy `godot_dev_tools/addons/dev_tools` to
`res://addons/dev_tools` and gitignore that path:

```bash
git clone --depth 1 --branch godot-dev-tools-v0.1.0 https://github.com/kuhyx/utils "$cache"
ln -sfn "$cache/godot_dev_tools/addons/dev_tools" addons/dev_tools   # CI: cp -a instead
```

Load it only for `--dev` runs, and only if it is there (an export has none of
it, and a missing mount must not stop the game):

```gdscript
const ADDON := "res://addons/dev_tools/dev_tools.gd"

if options.dev and ResourceLoader.exists(ADDON):
	var tools: Node = (load(ADDON) as GDScript).new()
	tools.setup(MyHost.new(self))   # before add_child
	add_child(tools)
```

Exclude `addons/dev_tools/*` from every export preset, and keep the host glue
out of exports too.

## The host interface

`setup(host)` takes ONE object of the game's own: any Object, no base class,
no addon path in its source. The addon calls only what the object has and
falls back to a default for the rest (`dev_host.gd` documents each member):

| Member | Meaning | Default |
|---|---|---|
| `game` | game name: `~/data/<game>_binaries/feedback`, bundle field `game` | `"game"` |
| `feedback_env` | env variable overriding the feedback folder | `"DEV_FEEDBACK_DIR"` |
| `colors` | `{mark, armed, panel, panel_pressed, ink}` overrides | the addon's own |
| `debug_state()` | the whole visible state as data: `snapshot.json` | `{}` |
| `pick_at(at)` | the game object under a canvas point, `{}` for none | no select tool |
| `context(state)` | game fields of the bundle (mode, screen, combo, pose...) | `{}` |
| `reset_progress()` | F9: wipe saved progress, return files removed | F9 does nothing |
| `add_menu_entry(id, icon, spoken, on_press)` | put the camera into the pause menu | none |
| `close_menu()` | close that menu before a frame is frozen | none |
| `attach_telemetry(t)` | connect game signals to `t.entry(event, fields)` | none |
| `summary_line(record)` | the Markdown entry's game line | the `Game ..., combo ...` line |
| `entity_line(entity)` | the Markdown entry's selected-object line | a generic line |

Keep `summary_line` out unless the game cannot fill the default's `game` and
`combo` fields: `feedback_inbox` parses `- Game `x`, combo `y``.

## Keys and arguments

F12 annotate (also the camera glyph top right and the pause menu entry), F9
reset. In the annotator: R A C P T S pick rect / arrow / circle / pen / text /
select, Ctrl+Z undo, Enter save, Esc cancel (with unsaved work the first press
only arms the cross). While it is open it sits in the group `annotator`:
a game leaves Esc and the mouse alone then.

Command line (after `--`): `--dev-shot=/abs/out.png` scripted annotate and save
into `/abs/out/` then quit, `--feedback-dir=DIR`, `--save-dir=DIR` (logs go to
`DIR/dev`), `--session-id=ID`, `--dev-tag=T`. The feedback folder is, first
match: `--feedback-dir`, `--save-dir`, the host's env variable,
`~/data/<game>_binaries/feedback` on `--dev` when that `<game>_binaries`
directory exists, else `user://dev`. A headless run
(a bot, a test) gets a blank frame instead of a screenshot.

## The bundle on disk (the contract `feedback_inbox` reads)

`<feedback dir>/<YYYY-MM-DDTHH-MM-SS-mmm>/` holds `screenshot.png`,
`annotated.png` (marks burned in), `report.json`, `game.log` (tail of
`dev.log`) and `snapshot.json`. `report.json` carries `kind` (`annotation`),
`time`, `note`, `session`, `build`, `godot`, `game`, the host's `context`
fields, `paused`, `scene`, `window`, `canvas`, `shapes` and `selected` (in
`annotated.png` pixels), `image` and `files` (absolute paths). Beside it
`feedback-<date>.md` gets one `## <time>: <note>` section per bundle, ending in
a ready-to-run prompt, and `feedback.jsonl` one line per moment (`annotation`
on save, plus `session_start`, `recording_sync`, `engine_error`, `session_end`
and whatever the host's telemetry adds).

## Tests

```bash
godot_dev_tools/test.sh                        # all, under 60 s
godot_dev_tools/test.sh -gselect=test_dev_host  # one file
godot_dev_tools/lint.sh
```

CI: `.github/workflows/godot-dev-tools-tests.yml` (path-filtered).
