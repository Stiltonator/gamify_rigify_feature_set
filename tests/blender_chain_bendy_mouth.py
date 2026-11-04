"""Run with the supplied mouth .blend loaded; optionally pass -- OUTPUT.blend."""
import sys
from pathlib import Path
from math import degrees

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bpy

bpy.ops.preferences.addon_enable(module='rigify')
import rigify
from rigify import rig_lists
from gamify import generation_defaults
from gamify.rigs.game_ready import chain_bendy

for module in list(sys.modules.values()):
    if (module is not None and module is not generation_defaults
            and getattr(module, '__name__', '').endswith('.generation_defaults')
            and getattr(module, '_enabled', False)):
        module.unregister()
generation_defaults.register()
rig_lists.rigs['game_ready.chain_bendy'] = {'module': chain_bendy, 'feature_set': 'rigify'}
rigify.register_rig_parameters()
meta = bpy.data.objects['RigChan - METARIG']
rig = meta.data.rigify_target_rig
action = rig.animation_data.nla_tracks[0].strips[0].action
settings = [(bone.rigify_parameters,
             bone.rigify_parameters.gr_chain_bendy_override_orientation,
             bone.rigify_parameters.gr_chain_bendy_orient_bone)
            for bone in meta.pose.bones if bone.rigify_type == 'game_ready.chain_bendy']


def frames(rig):
    evaluated = rig.evaluated_get(bpy.context.evaluated_depsgraph_get())
    result = {b.name: evaluated.matrix_world @ b.matrix for b in evaluated.pose.bones
              if b.name.startswith(('MCH-INT-Mouth', 'DEF-Mouth'))}
    for bone in evaluated.pose.bones:
        if bone.name.startswith('MCH-Mouth') and bone.name.endswith('_bbone'):
            for index in range(bone.bone.bbone_segments + 1):
                result[bone.name, index] = (evaluated.matrix_world @ bone.matrix
                                          @ bone.bbone_segment_matrix(index))
    return result


for generation in range(4):
    for params, enabled, reference in settings:
        params.gr_chain_bendy_override_orientation = True if generation == 2 else enabled
        params.gr_chain_bendy_orient_bone = 'Mouth' if generation == 2 else reference
    bpy.context.scene.frame_set(0)
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    meta.hide_set(False)
    meta.select_set(True)
    bpy.context.view_layer.objects.active = meta
    assert 'FINISHED' in bpy.ops.pose.rigify_generate()
    rig = meta.data.rigify_target_rig
    assert rig.animation_data.nla_tracks[0].strips[0].action == action
    bpy.context.scene.frame_set(0)
    bpy.context.view_layer.update()
    max_offset = 0
    for bone in rig.pose.bones:
        if bone.name.startswith('MCH-INT-Mouth'):
            offset = bone.bone.matrix_local.to_quaternion().rotation_difference(
                bone.matrix.to_quaternion()).angle
            max_offset = max(max_offset, degrees(offset))
            assert offset < 0.001, (bone.name, degrees(offset))
    print('MOUTH_MAX_INITIAL_ROTATION_OFFSET_DEGREES', max_offset)
    for bone in rig.pose.bones:
        if bone.name.startswith('DEF-Mouth'):
            assert bone.matrix.to_quaternion().rotation_difference(
                bone.bone.matrix_local.to_quaternion()).angle < 0.001, bone.name
            if generation == 2:
                assert bone.bone.matrix_local.to_quaternion().rotation_difference(
                    rig.data.bones['ORG-Mouth'].matrix_local.to_quaternion()).angle < 0.001
    for role in ('Top', 'Bottom'):
        drivers = [rig.data.bones['MCH-Mouth.' + role + '.' + side + '_bbone']
                   for side in ('L', 'R')]
        normals = [b.bbone_custom_handle_start.matrix_local.to_3x3().col[2]
                   for b in drivers]
        assert normals[0].dot(normals[1]) > 0.999
    # Preserve a local tweak offset while checking the supplied root animation.
    intermediary = rig.pose.bones['MCH-INT-Mouth.Top.R_sample_02']
    tweak = next(b for b in rig.pose.bones if b.parent == intermediary)
    tweak.location.x = 0.005
    tweak.rotation_euler.y = 0.1
    bpy.context.view_layer.update()
    baseline = frames(rig)
    root_start = rig.matrix_world @ rig.pose.bones['root'].matrix
    for frame in (45, 89, 90, 91, 135, 179, 180):
        bpy.context.scene.frame_set(frame)
        delta = (rig.matrix_world @ rig.pose.bones['root'].matrix) @ root_start.inverted()
        for key, actual in frames(rig).items():
            expected = delta @ baseline[key]
            assert max(abs(actual[r][c] - expected[r][c]) for r in range(4)
                       for c in range(4)) < 0.002, (frame, key)
    assert degrees(delta.to_quaternion().angle) > 179
    tweak.location.x = 0
    tweak.rotation_euler.y = 0
    print('MOUTH_REGENERATION_AND_TURN_OK', generation)

bpy.context.scene.frame_set(0)
if '--' in sys.argv:
    output = Path(sys.argv[sys.argv.index('--') + 1]).resolve()
    assert str(output) != str(Path(bpy.data.filepath).resolve())
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
print('CHAIN_BENDY_MOUTH_OK')
