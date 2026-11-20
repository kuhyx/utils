extends "res://tests/click_test.gd"
## E2E: the demo scene, two clicks through the viewport, the URL that would open.

const CreditData = preload("res://addons/kuhy_credit/credit_data.gd")
const Demo = preload("res://demo/demo.tscn")


func _click(at: Vector2) -> void:
	for pressed in [true, false]:
		var ev := InputEventMouseButton.new()
		ev.button_index = MOUSE_BUTTON_LEFT
		ev.pressed = pressed
		ev.position = at
		ev.global_position = at
		get_viewport().push_input(ev, true)
	await wait_process_frames(2)


func test_two_clicks_open_the_website() -> void:
	var demo: Control = Demo.instantiate()
	add_child_autofree(demo)
	await wait_process_frames(2)
	var opened: Array[String] = []
	demo.credit.opener = func(url: String) -> void: opened.append(url)
	assert_false(demo.credit.is_open())
	await _click(demo.credit.logo.get_global_rect().get_center())
	assert_true(demo.credit.is_open())
	assert_eq(opened, [] as Array[String])
	await _click(demo.credit.panel.get_global_rect().get_center())
	assert_eq(opened, [CreditData.URL] as Array[String])
	assert_false(demo.credit.is_open())
