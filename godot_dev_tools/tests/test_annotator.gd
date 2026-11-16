extends GutTest
## The annotator: red rectangles, arrows, circles and pen strokes, undo, the
## note, and the PNG + JSON it saves. Everything writes into a temp dir.

const Annotator = preload("res://addons/dev_tools/annotator.gd")
const DevHost = preload("res://addons/dev_tools/dev_host.gd")
const DevLog = preload("res://addons/dev_tools/dev_log.gd")
const FeedbackContext = preload("res://addons/dev_tools/feedback_context.gd")
const Glyph = preload("res://addons/dev_tools/dev_glyphs.gd")
const Hint = preload("res://addons/dev_tools/dev_hint.gd")
const StubHost = preload("res://tests/stub_host.gd")
const TmpDir = preload("res://tests/tmp_dir.gd")

var log: RefCounted
var annotator: Control
var _temp := TmpDir.path("annotator")


func before_each() -> void:
	log = DevLog.new()
	log.dir = _temp.path_join("fb")
	log.session = "test-session-1"
	annotator = Annotator.new()
	add_child_autofree(annotator)
	var frame := Image.create(400, 200, false, Image.FORMAT_RGBA8)
	frame.fill(Color(0.2, 0.3, 0.4))
	var host := DevHost.new(StubHost.new())
	annotator.open(frame, log, FeedbackContext.capture(host, get_tree(), log, false))
	annotator.size = Vector2(200, 100)  # after open: a bare Node parent gives no layout


func after_each() -> void:
	TmpDir.remove_tree(_temp)


func _v(pair: Array) -> Vector2:
	return Vector2(pair[0], pair[1])


func _mouse(pressed: bool, at: Vector2) -> InputEventMouseButton:
	var event := InputEventMouseButton.new()
	event.button_index = MOUSE_BUTTON_LEFT
	event.pressed = pressed
	event.position = at
	return event


func _motion(at: Vector2) -> InputEventMouseMotion:
	var event := InputEventMouseMotion.new()
	event.position = at
	return event


func test_a_rect_and_an_arrow_are_shapes_with_their_tool() -> void:
	assert_true(annotator.add_shape("rect", Vector2(10, 10), Vector2(80, 60)))
	assert_true(annotator.add_shape("arrow", Vector2(100, 20), Vector2(150, 70)))
	assert_eq(annotator.shapes.size(), 2)
	assert_eq(annotator.shapes[0]["tool"], "rect")
	assert_eq(annotator.shapes[1]["tool"], "arrow")
	assert_eq(annotator.shapes[1]["b"], Vector2(150, 70), "an arrow points at b")


func test_a_too_short_drag_adds_nothing() -> void:
	assert_false(annotator.add_shape("rect", Vector2(10, 10), Vector2(11, 11)))
	assert_false(annotator.add_stroke(PackedVector2Array([Vector2(5, 5)])))
	assert_true(annotator.shapes.is_empty())


func test_a_mouse_drag_draws_the_shape_of_the_tool() -> void:
	annotator.set_tool("arrow")
	annotator._gui_input(_mouse(true, Vector2(10, 10)))
	annotator._gui_input(_motion(Vector2(60, 40)))
	annotator._gui_input(_mouse(false, Vector2(120, 80)))
	assert_eq(annotator.shapes.size(), 1)
	assert_eq(annotator.shapes[0]["tool"], "arrow")
	assert_eq(annotator.shapes[0]["b"], Vector2(120, 80))


func test_a_pen_stroke_follows_the_mouse() -> void:
	annotator.set_tool("pen")
	annotator._gui_input(_mouse(true, Vector2(10, 10)))
	for x in range(20, 100, 10):
		annotator._gui_input(_motion(Vector2(x, 10 + x / 2.0)))
	annotator._gui_input(_mouse(false, Vector2(100, 60)))
	assert_eq(annotator.shapes.size(), 1)
	assert_gt((annotator.shapes[0]["points"] as PackedVector2Array).size(), 5)


func test_tool_buttons_and_keys_pick_the_tool() -> void:
	for id in ["rect", "arrow", "circle", "pen", "text", "select"]:
		assert_true(annotator.tool_buttons.has(id), id)
	annotator.tool_buttons["circle"].pressed.emit()
	assert_eq(annotator.drawing_tool, "circle")
	var key := InputEventKey.new()
	key.keycode = KEY_P
	key.pressed = true
	annotator._unhandled_key_input(key)
	assert_eq(annotator.drawing_tool, "pen")


