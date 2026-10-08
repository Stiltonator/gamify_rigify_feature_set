"""Run in Blender with --background --factory-startup --python-exit-code 1."""
import sys
from pathlib import Path
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bpy
bpy.ops.preferences.addon_enable(module='rigify')
import rigify
from rigify import rig_lists
from gamify import generation_defaults
from gamify.rigs.game_ready import super_copy, chain_bendy
for name, module in (('super_copy', super_copy), ('chain_bendy', chain_bendy)):
    rig_lists.rigs['game_ready.' + name] = {'module': module, 'feature_set': 'rigify'}
rigify.register_rig_parameters()
generation_defaults.register()
for name in ('super_copy', 'chain_bendy'):
    if bpy.context.object:
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    bpy.ops.object.armature_add()
    meta = bpy.context.object
    bpy.ops.object.mode_set(mode='EDIT')
    first = meta.data.edit_bones[0]
    first.name = 'Source'
    first.head, first.tail = (0, 0, 0), (0, 1, 0)
    if name == 'chain_bendy':
        second = meta.data.edit_bones.new('SourceNext')
        second.head, second.tail = first.tail, (0.2, 2, 0)
        second.parent, second.use_connect = first, True
    bpy.ops.object.mode_set(mode='OBJECT')
    meta.pose.bones['Source'].rigify_type = 'game_ready.' + name
    collection = meta.data.collections.new('Controls')
    collection.rigify_ui_row = 1
    color_set = meta.data.rigify_colors.add()
    color_set.name = 'Conflicting Collection Color'
    color_set.normal = (0.8, 0.8, 0.1)
    color_set.select = (0.8, 0.8, 0.1)
    color_set.active = (0.8, 0.8, 0.1)
    collection.rigify_color_set_id = len(meta.data.rigify_colors)
    for source in meta.pose.bones:
        collection.assign(source.bone)
        source.bone.color.palette = 'THEME04'
        source.color.palette = 'CUSTOM'
        source.color.custom.normal = (0.1, 0.2, 0.3)
        source.color.custom.select = (0.4, 0.5, 0.6)
        source.color.custom.active = (0.7, 0.8, 0.9)
    for generation in range(2):
        assert 'FINISHED' in bpy.ops.pose.rigify_generate()
        target = meta.data.rigify_target_rig
        copied = [bone for bone in target.pose.bones if 'gamify_metarig_color_source' in bone]
        assert copied
        for bone in copied:
            source = meta.pose.bones[bone['gamify_metarig_color_source']]
            assert bone.bone.color.palette == source.bone.color.palette
            assert bone.color.palette == source.color.palette
            for channel in ('normal', 'select', 'active'):
                assert tuple(getattr(bone.color.custom, channel)) == tuple(getattr(source.color.custom, channel))
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        meta.hide_set(False)
        meta.select_set(True)
        bpy.context.view_layer.objects.active = meta
        for source in meta.pose.bones:
            source.bone.color.palette = 'THEME02'
            source.color.custom.normal = (0.3, 0.2, 0.1)
generation_defaults.unregister()
print('METARIG_BONE_COLORS_OK')
