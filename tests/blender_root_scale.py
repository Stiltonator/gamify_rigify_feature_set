"""Run with Blender --background --factory-startup --python-exit-code 1."""
import sys
from math import radians
from pathlib import Path
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bpy
from mathutils import Vector
bpy.ops.preferences.addon_enable(module='rigify')
from rigify import generate
from gamify import generation_defaults

original = generate.generate_rig
original_create_root = generate.Generator._Generator__create_root_bone
# Isolate this checkout from a separately installed Gamify version's default.
if hasattr(bpy.types.Scene, 'gamify_root_z_forward'):
    del bpy.types.Scene.gamify_root_z_forward
generation_defaults.register()
generation_defaults.register()
bpy.ops.object.armature_add()
meta = bpy.context.object
meta.pose.bones[0].rigify_type = 'basic.super_copy'
collection = meta.data.collections.new('Controls')
collection.rigify_ui_row = 1
collection.assign(meta.data.bones[0])
assert not bpy.context.scene.gamify_root_z_forward
for index, enabled in enumerate((True, True, False, True)):
    bpy.context.scene.gamify_root_z_forward = enabled
    assert 'FINISHED' in bpy.ops.pose.rigify_generate()
    root = meta.data.rigify_target_rig.pose.bones['root']
    assert tuple(root.lock_scale) == (True, True, True)
    assert tuple(root.lock_location) == (False, False, False)
    assert tuple(root.lock_rotation) == (False, False, False)
    axes = root.bone.matrix_local.to_3x3()
    expected_y = Vector((0, 0, 1)) if enabled else Vector((0, 1, 0))
    expected_z = Vector((0, -1, 0)) if enabled else Vector((0, 0, 1))
    assert (axes @ Vector((0, 1, 0))).dot(expected_y) > 0.999
    assert (axes @ Vector((0, 0, 1))).dot(expected_z) > 0.999
    expected_shape_x = radians(-90) if enabled else 0.0
    assert abs(root.custom_shape_rotation_euler.x - expected_shape_x) < 1e-6
    # Reorienting the parent before parenting must preserve child rest positions.
    generated = meta.data.rigify_target_rig
    assert (generated.data.bones['ORG-Bone'].head_local - meta.data.bones['Bone'].head_local).length < 1e-6
    assert (generated.pose.bones['Bone'].matrix.translation - meta.data.bones['Bone'].head_local).length < 1e-6
    root.lock_scale = (False, False, False)
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    meta.hide_set(False)
    meta.select_set(True)
    bpy.context.view_layer.objects.active = meta
generation_defaults.unregister()
assert generate.generate_rig is original
assert generate.Generator._Generator__create_root_bone is original_create_root
assert not hasattr(bpy.types.Scene, 'gamify_root_z_forward')
print('ROOT_SCALE_LOCK_OK')
