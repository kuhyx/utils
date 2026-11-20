extends SceneTree
## Screenshot helper (not a test): renders the demo closed and open, saves PNGs.
## godot --path kuhy_credit/godot --rendering-driver opengl3 \
##     -s res://tests/shot.gd -- <out_dir> [--light]

const Demo = preload("res://demo/demo.tscn")


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	var args := OS.get_cmdline_user_args()
	var out: String = args[0]
	var theme := "light" if args.has("--light") else "dark"
	var demo: Control = Demo.instantiate()
	root.add_child(demo)
	for state in ["closed", "open"]:
		if state == "open":
			demo.credit.logo.pressed.emit()
		for _i in 5:
			await process_frame
		var img := root.get_texture().get_image()
		img.save_png(out.path_join("godot-%s-%s.png" % [theme, state]))
	quit()
