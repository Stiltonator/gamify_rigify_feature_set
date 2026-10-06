"""Run with Blender --background --factory-startup --python-exit-code 1 --python PATH."""
import sys
sys.dont_write_bytecode = True
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import bpy
from mathutils import Vector
bpy.ops.preferences.addon_enable(module='rigify')
import rigify
from rigify import rig_lists
from gamify.rigs.game_ready import chain_basic

key = 'game_ready.chain_basic'
rig_lists.rigs[key] = {'module': chain_basic, 'feature_set': 'rigify'}
rigify.register_rig_parameters()


def metarig(sequence=True, widget='circle', orientation=False, start=None, end=None):
    bpy.ops.object.mode_set(mode='OBJECT') if bpy.context.object else None
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    bpy.ops.object.armature_add()
    obj = bpy.context.object
    bpy.ops.object.mode_set(mode='EDIT')
    for bone in list(obj.data.edit_bones):
        obj.data.edit_bones.remove(bone)
    bpy.ops.object.mode_set(mode='OBJECT')
    chain_basic.create_sample(obj)
    bpy.ops.object.mode_set(mode='EDIT')
    reference = obj.data.edit_bones.new('Reference')
    reference.head, reference.tail = (2, 0, 0), (3, 0, 0)
    bpy.ops.object.mode_set(mode='OBJECT')
    params = obj.pose.bones['Chain'].rigify_parameters
    params.gr_cb_parent_in_sequence = sequence
    params.gr_cb_widget = widget
    params.gr_cb_override_orientation = orientation
    params.gr_cb_orientation_bone = 'Reference'
    for endpoint, parent in (('start', start), ('end', end)):
        if parent is not None:
            setattr(params, 'gr_cb_override_' + endpoint + '_parent', True)
            setattr(params, 'gr_cb_' + endpoint + '_parent', parent)
    collection = obj.data.collections.new('Controls')
    collection.rigify_ui_row = 1
    for bone in obj.data.bones:
        collection.assign(bone)
    return obj


for sequence, widget, orientation, start, end in (
        (True, 'circle', False, None, None),
        (False, 'cube', False, None, None),
        (True, 'arrow', True, 'ORG-Reference', 'ORG-Reference'),
        (False, 'sphere', True, 'NONE', 'NONE')):
    meta = metarig(sequence, widget, orientation, start, end)
    for generation in range(2):
        assert 'FINISHED' in bpy.ops.pose.rigify_generate()
        target = meta.data.rigify_target_rig
        stems = ('Chain.000', 'Chain.001', 'Chain.002.L')
        controls = [target.pose.bones[name[:-2] + '.Tweak' + name[-2:] if name.endswith(('.L', '.R')) else name + '.Tweak'] for name in stems]
        endpoints = [target.pose.bones[stems[0]], target.pose.bones[stems[-1]]]
        pivot = target.pose.bones['Chain.Pivot']
        backing = target.pose.bones['MCH-AUTO-Chain']
        defs = [target.pose.bones['DEF-' + name] for name in stems]
        assert len([bone for bone in target.data.bones if bone.name.startswith('DEF-')]) == 3
        for index, (control, deform) in enumerate(zip(controls, defs)):
            assert control.custom_shape is not None
            assert tuple(round(v, 5) for v in control.custom_shape_scale_xyz) == (0.2,) * 3
            assert deform.bone.bbone_segments == 1
            assert not deform.bone.use_connect
            assert [con.type for con in deform.constraints] == ['COPY_TRANSFORMS']
            assert control.parent.name == 'MCH-INT-' + stems[index]
            if index:
                expected = defs[index - 1] if sequence else defs[0]
                assert deform.parent.name == expected.name
            if orientation:
                rest_y = deform.bone.matrix_local.to_3x3() @ Vector((0, 1, 0))
                assert rest_y.dot(Vector((1, 0, 0))) > 0.999, (deform.name, tuple(rest_y))
        expected_start = 'root' if start is None else None if start == 'NONE' else start
        expected_end = expected_start if end is None else None if end == 'NONE' else end
        assert (endpoints[0].parent.name if endpoints[0].parent else None) == expected_start
        assert (endpoints[-1].parent.name if endpoints[-1].parent else None) == expected_end
        # Rest positions survive backing/pivot constraints, including a curved joint.
        for deform, stem in zip(defs, stems):
            assert (deform.matrix.translation - deform.bone.head_local).length < 1e-5
        before = controls[1].matrix.translation.copy()
        pivot.location.x += 0.25
        bpy.context.view_layer.update()
        assert (controls[1].matrix.translation - before).length > 0.2
        pivot.location.x = 0
        bpy.context.view_layer.update()
        assert [c.type for c in backing.constraints] == ['COPY_LOCATION', 'STRETCH_TO']
        assert pivot.parent.name == backing.name
        before = controls[1].matrix.translation.copy()
        endpoints[-1].location += Vector((0.1, 0.2, 0.3))
        bpy.context.view_layer.update()
        assert (controls[1].matrix.translation - before).length > 0.01
        controls[-1].location += Vector((0.1, 0.2, 0.3))
        bpy.context.view_layer.update()
        assert (defs[-1].matrix.translation - controls[-1].matrix.translation).length < 1e-5
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        meta.hide_set(False)
        meta.select_set(True)
        bpy.context.view_layer.objects.active = meta
    print('CHAIN_BASIC_OK', sequence, widget, orientation, start, end)

