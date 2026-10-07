rigify_info = {
    "name": "Gamify - Game Ready Rig Types",
    "description": "GameReady Rigify arm, spine, finger, super-copy and leg types.",
    "author": "Anthony Carter and Susan (ChatGPT)",
    "version": (0, 0, 404),
    "blender": (5, 0, 0),
}


def register():
    from . import generation_defaults
    generation_defaults.register()
    from . import gamify_menu, meta_rig_tools, rig_toggle, viewport_preview, weight_paint_memory
    rig_toggle.register()
    meta_rig_tools.register()
    viewport_preview.register()
    gamify_menu.register()
    weight_paint_memory.register()


def unregister():
    from . import generation_defaults
    generation_defaults.unregister()
    from . import gamify_menu, meta_rig_tools, rig_toggle, viewport_preview, weight_paint_memory
    weight_paint_memory.unregister()
    gamify_menu.unregister()
    viewport_preview.unregister()
    meta_rig_tools.unregister()
    rig_toggle.unregister()
