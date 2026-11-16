extends GutTest
## The annotator's second half: text labels, entity select, clear + undo, the
## unsaved-changes guard, and the bundle folder with its Markdown entry (the
## on-disk contract utils feedback_inbox reads).

const Annotator = preload("res://addons/dev_tools/annotator.gd")
const DevHost = preload("res://addons/dev_tools/dev_host.gd")
const DevLog = preload("res://addons/dev_tools/dev_log.gd")
const FeedbackContext = preload("res://addons/dev_tools/feedback_context.gd")
const StubHost = preload("res://tests/stub_host.gd")
const TmpDir = preload("res://tests/tmp_dir.gd")

const FILES := ["screenshot.png", "annotated.png", "report.json", "game.log", "snapshot.json"]
## Every top-level field of report.json: the generic ones plus the stub host's.
const REPORT_FIELDS := (
	"kind time note session build godot game screen mode variant"
	+ " paused scene window canvas shapes selected image files"
)
const ITEM := {
	"kind": "entity",
	"id": "entity_3",
	"team": "army",
	"count": 10,
	"state": "move",
	"position": [120.0, 80.5],
}

var log: RefCounted
var annotator: Control
var _host := DevHost.new(StubHost.new())
var _temp := TmpDir.path("annotator_bundle")


func before_each() -> void:
	log = DevLog.new()
	log.dir = _temp.path_join("fb")
	log.session = "test-session-2"
	annotator = Annotator.new()
	add_child_autofree(annotator)
	var frame := Image.create(400, 200, false, Image.FORMAT_RGBA8)
	frame.fill(Color(0.2, 0.3, 0.4))
	var context := FeedbackContext.capture(_host, get_tree(), log, false)
	annotator.open(frame, log, context, {"items": []})
	annotator.size = Vector2(200, 100)
	annotator.picker = func(_at: Vector2) -> Dictionary: return ITEM.duplicate()


func after_each() -> void:
	TmpDir.remove_tree(_temp)


func _click(at: Vector2) -> void:
	for pressed in [true, false]:
		var event := InputEventMouseButton.new()
		event.button_index = MOUSE_BUTTON_LEFT
		event.pressed = pressed
		event.position = at
		annotator._gui_input(event)


func _bundles() -> Array:
	return Array(DirAccess.get_directories_at(log.dir))


func _json(path: String) -> Variant:
	return JSON.parse_string(FileAccess.get_file_as_string(path))


func _save() -> String:
	annotator.write(Image.create(400, 200, false, Image.FORMAT_RGBA8))
	var dirs := _bundles()
	dirs.sort()
	return log.dir.path_join(dirs[dirs.size() - 1])


func test_a_text_label_keeps_its_words_and_empty_text_makes_none() -> void:
	assert_true(annotator.add_text(Vector2(20, 30), "wrong place"))
	assert_false(annotator.add_text(Vector2(20, 30), "   "))
	assert_eq(annotator.shapes.size(), 1)
	assert_eq(annotator.shapes[0]["tool"], "text")
	assert_eq(annotator.shapes[0]["text"], "wrong place")
	var mark: Dictionary = annotator.record()["shapes"][0]
	assert_eq(mark["text"], "wrong place")
	assert_eq(mark["a"], [40, 60], "in PNG pixels")


func test_the_text_tool_asks_for_the_words_where_you_click() -> void:
	annotator.set_tool("text")
	_click(Vector2(50, 40))
	assert_true(annotator.text_field != null and annotator.text_field.visible)
	assert_true(annotator.shapes.is_empty(), "nothing yet")
	annotator.text_field.text = "here"
	annotator.text_field.text_submitted.emit("here")
	assert_eq(annotator.shapes.size(), 1)
	assert_eq(annotator.shapes[0]["text"], "here")
	assert_eq(annotator.shapes[0]["a"], Vector2(50, 40))
	assert_false(annotator.text_field.visible)


func test_select_attaches_the_entity_under_the_cursor() -> void:
	assert_true(annotator.select_at(Vector2(60, 40)))
	assert_eq(annotator.shapes[0]["tool"], "select")
	var record: Dictionary = annotator.record()
	assert_eq(record["selected"].size(), 1)
	var entity: Dictionary = record["selected"][0]
	assert_eq(entity["id"], "entity_3")
	assert_eq(entity["state"], "move")
	assert_eq(entity["position"], [120.0, 80.5])
	assert_eq(entity["at"], [120, 80], "where you clicked, in PNG pixels")


func test_select_on_nothing_makes_no_mark() -> void:
	annotator.picker = func(_at: Vector2) -> Dictionary: return {}
	assert_false(annotator.select_at(Vector2(60, 40)))
	assert_true(annotator.shapes.is_empty())


func test_the_select_tool_picks_on_a_click() -> void:
	annotator.set_tool("select")
	_click(Vector2(60, 40))
	assert_eq(annotator.shapes.size(), 1)
	assert_eq(annotator.shapes[0]["entity"]["id"], "entity_3")


func test_clear_empties_the_marks_and_undo_brings_them_back() -> void:
	annotator.add_shape("rect", Vector2(10, 10), Vector2(80, 60))
	annotator.add_text(Vector2(20, 30), "x")
	annotator.clear()
	assert_true(annotator.shapes.is_empty())
	annotator.undo()
	assert_eq(annotator.shapes.size(), 2, "clear is one undo step")
	annotator.undo()
	assert_eq(annotator.shapes.size(), 1)


