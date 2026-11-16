extends Texture2D
## A vector glyph that any Texture2D slot can show (TextureRect, Button.icon,
## draw_texture_rect): it draws the vector shapes at the size asked for, so it
## never blurs when the screen is bigger than the layout.
## No class_name (the addon's scripts reach each other with relative preload).

const DevVectorGlyph = preload("vector_glyph.gd")

var glyph: DevVectorGlyph
## Natural size in pixels (what a theme slot lays out with).
var px: int = int(DevVectorGlyph.UNITS)
## Colour baked in for slots that cannot tint; white = tint on draw.
var tint: Color = Color.WHITE


static func of(p_glyph: DevVectorGlyph, p_px := int(DevVectorGlyph.UNITS)) -> Texture2D:
	var tex := new()
	tex.glyph = p_glyph
	tex.px = p_px
	return tex


func _get_width() -> int:
	return px


func _get_height() -> int:
	return px


func _has_alpha() -> bool:
	return true


func _draw(to_canvas_item: RID, pos: Vector2, modulate: Color, _transpose: bool) -> void:
	glyph.draw_rid(to_canvas_item, Rect2(pos, Vector2.ONE * px), modulate * tint)


func _draw_rect(
	to_canvas_item: RID, rect: Rect2, _tile: bool, modulate: Color, _transpose: bool
) -> void:
	glyph.draw_rid(to_canvas_item, rect, modulate * tint)


func _draw_rect_region(
	to_canvas_item: RID, rect: Rect2, _src: Rect2, modulate: Color, _transpose: bool, _clip_uv: bool
) -> void:
	glyph.draw_rid(to_canvas_item, rect, modulate * tint)
