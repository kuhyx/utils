extends Control
## F12 (or the camera glyph): the frozen frame with red tools over it, text-free.
## Mouse: tool glyphs (rect, arrow, circle, pen, text label, select-entity), undo,
## clear (undoable), an optional note, save (check) or cancel (cross; with unsaved
## work the first press only arms it). Keys: R A C P T S tools, Ctrl+Z undo, Enter
## save, Esc cancel (in a text field it only leaves it). Save burns the marks in.

signal closed(saved_to: String)

const DevShapes = preload("annotate_shapes.gd")
const DevBar = preload("annotate_bar.gd")
const DevEntry = preload("feedback_entry.gd")
const DevFrame = preload("dev_frame.gd")
const DevSaver = preload("feedback_saver.gd")
const DevStyle = preload("dev_style.gd")
const LOG_TAIL := 200

var dev_log: RefCounted
var shapes: Array[Dictionary] = []
var drawing_tool: String = "rect"
## The bundle folder; "" = <dev_log.dir>/<stamp>.
var save_path: String = ""
var raw: Image
## What F12 froze: the bundle context (feedback_context.gd) and the host's debug_state.
var context: Dictionary = {}
var snapshot: Dictionary = {}
## Callable(at: Vector2) -> Dictionary: the game object under a canvas point.
var picker := Callable()
## The host's summary_line / entity_line Callables (feedback_entry.gd).
var markdown_hooks: Dictionary = {}
var note: LineEdit
var text_field: LineEdit
## Filled by DevBar.build: the strips, buttons by tool id, buttons by action name.
var bars: Array[Control] = []
var tool_buttons: Dictionary = {}
var action_buttons: Dictionary = {}
## True after a first cancel with unsaved work: the next cancel closes.
var cancel_pending := false

var _stroke: Dictionary = {}
var _texture: ImageTexture
var _history: Array = []
var _text_at := Vector2.ZERO


func open(frame: Image, p_log: RefCounted, p_context := {}, p_snapshot := {}) -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	add_to_group(&"annotator")  # the game leaves Esc and the mouse alone while this is open
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_STOP
	raw = frame
	dev_log = p_log
	context = p_context
	snapshot = p_snapshot
	_texture = ImageTexture.create_from_image(frame)
	DevBar.build(self)
	set_tool("rect")


func set_tool(shape_tool: String) -> void:
	commit_text()
	drawing_tool = shape_tool
	for id: String in tool_buttons:
		tool_buttons[id].modulate = Color(Color.WHITE, 1.0 if id == shape_tool else 0.5)


## False (nothing added) for a drag too short to mean anything.
func add_shape(shape_tool: String, from: Vector2, to: Vector2) -> bool:
	return _add(DevShapes.make(shape_tool, from, to))


func add_stroke(points: PackedVector2Array) -> bool:
	return _add(DevShapes.make("pen", points[0], points[points.size() - 1], points))


## A typed label whose top-left sits at `at`; false for empty text.
func add_text(at: Vector2, text: String) -> bool:
	return _add(DevShapes.make("text", at, at, PackedVector2Array(), {"text": text.strip_edges()}))


## Attaches the game object under `at` (the picker's answer); false when there
## is none or no picker.
func select_at(at: Vector2) -> bool:
	if not picker.is_valid():
		return false
	var entity: Dictionary = picker.call(at)
	return _add(DevShapes.make("select", at, at, PackedVector2Array(), {"entity": entity}))


func undo() -> void:
	if not _history.is_empty():
		shapes.assign(_history.pop_back())
		disarm()
		queue_redraw()


## Removes every mark; one undo brings them all back.
func clear() -> void:
	if shapes.is_empty():
		return
	_remember()
	shapes.clear()
	queue_redraw()


func has_unsaved() -> bool:
	return not shapes.is_empty() or (note != null and note.text != "")


## The report: the frozen context, note, marks and selected objects (PNG pixels).
func record() -> Dictionary:
	var out := context.duplicate(true)
	var scale := Vector2.ONE
	if raw != null and size.x > 0.0 and size.y > 0.0:
		scale = Vector2(raw.get_width() / size.x, raw.get_height() / size.y)
	out["kind"] = "annotation"
	out["time"] = Time.get_datetime_string_from_system()
	out["note"] = note.text if note != null else ""
	out.merge(DevShapes.marks_json(shapes, scale))
	return out


