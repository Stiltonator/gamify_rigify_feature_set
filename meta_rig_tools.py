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


def _activate_armature(context, obj, mode='OBJECT'):
    """Select and activate an armature, then restore its requested mode."""
    active = context.view_layer.objects.active
    if active and active.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    for selected in context.selected_objects:
        selected.select_set(False)

    obj.hide_set(False, view_layer=context.view_layer)
    obj.select_set(True)
    context.view_layer.objects.active = obj

    if mode != 'OBJECT':
        bpy.ops.object.mode_set(mode=mode)


def _show_bone_collections(rig, context):
    """Show MCH/DEF collections requested in the Gamify menu."""
    scene = context.scene
    requested = (
        ('MCH', getattr(scene, 'gamify_show_mch_bones', False)),
        ('DEF', getattr(scene, 'gamify_show_def_bones', False)),
    )
    for name, show in requested:
        if not show:
            continue
        collection = rig.data.collections.get(name)
        if collection is not None:
            collection.is_visible = True


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

        # Rigify generation runs outside Edit Mode. Remember the starting mode
        # so it can be applied to the generated rig after a successful run.
        obj = context.active_object
        original_mode = obj.mode
        if original_mode == 'EDIT':
            bpy.ops.object.mode_set(mode='OBJECT')

        try:
            result = bpy.ops.pose.rigify_generate()
        except (RuntimeError, AttributeError) as exc:
            self.report({'ERROR'}, f"Rigify could not regenerate the rig: {exc}")
            if obj.name in context.view_layer.objects:
                _activate_armature(context, obj, original_mode)
            return {'CANCELLED'}

        if 'CANCELLED' in result:
            if obj.name in context.view_layer.objects:
                _activate_armature(context, obj, original_mode)
            return {'CANCELLED'}

        target = getattr(obj.data, 'rigify_target_rig', None)
        if (not target or target.type != 'ARMATURE' or
                context.view_layer.objects.get(target.name) is not target):
            self.report(
                {'WARNING'},
                "Rigify finished, but the generated rig could not be found in this view layer.",
            )
            if obj.name in context.view_layer.objects:
                _activate_armature(context, obj, original_mode)
            return {'CANCELLED'}

        _show_bone_collections(target, context)
        merge_warnings = target.get('gamify_bendy_merge_warnings', '')
        if merge_warnings:
            self.report({'WARNING'}, merge_warnings)
        _activate_armature(context, target, original_mode)

        # Keep the existing workflow: after regeneration, hide the metarig and
        # leave the generated rig selected and active.
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
