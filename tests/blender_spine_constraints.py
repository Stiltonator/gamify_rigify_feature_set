import sys
from pathlib import Path
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bpy
bpy.ops.preferences.addon_enable(module='rigify')
import rigify
from rigify import rig_lists
from rigify.rigs.spines.basic_spine import create_sample
from gamify.rigs.game_ready import spine_unity_humanoid
key = 'game_ready.spine_unity_humanoid'
rig_lists.rigs[key] = {'module': spine_unity_humanoid, 'feature_set': 'rigify'}
rigify.register_rig_parameters()
bpy.ops.object.armature_add()
meta = bpy.context.object
bpy.ops.object.mode_set(mode='EDIT')
for bone in list(meta.data.edit_bones):
    meta.data.edit_bones.remove(bone)
bpy.ops.object.mode_set(mode='OBJECT')
create_sample(meta)
bpy.ops.object.mode_set(mode='OBJECT')
collection = meta.data.collections.new('Controls')
collection.rigify_ui_row = 1
for bone in meta.pose.bones:
    if bone.rigify_type:
        bone.rigify_type = key
    collection.assign(bone.bone)
for generation in range(2):
    assert 'FINISHED' in bpy.ops.pose.rigify_generate()
    target = meta.data.rigify_target_rig
    defs = [bone for bone in target.pose.bones if bone.name.startswith('DEF-')]
    assert defs
    for bone in defs:
        assert [con.type for con in bone.constraints[:2]] == ['COPY_LOCATION', 'COPY_ROTATION']
        first, second = bone.constraints[:2]
        assert first.target == second.target == target
        assert first.subtarget == second.subtarget
        assert not any(con.type == 'COPY_TRANSFORMS' for con in bone.constraints)
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    meta.hide_set(False)
    meta.select_set(True)
    bpy.context.view_layer.objects.active = meta
print('SPINE_DEF_CONSTRAINTS_OK')

from gamify.rigs.game_ready import super_head_unity_humanoid as super_head
key = 'game_ready.super_head_unity_humanoid'
rig_lists.rigs[key] = {'module': super_head, 'feature_set': 'rigify'}
rigify.register_rig_parameters()
from rigify.rigs.spines import super_head as native_super_head
discovered, _ = rig_lists.get_rigs(str(Path(__file__).resolve().parents[1] / 'rigs'), ['gamify', 'rigs'])
assert 'spines.super_head' not in discovered
assert discovered['game_ready.super_head_unity_humanoid']['module'] is super_head
assert rig_lists.rigs[key]['module'] is super_head
for count in (1, 3, 5):
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    bpy.ops.object.armature_add()
    meta = bpy.context.object
    bpy.ops.object.mode_set(mode='EDIT')
    for bone in list(meta.data.edit_bones):
        meta.data.edit_bones.remove(bone)
    previous = None
    names = []
    for index in range(count):
        name = 'SkullHead' if index == count - 1 else 'CervicalNeck' if index == 0 else 'HeadChain.%03d' % index
        bone = meta.data.edit_bones.new(name)
        bone.head, bone.tail = (0, 0, index), (0, 0, index + 1)
        if previous:
            bone.parent, bone.use_connect = previous, True
        previous = bone
        names.append(bone.name)
    bpy.ops.object.mode_set(mode='OBJECT')
    meta.pose.bones[names[0]].rigify_type = key
    collection = meta.data.collections.new('Controls')
    collection.rigify_ui_row = 1
    for bone in meta.data.bones:
        collection.assign(bone)
    for generation in range(2):
        assert 'FINISHED' in bpy.ops.pose.rigify_generate()
        target = meta.data.rigify_target_rig
        assert names[-1] in target.pose.bones
        assert target.pose.bones[names[-1]].custom_shape is not None
        assert tuple(target.pose.bones[names[-1]].lock_scale) == (True, True, True)
        if count > 1:
            assert names[0] in target.pose.bones
            assert target.pose.bones[names[0]].custom_shape is not None
            assert tuple(target.pose.bones[names[0]].lock_scale) == (True, True, True)
        if count > 3:
            assert names[0] + '_bend' in target.pose.bones
        assert 'head' not in target.pose.bones and 'neck' not in target.pose.bones
        defs = [bone for bone in target.pose.bones if bone.name.startswith('DEF-')]
        assert len(defs) == count
        for bone in defs:
            assert [c.type for c in bone.constraints] == ['COPY_LOCATION', 'COPY_ROTATION']
            loc, rot = bone.constraints
            assert loc.target == rot.target == target
            assert loc.subtarget == rot.subtarget == 'ORG-' + bone.name[4:]
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        meta.hide_set(False)
        meta.select_set(True)
        bpy.context.view_layer.objects.active = meta
print('SUPER_HEAD_DEF_CONSTRAINTS_OK')
