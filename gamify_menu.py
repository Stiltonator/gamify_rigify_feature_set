"""Gamify actions and preview controls in the 3D View header menu."""

import bpy
from bpy.props import BoolProperty


class VIEW3D_MT_gamify_menu(bpy.types.Menu):
    bl_label = "Gamify"
    bl_idname = "VIEW3D_MT_gamify_menu"

    def draw(self, context):
        layout = self.layout
        layout.operator(
            "view3d.gamify_toggle_meta_generated_rig",
            text="Toggle Meta/Generated Rig",
        )

        layout.separator()
        obj = context.active_object
        row = layout.row()
        row.enabled = _is_valid_rigify_metarig(context, obj)
        row.operator(
            "view3d.gamify_regenerate_meta_rig",
            text="Regenerate Meta Rig",
        )
        layout.prop(context.scene, 'gamify_show_mch_bones', text="Show MCH Bones")
        layout.prop(context.scene, 'gamify_show_def_bones', text="Show DEF Bones")

        if obj and obj.type == 'ARMATURE' and obj.mode == 'POSE':
            layout.separator()
            layout.prop(context.scene, 'gamify_preview_all_gizmos', text="Preview All Gizmos")
            layout.prop(context.scene, 'gamify_gizmos_draw_in_front', text="Gizmos Draw In Front")


def _is_valid_rigify_metarig(context, obj):
    """Use Rigify's own metarig validation for the menu enabled state."""
    if not obj or obj.type != 'ARMATURE':
        return False

    try:
        from rigify.utils.rig import is_valid_metarig
        return bool(is_valid_metarig(context))
    except (ImportError, AttributeError, RuntimeError, TypeError):
        # Rigify may be disabled or not fully initialized; don't expose an
        # action that would fail in that state.
        return False


def _draw_gamify_header(self, context):
    obj = context.active_object
    if obj and obj.type == 'ARMATURE' and obj.mode in {'OBJECT', 'EDIT', 'POSE'}:
        self.layout.menu(VIEW3D_MT_gamify_menu.bl_idname, text="Gamify")


def register():
    bpy.types.Scene.gamify_show_mch_bones = BoolProperty(
        name="Show MCH Bones",
        description="Show the generated rig's MCH bone collection after regeneration",
        default=False,
    )
    bpy.types.Scene.gamify_show_def_bones = BoolProperty(
        name="Show DEF Bones",
        description="Show the generated rig's DEF bone collection after regeneration",
        default=False,
    )
    bpy.utils.register_class(VIEW3D_MT_gamify_menu)
    bpy.types.VIEW3D_MT_editor_menus.append(_draw_gamify_header)


def unregister():
    try:
        bpy.types.VIEW3D_MT_editor_menus.remove(_draw_gamify_header)
    except (RuntimeError, ValueError):
        pass
    if hasattr(bpy.types.Scene, 'gamify_show_mch_bones'):
        del bpy.types.Scene.gamify_show_mch_bones
    if hasattr(bpy.types.Scene, 'gamify_show_def_bones'):
        del bpy.types.Scene.gamify_show_def_bones
    try:
        bpy.utils.unregister_class(VIEW3D_MT_gamify_menu)
    except (RuntimeError, ValueError):
        pass
