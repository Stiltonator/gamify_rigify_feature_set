"""Run with Blender --background --factory-startup --python-exit-code 1."""
import sys
from pathlib import Path
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import bpy
bpy.ops.preferences.addon_enable(module='rigify')
import rigify
from rigify import rig_lists
from gamify.rigs.game_ready import super_copy, raw_copy
for name, module in (('super_copy', super_copy), ('raw_copy', raw_copy)):
    rig_lists.rigs['game_ready.' + name] = {'module': module, 'feature_set': 'rigify'}
rigify.register_rig_parameters()

bpy.ops.object.armature_add()
meta = bpy.context.object
bpy.ops.object.mode_set(mode='EDIT')
for bone in list(meta.data.edit_bones):
    meta.data.edit_bones.remove(bone)
for index, name in enumerate(('Copy', 'Raw', 'MCH-Hidden', 'DEF-Hidden', 'ORG-Explicit')):
    bone = meta.data.edit_bones.new(name)
    bone.head, bone.tail = (index, 0, 0), (index, 1, 0)
bpy.ops.object.mode_set(mode='OBJECT')
shape = bpy.data.objects.new('User Custom Shape', bpy.data.meshes.new('User Shape Mesh'))
bpy.context.scene.collection.objects.link(shape)
shape.data.from_pydata([(0, 0, 0), (1, 0, 0)], [(0, 1)], [])
collection = meta.data.collections.new('Controls')
collection.rigify_ui_row = 1
for bone in meta.pose.bones:
    collection.assign(bone.bone)
    bone.rigify_type = 'game_ready.super_copy' if bone.name == 'Copy' else 'game_ready.raw_copy'
    bone.custom_shape = shape
    bone.custom_shape_scale_xyz = (1.2, 2.3, 3.4)
    bone.custom_shape_translation = (0.1, 0.2, 0.3)
    bone.custom_shape_rotation_euler = (0.4, 0.5, 0.6)
    bone.use_custom_shape_bone_size = False
    bone.custom_shape_wire_width = 2
    bone.bone.show_wire = True
    bone.custom_shape_transform = bone

for generation in range(3):
    assert 'FINISHED' in bpy.ops.pose.rigify_generate()
    rig = meta.data.rigify_target_rig
    for name in ('Copy', 'Raw', 'ORG-Explicit'):
        bone = rig.pose.bones[name]
        if name == 'Copy' and generation == 1:
            assert bone.custom_shape is not None and bone.custom_shape != shape
            continue
        assert bone.custom_shape == shape, name
        assert tuple(round(v, 3) for v in bone.custom_shape_scale_xyz) == (1.2, 2.3, 3.4)
        assert tuple(round(v, 3) for v in bone.custom_shape_translation) == (0.1, 0.2, 0.3)
        assert tuple(round(v, 3) for v in bone.custom_shape_rotation_euler) == (0.4, 0.5, 0.6)
        assert not bone.use_custom_shape_bone_size
        assert bone.custom_shape_wire_width == 2
        assert bone.bone.show_wire
        assert bone.custom_shape_transform == bone
    for name in ('MCH-Hidden', 'DEF-Hidden'):
        assert rig.pose.bones[name].custom_shape is None
    assert 'ORG-Raw' not in rig.pose.bones
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    meta.hide_set(False)
    meta.select_set(True)
    bpy.context.view_layer.objects.active = meta
    meta.pose.bones['Copy'].rigify_parameters.gr_sc_make_widget = generation == 0
for name in ('Copy', 'Raw'):
    meta.pose.bones[name].custom_shape = None
assert 'FINISHED' in bpy.ops.pose.rigify_generate()
rig = meta.data.rigify_target_rig
assert rig.pose.bones['Copy'].custom_shape is None
assert rig.pose.bones['Raw'].custom_shape is None
print('COPY_SHAPES_OK')

# Automatic priority and explicit control overrides are independent of DEF settings.
for make_control, make_deform, override, expected in (
        (True, True, None, 'DEF-Face'),
        (True, False, None, 'Face'),
        (False, False, None, 'ORG-Face'),
        (True, True, 'Face', 'Face'),
        (True, True, 'ORG-Face', 'ORG-Face'),
        (True, True, 'NONE', None)):
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    bpy.ops.object.armature_add()
    meta = bpy.context.object
    bpy.ops.object.mode_set(mode='EDIT')
    face = meta.data.edit_bones[0]
    face.name = 'Face'
    mouth = meta.data.edit_bones.new('Mouth')
    mouth.head, mouth.tail = (0, 1, 0), (0, 2, 0)
    mouth.parent = face
    bpy.ops.object.mode_set(mode='OBJECT')
    for bone in meta.pose.bones:
        bone.rigify_type = 'game_ready.super_copy'
    params = meta.pose.bones['Face'].rigify_parameters
    params.make_control, params.make_deform = make_control, make_deform
    params = meta.pose.bones['Mouth'].rigify_parameters
    params.make_deform = False
    if override is not None:
        params.gr_sc_control_override_parent = True
        params.gr_sc_control_parent = override
    collection = meta.data.collections.new('Controls')
    collection.rigify_ui_row = 1
    for bone in meta.data.bones:
        collection.assign(bone)
    for generation in range(2):
        assert 'FINISHED' in bpy.ops.pose.rigify_generate()
        rig = meta.data.rigify_target_rig
        parent = rig.pose.bones['Mouth'].parent
        assert (parent.name if parent else None) == expected
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        meta.hide_set(False)
        meta.select_set(True)
        bpy.context.view_layer.objects.active = meta
print('SUPER_COPY_CONTROL_PARENT_PRIORITY_OK')
