extends RefCounted
## Icons of the dev tools, drawn as vector glyphs (sharp at any size, no text,
## no icon words). Kinds: rect arrow circle pen undo clear text select save
## cancel note camera. No class_name (the addon's scripts use relative preload).

const DevVectorGlyph = preload("vector_glyph.gd")
const DevGlyphTexture = preload("glyph_texture.gd")

static var _textures: Dictionary = {}


static func texture(kind: String) -> Texture2D:
	if not _textures.has(kind):
		_textures[kind] = DevGlyphTexture.of(_build(kind))
	return _textures[kind]


static func _build(kind: String) -> DevVectorGlyph:
	var g := DevVectorGlyph.new()
	match kind:
		"rect":
			g.frame(18, 30, 92, 68, 10)
		"arrow":
			g.line(Vector2(22, 106), Vector2(80, 48), 13)
			g.polygon(PackedVector2Array([Vector2(106, 22), Vector2(62, 34), Vector2(94, 66)]))
		"circle":
			g.ring(Vector2(64, 64), 46, 36)
		"pen":
			var path := [Vector2(18, 92), Vector2(44, 40), Vector2(66, 90)]
			path.append_array([Vector2(90, 38), Vector2(110, 78)])
			for i in path.size() - 1:
				g.line(path[i], path[i + 1], 10)
				g.ring(path[i + 1], 5)
		"undo":
			g.polygon(PackedVector2Array([Vector2(14, 54), Vector2(50, 22), Vector2(50, 86)]))
			g.line(Vector2(46, 54), Vector2(84, 54), 14)
			g.line(Vector2(84, 54), Vector2(106, 74), 14)
			g.line(Vector2(106, 74), Vector2(84, 98), 14)
			g.line(Vector2(84, 98), Vector2(40, 98), 14)
		"clear":
			g.rect(30, 44, 68, 12)
			g.rect(40, 62, 48, 44)
			g.rect(52, 28, 24, 12)
		"text":
			g.rect(18, 24, 92, 14)
			g.rect(57, 24, 14, 80)
		"select":
			g.ring(Vector2(64, 64), 34, 22)
			g.rect(60, 10, 8, 30)
			g.rect(60, 88, 8, 30)
			g.rect(10, 60, 30, 8)
			g.rect(88, 60, 30, 8)
		"save":
			g.line(Vector2(22, 66), Vector2(52, 96), 16)
			g.line(Vector2(52, 96), Vector2(106, 30), 16)
		"cancel":
			g.line(Vector2(26, 26), Vector2(102, 102), 16)
			g.line(Vector2(102, 26), Vector2(26, 102), 16)
		"note":
			g.rect(18, 30, 92, 12)
			g.rect(18, 58, 92, 12)
			g.rect(18, 86, 58, 12)
		"camera":
			g.rect(12, 38, 104, 72)
			g.rect(44, 24, 40, 18)
			g.ring(Vector2(64, 74), 26, 0.0, true)
			g.ring(Vector2(64, 74), 15)
		_:
			push_error("unknown dev glyph %s" % kind)
	return g
