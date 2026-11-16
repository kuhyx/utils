extends RefCounted
## What the game shows when F12 froze it, as the fields of one feedback record:
## the generic ones (session, build, engine, game, pause state, scene, window
## sizes, tag) plus the host's own (mode, screen, combo, pose, settings...).
## The session id and tag come from the dev log (the telemetry's session).
## No class_name (the addon's scripts reach each other with relative preload).

static var _build: Dictionary = {}


## `host` is a dev_host.gd wrapper; `state` its debug_state() (taken here when the caller has none).
static func capture(
	host: RefCounted, tree: SceneTree, dev_log: RefCounted, was_paused: bool, state := {}
) -> Dictionary:
	if state.is_empty():
		state = host.debug_state()
	var window := DisplayServer.window_get_size()
	var canvas := tree.root.get_visible_rect().size
	var out := {
		"session": dev_log.session,
		"build": build_info(),
		"godot": Engine.get_version_info()["string"],
		"game": host.game(),
	}
	out.merge(host.context(state), true)
	out["paused"] = was_paused
	out["scene"] = tree.current_scene.scene_file_path if tree.current_scene != null else ""
	out["window"] = [window.x, window.y]
	out["canvas"] = [canvas.x, canvas.y]
	if dev_log.tag != "":
		out["tag"] = dev_log.tag
	return out


## {id: the git commit of a source run ("export" in a build), version, debug}.
static func build_info() -> Dictionary:
	if _build.is_empty():
		var output: Array = []
		var id := "export"
		var root := ProjectSettings.globalize_path("res://")
		if not OS.has_feature("template") and root != "":
			if OS.execute("git", ["-C", root, "rev-parse", "--short", "HEAD"], output) == 0:
				id = str(output[0]).strip_edges()
		_build = {
			"id": id,
			"version": str(ProjectSettings.get_setting("application/config/version", "")),
			"debug": OS.is_debug_build(),
		}
	return _build
