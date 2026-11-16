extends RefCounted
## Writes one feedback as a bundle FOLDER:
##   screenshot.png  the frozen frame as it was
##   annotated.png   the same frame with the red marks burned in
##   report.json     the record (marks in annotated.png pixels, note, game,
##                   variant, player pose, settings, build, session id, files)
##   game.log        the tail of the run's dev.log
##   snapshot.json   the play state (every item and slot, judged)
## `dir` is injected, so tests use a temp dir and never the real feedback
## folder (R11). No class_name (dev files reach each other with preload).


## A file name base (local time, `YYYY-MM-DDTHH-MM-SS-mmm`) for the unix time
## `unix_time` (seconds, fractional); a negative value means now.
static func stamp(unix_time: float = -1.0) -> String:
	return _stamp_ms(_unix_ms(unix_time))


## A bundle folder under `root` that does not exist yet. A clash moves to the
## next free millisecond, so the name keeps the form feedback_inbox accepts.
static func bundle_dir(root: String, unix_time: float = -1.0) -> String:
	var total_ms := _unix_ms(unix_time)
	var dir := root.path_join(_stamp_ms(total_ms))
	while DirAccess.dir_exists_absolute(dir):
		total_ms += 1
		dir = root.path_join(_stamp_ms(total_ms))
	return dir


static func _unix_ms(unix_time: float) -> int:
	if unix_time < 0.0:
		unix_time = Time.get_unix_time_from_system()
	return int(floor(unix_time * 1000.0))


static func _stamp_ms(total_ms: int) -> String:
	var local_secs := total_ms / 1000 + int(Time.get_time_zone_from_system()["bias"]) * 60
	var text := Time.get_datetime_string_from_unix_time(local_secs).replace(":", "-")
	return "%s-%03d" % [text, total_ms % 1000]


## Writes the bundle into `dir` (either image may be null). Returns the record
## with its `files` (absolute paths of what was written) filled in.
static func save(
	dir: String,
	record: Dictionary,
	annotated: Image,
	raw: Image,
	game_log: String,
	snapshot: Dictionary
) -> Dictionary:
	DirAccess.make_dir_recursive_absolute(dir)
	var files := {}
	if annotated != null and annotated.save_png(dir.path_join("annotated.png")) == OK:
		files["annotated"] = dir.path_join("annotated.png")
		record["image"] = [annotated.get_width(), annotated.get_height()]
	if raw != null and raw.save_png(dir.path_join("screenshot.png")) == OK:
		files["screenshot"] = dir.path_join("screenshot.png")
	if _write(dir.path_join("game.log"), game_log):
		files["game_log"] = dir.path_join("game.log")
	if _write(dir.path_join("snapshot.json"), JSON.stringify(snapshot, "\t")):
		files["snapshot"] = dir.path_join("snapshot.json")
	files["report"] = dir.path_join("report.json")
	record["files"] = files
	if not _write(files["report"], JSON.stringify(record, "\t")):
		push_warning("feedback: cannot write %s" % files["report"])
		files.erase("report")
	return record


## The feedback.jsonl line of one saved bundle (the recorder stamps it on the
## video as an "annotation" moment).
static func log_entry(dir: String, record: Dictionary, marks: int) -> Dictionary:
	var files: Dictionary = record.get("files", {})
	return {
		"event": "annotation",
		"bundle": dir,
		"image": files.get("annotated", ""),
		"report": files.get("report", ""),
		"marks": marks,
	}


static func _write(path: String, text: String) -> bool:
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		return false
	file.store_string(text)
	file.close()
	return true
