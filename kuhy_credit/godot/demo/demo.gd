extends Control
## Demo: a token-coloured screen with the credit in the bottom-right corner.
## Run with `godot --path kuhy_credit/godot` (add `-- --light` for light).

const CreditData = preload("res://addons/kuhy_credit/credit_data.gd")
const CreditScene = preload("res://addons/kuhy_credit/kuhy_credit.tscn")

var credit: Control


func _ready() -> void:
	var is_light := OS.get_cmdline_user_args().has("--light")
	var bg := ColorRect.new()
	bg.color = (CreditData.LIGHT if is_light else CreditData.DARK)["bg"]
	bg.mouse_filter = Control.MOUSE_FILTER_IGNORE
	bg.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(bg)
	credit = CreditScene.instantiate()
	credit.light = is_light
	add_child(credit)
	_place()
	resized.connect(_place)


func _place() -> void:
	var margin := float(CreditData.SPACE_MD)
	credit.position = size - credit.size - Vector2(margin, margin)
