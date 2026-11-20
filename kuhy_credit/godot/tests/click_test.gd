extends GutTest
## Base for tests that click. GUT's own full-window GUI sits on a CanvasLayer
## above the scene and swallows pushed mouse events, so it is hidden while
## these tests run. The headless window of the official Godot build is 64x64,
## and a click outside the window is dropped, so the window takes the
## project's 640x360 size for these tests.

const TEST_WINDOW := Vector2i(640, 360)

var _gut_layers: Array[Node] = []
var _old_size: Vector2i


func before_all() -> void:
	_old_size = get_window().size
	get_window().size = TEST_WINDOW
	_gut_layers = get_tree().root.find_children("GutLayer", "CanvasLayer", true, false)
	for layer in _gut_layers:
		layer.visible = false


func after_all() -> void:
	for layer in _gut_layers:
		layer.visible = true
	get_window().size = _old_size
