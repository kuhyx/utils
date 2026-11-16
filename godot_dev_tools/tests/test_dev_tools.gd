extends GutTest
## The dev tools node and its parts: where the logs go, the session's structured
## log, the node joining a game through its host, F9 and F12, and the rules the
## addon keeps (no class_name, no game class, relative preload only).

const ADDON := "res://addons/dev_tools"
const DevHost = preload("res://addons/dev_tools/dev_host.gd")
const DevLog = preload("res://addons/dev_tools/dev_log.gd")
const DevTools = preload("res://addons/dev_tools/dev_tools.gd")
const Style = preload("res://addons/dev_tools/dev_style.gd")
const StubHost = preload("res://tests/stub_host.gd")
const Telemetry = preload("res://addons/dev_tools/telemetry.gd")
const TmpDir = preload("res://tests/tmp_dir.gd")

var host: RefCounted
var log: RefCounted
var _dir := TmpDir.path("dev_tools")


func before_each() -> void:
	host = StubHost.new()
	log = DevLog.new()
	log.dir = _dir


func after_each() -> void:
	get_tree().paused = false
	Style.apply({})
	TmpDir.remove_tree(_dir)


func _rows() -> Array:
	var rows := []
	for line in FileAccess.get_file_as_string(_dir.path_join("feedback.jsonl")).split("\n", false):
		rows.append(JSON.parse_string(line))
	return rows


func _events() -> Array:
	return _rows().map(func(row: Dictionary) -> String: return row.get("event", ""))


func _tools() -> Node:
	var tools: Node = DevTools.new()
	tools.setup(host)
	tools.dev_log.dir = _dir
	add_child_autofree(tools)
	return tools


## Waits for process frames (a paused tree stops GUT's own wait_until), 300 at most.
func _until(done: Callable) -> void:
	for _i in 300:
		if done.call():
			return
		await get_tree().process_frame
	fail_test("never happened")


func _key(code: Key) -> InputEventKey:
	var press := InputEventKey.new()
	press.keycode = code
	press.pressed = true
	return press


func test_the_log_folder_follows_the_arguments_and_the_game() -> void:
	assert_eq(DevLog.default_dir(["--feedback-dir=/x/fb", "--save-dir=/y"]), "/x/fb")
	assert_eq(DevLog.default_dir(["--save-dir=/y/save"]), "/y/save/dev", "a bot logs in its save")
	assert_eq(DevLog.arg_value(["--dev-tag=v03"], "--dev-tag="), "v03")
	assert_eq(DevLog.arg_value([], "--dev-tag="), "")
	assert_eq(
		DevLog.new("g", "NO_SUCH_VAR_X").dir, "user://dev", "no env, no --dev: the user folder"
	)


func test_the_env_variable_of_the_host_names_the_folder() -> void:
	OS.set_environment("STUB_FEEDBACK_DIR", "/env/fb")
	assert_eq(DevLog.default_dir([], "stub-game", "STUB_FEEDBACK_DIR"), "/env/fb")
	assert_eq(_tools_dir(), "/env/fb", "the node asks the host for the variable name")
	OS.unset_environment("STUB_FEEDBACK_DIR")


func _tools_dir() -> String:
	var tools: Node = DevTools.new()
	tools.setup(host)
	var dir: String = tools.dev_log.dir
	tools.free()
	return dir


func test_log_lines_and_entries_land_in_the_injected_folder() -> void:
	log.session = "s-1"
	log.write("first line")
	log.write("second line")
	assert_eq(log.tail(1), "%s\n" % log.tail(5).strip_edges().split("\n")[1])
	assert_string_contains(log.tail(5), "first line")
	log.entry({"event": "probe"})
	log.entry({"event": "probe"})
	var rows := _rows()
	assert_eq(rows.size(), 2)
	assert_eq(rows[1]["seq"], 2.0)
	assert_eq(rows[1]["session"], "s-1")
	for field: String in ["time", "ms", "frame"]:
		assert_true(rows[1].has(field), field)


func test_a_session_starts_with_the_host_moments_and_an_exact_clock_pair() -> void:
	var telemetry := Telemetry.new()
	telemetry.attach(log, DevHost.new(host))
	assert_eq(_events(), ["host_attached", "session_start", "recording_sync"])
	var sync: Dictionary = _rows()[2]
	assert_almost_eq(sync["unix_us"] / 1000000.0, Time.get_unix_time_from_system(), 5.0)
	assert_ne(telemetry.session_id, "")
	assert_eq(sync["session"], telemetry.session_id)
	telemetry.shutdown("test")
	telemetry.shutdown("again")
	assert_eq(_events().count("session_end"), 1, "a session ends once")


func test_engine_errors_become_entries() -> void:
	var telemetry := Telemetry.new()
	telemetry.attach(log, DevHost.new(host))
	push_error("boom from the test")
	telemetry.tick()
	telemetry.shutdown("test")
	assert_push_error("boom from the test")
	var errors := _rows().filter(
		func(row: Dictionary) -> bool: return row["event"] == "engine_error"
	)
	assert_eq(errors.size(), 1)
	assert_string_contains(str(errors[0]), "boom from the test")