func test_clear_with_nothing_to_clear_leaves_no_undo_step() -> void:
	annotator.add_shape("rect", Vector2(10, 10), Vector2(80, 60))
	annotator.clear()
	annotator.clear()
	annotator.undo()
	assert_eq(annotator.shapes.size(), 1)


func test_cancel_with_nothing_drawn_closes_at_once() -> void:
	watch_signals(annotator)
	annotator.cancel()
	assert_signal_emitted(annotator, "closed")


func test_cancel_with_marks_asks_first_and_the_second_press_closes() -> void:
	annotator.add_shape("rect", Vector2(10, 10), Vector2(80, 60))
	watch_signals(annotator)
	annotator.cancel()
	assert_signal_not_emitted(annotator, "closed")
	assert_true(annotator.cancel_pending)
	annotator.cancel()
	assert_signal_emitted(annotator, "closed")


func test_a_note_counts_as_unsaved_and_a_new_mark_disarms_the_ask() -> void:
	annotator.note.text = "typed"
	annotator.cancel()
	assert_true(annotator.cancel_pending, "a note counts as unsaved work")
	annotator.add_shape("rect", Vector2(10, 10), Vector2(80, 60))
	assert_false(annotator.cancel_pending)


func test_save_writes_the_bundle_folder_with_every_file() -> void:
	annotator.add_shape("rect", Vector2(10, 10), Vector2(80, 60))
	annotator.select_at(Vector2(60, 40))
	annotator.note.text = "this squad stands still"
	log.write("hello-from-the-test")
	var bundle := _save()
	assert_eq(_bundles().size(), 1)
	for file_name in FILES:
		assert_true(FileAccess.file_exists(bundle.path_join(file_name)), file_name)
	var game_log := FileAccess.get_file_as_string(bundle.path_join("game.log"))
	assert_true(game_log.contains("hello-from-the-test"))
	assert_eq(_json(bundle.path_join("snapshot.json")), {"items": []})


func test_report_json_has_the_fields_a_later_session_needs() -> void:
	annotator.add_shape("rect", Vector2(10, 10), Vector2(80, 60))
	annotator.select_at(Vector2(60, 40))
	annotator.note.text = "n"
	var report: Dictionary = _json(_save().path_join("report.json"))
	for field in REPORT_FIELDS.split(" "):
		assert_true(report.has(field), field)
	assert_eq(report["game"], "stub-game")
	assert_eq(report["kind"], "annotation")
	assert_eq(report["session"], "test-session-2")
	assert_eq(report["note"], "n")
	assert_eq(report["image"], [400.0, 200.0])
	assert_eq(report["shapes"].size(), 2)
	assert_eq(report["selected"][0]["id"], "entity_3")
	for field: String in ["id", "version", "debug"]:
		assert_true(report["build"].has(field), "build." + field)
	for file_key: String in ["annotated", "screenshot", "game_log", "snapshot", "report"]:
		assert_true(FileAccess.file_exists(report["files"][file_key]), file_key)
	assert_eq(String(report["files"]["annotated"]).get_file(), "annotated.png")


func test_two_saves_in_one_millisecond_get_two_folders() -> void:
	annotator.write(Image.create(400, 200, false, Image.FORMAT_RGBA8))
	annotator.write(Image.create(400, 200, false, Image.FORMAT_RGBA8))
	assert_eq(_bundles().size(), 2)


func test_each_save_appends_a_prompt_ready_markdown_entry() -> void:
	annotator.note.text = "the third card is cut off"
	var bundle := _save()
	annotator.note.text = "second thought"
	_save()
	var md_files := Array(DirAccess.get_files_at(log.dir)).filter(
		func(f: String) -> bool: return f.ends_with(".md")
	)
	assert_eq(md_files.size(), 1, "one Markdown file per day")
	assert_true(String(md_files[0]).begins_with("feedback-"))
	var md := FileAccess.get_file_as_string(log.dir.path_join(md_files[0]))
	assert_true(md.begins_with("## "))
	assert_eq(md.count("\n## "), 1, "two entries")
	assert_true(md.contains("the third card is cut off"))
	assert_true(md.contains(bundle.path_join("annotated.png")))
	assert_true(md.contains(bundle.path_join("report.json")))
	assert_true(md.contains("Task:"), "ends with what the next session should do")


func test_the_default_entry_has_the_line_the_inbox_parses() -> void:
	var md := FileAccess.get_file_as_string(_md_after_save())
	var line := RegEx.create_from_string("- Game `([^`]*)`, combo `([^`]*)`")
	assert_not_null(line.search(md), "feedback_inbox matches Game `..`, combo `..`")
	assert_string_contains(md, "- Game `stub-game`, combo ``")


func test_host_hooks_replace_the_summary_and_the_selected_lines() -> void:
	annotator.markdown_hooks = _host.markdown_hooks()
	annotator.select_at(Vector2(60, 40))
	var md := FileAccess.get_file_as_string(_md_after_save())
	assert_string_contains(md, "- Stub screen `hub`")
	assert_false(md.contains("- Game `"))
	assert_string_contains(md, "- Selected entity `entity_3` (move) at [120.0, 80.5]")


func _md_after_save() -> String:
	_save()
	var md_files := Array(DirAccess.get_files_at(log.dir)).filter(
		func(f: String) -> bool: return f.ends_with(".md")
	)
	return log.dir.path_join(md_files[0])
