extends RefCounted
## The red marks of the annotator as plain data, so a test or a bot draws the
## same marks a mouse does. A shape is {tool, a, b, points}: rect/circle span
## the box a..b, an arrow points at b, a pen stroke follows `points`, a text
## label starts at a (key `text`), a select ring sits at a around the game
## object that was under the cursor (key `entity`, the host's pick_at).
## No class_name (the addon's scripts reach each other with relative preload).

const DevStyle = preload("dev_style.gd")
const TOOLS: Array[String] = ["rect", "arrow", "circle", "pen", "text", "select"]
const KEYS := {
	KEY_R: "rect", KEY_A: "arrow", KEY_C: "circle", KEY_P: "pen", KEY_T: "text", KEY_S: "select"
}
const WIDTH := 5.0
const HEAD_LEN := 26.0
const HEAD_ANGLE := 0.45
const MIN_DRAG := 3.0
## Pen samples closer than this (px) are dropped.
const PEN_STEP := 3.0
const FONT_PX := 32
const OUTLINE_PX := 8
const RING_PX := 20.0


static func make(
	shape_tool: String, a: Vector2, b: Vector2, points := PackedVector2Array(), extra := {}
) -> Dictionary:
	var shape := {"tool": shape_tool, "a": a, "b": b, "points": points}
	shape.merge(extra)
	return shape


## A mouse drag moved `shape` on to `at`: a pen stroke also keeps the point.
static func extend(shape: Dictionary, at: Vector2) -> void:
	shape["b"] = at
	var points: PackedVector2Array = shape["points"]
	if shape["tool"] == "pen" and points[points.size() - 1].distance_to(at) >= PEN_STEP:
		points.append(at)
		shape["points"] = points


## A drag too short to mean anything is a stray click, not a mark.
static func meaningful(shape: Dictionary) -> bool:
	match shape["tool"]:
		"pen":
			return (shape["points"] as PackedVector2Array).size() >= 2
		"text":
			return str(shape.get("text", "")).strip_edges() != ""
		"select":
			return not (shape.get("entity", {}) as Dictionary).is_empty()
	return (shape["a"] as Vector2).distance_to(shape["b"]) > MIN_DRAG


static func paint(canvas: CanvasItem, shape: Dictionary) -> void:
	var a: Vector2 = shape["a"]
	var b: Vector2 = shape["b"]
	match shape["tool"]:
		"rect":
			canvas.draw_rect(Rect2(a, b - a).abs(), DevStyle.mark, false, WIDTH)
		"circle":
			canvas.draw_polyline(ellipse(Rect2(a, b - a).abs()), DevStyle.mark, WIDTH)
		"arrow":
			canvas.draw_line(a, b, DevStyle.mark, WIDTH)
			canvas.draw_colored_polygon(arrow_head(a, b), DevStyle.mark)
		"pen":
			var points: PackedVector2Array = shape["points"]
			if points.size() >= 2:
				canvas.draw_polyline(points, DevStyle.mark, WIDTH, true)
		"text":
			_label(canvas, a, str(shape["text"]))
		"select":
			canvas.draw_polyline(
				ellipse(Rect2(a - Vector2.ONE * RING_PX, Vector2.ONE * RING_PX * 2)),
				DevStyle.mark,
				WIDTH
			)
			canvas.draw_line(
				a - Vector2(RING_PX * 1.6, 0), a + Vector2(RING_PX * 1.6, 0), DevStyle.mark, 2.0
			)
			canvas.draw_line(
				a - Vector2(0, RING_PX * 1.6), a + Vector2(0, RING_PX * 1.6), DevStyle.mark, 2.0
			)
			_label(canvas, a + Vector2(RING_PX + 10, -RING_PX), str(shape["entity"].get("id", "")))


## Red words with a dark outline, `at` = the top-left of the text.
static func _label(canvas: CanvasItem, at: Vector2, text: String) -> void:
	var font := ThemeDB.fallback_font
	var base := at + Vector2(0, FONT_PX)
	canvas.draw_string_outline(
		font, base, text, HORIZONTAL_ALIGNMENT_LEFT, -1, FONT_PX, OUTLINE_PX, DevStyle.panel
	)
	canvas.draw_string(font, base, text, HORIZONTAL_ALIGNMENT_LEFT, -1, FONT_PX, DevStyle.mark)


static func ellipse(box: Rect2) -> PackedVector2Array:
	var points := PackedVector2Array()
	for i in 49:
		var angle := TAU * i / 48.0
		points.append(box.get_center() + Vector2(cos(angle), sin(angle)) * box.size / 2.0)
	return points


static func arrow_head(a: Vector2, b: Vector2) -> PackedVector2Array:
	var back := (a - b).normalized() * HEAD_LEN
	return PackedVector2Array([b, b + back.rotated(HEAD_ANGLE), b + back.rotated(-HEAD_ANGLE)])


## JSON-safe shape in the saved PNG's pixels (`scale` = png size / canvas size).
static func to_json(shape: Dictionary, scale: Vector2) -> Dictionary:
	var out := {"tool": shape["tool"], "a": _pt(shape["a"], scale), "b": _pt(shape["b"], scale)}
	if shape["tool"] == "pen":
		var points := []
		for p: Vector2 in shape["points"]:
			points.append(_pt(p, scale))
		out["points"] = points
	if shape["tool"] == "text":
		out["text"] = shape["text"]
	if shape["tool"] == "select":
		out["entity"] = entity_json(shape, scale)
	return out


## {shapes, selected} for the report: every mark, and the game objects the
## select marks name, all in the saved PNG's pixels.
## `first`: an object selected without a click (the painting held up in an
## inspection, its "at" already in PNG pixels); a click on it is not listed twice.
static func marks_json(shapes: Array[Dictionary], scale: Vector2, first := {}) -> Dictionary:
	var marks := []
	var selected := [] if first.is_empty() else [first.duplicate(true)]
	for shape in shapes:
		marks.append(to_json(shape, scale))
		var entity: Dictionary = shape.get("entity", {})
		if shape["tool"] == "select" and (first.is_empty() or entity.get("id") != first["id"]):
			selected.append(entity_json(shape, scale))
	return {"shapes": marks, "selected": selected}


## The selected game object plus where you clicked, in the PNG's pixels.
static func entity_json(shape: Dictionary, scale: Vector2) -> Dictionary:
	var out: Dictionary = (shape["entity"] as Dictionary).duplicate(true)
	out["at"] = _pt(shape["a"], scale)
	return out


static func _pt(p: Vector2, scale: Vector2) -> Array:
	return [roundi(p.x * scale.x), roundi(p.y * scale.y)]
