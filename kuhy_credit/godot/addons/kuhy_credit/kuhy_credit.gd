extends Control
## The shared kuhy credit: an M1 logo button that opens a panel.
##
## A click or Enter on the logo opens a panel (logo + credit text); a
## click or Enter on the panel opens the website through [member opener]
## (default OS.shell_open) and closes it. Escape, a click anywhere else and a
## second logo click close it. The logo is rasterised at runtime from the
## inlined M1 SVG, so the addon needs no import step and loads nothing.

const CreditData = preload("credit_data.gd")

@export var logo_size := 48:
	set = _set_logo_size
@export var placement_below := false
@export var align_start := false
@export var light := false:
	set = _set_light

## Called with the URL when the panel is activated.
var opener: Callable
var logo: TextureButton
var panel: PanelContainer
var panel_logo: TextureRect
var label: Label


func _init() -> void:
	opener = _shell_open
	logo = TextureButton.new()
	logo.ignore_texture_size = true
	logo.stretch_mode = TextureButton.STRETCH_KEEP_ASPECT_CENTERED
	logo.focus_mode = Control.FOCUS_ALL
	logo.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	logo.accessibility_name = CreditData.TEXT
	logo.pressed.connect(_toggle)
	add_child(logo)
	panel = PanelContainer.new()
	panel.visible = false
	panel.focus_mode = Control.FOCUS_ALL
	panel.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	panel.accessibility_name = CreditData.TEXT
	panel.gui_input.connect(_on_panel_input)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", CreditData.SPACE_SM)
	row.mouse_filter = Control.MOUSE_FILTER_IGNORE
	panel_logo = TextureRect.new()
	panel_logo.mouse_filter = Control.MOUSE_FILTER_IGNORE
	label = Label.new()
	label.text = CreditData.TEXT
	label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	row.add_child(panel_logo)
	row.add_child(label)
	panel.add_child(row)
	add_child(panel)
	_set_logo_size(logo_size)
	_apply_theme()


## True while the panel shows.
func is_open() -> bool:
	return panel.visible


## Hide the panel.
func close() -> void:
	panel.visible = false


func _input(event: InputEvent) -> void:
	if not panel.visible:
		return
	if event is InputEventKey and event.pressed and event.keycode == KEY_ESCAPE:
		close()
		logo.grab_focus()
		get_viewport().set_input_as_handled()
	elif event is InputEventMouseButton and event.pressed:
		var at: Vector2 = event.position
		if not panel.get_global_rect().has_point(at) and not logo.get_global_rect().has_point(at):
			close()


func _toggle() -> void:
	if panel.visible:
		close()
		return
	panel.reset_size()
	var box := panel.get_combined_minimum_size()
	var x := 0.0 if align_start else logo_size - box.x
	var y := logo_size + CreditData.SPACE_SM if placement_below else -box.y - CreditData.SPACE_SM
	panel.position = Vector2(x, y)
	panel.visible = true
	panel.grab_focus()


func _on_panel_input(event: InputEvent) -> void:
	var clicked: bool = (
		event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT
	)
	if clicked or event.is_action_pressed("ui_accept"):
		accept_event()
		close()
		opener.call(CreditData.URL)


## Scene/inspector values arrive after _init, so the size rebuilds here.
func _set_logo_size(value: int) -> void:
	logo_size = value
	close()
	var texture := _logo_texture(value)
	var edge := Vector2(value, value)
	logo.texture_normal = texture
	logo.custom_minimum_size = edge
	logo.size = edge
	panel_logo.texture = texture
	custom_minimum_size = edge
	size = edge


func _set_light(value: bool) -> void:
	light = value
	_apply_theme()


func _apply_theme() -> void:
	var pal: Dictionary = CreditData.LIGHT if light else CreditData.DARK
	var box := StyleBoxFlat.new()
	box.bg_color = pal["surface"]
	box.border_color = pal["border"]
	box.set_border_width_all(1)
	box.set_corner_radius_all(CreditData.RADIUS)
	box.set_content_margin_all(CreditData.SPACE_MD)
	panel.add_theme_stylebox_override("panel", box)
	var ring := StyleBoxFlat.new()
	ring.draw_center = false
	ring.border_color = CreditData.FOCUS
	ring.set_border_width_all(2)
	ring.set_corner_radius_all(CreditData.RADIUS)
	ring.set_expand_margin_all(2)
	logo.add_theme_stylebox_override("focus", ring)
	panel.add_theme_stylebox_override("focus", ring)
	label.add_theme_color_override("font_color", pal["text"])
	label.add_theme_font_size_override("font_size", CreditData.TEXT_BODY)


func _shell_open(url: String) -> void:
	OS.shell_open(url)


static func _logo_texture(px: int) -> ImageTexture:
	var img := Image.new()
	img.load_svg_from_string(CreditData.LOGO_SVG, float(px) / CreditData.LOGO_SIZE)
	return ImageTexture.create_from_image(img)
