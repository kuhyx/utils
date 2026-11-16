extends RefCounted
## The few colours of the dev tools. The defaults suit any game; a host (see
## dev_host.gd) can restyle them through its `colors()` keys: mark, armed,
## panel, panel_pressed, ink. Shared by every script of the addon, set once by
## dev_tools.gd before any widget is built.
## No class_name (the addon's scripts reach each other with relative preload).

const DEFAULT_MARK := Color("#FF2626")
const DEFAULT_ARMED := Color("#FF5959")
const DEFAULT_PANEL := Color("#0F121A")
const DEFAULT_PANEL_PRESSED := Color("#333B4D")
const DEFAULT_INK := Color("#FFFFFF")

## The red of the marks and the label text.
static var mark := DEFAULT_MARK
## The cancel button after a first press with unsaved work.
static var armed := DEFAULT_ARMED
## Dark strips, label outlines, the hint's shadow.
static var panel := DEFAULT_PANEL
## The note field's background.
static var panel_pressed := DEFAULT_PANEL_PRESSED
## The hint glyph.
static var ink := DEFAULT_INK


## Takes the host's overrides over the defaults (an unknown key is ignored).
static func apply(colors: Dictionary) -> void:
	mark = colors.get("mark", DEFAULT_MARK)
	armed = colors.get("armed", DEFAULT_ARMED)
	panel = colors.get("panel", DEFAULT_PANEL)
	panel_pressed = colors.get("panel_pressed", DEFAULT_PANEL_PRESSED)
	ink = colors.get("ink", DEFAULT_INK)
