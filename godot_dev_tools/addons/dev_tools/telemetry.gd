extends RefCounted
## The session's structured log: one JSON line per moment in
## <feedback dir>/feedback.jsonl. The addon writes the session start and end,
## the exact clock pair a recorder syncs on, and every engine error; the game
## adds its own moments (screens, buys, orders, outcomes...) through `entry`,
## from its host's attach_telemetry (dev_host.gd).
## No class_name (the addon's scripts reach each other with relative preload).

const DevLogger = preload("dev_logger.gd")
const SESSION_ARG := "--session-id="

var dev_log: RefCounted
var logger: Logger
var session_id := ""

var _start_ms := 0
var _done := false


## Starts the run: lets the host connect its moments, writes session_start +
## recording_sync and begins listening for engine errors.
func attach(p_log: RefCounted, host: RefCounted) -> void:
	dev_log = p_log
	var args := OS.get_cmdline_user_args()
	session_id = dev_log.arg_value(args, SESSION_ARG)
	if session_id == "":
		session_id = "%d-%04x" % [Time.get_unix_time_from_system(), randi() & 0xffff]
	dev_log.session = session_id
	_start_ms = Time.get_ticks_msec()
	logger = DevLogger.new()
	OS.add_logger(logger)
	host.attach_telemetry(self)
	entry("session_start", {"args": Array(args), "godot": Engine.get_version_info()["string"]})
	# One exact (unix time, ms) pair: an external recorder places every entry on
	# its timeline with it.
	entry("recording_sync", {"unix_us": int(Time.get_unix_time_from_system() * 1_000_000.0)})


## Once per frame: engine errors caught since the last frame become entries.
func tick() -> void:
	if logger == null:
		return
	for error: Dictionary in logger.drain():
		entry("engine_error", error)


## Ends the session once (window close, quit, tree exit).
func shutdown(reason: String) -> void:
	if _done or dev_log == null:
		return
	_done = true
	tick()
	var elapsed := (Time.get_ticks_msec() - _start_ms) / 1000.0
	entry("session_end", {"reason": reason, "elapsed_s": snappedf(elapsed, 0.001)})
	OS.remove_logger(logger)
	logger = null


## One moment of the run: `event` names it, `fields` is its data.
func entry(event: String, fields: Dictionary) -> void:
	var row := fields.duplicate(true)
	row["event"] = event
	dev_log.entry(row)
