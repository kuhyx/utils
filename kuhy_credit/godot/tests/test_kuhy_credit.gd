extends "res://tests/click_test.gd"
## The credit control: logo -> panel -> URL, every close path, theme tokens.
## Input goes through the viewport (push_input), as a real click would.

const CreditData = preload("res://addons/kuhy_credit/credit_data.gd")
const Scene = preload("res://addons/kuhy_credit/kuhy_credit.tscn")

var credit: Control
var opened: Array[String] = []


func before_each() -> void:
	opened.clear()
	credit = Scene.instantiate()
	credit.opener = func(url: String) -> void: opened.append(url)
	credit.position = Vector2(500, 260)
	add_child_autofree(credit)
	await wait_process_frames(2)


func _click_at(pos: Vector2) -> void:
	for pressed in [true, false]:
		var ev := InputEventMouseButton.new()
		ev.button_index = MOUSE_BUTTON_LEFT
		ev.pressed = pressed
		ev.position = pos
		ev.global_position = pos
		get_viewport().push_input(ev, true)
	await wait_process_frames(2)


func _click(control: Control) -> void:
	await _click_at(control.get_global_rect().get_center())


func _key(code: Key) -> void:
	for pressed in [true, false]:
		var ev := InputEventKey.new()
		ev.keycode = code
		ev.physical_keycode = code
		ev.pressed = pressed
		get_viewport().push_input(ev)
	await wait_process_frames(2)


func test_shows_only_the_logo_at_start() -> void:
	assert_true(credit.logo.visible)
	assert_false(credit.panel.visible)
	assert_not_null(credit.logo.texture_normal)
	assert_eq(credit.logo.accessibility_name, CreditData.TEXT)
	assert_eq(opened, [] as Array[String])


func test_logo_click_opens_panel_with_logo_and_text() -> void:
	await _click(credit.logo)
	assert_true(credit.is_open())
	assert_eq(credit.label.text, CreditData.TEXT)
	assert_not_null(credit.panel_logo.texture)
	assert_eq(opened, [] as Array[String])


func test_panel_click_opens_the_url_and_closes() -> void:
	await _click(credit.logo)
	await _click(credit.label)
	assert_eq(opened, [CreditData.URL] as Array[String])
	assert_false(credit.is_open())


func test_escape_closes_without_opening() -> void:
	await _click(credit.logo)
	await _key(KEY_ESCAPE)
	assert_false(credit.is_open())
	assert_true(credit.logo.has_focus())
	assert_eq(opened, [] as Array[String])


func test_outside_click_closes() -> void:
	await _click(credit.logo)
	await _click_at(Vector2(10, 10))
	assert_false(credit.is_open())
	assert_eq(opened, [] as Array[String])


func test_second_logo_click_closes_and_stays_closed() -> void:
	await _click(credit.logo)
	await _click(credit.logo)
	assert_false(credit.is_open())
	assert_eq(opened, [] as Array[String])


func test_keyboard_reaches_and_opens() -> void:
	assert_eq(credit.logo.focus_mode, Control.FOCUS_ALL)
	credit.logo.grab_focus()
	await _key(KEY_ENTER)
	assert_true(credit.is_open())
	assert_true(credit.panel.has_focus())
	await _key(KEY_ENTER)
	assert_eq(opened, [CreditData.URL] as Array[String])


func test_other_input_is_ignored() -> void:
	await _key(KEY_ESCAPE)
	await _click_at(Vector2(10, 10))
	assert_false(credit.is_open())
	await _click(credit.logo)
	await _key(KEY_A)
	assert_true(credit.is_open())


func test_panel_sits_above_and_end_aligned_by_default() -> void:
	await _click(credit.logo)
	var p: Rect2 = credit.panel.get_global_rect()
	var l: Rect2 = credit.logo.get_global_rect()
	assert_lt(p.end.y, l.position.y)
	assert_almost_eq(p.end.x, l.end.x, 0.5)


func test_below_and_start_placement() -> void:
	credit.placement_below = true
	credit.align_start = true
	await _click(credit.logo)
	var p: Rect2 = credit.panel.get_global_rect()
	var l: Rect2 = credit.logo.get_global_rect()
	assert_gt(p.position.y, l.end.y)
	assert_almost_eq(p.position.x, l.position.x, 0.5)


func test_logo_size_set_after_init_resizes_and_anchors() -> void:
	credit.logo_size = 96
	assert_eq(credit.logo.size, Vector2(96, 96))
	assert_eq(credit.size, Vector2(96, 96))
	assert_eq(credit.logo.texture_normal.get_width(), 96)
	await _click(credit.logo)
	var p: Rect2 = credit.panel.get_global_rect()
	assert_almost_eq(p.end.x, credit.logo.get_global_rect().end.x, 0.5)


func test_scene_values_apply_on_instantiate() -> void:
	var packed := PackedScene.new()
	var node: Control = Scene.instantiate()
	node.logo_size = 64
	node.placement_below = true
	packed.pack(node)
	node.free()
	var fresh: Control = packed.instantiate()
	add_child_autofree(fresh)
	assert_eq(fresh.logo.size, Vector2(64, 64))
	assert_true(fresh.placement_below)


func test_theme_colours_come_from_tokens() -> void:
	var box: StyleBoxFlat = credit.panel.get_theme_stylebox("panel")
	assert_eq(box.bg_color, CreditData.DARK.surface)
	assert_eq(box.border_color, CreditData.DARK.border)
	assert_eq(box.corner_radius_top_left, CreditData.RADIUS)
	credit.light = true
	box = credit.panel.get_theme_stylebox("panel")
	assert_eq(box.bg_color, CreditData.LIGHT.surface)
	assert_eq(credit.label.get_theme_color("font_color"), CreditData.LIGHT.text)


func test_default_opener_is_shell_open() -> void:
	var fresh: Control = Scene.instantiate()
	assert_true(fresh.opener.is_valid())
	assert_eq(fresh.opener.get_method(), &"_shell_open")
	fresh.free()
