"""Exercise production generation methods with a small Blender-free bone model.

These check topology and rest directions; Blender dependency-graph evaluation
and visual B-Bone deformation still require an integration check in Blender.
"""
import ast
import math
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
import warnings


class Vector:
    def __init__(self, values):
        self.values = tuple(values.values if isinstance(values, Vector) else values)

    x = property(lambda self: self.values[0])
    y = property(lambda self: self.values[1])
    z = property(lambda self: self.values[2])
    length = property(lambda self: math.sqrt(self.dot(self)))

    def copy(self):
        return Vector(self.values)

    def __add__(self, other):
        return Vector(a + b for a, b in zip(self.values, other.values))

    def __sub__(self, other):
        return Vector(a - b for a, b in zip(self.values, other.values))

    def __mul__(self, scale):
        return Vector(a * scale for a in self.values)

    def __neg__(self):
        return self * -1

    def dot(self, other):
        return sum(a * b for a, b in zip(self.values, other.values))

    def normalized(self):
        return self * (1 / self.length) if self.length else self.copy()

    def normalize(self):
        self.values = self.normalized().values

    def lerp(self, other, t):
        return self + (other - self) * t


class WorldMatrix:
    def __init__(self, shift=(0, 0, 0)):
        self.shift = Vector(shift)

    def __matmul__(self, point):
        return point + self.shift


class Bone:
    def __init__(self, name, head, tail):
        self.name, self.head, self.tail = name, Vector(head), Vector(tail)
        self.x_axis = Vector((0, 0, 1))
        self.parent = None

    y_axis = property(lambda self: (Vector(self.tail) - Vector(self.head)).normalized())
    length = property(lambda self: (Vector(self.tail) - Vector(self.head)).length)


class Entries(list):
    def new(self, kind=None):
        item = NS(type=kind, targets=Entries())
        self.append(item)
        return item


# Load the actual method bodies, without importing bpy or Rigify.
source = Path(__file__).resolve().parents[1] / 'rigs/game_ready/chain_bendy.py'
tree = ast.parse(source.read_text(encoding='utf-8-sig'))
rig_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Rig')
rig_class.bases = []
for method in rig_class.body:
    if isinstance(method, ast.FunctionDef):
        method.decorator_list = [decorator for decorator in method.decorator_list
                                 if isinstance(decorator, ast.Name)]
namespace = dict(Vector=Vector, warnings=warnings, strip_org=lambda name: name.removeprefix('ORG-'),
                 make_derived_name=lambda name, kind, suffix: kind.upper() + '-' + name + suffix,
                 make_mechanism_name=lambda name: 'MCH-' + name,
                 make_deformer_name=lambda name: 'DEF-' + name)
exec(compile(ast.Module(body=[rig_class], type_ignores=[]), str(source), 'exec'), namespace)


class ModelRig(namespace['Rig']):
    def make_constraint(self, bone, kind, target, **kwargs):
        constraint = self.obj.pose.bones[bone].constraints.new(kind)
        constraint.subtarget = target
        for key, value in kwargs.items():
            setattr(constraint, key, value)
        return constraint

    def copy_bone(self, source, name):
        if name in self.obj.data.edit_bones:
            raise AssertionError('Duplicate generated bone: ' + name)
        bone = self.obj.data.edit_bones[source]
        self.obj.data.edit_bones[name] = Bone(name, bone.head, bone.tail)
        return name

    def _place_bone(self, name, head, direction, length, roll_axis=None):
        bone = self.obj.data.edit_bones[name]
        bone.head = head.copy()
        bone.tail = head + direction.normalized() * length
        bone.x_axis = roll_axis.normalized() if roll_axis else Vector((0, 0, 1))

    def get_bone(self, name):
        return self.obj.data.edit_bones[name]

    def get_bone_parent(self, name):
        parent = self.get_bone(name).parent
        return parent.name if parent else None

    def set_bone_parent(self, name, parent, **kwargs):
        self.get_bone(name).parent = self.get_bone(parent) if parent else None

    def raise_error(self, message, *args):
        raise ValueError(message.format(*args))


