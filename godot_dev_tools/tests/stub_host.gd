extends RefCounted
## A minimal host for the dev_tools addon: what a game would hand in, with a
## fixed answer for everything, and a record of what the addon asked of it.
## No class_name (tests load it by path).

var game := "stub-game"
var feedback_env := "STUB_FEEDBACK_DIR"
var colors := {"mark": Color(0.0, 1.0, 0.0)}
var menu: Array = []
var menu_closed := 0
var resets := 0
var telemetry: RefCounted = null


func debug_state() -> Dictionary:
	return {"screen": "hub", "items": [{"id": "thing"}]}


func pick_at(at: Vector2) -> Dictionary:
	if at.x < 100.0:
		return {"kind": "stub", "id": "thing", "state": "idle", "position": [at.x, at.y]}
	return {}


func context(state: Dictionary) -> Dictionary:
	return {"screen": state["screen"], "mode": "stub", "variant": {"seed": 7}}


func reset_progress() -> int:
	resets += 1
	return 3


func add_menu_entry(id: String, icon: Texture2D, spoken: String, on_press: Callable) -> void:
	menu.append({"id": id, "icon": icon, "spoken": spoken, "press": on_press})


func close_menu() -> void:
	menu_closed += 1


func attach_telemetry(p_telemetry: RefCounted) -> void:
	telemetry = p_telemetry
	telemetry.entry("host_attached", {"game": game})


func summary_line(record: Dictionary) -> String:
	return "- Stub screen `%s`" % record.get("screen", "-")
