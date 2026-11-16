extends RefCounted
## One throwaway folder per test run under user:// (test.sh points user:// at a
## temporary XDG_DATA_HOME, so nothing lands in a real game's saves).
## No class_name (tests load it by path).

const META := "dev_tools_test_run_dir"


## A subfolder of this run's folder, made.
static func path(name: String) -> String:
	if not Engine.has_meta(META):
		Engine.set_meta(META, "user://dev_tools_test_%d_%d" % [OS.get_process_id(), randi()])
	var dir: String = Engine.get_meta(META).path_join(name)
	DirAccess.make_dir_recursive_absolute(dir)
	return dir


## Deletes `dir` with everything in it.
static func remove_tree(dir: String) -> void:
	if not DirAccess.dir_exists_absolute(dir):
		return
	for file_name in DirAccess.get_files_at(dir):
		DirAccess.remove_absolute(dir.path_join(file_name))
	for sub in DirAccess.get_directories_at(dir):
		remove_tree(dir.path_join(sub))
	DirAccess.remove_absolute(dir)