func test_the_node_joins_the_game_through_its_host() -> void:
	var tools := _tools()
	assert_eq(host.menu.size(), 1, "the pause menu gets a camera")
	assert_eq(host.menu[0]["id"], "annotate")
	assert_not_null(host.menu[0]["icon"])
	assert_not_null(tools.hint)
	assert_has(_events(), "session_start")
	assert_has(_events(), "host_attached")
	assert_eq(Style.mark, Color(0.0, 1.0, 0.0), "the host's colours restyle the tools")
	assert_ne(tools.first_pickable(), Vector2.INF, "the stub has something at the left")
	assert_string_contains(tools.dev_log.tail(50), "dev tools on")


func test_a_bare_host_still_works() -> void:
	var tools: Node = DevTools.new()
	tools.setup(null)
	tools.dev_log.dir = _dir
	add_child_autofree(tools)
	assert_eq(tools.first_pickable(), Vector2.INF, "no pick_at: nothing to select")
	tools._input(_key(KEY_F9))
	assert_does_not_have(_events(), "reset_progress")
	assert_eq(Style.mark, Style.DEFAULT_MARK)


func test_f9_resets_through_the_host_and_logs_it() -> void:
	var tools := _tools()
	tools._input(_key(KEY_F9))
	assert_eq(host.resets, 1)
	var rows := _rows()
	var reset: Dictionary = rows[_events().find("reset_progress")]
	assert_eq(reset["files"], 3.0)


func test_f12_freezes_the_game_and_the_marks_save_a_bundle() -> void:
	var tools := _tools()
	tools.annotate()
	await _until(func() -> bool: return tools.annotator != null)
	assert_true(get_tree().paused, "the frame is frozen")
	assert_true(tools.annotator.is_in_group(&"annotator"))
	assert_true(tools.annotator.add_shape("rect", Vector2(10, 10), Vector2(80, 60)))
	tools.annotator.note.text = "from the f12 test"
	tools.annotator.save()
	await _until(func() -> bool: return tools.annotator == null)
	assert_false(get_tree().paused, "the game runs again")
	assert_eq(DirAccess.get_directories_at(_dir).size(), 1, "one bundle")
	assert_eq(host.menu_closed, 0)
	var report: Dictionary = JSON.parse_string(
		FileAccess.get_file_as_string(
			_dir.path_join(DirAccess.get_directories_at(_dir)[0]).path_join("report.json")
		)
	)
	assert_eq(report["game"], "stub-game")
	assert_eq(report["screen"], "hub")


func test_the_pause_menu_entry_closes_the_menu_first() -> void:
	var tools := _tools()
	host.menu[0]["press"].call()
	await _until(func() -> bool: return tools.annotator != null)
	assert_eq(host.menu_closed, 1)
	tools.annotator.cancel()
	await _until(func() -> bool: return tools.annotator == null)


func test_no_addon_file_declares_a_class_name() -> void:
	for source in _sources():
		assert_false(source.contains("\nclass_name "))
		assert_false(source.begins_with("class_name "))


func test_the_addon_names_no_game_class_and_no_mount_path() -> void:
	for source in _sources():
		assert_false(source.contains('load("res://'), "scripts reach siblings by relative preload")
		assert_false(source.contains("Palette"), "no game palette")
		assert_false(source.contains("SaveStore"), "no game save")


func test_every_preload_alias_is_prefixed_so_no_game_class_can_shadow_it() -> void:
	var alias := RegEx.create_from_string("(?m)^const (\\w+) = preload")
	var seen := 0
	for source in _sources():
		for found in alias.search_all(source):
			seen += 1
			assert_true(found.get_string(1).begins_with("Dev"), found.get_string(1))
	assert_gt(seen, 20)


func test_the_addon_loads_from_any_folder() -> void:
	var copy := TmpDir.path("mounted_elsewhere")
	for file_name in DirAccess.get_files_at(ADDON):
		if file_name.ends_with(".gd"):
			var text := FileAccess.get_file_as_string(ADDON.path_join(file_name))
			var out := FileAccess.open(copy.path_join(file_name), FileAccess.WRITE)
			out.store_string(text)
			out.close()
	var script := ResourceLoader.load(
		copy.path_join("dev_tools.gd"), "", ResourceLoader.CACHE_MODE_IGNORE
	)
	assert_not_null(script, "a copy at another path still parses and preloads its siblings")
	var tools: Node = script.new()
	assert_not_null(tools.get("telemetry"))
	tools.free()
	TmpDir.remove_tree(copy)


func _sources() -> Array[String]:
	var out: Array[String] = []
	for file_name in DirAccess.get_files_at(ADDON):
		if file_name.ends_with(".gd"):
			out.append(FileAccess.get_file_as_string(ADDON.path_join(file_name)))
	assert_gt(out.size(), 10)
	return out
