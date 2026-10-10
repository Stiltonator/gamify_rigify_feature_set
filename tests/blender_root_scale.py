"""Run with Blender --background --factory-startup --python-exit-code 1."""
import sys
from math import radians
from pathlib import Path
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bpy
from mathutils import Matrix, Vector
bpy.ops.preferences.addon_enable(module='rigify')
from rigify import generate
from gamify import generation_defaults

# Disable generation hooks from independently installed feature-set copies.
for module in list(sys.modules.values()):
    if (module is not None and module is not generation_defaults
            and getattr(module, '__name__', '').endswith('.generation_defaults')
            and getattr(module, '_enabled', False)):
        module.unregister()

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
assert not bpy.context.scene.gamify_root_flip_y
for enabled, flipped in ((True, False), (True, False), (False, False), (True, True), (True, True), (False, True), (False, False)):
    bpy.context.scene.gamify_root_z_forward = enabled
    bpy.context.scene.gamify_root_flip_y = flipped
    assert 'FINISHED' in bpy.ops.pose.rigify_generate()
    root = meta.data.rigify_target_rig.pose.bones['root']
    assert tuple(root.lock_scale) == (True, True, True)
    assert tuple(root.lock_location) == (False, False, False)
    assert tuple(root.lock_rotation) == (False, False, False)
    generated = meta.data.rigify_target_rig
    axes = generated.matrix_world.to_3x3() @ root.bone.matrix_local.to_3x3()
    expected_y = Vector((0, 0, 1)) if enabled else Vector((0, 1, 0))
    expected_z = Vector((0, -1, 0)) if enabled else Vector((0, 0, 1))
    if flipped:
        expected_y = -expected_y
    assert (axes @ Vector((1, 0, 0))).dot(Vector((-1, 0, 0) if flipped else (1, 0, 0))) > 0.999
    assert (axes @ Vector((0, 1, 0))).dot(expected_y) > 0.999, (enabled, flipped, tuple(axes @ Vector((0, 1, 0))), tuple(generated.rotation_euler))
    assert (axes @ Vector((0, 0, 1))).dot(expected_z) > 0.999
    expected_shape_x = radians(-90) if enabled else 0.0
    assert abs(root.custom_shape_rotation_euler.x - expected_shape_x) < 1e-6
    # Reorienting the parent before parenting must preserve child rest positions.
    generated = meta.data.rigify_target_rig
    assert (generated.matrix_world @ generated.data.bones['ORG-Bone'].head_local - meta.data.bones['Bone'].head_local).length < 1e-6
    assert (generated.matrix_world @ generated.pose.bones['Bone'].matrix.translation - meta.data.bones['Bone'].head_local).length < 1e-6
    expected_x = radians(90) if flipped else 0.0
    assert abs(generated.rotation_euler.x - expected_x) < 1e-6
    root.lock_scale = (False, False, False)
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    meta.hide_set(False)
    meta.select_set(True)
    bpy.context.view_layer.objects.active = meta
# An independently baked +90 object rotation must not rotate fresh bones again.
generated.data.transform(Matrix.Rotation(radians(-90), 4, 'X'))
generated.rotation_euler.x = radians(90)
bpy.context.view_layer.update()
bpy.context.scene.gamify_root_z_forward = True
for _ in range(3):
    assert 'FINISHED' in bpy.ops.pose.rigify_generate()
    generated = meta.data.rigify_target_rig
    assert abs(generated.rotation_euler.x - radians(90)) < 1e-6
    for name in ('ORG-Bone', 'Bone'):
        bone = generated.data.bones[name]
        assert (generated.matrix_world @ bone.head_local - meta.data.bones['Bone'].head_local).length < 1e-6
        assert (generated.matrix_world @ bone.tail_local - meta.data.bones['Bone'].tail_local).length < 1e-6
    axes = generated.matrix_world.to_3x3() @ generated.data.bones['root'].matrix_local.to_3x3()
    assert (axes @ Vector((0, 1, 0))).dot(Vector((0, 0, 1))) > 0.999
    assert (axes @ Vector((0, 0, 1))).dot(Vector((0, -1, 0))) > 0.999
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    meta.select_set(True)
    bpy.context.view_layer.objects.active = meta

# Direct object and bone children retain their complete world transforms.
children = []
for name, bone_parent in (('Object child', False), ('Bone child', True)):
    child = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(child)
    child.parent = generated
    if bone_parent:
        child.parent_type = 'BONE'
        child.parent_bone = 'Bone'
    child.location = (2, 3, 4)
    child.rotation_euler = (0.2, 0.4, 0.6)
    child.scale = (1.2, 0.8, 1.5)
    children.append(child)
grandchild = bpy.data.objects.new('Grandchild', None)
bpy.context.collection.objects.link(grandchild)
grandchild.parent = children[0]
grandchild.location = (1, 2, 3)
bpy.context.view_layer.update()
worlds = {obj: obj.matrix_world.copy() for obj in [*children, grandchild]}
inverses = {obj: obj.matrix_parent_inverse.copy() for obj in children}
generation_defaults._apply_root_flip_object_rotation(bpy.context, generated)
for obj, world in worlds.items():
    assert max(abs(obj.matrix_world[r][c] - world[r][c])
               for r in range(4) for c in range(4)) < 1e-5, obj.name
for obj in children:
    assert obj.parent == generated
    assert obj.matrix_parent_inverse == inverses[obj]
assert children[0].parent_type == 'OBJECT'
assert children[1].parent_type == 'BONE'
assert children[1].parent_bone == 'Bone'
assert grandchild.parent == children[0]

generation_defaults.unregister()
assert generate.generate_rig is original
assert generate.Generator._Generator__create_root_bone is original_create_root
assert not hasattr(bpy.types.Scene, 'gamify_root_z_forward')
assert not hasattr(bpy.types.Scene, 'gamify_root_flip_y')
print('ROOT_SCALE_LOCK_OK')
