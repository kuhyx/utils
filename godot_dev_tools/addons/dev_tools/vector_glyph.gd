extends RefCounted
## A vector icon: shapes recorded in a 128-unit square (rect, polygon, line,
## frame, ring; `erase` punches a shape out of what is there), resolved once into
## simple, hole-free, non-overlapping polygons. They are drawn at any size
## (CanvasItem or a Texture2D, see glyph_texture.gd), so an icon is as sharp at
## 3840x2160 as at 1280x800. White-on-nothing: tint on draw. No class_name (the
## addon's scripts reach each other with relative preload).

const UNITS := 128.0
const CIRCLE_SEGMENTS := 96
const REACH := 4096.0

## Hole-free pieces in glyph units; they never overlap (an alpha tint stays even).
var pieces: Array[PackedVector2Array] = []

var _points := PackedVector2Array()
var _indices := PackedInt32Array()


## Fills a polygon; erase=true punches it out of what is already there.
func polygon(points: PackedVector2Array, erase := false) -> void:
	var shape := _upright(points)
	_subtract(shape)
	if not erase:
		pieces.append(shape)
	_points = PackedVector2Array()


func rect(x: float, y: float, w: float, h: float, erase := false) -> void:
	polygon(
		PackedVector2Array(
			[Vector2(x, y), Vector2(x + w, y), Vector2(x + w, y + h), Vector2(x, y + h)]
		),
		erase
	)


## Thick segment between two points (flat ends).
func line(a: Vector2, b: Vector2, width: float, erase := false) -> void:
	var n := (b - a).normalized().orthogonal() * width / 2.0
	polygon(PackedVector2Array([a + n, b + n, b - n, a - n]), erase)


## Outline of a rectangle, `t` thick.
func frame(x: float, y: float, w: float, h: float, t: float) -> void:
	rect(x, y, w, h)
	rect(x + t, y + t, w - 2.0 * t, h - 2.0 * t, true)


## Disc or ring (inner > 0); with erase=true it removes that disc or ring.
func ring(center: Vector2, outer: float, inner := 0.0, erase := false) -> void:
	var disc := _circle(center, outer)
	if inner <= 0.0:
		polygon(disc, erase)
		return
	var hole := _circle(center, inner)
	if erase:
		var kept := _intersect_all(hole)
		_subtract(disc)
		pieces.append_array(kept)
	else:
		_subtract(disc)
		pieces.append_array(_difference(disc, hole))
	_points = PackedVector2Array()


func area() -> float:
	var total := 0.0
	for piece in pieces:
		total += piece_area(piece)
	return total


func piece_area(piece: PackedVector2Array) -> float:
	var sum := 0.0
	for i in piece.size():
		sum += piece[i].cross(piece[(i + 1) % piece.size()])
	return absf(sum) / 2.0


## Draws the glyph into `box` of `canvas` (call from its _draw), tinted.
func draw(canvas: CanvasItem, box: Rect2, tint: Color) -> void:
	draw_rid(canvas.get_canvas_item(), box, tint)


## Same, onto a canvas item RID (what a Texture2D is handed to draw on).
func draw_rid(item: RID, box: Rect2, tint: Color) -> void:
	_triangulate()
	var xform := Transform2D(
		Vector2(box.size.x / UNITS, 0), Vector2(0, box.size.y / UNITS), box.position
	)
	RenderingServer.canvas_item_add_set_transform(item, xform)
	RenderingServer.canvas_item_add_triangle_array(
		item, _indices, _points, PackedColorArray([tint])
	)
	RenderingServer.canvas_item_add_set_transform(item, Transform2D.IDENTITY)


func _triangulate() -> void:
	if not _points.is_empty():
		return
	_indices = PackedInt32Array()
	for piece in pieces:
		var base := _points.size()
		_points.append_array(piece)
		for index in Geometry2D.triangulate_polygon(piece):
			_indices.append(base + index)


## Removes `cutter` from every piece, splitting a piece wherever the cutter
## would leave a hole in it.
func _subtract(cutter: PackedVector2Array) -> void:
	var next: Array[PackedVector2Array] = []
	for piece in pieces:
		next.append_array(_difference(piece, cutter))
	pieces = next


## piece minus cutter, as hole-free polygons.
func _difference(
	piece: PackedVector2Array, cutter: PackedVector2Array, depth := 0
) -> Array[PackedVector2Array]:
	var out: Array[PackedVector2Array] = []
	var result := Geometry2D.clip_polygons(piece, cutter)
	if not _has_hole(result) or depth > 4:
		for part in result:
			if depth > 4 and Geometry2D.is_polygon_clockwise(part) != _outer_clockwise(result):
				continue
			out.append(_upright(part))
		return out
	# The cutter sits inside the piece: cut the piece along a line through the
	# cutter first, so the cutter only ever notches an edge.
	var y := _bounds(cutter).get_center().y
	for half in [
		Rect2(-REACH, -REACH, 2.0 * REACH, REACH + y), Rect2(-REACH, y, 2.0 * REACH, REACH)
	]:
		for part in Geometry2D.intersect_polygons(piece, _rect_points(half)):
			out.append_array(_difference(_upright(part), cutter, depth + 1))
	return out


func _intersect_all(shape: PackedVector2Array) -> Array[PackedVector2Array]:
	var out: Array[PackedVector2Array] = []
	for piece in pieces:
		for part in Geometry2D.intersect_polygons(piece, shape):
			out.append(_upright(part))
	return out


func _has_hole(polygons: Array[PackedVector2Array]) -> bool:
	if polygons.size() < 2:
		return false
	var outer := _outer_clockwise(polygons)
	for part in polygons:
		if Geometry2D.is_polygon_clockwise(part) != outer:
			return true
	return false


## Winding of the biggest polygon (an outline; holes wind the other way).
func _outer_clockwise(polygons: Array[PackedVector2Array]) -> bool:
	var biggest := polygons[0]
	for part in polygons:
		if piece_area(part) > piece_area(biggest):
			biggest = part
	return Geometry2D.is_polygon_clockwise(biggest)


## The same polygon wound one fixed way.
func _upright(points: PackedVector2Array) -> PackedVector2Array:
	if not Geometry2D.is_polygon_clockwise(points):
		return points
	var flipped := points.duplicate()
	flipped.reverse()
	return flipped


func _circle(center: Vector2, radius: float) -> PackedVector2Array:
	var points := PackedVector2Array()
	for i in CIRCLE_SEGMENTS:
		points.append(center + Vector2.from_angle(TAU * i / CIRCLE_SEGMENTS) * radius)
	return points


func _bounds(points: PackedVector2Array) -> Rect2:
	var box := Rect2(points[0], Vector2.ZERO)
	for p in points:
		box = box.expand(p)
	return box


func _rect_points(box: Rect2) -> PackedVector2Array:
	return PackedVector2Array(
		[
			box.position,
			Vector2(box.end.x, box.position.y),
			box.end,
			Vector2(box.position.x, box.end.y)
		]
	)
