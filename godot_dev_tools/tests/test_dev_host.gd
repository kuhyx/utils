extends GutTest
## The host wrapper: a game hands in any object, the addon fills every gap with
## a default, and the colours a host names replace the defaults.

const DevHost = preload("res://addons/dev_tools/dev_host.gd")
const Style = preload("res://addons/dev_tools/dev_style.gd")
const StubHost = preload("res://tests/stub_host.gd")


class MethodsOnly:
	extends RefCounted

	func game() -> String:
		return "from-a-method"

	func feedback_env() -> String:
		return "METHOD_ENV"


func after_each() -> void:
	Style.apply({})


func test_a_missing_host_answers_with_defaults() -> void:
	var host := DevHost.new()
	assert_eq(host.game(), "game")
	assert_eq(host.feedback_env(), "DEV_FEEDBACK_DIR")
	assert_eq(host.colors(), {})
	assert_eq(host.debug_state(), {})
	assert_eq(host.pick_at(Vector2.ONE), {})
	assert_eq(host.context({"a": 1}), {})
	assert_false(host.can_reset())
	assert_eq(host.markdown_hooks(), {})
	host.close_menu()
	host.add_menu_entry("x", null, "x", func() -> void: pass)
	host.attach_telemetry(null)


func test_a_value_may_be_a_property_or_a_method() -> void:
	assert_eq(DevHost.new(StubHost.new()).game(), "stub-game")
	assert_eq(DevHost.new(StubHost.new()).feedback_env(), "STUB_FEEDBACK_DIR")
	assert_eq(DevHost.new(MethodsOnly.new()).game(), "from-a-method")
	assert_eq(DevHost.new(MethodsOnly.new()).feedback_env(), "METHOD_ENV")


func test_the_host_answers_what_it_has() -> void:
	var host := DevHost.new(StubHost.new())
	assert_true(host.can_reset())
	assert_eq(host.pick_at(Vector2(5, 5))["id"], "thing")
	assert_eq(host.pick_at(Vector2(500, 5)), {})
	assert_eq(host.context(host.debug_state())["mode"], "stub")
	assert_eq(host.markdown_hooks().keys(), ["summary_line"], "only the hooks the game has")


func test_host_colours_replace_the_defaults_and_apply_resets_them() -> void:
	Style.apply({"mark": Color.BLUE, "ink": Color.RED})
	assert_eq(Style.mark, Color.BLUE)
	assert_eq(Style.ink, Color.RED)
	assert_eq(Style.panel, Style.DEFAULT_PANEL, "a key the host leaves out keeps the default")
	Style.apply({})
	assert_eq(Style.mark, Style.DEFAULT_MARK)
