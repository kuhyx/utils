extends Logger
## Forwards engine and script errors to the error reporter. The engine may call
## a logger from any thread, so it only hands over; the reporter locks.
## No class_name (the addon stays out of the global class cache).

var _sink: Callable


func _init(sink: Callable) -> void:
	_sink = sink


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
	_sink.call(function, file, line, code, rationale, error_type, script_backtraces)


func _log_message(_message: String, _error: bool) -> void:
	pass
