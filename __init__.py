rigify_info = {
    "name": "Gamify - Game Ready Rig Types",
    "description": "GameReady Rigify arm, spine, finger, super-copy and leg types.",
    "author": "Anthony Carter and Susan (ChatGPT)",
    "version": (0, 0, 403),
    "blender": (5, 0, 0),
}


def register():
    from . import viewport_preview
    viewport_preview.register()


def unregister():
    from . import viewport_preview
    viewport_preview.unregister()
