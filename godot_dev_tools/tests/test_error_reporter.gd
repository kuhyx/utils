extends GutTest
## The app_errors addon: engine and script errors and slow waits become spool
## lines in the shape utils app_errors ingests (app_errors/README.md "Entry").

const Reporter = preload("res://addons/app_errors/error_reporter.gd")
const TmpDir = preload("res://tests/tmp_dir.gd")

var _dir := TmpDir.path("app_errors")
var _rep: Node


func before_each() -> void:
	_rep = Reporter.new()
	_rep.spool_dir = ProjectSettings.globalize_path(_dir)
	_rep.setup("car-rental-sim", "kuhyx/car-rental-sim", 12, "0.4.0")
	_rep.clock = func() -> float: return 1800000000.0
	add_child_autofree(_rep)


func after_each() -> void:
	TmpDir.remove_tree(_dir)


func _lines() -> Array:
	var path := _dir.path_join("car-rental-sim.jsonl")
	if not FileAccess.file_exists(path):
		return []
	var out := []
	for line in FileAccess.get_file_as_string(path).split("\n", false):
		out.append(JSON.parse_string(line))
	return out


func _none() -> Array[ScriptBacktrace]:
	var out: Array[ScriptBacktrace] = []
	return out


func _script_error(message: String) -> void:
	_rep.logger._log_error(
		"_ready", "res://scripts/car.gd", 77, message, "", false, Logger.ERROR_TYPE_SCRIPT, _none()
	)


func test_script_error_is_one_entry() -> void:
	_script_error("Invalid access to property 'x'")
	var lines := _lines()
	assert_eq(lines.size(), 1)
	var entry: Dictionary = lines[0]
	assert_eq(entry.kind, "uncaught.gdscript")
	assert_eq(entry.error, "Invalid access to property 'x'")
	assert_eq(entry.repo, "kuhyx/car-rental-sim")
	assert_eq(entry.mark, "res://")
	assert_eq(int(entry.build), 12)
	assert_eq(entry.version, "0.4.0")
	assert_eq(entry.at, "2027-01-15T08:00:00.000Z")
	assert_eq(entry.stack, ["res://scripts/car.gd:77 in _ready"])


func test_push_error_uses_the_script_backtrace() -> void:
	var bts := _none()
	bts.append(ScriptBacktrace.new())
	_rep.logger._log_error(
		"push_error",
		"core/variant/variant_utility.cpp",
		1023,
		"deliberate",
		"",
		false,
		Logger.ERROR_TYPE_ERROR,
		bts
	)
	var entry: Dictionary = _lines()[0]
	assert_eq(entry.kind, "godot.error")
	assert_eq(entry.error, "deliberate")
	assert_eq(entry.stack, [], "an empty backtrace and a C++ file give no frames")


func test_rationale_wins_over_code() -> void:
	_rep.logger._log_error(
		"f",
		"res://a.gd",
		1,
		"p_index < 0",
		"Index out of range",
		false,
		Logger.ERROR_TYPE_ERROR,
		_none()
	)
	assert_eq(_lines()[0].error, "Index out of range")


func test_warnings_are_ignored() -> void:
	_rep.logger._log_error("f", "res://a.gd", 1, "w", "", false, Logger.ERROR_TYPE_WARNING, _none())
	_rep.logger._log_message("hello", false)
	assert_eq(_lines(), [])


func test_identical_errors_are_deduplicated() -> void:
	for i in 5:
		_script_error("same")
	assert_eq(_lines().size(), 1)


func test_rate_cap_per_minute() -> void:
	for i in Reporter.MAX_PER_MINUTE + 4:
		_script_error("e%d" % i)
	assert_eq(_lines().size(), Reporter.MAX_PER_MINUTE)


func test_report_wait_over_threshold() -> void:
	_rep.report_wait("level.load", 2000)
	_rep.report_wait("level.load", 400)
	var lines := _lines()
	assert_eq(lines.size(), 1, "a wait under 1 s writes nothing")
	var entry: Dictionary = lines[0]
	assert_eq(entry.kind, "perf.slow")
	assert_eq(entry.operation, "level.load")
	assert_eq(int(entry.durationMs), 2000)
	assert_eq(entry.error, "level.load waited 2000 ms")


func test_begin_and_end_wait() -> void:
	var t := [1800000000.0]
	_rep.clock = func() -> float: return t[0]
	var wait: Dictionary = _rep.begin_wait("shop.open")
	t[0] += 1.5
	_rep.end_wait(wait)
	_rep.end_wait(wait)
	assert_eq(_lines().size(), 1)
	assert_eq(int(_lines()[0].durationMs), 1500)


func test_long_frame_is_a_stall() -> void:
	_rep._check_frame(0.016)
	_rep._check_frame(2.5)
	var lines := _lines()
	assert_eq(lines.size(), 1)
	assert_eq(lines[0].operation, "godot.frame")
	assert_eq(int(lines[0].durationMs), 2500)


func test_no_spool_dir_writes_nothing() -> void:
	_rep.spool_dir = ""
	_script_error("x")
	assert_eq(_lines(), [])


func test_logger_is_removed_on_exit() -> void:
	var rep: Node = Reporter.new()
	rep.spool_dir = ProjectSettings.globalize_path(_dir)
	rep.setup("x", "kuhyx/x")
	add_child(rep)
	var logger: Logger = rep.logger
	assert_not_null(logger)
	remove_child(rep)
	assert_null(rep.logger)
	rep.free()


func test_default_spool_dir_follows_xdg() -> void:
	var saved := OS.get_environment("XDG_STATE_HOME")
	OS.set_environment("XDG_STATE_HOME", "/tmp/xdg-state")
	assert_eq(Reporter.default_spool_dir(), "/tmp/xdg-state/app-errors-spool")
	OS.unset_environment("XDG_STATE_HOME")
	assert_eq(
		Reporter.default_spool_dir(),
		OS.get_environment("HOME").path_join(".local/state/app-errors-spool")
	)
	if saved != "":
		OS.set_environment("XDG_STATE_HOME", saved)


func test_real_push_error_reaches_the_spool() -> void:
	push_error("deliberate test error")
	assert_push_error("deliberate test error")
	var errors := []
	for entry in _lines():
		errors.append(entry.error)
	assert_has(errors, "deliberate test error")
