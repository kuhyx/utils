extends RefCounted
## What the dev tools know about the game they sit in. A game hands in ONE
## object (any Object: a RefCounted of its own, no base class, no addon path in
## its source) and this wrapper asks it, with a default for everything the game
## does not provide. A method the object lacks is simply not called.
##
## Values (a property or a method of the same name, either works):
##   game            name of the game: the folder ~/data/<game>_binaries/feedback
##                   and the "game" field of a bundle (default "game")
##   feedback_env    environment variable that overrides the feedback folder
##                   (default DEV_FEEDBACK_DIR)
##   colors          Dictionary, keys mark armed panel panel_pressed ink (dev_style.gd)
## Methods:
##   debug_state() -> Dictionary        the whole visible state: snapshot.json
##   pick_at(at: Vector2) -> Dictionary the game object under a canvas point ({} = none)
##   context(state: Dictionary) -> Dictionary
##                                      game fields of the bundle (mode, screen, ...)
##   reset_progress() -> int            F9: wipe saved progress, return files removed
##                                      (without it F9 does nothing)
##   add_menu_entry(id, icon, spoken, on_press) -> void
##                                      put the camera into the game's pause menu
##   close_menu() -> void               close that menu before a frame is frozen
##   attach_telemetry(telemetry) -> void
##                                      connect the game's signals to telemetry.entry(
##                                      event: String, fields: Dictionary)
##   summary_line(record) -> String     the Markdown entry's "Game ..." line
##   entity_line(entity) -> String      the Markdown entry's "Selected ..." line
## No class_name (the addon's scripts reach each other with relative preload).

const DEFAULT_GAME := "game"
const DEFAULT_ENV := "DEV_FEEDBACK_DIR"

var _impl: Object


func _init(impl: Object = null) -> void:
	_impl = impl


func game() -> String:
	return str(_value("game", DEFAULT_GAME))


func feedback_env() -> String:
	return str(_value("feedback_env", DEFAULT_ENV))


func colors() -> Dictionary:
	return _value("colors", {})


func debug_state() -> Dictionary:
	return _call("debug_state", [], {})


func pick_at(at: Vector2) -> Dictionary:
	return _call("pick_at", [at], {})


func context(state: Dictionary) -> Dictionary:
	return _call("context", [state], {})


func can_reset() -> bool:
	return _has("reset_progress")


func reset_progress() -> int:
	return _call("reset_progress", [], 0)


func add_menu_entry(id: String, icon: Texture2D, spoken: String, on_press: Callable) -> void:
	_call("add_menu_entry", [id, icon, spoken, on_press], null)


func close_menu() -> void:
	_call("close_menu", [], null)


func attach_telemetry(telemetry: RefCounted) -> void:
	_call("attach_telemetry", [telemetry], null)


## {summary_line, entity_line} Callables for feedback_entry.gd (only the ones the game has).
func markdown_hooks() -> Dictionary:
	var hooks := {}
	for hook: String in ["summary_line", "entity_line"]:
		if _has(hook):
			hooks[hook] = Callable(_impl, hook)
	return hooks


func _has(member: String) -> bool:
	return _impl != null and _impl.has_method(member)


## A method's answer, else a property of the same name, else `fallback`.
func _value(member: String, fallback: Variant) -> Variant:
	if _has(member):
		return _impl.call(member)
	if _impl != null and member in _impl:
		return _impl.get(member)
	return fallback


func _call(member: String, args: Array, fallback: Variant) -> Variant:
	return _impl.callv(member, args) if _has(member) else fallback
