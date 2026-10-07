"""Run with Blender --background --factory-startup --python-exit-code 1."""
import sys
from pathlib import Path
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import bpy
bpy.ops.preferences.addon_enable(module='rigify')
import rigify
from rigify import rig_lists
from rigify.rigs.limbs import arm as native_arm, super_finger as native_finger, leg as native_leg
from gamify.rigs.game_ready import arm_unity_humanoid as arm, finger, leg_unity_humanoid as leg
for name, module in (('arm_unity_humanoid', arm), ('finger', finger), ('leg_unity_humanoid', leg)):
    rig_lists.rigs['game_ready.' + name] = {'module': module, 'feature_set': 'rigify'}
rigify.register_rig_parameters()

for name, native in (('arm', native_arm), ('finger', native_finger), ('leg', native_leg)):
    for variant in (1, 2):
        if bpy.context.object:
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        bpy.ops.object.armature_add()
        meta = bpy.context.object
        bpy.ops.object.mode_set(mode='EDIT')
        for bone in list(meta.data.edit_bones):
            meta.data.edit_bones.remove(bone)
        bpy.ops.object.mode_set(mode='OBJECT')
        native.create_sample(meta)
        bpy.ops.object.mode_set(mode='OBJECT')
        if name == 'finger':
            # Native sample includes an untyped palm; test a standalone finger.
            first = next(bone.name for bone in meta.pose.bones if bone.rigify_type)
            bpy.ops.object.mode_set(mode='EDIT')
            meta.data.edit_bones[first].use_connect = False
            meta.data.edit_bones[first].parent = None
            bpy.ops.object.mode_set(mode='OBJECT')
        collection = meta.data.collections.new('Controls')
        collection.rigify_ui_row = 1
        for bone in meta.pose.bones:
            if bone.rigify_type:
                bone.rigify_type = 'game_ready.finger' if name == 'finger' else 'game_ready.' + name + '_unity_humanoid'
                if name in {'arm', 'leg'}:
                    bone.rigify_parameters.segments = variant
                    if name == 'leg':
                        bone.rigify_parameters.gr_toes_override_parent = True
                        bone.rigify_parameters.gr_toes_parent = 'root'
                        bone.rigify_parameters.extra_ik_toe = variant == 2
                        bone.rigify_parameters.extra_toe_roll = variant == 2
                else:
                    bone.rigify_parameters.make_extra_ik_control = variant == 2
            collection.assign(bone.bone)
        for generation in range(2):
            assert 'FINISHED' in bpy.ops.pose.rigify_generate()
            target = meta.data.rigify_target_rig
            if name in {'arm', 'leg'}:
                ik_constraints = [con for bone in target.pose.bones for con in bone.constraints if con.type == 'IK']
                assert len(ik_constraints) == 2
                assert all(not con.use_stretch for con in ik_constraints)
                assert all('IK_Stretch' not in bone for bone in target.pose.bones)
                assert not any('IK_Stretch' in var.targets[0].data_path
                               for driver in target.animation_data.drivers for var in driver.driver.variables)
                ui_text = '\n'.join(text.as_string() for text in bpy.data.texts)
                assert 'IK_Stretch' not in ui_text
            defs = [bone for bone in target.pose.bones if bone.name.startswith('DEF-')]
            assert defs
            for bone in defs:
                assert [con.type for con in bone.constraints[:2]] == ['COPY_LOCATION', 'COPY_ROTATION']
                first, second = bone.constraints[:2]
                assert first.target == second.target == target
                assert first.subtarget == second.subtarget
                assert not any(con.type in {'COPY_TRANSFORMS', 'STRETCH_TO'} for con in bone.constraints)
            bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.select_all(action='DESELECT')
            meta.hide_set(False)
            meta.select_set(True)
            bpy.context.view_layer.objects.active = meta
print('ARM_FINGER_AND_LEG_DEF_CONSTRAINTS_OK')