def pair(role='start', skip=(False, False), shift=(0, 0, 0)):
    bones = {'root': Bone('root', (0, 0, 0), (0, 1, 0))}
    obj = type('Armature', (dict,), {})()
    obj.data = NS(edit_bones=bones)
    obj.matrix_world = WorldMatrix(shift)
    generator = NS(root_bone='root', _gamify_bendy_rigs=[], disable_auto_parent=lambda name: None)
    rigs = []
    for side, sign, omit in zip(('L', 'R'), (1, -1), skip):
        points = [Vector((0, 0, 0)), Vector((sign, 1, 0)), Vector((2 * sign, 2, 0))]
        if role == 'end':
            points.reverse()
        names = ['ORG-chain.' + side, 'ORG-tip.' + side]
        for name, head, tail in zip(names, points, points[1:]):
            bones[name] = Bone(name, head, tail)
        rig = ModelRig()
        rig.obj, rig.generator, rig.org_chain = obj, generator, names
        rig.params = NS(**{
            'gr_chain_bendy_mirror_merge_start': role == 'start',
            'gr_chain_bendy_mirror_merge_end': role == 'end',
            'gr_chain_bendy_skip_start_control': omit if role == 'start' else False,
            'gr_chain_bendy_skip_end_control': omit if role == 'end' else False,
            'gr_chain_bendy_skip_first_def': False, 'gr_chain_bendy_skip_last_def': False,
            'gr_chain_bendy_override_orientation': False,
            'gr_chain_bendy_override_parent': False,
            'gr_chain_bendy_end_override_parent': False,
            'gr_chain_bendy_parent_def_sequence': True,
        })
        rig.sample_count = 1
        rig.control_shape_size = 0.5
        rig.main_widget_type = 'circle'
        rig.bones = NS(ctrl=NS(), mch=NS())
        rig._mirror_groups = {}
        rig._orient_axes = None
        generator._gamify_bendy_rigs.append(rig)
        rigs.append(rig)
    return rigs


