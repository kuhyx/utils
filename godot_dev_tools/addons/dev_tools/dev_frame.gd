extends RefCounted
## The frame as drawn, for the annotator. A headless run (a bot, a test) draws
## nothing and never emits frame_post_draw, so it gets a blank frame of the
## viewport's size at once: the bundle is still written, only the picture is empty.
## No class_name (the addon's scripts reach each other with relative preload).

const BLANK := Color(0.1, 0.1, 0.1)


## The viewport's last drawn frame (waits for the draw; instant when headless).
static func grab(viewport: Viewport) -> Image:
	if DisplayServer.get_name() == "headless":
		var size := viewport.get_visible_rect().size
		var blank := Image.create(
			maxi(1, int(size.x)), maxi(1, int(size.y)), false, Image.FORMAT_RGBA8
		)
		blank.fill(BLANK)
		return blank
	await RenderingServer.frame_post_draw
	return viewport.get_texture().get_image()
