"""Utilities for regenerating a Rigify metarig from the 3D View."""

import bpy
from bpy.types import Operator


OPERATOR_ID = "view3d.gamify_regenerate_meta_rig"
_keymap_items = []


def _is_valid_rigify_metarig(context):
    """Return whether the active object is accepted by Rigify as a metarig."""
    obj = context.active_object
    if not obj or obj.type != 'ARMATURE':
        return False

    try:
        from rigify.utils.rig import is_valid_metarig
        return bool(is_valid_metarig(context))
    except (ImportError, AttributeError, RuntimeError, TypeError):
        return False


class VIEW3D_OT_gamify_regenerate_meta_rig(Operator):
    bl_idname = OPERATOR_ID
    bl_label = "Regenerate Meta Rig"
    bl_description = "Generate or regenerate the Rigify rig from the active metarig"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return _is_valid_rigify_metarig(context)

    def execute(self, context):
        if not _is_valid_rigify_metarig(context):
            self.report({'WARNING'}, "Select a valid Rigify metarig first.")
            return {'CANCELLED'}

        # Rigify's own Generate/Re-Generate button calls this operator. Ensure
        # it runs outside Edit Mode, then restore the user's original mode.
        obj = context.active_object
        original_mode = obj.mode
        if original_mode == 'EDIT':
            bpy.ops.object.mode_set(mode='OBJECT')

        try:
            result = bpy.ops.pose.rigify_generate()
        except (RuntimeError, AttributeError) as exc:
            self.report({'ERROR'}, f"Rigify could not regenerate the rig: {exc}")
            return {'CANCELLED'}
        finally:
            active = context.view_layer.objects.active
            if (original_mode == 'EDIT' and active == obj and
                    obj.name in context.view_layer.objects):
                bpy.ops.object.mode_set(mode='EDIT')

        if 'CANCELLED' in result:
            return {'CANCELLED'}

        # Hide the source metarig after a successful generation when its
        # generated rig is available in this view layer. hide_set is local to
        # the view layer, so the Toggle Meta/Generated Rig tool can reveal it.
        generated_rig = getattr(obj.data, 'rigify_target_rig', None)
        if (
            generated_rig
            and generated_rig.type == 'ARMATURE'
            and generated_rig != obj
            and context.view_layer.objects.get(generated_rig.name) == generated_rig
        ):
            obj.hide_set(True, view_layer=context.view_layer)

        return {'FINISHED'}


def register():
    bpy.utils.register_class(VIEW3D_OT_gamify_regenerate_meta_rig)

    window_manager = bpy.context.window_manager
    keyconfig = window_manager.keyconfigs.addon if window_manager else None
    if keyconfig:
        keymap = keyconfig.keymaps.new(name="3D View", space_type='VIEW_3D')
        keymap_item = keymap.keymap_items.new(
            OPERATOR_ID, 'R', 'PRESS', ctrl=True, shift=True,
        )
        _keymap_items.append((keymap, keymap_item))


def unregister():
    for keymap, keymap_item in _keymap_items:
        keymap.keymap_items.remove(keymap_item)
    _keymap_items.clear()

    try:
        bpy.utils.unregister_class(VIEW3D_OT_gamify_regenerate_meta_rig)
    except (RuntimeError, ValueError):
        pass