## Burns the marks in (viewport capture without the bars) and writes.
func save() -> void:
	_stroke = {}
	commit_text()
	for bar in bars:
		bar.hide()
	var annotated: Image = await DevFrame.grab(get_viewport())
	for bar in bars:
		bar.show()
	if annotated != null and raw != null and annotated.get_size() != raw.get_size():
		annotated.resize(raw.get_width(), raw.get_height(), Image.INTERPOLATE_NEAREST)
	write(annotated)


## Writes the bundle folder + Markdown entry; emits `closed` with the PNG path ("" = failed).
func write(annotated: Image) -> void:
	var dir := save_path if save_path != "" else DevSaver.bundle_dir(dev_log.dir)
	var saved := DevSaver.save(dir, record(), annotated, raw, dev_log.tail(LOG_TAIL), snapshot)
	DevEntry.append(dev_log.dir, saved, markdown_hooks)
	var png: String = saved["files"].get("annotated", "")
	dev_log.entry(DevSaver.log_entry(dir, saved, shapes.size()))
	dev_log.write("feedback saved %s ok=%s" % [dir, png != ""])
	closed.emit(png)


## With unsaved marks or a note the first cancel only arms the cross.
func cancel() -> void:
	if has_unsaved() and not cancel_pending:
		cancel_pending = true
		action_buttons["cancel"].modulate = DevStyle.armed
		return
	closed.emit("")


func _add(shape: Dictionary) -> bool:
	if not DevShapes.meaningful(shape):
		return false
	_remember()
	shapes.append(shape)
	queue_redraw()
	return true


## The undo step before a change; any change also disarms the cancel ask.
func _remember() -> void:
	_history.append(shapes.duplicate())
	disarm()


func disarm() -> void:
	cancel_pending = false
	if action_buttons.has("cancel"):
		action_buttons["cancel"].modulate = Color.WHITE


func _gui_input(event: InputEvent) -> void:
	var button := event as InputEventMouseButton
	var motion := event as InputEventMouseMotion
	if button != null and button.button_index == MOUSE_BUTTON_LEFT:
		if button.pressed:
			_press(button.position)
		else:
			_release(button.position)
		accept_event()
	elif motion != null and not _stroke.is_empty():
		_drag(motion.position)
		accept_event()


func _press(at: Vector2) -> void:
	commit_text()
	if drawing_tool == "select":
		select_at(at)
	elif drawing_tool == "text":
		_text_at = at
		text_field.position = at
		text_field.show()
		text_field.grab_focus()
	else:
		_stroke = DevShapes.make(drawing_tool, at, at, PackedVector2Array([at]))
		queue_redraw()


func _drag(at: Vector2) -> void:
	DevShapes.extend(_stroke, at)
	queue_redraw()


func _release(at: Vector2) -> void:
	if _stroke.is_empty():
		return
	_drag(at)
	_add(_stroke)
	_stroke = {}
	queue_redraw()


func commit_text() -> void:
	if text_field != null and text_field.visible:
		add_text(_text_at, text_field.text)
		text_field.text = ""
		text_field.hide()


func _unhandled_key_input(event: InputEvent) -> void:
	var key := event as InputEventKey
	if key == null or not key.pressed or key.echo:
		return
	if DevShapes.KEYS.has(key.keycode) and not key.ctrl_pressed:
		set_tool(DevShapes.KEYS[key.keycode])
	elif key.keycode == KEY_Z and key.ctrl_pressed:
		undo()
	elif key.keycode == KEY_ENTER or key.keycode == KEY_KP_ENTER:
		save()
	elif key.keycode == KEY_ESCAPE:
		cancel()
	else:
		return
	get_viewport().set_input_as_handled()


func _draw() -> void:
	draw_texture_rect(_texture, Rect2(Vector2.ZERO, size), false)
	for shape in shapes:
		DevShapes.paint(self, shape)
	if not _stroke.is_empty():
		DevShapes.paint(self, _stroke)
