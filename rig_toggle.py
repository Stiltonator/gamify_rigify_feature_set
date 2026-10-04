"""Toggle between a Rigify metarig and its generated target rig."""

import bpy
from bpy.types import Operator


OPERATOR_ID = "view3d.gamify_toggle_meta_generated_rig"
_keymap_items = []


def _find_paired_rig(context, obj):
    """Return the linked generated rig or metarig for this armature object."""
    target = getattr(obj.data, 'rigify_target_rig', None)
    if target and target.type == 'ARMATURE' and target != obj:
        return target

    for candidate in context.scene.objects:
        if candidate.type != 'ARMATURE' or candidate == obj:
            continue
        if getattr(candidate.data, 'rigify_target_rig', None) == obj:
            return candidate

    return None


class VIEW3D_OT_gamify_toggle_meta_generated_rig(Operator):
    bl_idname = OPERATOR_ID
    bl_label = "Toggle Meta/Generated Rig"
    bl_description = "Switch between a Rigify metarig and its generated rig"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return bool(obj and obj.type == 'ARMATURE' and obj.mode in {'OBJECT', 'EDIT', 'POSE'})

    def execute(self, context):
        source = context.active_object
        target = _find_paired_rig(context, source)
        if not target:
            self.report({'WARNING'}, "No linked metarig or generated rig was found.")
            return {'CANCELLED'}

        if context.view_layer.objects.get(target.name) is not target:
            self.report({'WARNING'}, "The paired rig is not available in the current view layer.")
            return {'CANCELLED'}

        target_mode = source.mode
        if target_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        # Reveal and select the paired object before hiding the current one.
        target.hide_set(False, view_layer=context.view_layer)
        for selected in context.selected_objects:
            selected.select_set(False)
        target.select_set(True)
        context.view_layer.objects.active = target

        if target_mode == 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
        elif target_mode == 'POSE':
            bpy.ops.object.mode_set(mode='POSE')

        source.hide_set(True, view_layer=context.view_layer)
        return {'FINISHED'}


def register():
    bpy.utils.register_class(VIEW3D_OT_gamify_toggle_meta_generated_rig)

    window_manager = bpy.context.window_manager
    keyconfig = window_manager.keyconfigs.addon if window_manager else None
    if keyconfig:
        keymap = keyconfig.keymaps.new(name="3D View", space_type='VIEW_3D')
        keymap_item = keymap.keymap_items.new(OPERATOR_ID, 'T', 'PRESS', shift=True)
        _keymap_items.append((keymap, keymap_item))


def unregister():
    for keymap, keymap_item in _keymap_items:
        keymap.keymap_items.remove(keymap_item)
    _keymap_items.clear()

    try:
        bpy.utils.unregister_class(VIEW3D_OT_gamify_toggle_meta_generated_rig)
    except (RuntimeError, ValueError):
        pass