for missing in ('DoesNotExist', 'Chain.000'):
    meta = metarig(start=missing)
    try:
        bpy.ops.pose.rigify_generate()
    except RuntimeError as exc:
        assert ('not found' if missing == 'DoesNotExist' else 'cycle') in str(exc)
    else:
        raise AssertionError('Invalid parent accepted: ' + missing)
print('CHAIN_BASIC_INVALID_PARENTS_OK')

for use_deform in (True, False):
    meta = metarig()
    reference = meta.pose.bones['Reference']
    reference.rigify_type = 'basic.super_copy'
    reference.rigify_parameters.make_deform = use_deform
    bpy.ops.object.mode_set(mode='EDIT')
    meta.data.edit_bones['Chain'].parent = meta.data.edit_bones['Reference']
    bpy.ops.object.mode_set(mode='OBJECT')
    assert 'FINISHED' in bpy.ops.pose.rigify_generate()
    target = meta.data.rigify_target_rig
    expected = 'DEF-Reference' if use_deform else 'Reference'
    assert target.data.bones['Chain.000'].parent.name == expected
    assert target.data.bones['DEF-Chain.000'].parent.name == expected
print('CHAIN_BASIC_AUTOMATIC_PARENT_OK')

# Longer asymmetric chains exercise even/odd pivot placement and falloff.
for count in (1, 3, 4):
    meta = metarig()
    bpy.ops.object.mode_set(mode='EDIT')
    arm = meta.data.edit_bones
    arm.remove(arm['Chain.001'])
    previous = arm['Chain']
    for index in range(1, count):
        bone = arm.new('Chain.%03d' % index)
        bone.head = previous.tail
        bone.tail = (0.2 * index, index + 1, 0.15 * (index % 2))
        bone.parent, bone.use_connect = previous, True
        previous = bone
    expected = [arm['Chain'].head.copy()] + [arm['Chain' if i == 0 else 'Chain.%03d' % i].tail.copy() for i in range(count)]
    bpy.ops.object.mode_set(mode='OBJECT')
    assert 'FINISHED' in bpy.ops.pose.rigify_generate()
    target = meta.data.rigify_target_rig
    defs = [bone for bone in target.pose.bones if bone.name.startswith('DEF-Chain.')]
    assert len(defs) == count + 1
    assert all(bone.bone.bbone_segments == 1 and not bone.bone.use_connect for bone in defs)
    for bone, point in zip(sorted(defs, key=lambda b: b.name), expected):
        assert (bone.matrix.translation - point).length < 1e-5
    frames = [bone for bone in target.pose.bones if bone.name.startswith('MCH-INT-') and bone.constraints]
    assert len(frames) == count - 1
    for frame in frames:
        assert 0 < frame.constraints[0].influence <= 1
    before = [bone.matrix.translation.copy() for bone in defs]
    target.pose.bones['Chain.Pivot'].location.x = 0.3
    bpy.context.view_layer.update()
    if count > 1:
        assert any((bone.matrix.translation - point).length > 0.1 for bone, point in zip(defs, before))
print('CHAIN_BASIC_LENGTHS_OK')