func test_every_icon_only_control_has_an_accessibility_name() -> void:
	for id: String in annotator.tool_buttons:
		assert_ne(annotator.tool_buttons[id].accessibility_name, "", id)
	for id: String in annotator.action_buttons:
		assert_ne(annotator.action_buttons[id].accessibility_name, "", id)
	var hint := Hint.new()
	add_child_autofree(hint)
	assert_ne(hint.accessibility_name, "")


func test_undo_removes_the_last_shape_and_is_safe_when_empty() -> void:
	annotator.undo()
	annotator.add_shape("rect", Vector2(10, 10), Vector2(80, 60))
	annotator.add_shape("circle", Vector2(20, 20), Vector2(90, 70))
	annotator.undo()
	assert_eq(annotator.shapes.size(), 1)
	assert_eq(annotator.shapes[0]["tool"], "rect")


func test_saving_writes_the_bundle_with_every_field() -> void:
	annotator.add_shape("rect", Vector2(10, 10), Vector2(80, 60))
	annotator.add_shape("arrow", Vector2(100, 20), Vector2(150, 70))
	annotator.note.text = "the frame is crooked"
	var base := _temp.path_join("fb/one")
	annotator.save_path = base
	annotator.write(Image.create(400, 200, false, Image.FORMAT_RGBA8))
	for file_name in ["annotated.png", "screenshot.png", "report.json"]:
		assert_true(FileAccess.file_exists(base.path_join(file_name)), file_name)
	var saved: Dictionary = JSON.parse_string(
		FileAccess.get_file_as_string(base.path_join("report.json"))
	)
	for field in ["session", "build", "godot", "game", "mode", "window", "canvas"]:
		assert_true(saved.has(field), field)
	assert_eq(saved["session"], "test-session-1")
	assert_eq(saved["game"], "stub-game")
	assert_eq(saved["mode"], "stub", "the host's own fields are in the report")
	assert_eq(saved["note"], "the frame is crooked")
	assert_eq(_v(saved["image"]), Vector2(400, 200))
	assert_eq(saved["files"]["annotated"], base.path_join("annotated.png"))
	assert_eq(saved["shapes"].size(), 2)
	assert_eq(_v(saved["shapes"][0]["a"]), Vector2(20, 20))
	assert_eq(_v(saved["shapes"][0]["b"]), Vector2(160, 120))
	assert_eq(_v(saved["shapes"][1]["b"]), Vector2(300, 140), "shapes are in the PNG's pixels")
	var entry := FileAccess.get_file_as_string(log.dir.path_join("feedback.jsonl"))
	assert_true(entry.contains("one/report.json"))


func test_the_default_save_goes_under_the_injected_dir() -> void:
	watch_signals(annotator)
	annotator.write(Image.create(400, 200, false, Image.FORMAT_RGBA8))
	assert_signal_emitted(annotator, "closed")
	assert_eq(DirAccess.get_directories_at(log.dir).size(), 1, "one bundle folder")


func test_the_hint_glyph_emits_pressed_on_a_click() -> void:
	var hint := Hint.new()
	add_child_autofree(hint)
	watch_signals(hint)
	hint._gui_input(_mouse(true, Vector2(5, 5)))
	assert_signal_emitted(hint, "pressed")


func test_the_hint_sits_inside_the_top_right_corner() -> void:
	var layer := CanvasLayer.new()
	add_child_autofree(layer)
	var hint := Hint.new()
	layer.add_child(hint)
	var view := get_tree().root.get_visible_rect().size
	assert_almost_eq(hint.position.x + hint.size.x, view.x - Hint.MARGIN_PX, 0.5)
	assert_almost_eq(hint.position.y, float(Hint.MARGIN_PX), 0.5)


func test_every_dev_glyph_draws_something() -> void:
	var kinds := "rect arrow circle pen undo save cancel note camera text select clear"
	for kind in kinds.split(" "):
		assert_gt(Glyph.texture(kind).glyph.pieces.size(), 0, kind)
		assert_gt(Glyph.texture(kind).glyph.area(), 100.0, kind)
