extends Control
## The dev mode's discoverability hint: a small camera glyph in a corner of the
## screen (no text). Click it (when the mouse is free: hub, pause menu) or press
## F12 to annotate the frame. Faint until hovered; never takes focus.
## No class_name (the addon's scripts reach each other with relative preload).

signal pressed

const DevGlyphs = preload("dev_glyphs.gd")
const DevStyle = preload("dev_style.gd")
const SIZE_PX := 56.0
const MARGIN_PX := 14

var _hover := false


func _init() -> void:
	custom_minimum_size = Vector2.ONE * SIZE_PX
	accessibility_name = "annotate"
	mouse_filter = Control.MOUSE_FILTER_STOP
	focus_mode = Control.FOCUS_NONE
	mouse_entered.connect(_set_hover.bind(true))
	mouse_exited.connect(_set_hover.bind(false))


func _ready() -> void:
	set_anchors_preset(Control.PRESET_TOP_RIGHT)
	offset_right = -MARGIN_PX
	offset_left = -MARGIN_PX - SIZE_PX
	offset_top = MARGIN_PX
	offset_bottom = MARGIN_PX + SIZE_PX


func _gui_input(event: InputEvent) -> void:
	var button := event as InputEventMouseButton
	if button != null and button.button_index == MOUSE_BUTTON_LEFT and button.pressed:
		accept_event()
		pressed.emit()


func _set_hover(on: bool) -> void:
	_hover = on
	queue_redraw()


func _draw() -> void:
	# A dark copy under the white one keeps it readable on a light wall too.
	var glyph := DevGlyphs.texture("camera")
	var shadow := Color(DevStyle.panel, 0.45)
	var ink := Color(DevStyle.ink, 0.95 if _hover else 0.38)
	draw_texture_rect(glyph, Rect2(Vector2(2, 2), size), false, shadow)
	draw_texture_rect(glyph, Rect2(Vector2.ZERO, size), false, ink)