class MirrorMergeTests(unittest.TestCase):
    def generate(self, rigs, reverse=False):
        for rig in reversed(rigs) if reverse else rigs:
            rig.generate_bendy_bones()
        for rig in reversed(rigs) if reverse else rigs:
            rig.parent_bendy_chain()

    def test_endpoint_options_and_generation_order(self):
        for role in ('start', 'end'):
            for skip in ((False, False), (True, False), (False, True), (True, True)):
                for reverse in (False, True):
                    with self.subTest(role=role, skip=skip, reverse=reverse):
                        rigs = pair(role, skip)
                        self.generate(rigs, reverse)
                        group = rigs[0]._mirror_groups[role]
                        self.assertIs(group, rigs[1]._mirror_groups[role])
                        index = group['index']
                        controls = [name for rig in rigs for name in rig.bones.ctrl.joints
                                    if name == group['control']]
                        self.assertEqual(len(controls), 0 if all(skip) else 1)
                        tangents = [rig.get_bone(rig.bones.mch.tangents[index]) for rig in rigs]
                        self.assertAlmostEqual(tangents[0].y_axis.dot(tangents[1].y_axis), -1)
                        self.assertIs(tangents[0].parent, tangents[1].parent)
                        for rig in rigs:
                            # The ordinary interior joint control is retained.
                            self.assertIn(rig._point_controls[1], rig.bones.ctrl.joints)
                        if group['control']:
                            frame = rigs[0].get_bone(group['frame'])
                            control = rigs[0].get_bone(group['control'])
                            self.assertAlmostEqual(frame.y_axis.dot(control.y_axis), 1)

    def test_parent_mismatch_warns_and_preserves_both_targets(self):
        for role in ('start', 'end'):
            rigs = pair(role)
            for rig, target in zip(rigs, ('root', 'external')):
                rig.obj.data.edit_bones.setdefault(target, Bone(target, (0, 0, 0), (0, 1, 0)))
                key = 'gr_chain_bendy_' + ('end_' if role == 'end' else '')
                setattr(rig.params, key + 'override_parent', True)
                setattr(rig.params, key + 'parent', target)
            with warnings.catch_warnings(record=True) as feedback:
                warnings.simplefilter('always')
                self.generate(rigs)
            self.assertTrue(any('different parent targets' in str(item.message) for item in feedback))
            group = rigs[0]._mirror_groups[role]
            self.assertEqual([rig.get_bone(group['anchors'][rig]).parent.name for rig in rigs],
                             ['root', 'external'])

    def test_world_plane_not_armature_plane(self):
        rigs = pair(shift=(2, 0, 0))
        with warnings.catch_warnings(record=True):
            self.generate(rigs)
        self.assertFalse(rigs[0]._mirror_groups)
        self.assertFalse(rigs[1]._mirror_groups)

    def test_both_sides_must_opt_in(self):
        rigs = pair()
        rigs[1].params.gr_chain_bendy_mirror_merge_start = False
        with warnings.catch_warnings(record=True):
            self.generate(rigs)
        self.assertFalse(rigs[0]._mirror_groups)
        self.assertFalse(rigs[1]._mirror_groups)

    def test_asymmetric_geometry_stays_independent(self):
        rigs = pair()
        rigs[0].get_bone(rigs[0].org_chain[-1]).tail += Vector((0, 0.1, 0))
        with warnings.catch_warnings(record=True):
            self.generate(rigs)
        self.assertFalse(rigs[0]._mirror_groups)

    def test_shared_constraint_and_no_tangent_copy_transform(self):
        for skip in ((False, False), (True, True)):
            rigs = pair(skip=skip)
            self.generate(rigs)
            obj = rigs[0].obj
            obj.pose = NS(bones={name: NS(constraints=Entries()) for name in obj.data.edit_bones})
            for rig in rigs:
                rig.rig_bendy_chain()
            group = rigs[0]._mirror_groups['start']
            constraints = obj.pose.bones[group['frame']].constraints
            self.assertEqual(len(constraints), 1)
            blend = constraints[0]
            self.assertEqual(blend.type, 'ARMATURE')
            self.assertEqual([item.weight for item in blend.targets], [0.5, 0.5])
            self.assertEqual([item.subtarget for item in blend.targets],
                             [group['anchors'][rig] for rig in group['rigs']])
            for rig in rigs:
                self.assertFalse(obj.pose.bones[rig.bones.mch.tangents[0]].constraints)
                self.assertTrue(obj.pose.bones[rig.bones.mch.tangents[1]].constraints)

    def test_no_parent_override_with_both_controls_omitted(self):
        rigs = pair('end', (True, True))
        for rig in rigs:
            rig.params.gr_chain_bendy_end_override_parent = True
            rig.params.gr_chain_bendy_end_parent = 'NONE'
        self.generate(rigs)
        group = rigs[0]._mirror_groups['end']
        self.assertIsNone(group['control'])
        for rig in rigs:
            self.assertIsNone(rig.get_bone(group['anchors'][rig]).parent)

    def test_ambiguous_pair_does_not_merge(self):
        rigs = pair()
        duplicate = pair()[1]
        duplicate.obj = rigs[0].obj
        duplicate.generator = rigs[0].generator
        duplicate.org_chain = ['ORG-duplicate.R', 'ORG-duplicate-tip.R']
        for old, new in zip(rigs[1].org_chain, duplicate.org_chain):
            bone = rigs[0].get_bone(old)
            duplicate.obj.data.edit_bones[new] = Bone(new, bone.head, bone.tail)
        duplicate.generator._gamify_bendy_rigs.append(duplicate)
        with warnings.catch_warnings(record=True):
            self.generate(rigs + [duplicate])
        self.assertTrue(all(not rig._mirror_groups for rig in rigs + [duplicate]))


if __name__ == '__main__':
    unittest.main()
