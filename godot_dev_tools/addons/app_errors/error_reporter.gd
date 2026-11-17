extends Node
## Reports every error and every wait over 1 s of a Godot game to kuhy's shared
## app-errors pipeline (utils DOCS-app-errors.md). Mount it like dev_tools, but
## in every build, not only --dev runs: player errors are the point.
##
##     var rep: Node = (load("res://addons/app_errors/error_reporter.gd") as GDScript).new()
##     rep.setup("car-rental-sim", "kuhyx/car-rental-sim")
##     add_child(rep)
##     rep.report_wait("level.load", msec)       # or begin_wait / end_wait
##
## Script errors and push_error arrive through an OS logger; a frame over 1 s is
## reported as the wait `godot.frame`. Each report is one JSON line in
## $XDG_STATE_HOME/app-errors-spool/<app>.jsonl, which the PC's app-errors
## ingest turns into a board ticket. Desktop only (a web build has no spool),
## off in headless runs and with APP_ERRORS_OFF=1 (see default_enabled),
## shows nothing on screen, and never reports from inside a report. Identical
## errors within WINDOW_SEC are dropped; at most MAX_PER_MINUTE are written.
## No class_name (the addon stays out of the global class cache).

const ReporterLogger = preload("res://addons/app_errors/reporter_logger.gd")
const SLOW_KIND := "perf.slow"
const MARK := "res://"
const WINDOW_SEC := 30.0
const MAX_PER_MINUTE := 20
const MAX_SLOW_PER_MINUTE := 30
const THRESHOLD_MS := 1000
const KINDS := {
	Logger.ERROR_TYPE_ERROR: "godot.error",
	Logger.ERROR_TYPE_SCRIPT: "uncaught.gdscript",
	Logger.ERROR_TYPE_SHADER: "godot.shader",
}

## Seconds since the epoch (tests replace it).
var clock: Callable = Time.get_unix_time_from_system
## Folder of the spool; empty writes nothing (a web build).
var spool_dir := default_spool_dir()
## False writes nothing: headless runs (tests, CI, bots) and APP_ERRORS_OFF.
var enabled := default_enabled()
var logger: Logger

var _app := ""
var _repo := ""
var _build := 0
var _version := ""
var _mutex := Mutex.new()
var _busy := false
var _seen := {}
var _minutes := {}
var _serial := 0
var _frames := 0


## The spool folder: $XDG_STATE_HOME (else ~/.local/state)/app-errors-spool;
## empty off desktop Linux.
static func default_spool_dir() -> String:
	if not OS.has_feature("linuxbsd"):
		return ""
	var base := OS.get_environment("XDG_STATE_HOME")
	if base == "":
		base = OS.get_environment("HOME").path_join(".local/state")
	return base.path_join("app-errors-spool")


## Whether this process reports: never with APP_ERRORS_OFF=1, and not when
## headless (tests, CI, smoke runs, export checks: their errors are not a
## player's) unless APP_ERRORS_FORCE=1 (an end-to-end probe).
static func default_enabled() -> bool:
	if OS.get_environment("APP_ERRORS_OFF") == "1":
		return false
	if DisplayServer.get_name() == "headless":
		return OS.get_environment("APP_ERRORS_FORCE") == "1"
	return true


## Names the game: `app` as the board shows it, `repo` as owner/name, and the
## build number when the game knows one.
func setup(app: String, repo: String, build := 0, version := "") -> void:
	_app = app
	_repo = repo
	_build = build
	_version = version


func _enter_tree() -> void:
	logger = ReporterLogger.new(_on_error)
	OS.add_logger(logger)


func _exit_tree() -> void:
	OS.remove_logger(logger)
	logger = null


func _process(delta: float) -> void:
	_check_frame(delta)


## A frame that took over a second is a wait the player saw (the first frame
## is the boot, before the window shows anything).
func _check_frame(delta: float) -> void:
	_frames += 1
	if _frames > 1 and delta * 1000.0 > THRESHOLD_MS:
		_slow("godot.frame", roundi(delta * 1000.0), "frame-%d" % _frames)


## Reports a finished wait of `msec` on `operation` when it took over 1 s.
func report_wait(operation: String, msec: int) -> void:
	if msec > THRESHOLD_MS:
		_serial += 1
		_slow(operation, msec, "%s-%d" % [operation, _serial])


## Starts timing a wait on `operation`; pass the result to end_wait.
func begin_wait(operation: String) -> Dictionary:
	return {"operation": operation, "started": clock.call(), "ended": false}


## Ends a wait from begin_wait; repeat calls do nothing.
func end_wait(wait: Dictionary) -> void:
	if wait.ended:
		return
	wait.ended = true
	report_wait(wait.operation, roundi((clock.call() - wait.started) * 1000.0))


func _on_error(
	function: String,
	file: String,
	line: int,
	code: String,
	rationale: String,
	error_type: int,
	backtraces: Array[ScriptBacktrace]
) -> void:
	if not KINDS.has(error_type):
		return
	var stack: Array[String] = []
	for bt in backtraces:
		for i in bt.get_frame_count():
			stack.append(
				(
					"%s:%d in %s"
					% [bt.get_frame_file(i), bt.get_frame_line(i), bt.get_frame_function(i)]
				)
			)
	if stack.is_empty() and file.begins_with(MARK):
		stack.append("%s:%d in %s" % [file, line, function])
	var message := rationale if rationale != "" else code
	_report(KINDS[error_type], message, stack)


func _report(kind: String, message: String, stack: Array[String]) -> void:
	_mutex.lock()
	if _busy:
		_mutex.unlock()
		return
	_busy = true
	var now: float = clock.call()
	var key := "%s|%s" % [kind, message]
	for seen_key in _seen.keys():
		if now - _seen[seen_key] >= WINDOW_SEC:
			_seen.erase(seen_key)
	if not _seen.has(key) and _allowed("error", MAX_PER_MINUTE, now):
		_seen[key] = now
		_write({"kind": kind, "error": message, "stack": stack}, now)
	_busy = false
	_mutex.unlock()


func _slow(operation: String, msec: int, wait_id: String) -> void:
	_mutex.lock()
	var now: float = clock.call()
	if _allowed("slow", MAX_SLOW_PER_MINUTE, now):
		var entry := {
			"kind": SLOW_KIND,
			"error": "%s waited %d ms" % [operation, msec],
			"operation": operation,
			"durationMs": msec,
			"waitId": wait_id,
			"still": false,
		}
		_write(entry, now)
	_mutex.unlock()


func _allowed(bucket: String, cap: int, now: float) -> bool:
	var minute: Array = _minutes.get(bucket, [now, 0])
	if now - minute[0] >= 60.0:
		minute = [now, 0]
	if minute[1] >= cap:
		return false
	_minutes[bucket] = [minute[0], minute[1] + 1]
	return true


## Appends one entry; a missing spool folder is made, a failure drops it.
func _write(entry: Dictionary, now: float) -> void:
	if spool_dir == "" or not enabled:
		return
	var ms := int(fmod(now, 1.0) * 1000.0)
	entry.at = "%s.%03dZ" % [Time.get_datetime_string_from_unix_time(int(now)), ms]
	entry.repo = _repo
	entry.mark = MARK
	entry.build = _build
	if _version != "":
		entry.version = _version
	DirAccess.make_dir_recursive_absolute(spool_dir)
	var path := spool_dir.path_join("%s.jsonl" % _app)
	var file := FileAccess.open(path, FileAccess.READ_WRITE)
	if file == null:
		file = FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		return
	file.seek_end()
	file.store_line(JSON.stringify(entry, "", true))
	file.close()
