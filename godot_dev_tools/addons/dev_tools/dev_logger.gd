extends Logger
## Catches what the engine prints to stderr (script errors, push_error,
## push_warning, shader errors, stderr lines) so the telemetry can write it
## into feedback.jsonl next to what the player did. The engine calls this from
## any thread, so it only queues under a mutex; `drain` hands the queue to the
## main thread once per frame. Identical entries fold into one with a count.
## No class_name (dev files reach each other with preload).

const KINDS: Array[String] = ["error", "warning", "script_error", "shader_error"]
## Distinct entries kept between two drains; the rest is only counted.
const MAX_DISTINCT := 20

var dropped := 0

var _mutex := Mutex.new()
var _queue: Dictionary = {}


func _log_error(
	function: String,
	file: String,
	line: int,
	code: String,
	rationale: String,
	_editor_notify: bool,
	error_type: int,
	script_backtraces: Array[ScriptBacktrace]
) -> void:
	var kind := KINDS[error_type] if error_type >= 0 and error_type < KINDS.size() else "error"
	var entry := {
		"kind": kind,
		"message": code,
		"detail": rationale,
		"file": file,
		"line": line,
		"function": function,
	}
	if not script_backtraces.is_empty():  # where in the GDScript it came from
		entry["where"] = script_backtraces[0].format().left(400)
	_add(entry)


func _log_message(message: String, error: bool) -> void:
	if error:
		_add({"kind": "stderr", "message": message.strip_edges()})


## The queued entries (each with a `count`), oldest first; empties the queue.
func drain() -> Array[Dictionary]:
	_mutex.lock()
	var out: Array[Dictionary] = []
	for entry: Dictionary in _queue.values():
		out.append(entry)
	_queue = {}
	_mutex.unlock()
	return out


func _add(entry: Dictionary) -> void:
	var key := (
		"%s|%s|%s|%s"
		% [entry["kind"], entry.get("file", ""), entry.get("line", 0), entry["message"]]
	)
	_mutex.lock()
	if _queue.has(key):
		_queue[key]["count"] += 1
	elif _queue.size() < MAX_DISTINCT:
		entry["count"] = 1
		_queue[key] = entry
	else:
		dropped += 1
	_mutex.unlock()
