extends RefCounted
## Widgets of the annotator's bars: glyph buttons, the note field and the dark
## strip they sit on. No class_name (the addon's scripts reach each other with relative preload).

const DevGlyphs = preload("dev_glyphs.gd")
const DevShapes = preload("annotate_shapes.gd")
const DevStyle = preload("dev_style.gd")
const BUTTON_PX := 72
const LABEL_WIDTH_PX := 420.0


## Builds the toolbar (tools, undo, clear, save, cancel), the note strip and the
## floating label field of `owner` (an annotator) and fills its bars,
## tool_buttons, action_buttons, note and text_field.
static func build(owner: Control) -> void:
	var top := _strip(owner, Control.PRESET_TOP_WIDE)
	for id: String in DevShapes.TOOLS:
		owner.tool_buttons[id] = icon_button(top, id, owner.set_tool.bind(id))
	owner.action_buttons["undo"] = icon_button(top, "undo", owner.undo)
	owner.action_buttons["clear"] = icon_button(top, "clear", owner.clear)
	var gap := Control.new()
	gap.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	top.add_child(gap)
	owner.action_buttons["save"] = icon_button(top, "save", owner.save)
	owner.action_buttons["cancel"] = icon_button(top, "cancel", owner.cancel)
	var bottom := _strip(owner, Control.PRESET_BOTTOM_WIDE)
	bottom.add_child(glyph("note"))
	owner.note = note_field()
	owner.note.text_submitted.connect(func(_text: String) -> void: owner.save())
	owner.note.text_changed.connect(func(_text: String) -> void: owner.disarm())
	owner.note.gui_input.connect(_leave_on_escape.bind(owner.note, false))
	bottom.add_child(owner.note)
	# The label field floats at the click; Enter adds the label, Esc drops it.
	var field := note_field()
	field.size_flags_horizontal = Control.SIZE_FILL
	field.custom_minimum_size.x = LABEL_WIDTH_PX
	field.size.x = LABEL_WIDTH_PX
	field.hide()
	field.text_submitted.connect(func(_text: String) -> void: owner.commit_text())
	field.gui_input.connect(_leave_on_escape.bind(field, true))
	owner.add_child(field)
	owner.text_field = field


## Esc inside a text field only leaves it (a label is dropped); a second Esc cancels.
static func _leave_on_escape(event: InputEvent, field: LineEdit, drop: bool) -> void:
	var key := event as InputEventKey
	if key != null and key.pressed and key.keycode == KEY_ESCAPE:
		if drop:
			field.text = ""
			field.hide()
		field.release_focus()
		field.accept_event()


static func _strip(owner: Control, preset: Control.LayoutPreset) -> HBoxContainer:
	var strip := panel(preset)
	owner.add_child(strip)
	strip.set_anchors_and_offsets_preset(preset)
	owner.bars.append(strip)
	return strip.get_child(0)


static func icon_button(row: Control, kind: String, on_press: Callable) -> Button:
	var button := Button.new()
	button.icon = DevGlyphs.texture(kind)
	button.accessibility_name = kind
	button.expand_icon = true
	button.custom_minimum_size = Vector2.ONE * BUTTON_PX
	button.focus_mode = Control.FOCUS_NONE
	button.pressed.connect(on_press)
	row.add_child(button)
	return button


static func glyph(kind: String) -> TextureRect:
	var rect := TextureRect.new()
	rect.texture = DevGlyphs.texture(kind)
	rect.accessibility_name = kind
	rect.custom_minimum_size = Vector2.ONE * 48.0
	rect.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return rect


static func note_field() -> LineEdit:
	var field := LineEdit.new()
	field.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	field.custom_minimum_size.y = 56.0
	field.accessibility_name = "note"
	field.add_theme_font_size_override("font_size", 28)
	var style := StyleBoxFlat.new()
	style.bg_color = DevStyle.panel_pressed
	style.set_content_margin_all(8)
	field.add_theme_stylebox_override("normal", style)
	return field


## A dark strip (the caller anchors it to `preset`) holding one HBoxContainer row.
static func panel(preset: Control.LayoutPreset) -> PanelContainer:
	var strip := PanelContainer.new()
	var style := StyleBoxFlat.new()
	style.bg_color = Color(DevStyle.panel, 0.88)
	style.set_content_margin_all(8)
	strip.add_theme_stylebox_override("panel", style)
	var bottom := preset == Control.PRESET_BOTTOM_WIDE
	strip.grow_vertical = Control.GROW_DIRECTION_BEGIN if bottom else Control.GROW_DIRECTION_END
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 10)
	strip.add_child(row)
	return strip
