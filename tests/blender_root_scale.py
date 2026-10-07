"""Run with Blender --background --factory-startup --python-exit-code 1."""
import sys
from pathlib import Path
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bpy
bpy.ops.preferences.addon_enable(module='rigify')
from rigify import generate
from gamify import generation_defaults

original = generate.generate_rig
generation_defaults.register()
generation_defaults.register()
bpy.ops.object.armature_add()
meta = bpy.context.object
meta.pose.bones[0].rigify_type = 'basic.super_copy'
collection = meta.data.collections.new('Controls')
collection.rigify_ui_row = 1
collection.assign(meta.data.bones[0])
for index in range(2):
    assert 'FINISHED' in bpy.ops.pose.rigify_generate()
    root = meta.data.rigify_target_rig.pose.bones['root']
    assert tuple(root.lock_scale) == (True, True, True)
    assert tuple(root.lock_location) == (False, False, False)
    assert tuple(root.lock_rotation) == (False, False, False)
    root.lock_scale = (False, False, False)
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    meta.hide_set(False)
    meta.select_set(True)
    bpy.context.view_layer.objects.active = meta
generation_defaults.unregister()
assert generate.generate_rig is original
print('ROOT_SCALE_LOCK_OK')
