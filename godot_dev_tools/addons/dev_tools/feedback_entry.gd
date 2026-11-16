extends RefCounted
## One saved feedback as Markdown: a ready-to-run prompt for a later Claude
## session. Entries go to <feedback dir>/feedback-<date>.md (kuhy's
## ~/data/<game>_binaries/feedback, never a TODO file in the repo). The inbox
## (utils feedback_inbox) reads the file paths and, by default, the `Game ..., combo ...`
## line: a host may replace that line and the selected-object line with the
## `summary_line` and `entity_line` callables (record / entity -> String).
## No class_name (the addon's scripts reach each other with relative preload).

const TITLE_CHARS := 60


## Appends the entry for `record` (as returned by FeedbackSaver.save) to the
## day's file in `root`; returns that file's path.
static func append(root: String, record: Dictionary, hooks := {}) -> String:
	DirAccess.make_dir_recursive_absolute(root)
	var path := root.path_join("feedback-%s.md" % Time.get_date_string_from_system())
	var mode := FileAccess.READ_WRITE if FileAccess.file_exists(path) else FileAccess.WRITE
	var file := FileAccess.open(path, mode)
	if file == null:
		push_warning("feedback: cannot open %s" % path)
		return ""
	file.seek_end()
	file.store_string(("\n" if file.get_position() > 0 else "") + markdown(record, hooks))
	file.close()
	return path


static func markdown(record: Dictionary, hooks := {}) -> String:
	var note: String = str(record.get("note", "")).strip_edges()
	var title := note.get_slice("\n", 0).left(TITLE_CHARS)
	var out: Array[String] = ["## %s: %s" % [record.get("time", "?"), title], ""]
	out.append(note if note != "" else "(no note)")
	out.append("")
	out.append_array(_facts(record, hooks))
	out.append("")
	out.append(_task(record))
	return "\n".join(out) + "\n"


static func _facts(record: Dictionary, hooks: Dictionary) -> Array[String]:
	var files: Dictionary = record.get("files", {})
	var facts: Array[String] = []
	var annotated: String = files.get("annotated", "-")
	var raw: String = files.get("screenshot", "-")
	facts.append("- Screenshot (red marks are kuhy's): `%s` (raw: `%s`)" % [annotated, raw])
	facts.append("- Report: `%s` (marks in screenshot pixels)" % files.get("report", "-"))
	facts.append(
		(
			"- Game state: `%s`; log tail: `%s`"
			% [files.get("snapshot", "-"), files.get("game_log", "-")]
		)
	)
	facts.append(
		_call(
			hooks,
			"summary_line",
			record,
			"- Game `%s`, combo `%s`, build %s, session `%s`" % _where(record)
		)
	)
	for entity: Dictionary in record.get("selected", []):
		facts.append(
			_call(hooks, "entity_line", entity, "- Selected %s `%s` (%s) at %s" % _entity(entity))
		)
	for shape: Dictionary in record.get("shapes", []):
		if shape["tool"] == "text":
			facts.append('- Label at %s: "%s"' % [shape["a"], shape["text"]])
	return facts


## The host's line when it gave a hook for `name`, else `fallback`.
static func _call(hooks: Dictionary, name: String, arg: Dictionary, fallback: String) -> String:
	var hook: Callable = hooks.get(name, Callable())
	return str(hook.call(arg)) if hook.is_valid() else fallback


static func _where(record: Dictionary) -> Array:
	var build: Dictionary = record.get("build", {})
	return [
		record.get("game", "-"),
		record.get("combo", ""),
		build.get("id", "?"),
		record.get("session", "")
	]


static func _entity(entity: Dictionary) -> Array:
	return [
		entity.get("kind", "?"),
		entity.get("id", "?"),
		entity.get("state", "-"),
		entity.get("position", entity.get("at", [])),
	]


static func _task(record: Dictionary) -> String:
	var count := (record.get("shapes", []) as Array).size()
	return (
		"Task: Read the annotated screenshot (%d marks), match the marks and selected" % count
		+ " objects to `snapshot.json` and the code, and find what is wrong. Write a red"
		+ " test first, fix it, and show kuhy before and after."
	)
