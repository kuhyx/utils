extends Node
## The dev feedback mode. A game adds this node (after `setup(host)`, see
## dev_host.gd) when it was started with --dev; nothing of the addon belongs in
## an exported build.
##   F12  freeze the frame and annotate it (rect/arrow/circle/pen/text/select
##        + note) -> a bundle folder + a Markdown entry + a jsonl line. The
##        camera glyph (top right) and the game's pause menu entry do the same.
##   F9   reset the game's saved progress (when its host can)
##   always: every key / button press and the host's moments are logged
##   --dev-shot=/abs/out.png  scripted annotate-and-save into the folder
##        /abs/out/ (bundle + overlay.png), then quit (Xvfb proof)
## While the annotator is open it is in the group "annotator": a game leaves
## Esc and the mouse alone then.
## No class_name (the addon's scripts reach each other with relative preload).

const DevAnnotator = preload("annotator.gd")
const DevFrame = preload("dev_frame.gd")
const DevHost = preload("dev_host.gd")
const DevLog = preload("dev_log.gd")
const DevFeedbackContext = preload("feedback_context.gd")
const DevGlyphs = preload("dev_glyphs.gd")
const DevHint = preload("dev_hint.gd")
const DevStyle = preload("dev_style.gd")
const DevTelemetry = preload("telemetry.gd")
const SHOT_PREFIX := "--dev-shot="
const LAYER := 120
const PROBE_GRID := Vector2i(48, 27)
const MENU_ENTRY := "annotate"

var host: RefCounted
var dev_log: RefCounted
var telemetry := DevTelemetry.new()
var annotator: Control = null
var hint: Control

var _layer: CanvasLayer
var _shot_path := ""


## Hands the game in: `impl` is its host object (any Object, see dev_host.gd).
## Call before add_child.
func setup(impl: Object) -> void:
	host = DevHost.new(impl)
	DevStyle.apply(host.colors())
	dev_log = DevLog.new(host.game(), host.feedback_env())


func _ready() -> void:
	if host == null:
		setup(null)
	process_mode = Node.PROCESS_MODE_ALWAYS
	_layer = CanvasLayer.new()
	_layer.layer = LAYER
	add_child(_layer)
	hint = DevHint.new()
	hint.pressed.connect(func() -> void: annotate())
	_layer.add_child(hint)
	host.add_menu_entry(MENU_ENTRY, DevGlyphs.texture("camera"), "annotate", _annotate_from_menu)
	dev_log.write("dev tools on; logs in %s" % dev_log.dir)
	telemetry.attach(dev_log, host)
	_shot_path = dev_log.arg_value(OS.get_cmdline_user_args(), SHOT_PREFIX)
	if _shot_path != "":
		_scripted_shot.call_deferred()


func _process(_delta: float) -> void:
	telemetry.tick()


func _input(event: InputEvent) -> void:
	_log_input(event)
	var key := event as InputEventKey
	if key == null or not key.pressed or key.echo:
		return
	if key.keycode == KEY_F12:
		get_viewport().set_input_as_handled()
		annotate()
	elif key.keycode == KEY_F9 and host.can_reset():
		get_viewport().set_input_as_handled()
		var removed: int = host.reset_progress()
		dev_log.write("reset progress: %d files removed" % removed)
		telemetry.entry("reset_progress", {"files": removed})


## The window's close button / Alt-F4 / SIGTERM reach every node in the tree.
func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_CLOSE_REQUEST:
		telemetry.shutdown("window_close")


func _exit_tree() -> void:
	telemetry.shutdown("exit")


## Freezes the game and opens the annotator over the frame as it was; the
## previous pause state comes back on close. `path` = scripted marks and save.
func annotate(path := "") -> void:
	if annotator != null:
		return
	var was_paused := get_tree().paused
	var state: Dictionary = host.debug_state()
	var context := DevFeedbackContext.capture(host, get_tree(), dev_log, was_paused, state)
	hint.hide()
	get_tree().paused = true
	var frame: Image = await DevFrame.grab(get_viewport())
	annotator = DevAnnotator.new()
	annotator.save_path = path
	annotator.markdown_hooks = host.markdown_hooks()
	_layer.add_child(annotator)
	annotator.open(frame, dev_log, context, state)
	annotator.picker = func(at: Vector2) -> Dictionary: return host.pick_at(at)
	if path != "":
		await _scripted_marks(path)
		annotator.save()
	await annotator.closed
	annotator.remove_from_group(&"annotator")  # Esc is the game's again now
	annotator.queue_free()
	annotator = null
	hint.show()
	get_tree().paused = was_paused


## The pause menu's camera: the menu goes away first, so the frame is the game.
func _annotate_from_menu() -> void:
	host.close_menu()
	await get_tree().process_frame
	annotate()


func _scripted_shot() -> void:
	await get_tree().create_timer(1.5).timeout
	await annotate(_shot_path.get_basename())
	var png := _shot_path.get_basename().path_join("annotated.png")
	get_tree().quit(0 if FileAccess.file_exists(png) else 1)


## The marks a mouse would draw, and a frame of the overlay itself
## (<bundle>/overlay.png, toolbar visible) for a human to read, with a label
## and a select mark on the first thing the current screen lets you pick.
func _scripted_marks(dir: String) -> void:
	annotator.add_shape("rect", Vector2(260, 220), Vector2(760, 640))
	annotator.add_shape("arrow", Vector2(1100, 300), Vector2(820, 420))
	annotator.add_shape("circle", Vector2(1150, 600), Vector2(1500, 860))
	var squiggle := [Vector2(300, 800), Vector2(380, 760), Vector2(460, 820)]
	annotator.add_stroke(PackedVector2Array(squiggle))
	annotator.add_text(Vector2(300, 860), "wrong place?")
	var target := first_pickable()
	if target != Vector2.INF:
		annotator.select_at(target)
	var overlay: Image = await DevFrame.grab(get_viewport())
	DirAccess.make_dir_recursive_absolute(dir)
	overlay.save_png(dir.path_join("overlay.png"))


## The first canvas point of a coarse grid where the screen has something to
## select (Vector2.INF when it has nothing).
func first_pickable() -> Vector2:
	var view := get_viewport().get_visible_rect().size
	for y in PROBE_GRID.y:
		for x in PROBE_GRID.x:
			var at := Vector2((x + 0.5) / PROBE_GRID.x, (y + 0.5) / PROBE_GRID.y) * view
			if not host.pick_at(at).is_empty():
				return at
	return Vector2.INF


func _log_input(event: InputEvent) -> void:
	if not event.is_pressed() or event.is_echo():
		return
	if event is InputEventKey or event is InputEventJoypadButton or event is InputEventMouseButton:
		dev_log.write("input %s" % event.as_text())
