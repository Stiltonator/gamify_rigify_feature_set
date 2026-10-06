"""GameReady B-Bone chain with tangent controls and sampled deform bones.

The B-Bones are mechanism drivers (MCH-BBone-*). Skinning DEF bones are
created at the chain joints and at evenly spaced samples inside each B-Bone.
"""

import bpy
import warnings
from mathutils import Vector
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, StringProperty

from rigify.base_rig import BaseRig, stage
from rigify.utils import (
    align_bone_x_axis,
    align_bone_y_axis,
    connected_children_names,
    make_deformer_name,
    make_mechanism_name,
    org,
    strip_org,
)
from rigify.utils.naming import make_derived_name

from rigify.utils.widgets_basic import (
    create_bone_widget,
    create_circle_widget,
    create_cube_widget,
    create_cuboctahedron_widget,
    create_diamond_widget,
    create_limb_widget,
    create_line_widget,
    create_pivot_widget,
    create_shoulder_widget,
    create_sphere_widget,
    create_truncated_cube_widget,
)
from rigify.utils.widgets import create_widget


WIDGET_ITEMS = [
    ('arrow', 'Arrow', 'Directional arrow widget'),
    ('bone', 'Bone', 'Bone-shaped widget'),
    ('circle', 'Circle', 'Circular widget'),
    ('cube', 'Cube', 'Cube widget'),
    ('cube_truncated', 'T-Cube', 'Truncated cube widget'),
    ('cuboctahedron', 'Cubocta', 'Cuboctahedron widget'),
    ('diamond', 'Diamond', 'Diamond widget'),
    ('limb', 'Limb', 'Limb widget'),
    ('line', 'Line', 'Line widget'),
    ('pivot', 'Pivot', 'Pivot axes widget'),
    ('pivot_cross', 'Cross', 'Pivot cross widget'),
    ('shoulder', 'Shoulder', 'Shoulder widget'),
    ('sphere', 'Sphere', 'Sphere widget'),
]

WIDGET_BUILDERS = {
    'bone': (create_bone_widget, {}),
    'circle': (create_circle_widget, {'radius': 0.5}),
    'cube': (create_cube_widget, {'radius': 0.5}),
    'cube_truncated': (create_truncated_cube_widget, {'radius': 0.5}),
    'cuboctahedron': (create_cuboctahedron_widget, {'radius': 0.5}),
    'diamond': (create_diamond_widget, {'radius': 0.5}),
    'limb': (create_limb_widget, {}),
    'line': (create_line_widget, {}),
    'pivot': (create_pivot_widget, {'radius': 0.5}),
    'pivot_cross': (create_pivot_widget, {'radius': 0.5, 'square': False}),
    'shoulder': (create_shoulder_widget, {'radius': 0.5}),
    'sphere': (create_sphere_widget, {'radius': 0.5}),
}

ARROW_VERTICES = [
    (-0.10, -0.35, -0.10), (0.10, -0.35, -0.10),
    (0.10, -0.35, 0.10), (-0.10, -0.35, 0.10),
    (-0.10, 0.08, -0.10), (0.10, 0.08, -0.10),
    (0.10, 0.08, 0.10), (-0.10, 0.08, 0.10),
    (-0.27, 0.08, -0.27), (0.27, 0.08, -0.27),
    (0.27, 0.08, 0.27), (-0.27, 0.08, 0.27),
    (0.0, 0.52, 0.0),
]
ARROW_EDGES = [
    (0, 1), (1, 2), (2, 3), (3, 0),
    (4, 5), (5, 6), (6, 7), (7, 4),
    (0, 4), (1, 5), (2, 6), (3, 7),
    (8, 9), (9, 10), (10, 11), (11, 8),
    (8, 12), (9, 12), (10, 12), (11, 12),
]


class Rig(BaseRig):
    """A connected chain of tangent-controlled B-Bone mechanism drivers."""

    min_chain_length = 2
    none_parent_token = 'NONE'

    def find_org_bones(self, bone):
        names = [bone.name]
        current = bone.bone
        while True:
            children = [child for child in current.children if child.use_connect]
            if len(children) > 1:
                self.raise_error(
                    "GameReady Chain Bendy requires one connected chain without branches."
                )
            if not children:
                break
            current = children[0]
            if self.obj.pose.bones[current.name].rigify_type:
                self.raise_error(
                    "Only the first bone of GameReady Chain Bendy may have a Rigify Type."
                )
            names.append(current.name)
        return names

    def initialize(self):
        super().initialize()
        self.org_chain = list(self.bones.org)
        if len(self.org_chain) < self.min_chain_length:
            self.raise_error(
                "GameReady Chain Bendy requires at least {} connected bones.",
                self.min_chain_length,
            )
        self.sample_count = self.params.gr_chain_bendy_deformers_per_bbone
        self.bbone_segments = self.params.gr_chain_bendy_bbone_segments
        self.control_shape_size = self.params.gr_chain_bendy_control_shape_size
        self.tweak_shape_size = self.params.gr_chain_bendy_tweak_shape_size
        self.main_widget_type = self.params.gr_chain_bendy_main_widget
        self.tweak_widget_type = self.params.gr_chain_bendy_tweak_widget
        self.resolved_parent = None
        # Resolved lazily: edit bones are not available during initialize.
        self._orient_axes = None
        self._mirror_groups = {}
        if not hasattr(self.generator, '_gamify_bendy_rigs'):
            self.generator._gamify_bendy_rigs = []
        self.generator._gamify_bendy_rigs.append(self)

    def _merge_warning(self, message):
        warnings.warn('Gamify Chain Bendy: ' + message, stacklevel=2)
        # Retain feedback on the generated armature as well as in Blender's console.
        key = 'gamify_bendy_merge_warnings'
        previous = self.obj.get(key, '')
        self.obj[key] = previous + ('\n' if previous else '') + message

    def _world_chain(self):
        bones = self.obj.data.edit_bones
        points = [bones[name].head.copy() for name in self.org_chain]
        points.append(bones[self.org_chain[-1]].tail.copy())
        return [self.obj.matrix_world @ point for point in points]

    def _prepare_mirror_groups(self):
        """Pair opted-in mirrored chains before any controls are generated."""
        if getattr(self.generator, '_gamify_bendy_merges_prepared', False):
            return
        self.generator._gamify_bendy_merges_prepared = True
        self.obj['gamify_bendy_merge_warnings'] = ''
        rigs = sorted(self.generator._gamify_bendy_rigs, key=lambda rig: rig.org_chain[0])
        world = {rig: rig._world_chain() for rig in rigs}
        tolerance = 1.0e-5
        for role, index in (('start', 0), ('end', -1)):
            enabled = [rig for rig in rigs if getattr(rig.params, 'gr_chain_bendy_mirror_merge_' + role)]
            candidates = {}
            for rig in enabled:
                points = world[rig]
                matches = []
                if abs(points[index].x) <= tolerance:
                    for other in enabled:
                        if other is rig or len(world[other]) != len(points):
                            continue
                        mirrored = all(
                            (Vector((-a.x, a.y, a.z)) - b).length <= tolerance
                            for a, b in zip(points, world[other])
                        )
                        # Exclude chains lying entirely in the centre plane.
                        opposite_sides = any(a.x * b.x < -tolerance ** 2
                                             for a, b in zip(points, world[other]))
                        if mirrored and opposite_sides and (points[index] - world[other][index]).length <= tolerance:
                            matches.append(other)
                candidates[rig] = matches
            for rig in enabled:
                matches = candidates[rig]
                if len(matches) != 1 or len(candidates[matches[0]]) != 1:
                    rig._merge_warning(
                        f"{rig._label(rig.org_chain[0])}: Mirror Merge {role.title()} has no unique "
                        'mirrored partner at world X=0; the endpoint remains independent.'
                    )
                    continue
                other = matches[0]
                if role in rig._mirror_groups:
                    continue
                pair = (rig, other)
                bones = self.obj.data.edit_bones
                sources = [bones[item.org_chain[index]] for item in pair]
                # Same-role endpoints travel in opposite directions through a smooth seam.
                direction = sources[0].y_axis.normalized() - sources[1].y_axis.normalized()
                if direction.length < tolerance:
                    direction = sources[0].y_axis.copy()
                direction.normalize()
                roll = sources[0].x_axis.normalized() + sources[1].x_axis.normalized()
                roll -= direction * roll.dot(direction)
                if roll.length < tolerance:
                    roll = min((Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))),
                               key=lambda axis: abs(axis.dot(direction)))
                    roll -= direction * roll.dot(direction)
                group = dict(rigs=pair, role=role, index=index, direction=direction,
                             roll=roll.normalized(), anchors={}, parents={})
                for item in pair:
                    item._mirror_groups[role] = group

    def _generate_merged_endpoint(self, group, source_name, point, length):
        """Generate one shared frame/control, plus a parent anchor for each side."""
        if 'frame' not in group:
            group['owner'] = self
            canonical = group['rigs'][0]
            label = canonical._label(canonical.org_chain[group['index']])
            suffix = '_bendy_merged_' + group['role']
            frame = self.copy_bone(source_name, make_derived_name(label, 'mch', suffix))
            self._place_bone(frame, point, group['direction'], length, group['roll'])
            group['frame'] = frame
            visible = [rig for rig in group['rigs'] if not getattr(
                rig.params, 'gr_chain_bendy_skip_' + group['role'] + '_control')]
            group['control'] = None
            if visible:
                control = self.copy_bone(source_name, make_derived_name(label, 'ctrl', suffix))
                self._place_bone(control, point, group['direction'], length, group['roll'])
                group['control'] = control
                group['style_rig'] = visible[0]
        anchor = self.copy_bone(source_name, make_derived_name(
            self._label(source_name), 'mch', '_bendy_merge_' + group['role'] + '_parent'))
        self._place_bone(anchor, point, group['direction'], length, group['roll'])
        group['anchors'][self] = anchor
        return group['control']

    @staticmethod
    def _label(name):
        return strip_org(name)

    def _orientation_override(self):
        """Return (y_axis, x_axis) of the orientation bone, or None when not overriding."""
        if not self.params.gr_chain_bendy_override_orientation:
            return None

        if self._orient_axes is None:
            requested = self.params.gr_chain_bendy_orient_bone.strip()
            chain_name = self._label(self.org_chain[0])
            if not requested:
                self.raise_error(
                    "Chain '{}' has Override Bone Orientation enabled but no orientation bone is set.",
                    chain_name,
                )
            edit_bones = self.obj.data.edit_bones
            reference = None
            # Metarig bones become ORG bones in the generated rig; also accept
            # an exact generated name.
            for candidate in (org(requested), requested):
                if candidate in edit_bones:
                    reference = edit_bones[candidate]
                    break
            if reference is None:
                self.raise_error(
                    "Chain '{}' orientation bone '{}' was not found in the metarig.",
                    chain_name,
                    requested,
                )
            self._orient_axes = (
                reference.y_axis.normalized(),
                reference.x_axis.normalized(),
            )
        return self._orient_axes

    def _conform_orientation(self, direction, roll_axis):
        """Orientation for tweak and DEF bones: the override if set."""
        axes = self._orientation_override()
        if axes is None:
            return direction, roll_axis
        return axes[0].copy(), axes[1].copy()

    def _target_reaches_owned(self, target, owned):
        """True if target, or any of its ancestors, is one of this rig's own bones."""
        ancestor = self.obj.data.edit_bones[target]
        seen = set()
        while ancestor:
            if ancestor.name in owned or ancestor.name in seen:
                return True
            seen.add(ancestor.name)
            ancestor = ancestor.parent
        return False

    def _bone_length(self, source_name):
        return max(self.obj.data.edit_bones[source_name].length, 0.001)

    def _place_bone(self, name, head, direction, length, roll_axis=None):
        eb = self.obj.data.edit_bones[name]
        direction = direction.normalized()
        if direction.length < 1.0e-6:
            direction = self.obj.data.edit_bones[self.org_chain[0]].y_axis.normalized()
        eb.head = head
        eb.tail = head + direction * max(length, 0.001)
        if roll_axis is not None:
            try:
                align_bone_y_axis(self.obj, name, direction)
                align_bone_x_axis(self.obj, name, roll_axis)
            except (ValueError, RuntimeError):
                # The copied source roll is a safe fallback for parallel axes.
                pass

    def _sample_specs(self):
        """Return ordered sample points; a shared joint has one sample entry."""
        edit_bones = self.obj.data.edit_bones
        specs = []
        for index, org_name in enumerate(self.org_chain):
            source = edit_bones[org_name]
            if index == 0:
                specs.append((source.head.copy(), index, 0.0, 'start'))

            for inner in range(1, self.sample_count + 1):
                t = inner / (self.sample_count + 1.0)
                point = source.head.lerp(source.tail, t)
                specs.append((point, index, t, 'inner'))

            if index < len(self.org_chain) - 1:
                next_source = edit_bones[self.org_chain[index + 1]]
                specs.append((source.tail.copy(), index, 1.0, 'joint'))
            else:
                specs.append((source.tail.copy(), index, 1.0, 'end'))
        return specs

    def _sample_orientation(self, spec):
        _, index, t, kind = spec
        edit_bones = self.obj.data.edit_bones
        current = edit_bones[self.org_chain[index]]
        if kind == 'joint' and index + 1 < len(self.org_chain):
            following = edit_bones[self.org_chain[index + 1]]
            direction = current.y_axis.normalized() + following.y_axis.normalized()
            if direction.length < 1.0e-6:
                direction = following.y_axis.copy()
            roll_axis = current.x_axis.normalized() + following.x_axis.normalized()
            if roll_axis.length < 1.0e-6:
                roll_axis = following.x_axis.copy()
            return direction.normalized(), roll_axis.normalized()
        return current.y_axis.normalized(), current.x_axis.normalized()

    @stage.generate_bones
    def generate_bendy_bones(self):
        self._prepare_mirror_groups()
        edit_bones = self.obj.data.edit_bones
        bbone_drivers = []
        tangent_bones = []
        controls = []
        point_controls = []

        # One start point, one point at every connected joint, and one end.
        for point_index in range(len(self.org_chain) + 1):
            source_index = min(point_index, len(self.org_chain) - 1)
            source_name = self.org_chain[source_index]
            source_label = self._label(source_name)
            if point_index == 0:
                point_role = 'start'
            elif point_index == len(self.org_chain):
                point_role = 'end'
            else:
                point_role = 'joint_' + str(point_index)

            skip_control = (
                point_role == 'start' and self.params.gr_chain_bendy_skip_start_control
                or point_role == 'end' and self.params.gr_chain_bendy_skip_end_control
            )
            group = self._mirror_groups.get(point_role)
            control = None if skip_control or group else self.copy_bone(
                source_name,
                make_derived_name(source_label, 'ctrl', '_bendy_' + point_role),
            )
            tangent = self.copy_bone(
                source_name,
                make_mechanism_name(source_label) + '_tangent_' + str(point_index),
            )

            if point_index == 0:
                point = edit_bones[source_name].head.copy()
                direction, roll_axis = self._sample_orientation(
                    (point, source_index, 0.0, 'start')
                )
            elif point_index == len(self.org_chain):
                point = edit_bones[self.org_chain[-1]].tail.copy()
                direction, roll_axis = self._sample_orientation(
                    (point, source_index, 1.0, 'end')
                )
            else:
                previous = edit_bones[self.org_chain[point_index - 1]]
                following = edit_bones[self.org_chain[point_index]]
                point = previous.tail.copy()
                direction = previous.y_axis.normalized() + following.y_axis.normalized()
                if direction.length < 1.0e-6:
                    direction = following.y_axis.copy()
                roll_axis = previous.x_axis.normalized() + following.x_axis.normalized()
                if roll_axis.length < 1.0e-6:
                    roll_axis = following.x_axis.copy()
                direction.normalize()
                roll_axis.normalize()

            point_length = self._bone_length(source_name) * 0.25
            if group:
                control = self._generate_merged_endpoint(group, source_name, point, point_length)
                direction = group['direction'] if self is group['rigs'][0] else -group['direction']
                roll_axis = group['roll']
            # Main controls and tangents always share the B-Bone chain orientation.
            # The orientation override applies only to tweaks and DEF samples.
            if control is not None and (not group or group['owner'] is self):
                if not group:
                    self._place_bone(control, point, direction, point_length, roll_axis)
                controls.append(control)
            self._place_bone(tangent, point, direction, point_length, roll_axis)
            point_controls.append(control)
            tangent_bones.append(tangent)

        # Each metarig segment gets a separate B-Bone driver between two
        # adjacent tangent points.
        for index, org_name in enumerate(self.org_chain):
            source = edit_bones[org_name]
            name = self.copy_bone(
                org_name,
                make_mechanism_name(self._label(org_name)) + '_bbone',
            )
            driver = edit_bones[name]
            driver.head = source.head
            driver.tail = source.tail
            driver.use_deform = False
            bbone_drivers.append(name)

        # This single pivot is shared if several Chain Bendy rigs are present.
        pivot_name = 'MCH-ArmaturePivot'
        if pivot_name in edit_bones:
            pivot = pivot_name
        else:
            pivot = self.copy_bone(self.org_chain[0], pivot_name)
            # New pivots use the armature origin and Blender's default bone
            # orientation, independent of the metarig chain's location/roll.
            pivot_bone = edit_bones[pivot]
            pivot_bone.head = (0.0, 0.0, 0.0)
            pivot_bone.tail = (0.0, 0.05, 0.0)
            pivot_bone.roll = 0.0

        sample_names = []
        tweak_names = []
        deform_names = []
        deform_name_base = make_deformer_name(self._label(self.org_chain[0]))
        sample_specs = self._sample_specs()
        # Skipping drops the whole sample (MCH-INT, tweak and DEF), since those
        # exist only to drive that DEF. Kept samples keep their original index,
        # so bone names do not renumber when these options are toggled.
        first_kept = 1 if self.params.gr_chain_bendy_skip_first_def else 0
        end_kept = (
            len(sample_specs) - 1
            if self.params.gr_chain_bendy_skip_last_def
            else len(sample_specs)
        )
        kept_indices = range(first_kept, end_kept)
        kept_specs = [sample_specs[index] for index in kept_indices]
        for sample_index in kept_indices:
            spec = sample_specs[sample_index]
            point, source_index, t, kind = spec
            source_name = self.org_chain[source_index]
            source_label = self._label(source_name)
            int_name = 'MCH-INT-' + source_label + '_sample_' + str(sample_index + 1).zfill(2)
            int_name = self.copy_bone(source_name, int_name)

            direction, roll_axis = self._sample_orientation(spec)
            self._place_bone(
                int_name,
                point,
                direction,
                self._bone_length(source_name) * 0.12,
                roll_axis,
            )
            tweak_name = 'CTRL-' + source_label + '_tweak_' + str(sample_index + 1).zfill(2)
            # The tweak and its DEF must share one rest orientation, because the
            # DEF copies the tweak's world transform. MCH-INT keeps the chain
            # direction; the tweak's local axes are what the animator sees.
            sample_direction, sample_roll = self._conform_orientation(direction, roll_axis)
            tweak_name = self.copy_bone(int_name, tweak_name)
            self._place_bone(
                tweak_name,
                point,
                sample_direction,
                self._bone_length(source_name) * 0.2,
                sample_roll,
            )
            def_name = deform_name_base + '.' + str(sample_index).zfill(3)
            def_name = self.copy_bone(int_name, def_name)
            self._place_bone(
                def_name,
                point,
                sample_direction,
                self._bone_length(source_name) * 0.12,
                sample_roll,
            )
            edit_bones[def_name].use_deform = True
            sample_names.append(int_name)
            tweak_names.append(tweak_name)
            deform_names.append(def_name)

        self.bones.ctrl.joints = controls
        # Keep endpoint slots even when their animator-facing controls are omitted.
        self._point_controls = point_controls
        self.bones.mch.tangents = tangent_bones
        self.bones.mch.bbone_drivers = bbone_drivers
        self.bones.mch.intermediary = sample_names
        self.bones.mch.armature_pivot = pivot
        self.bones.ctrl.tweaks = tweak_names
        self.bones.deform = deform_names

        # Map each intermediary to its nearest B-Bone driver(s). A joint is
        # intentionally shared 50/50 by the two adjacent drivers.
        targets = []
        for spec in kept_specs:
            _, segment_index, t, kind = spec
            if kind == 'joint' and segment_index + 1 < len(bbone_drivers):
                targets.append(((bbone_drivers[segment_index], 0.5),
                                (bbone_drivers[segment_index + 1], 0.5)))
            else:
                targets.append(((bbone_drivers[segment_index], 1.0),))
        self._intermediary_targets = targets
        self._intermediary_curve_targets = [
            (bbone_drivers[segment_index], t)
            for _, segment_index, t, _ in kept_specs
        ]

    @stage.parent_bones
    def parent_bendy_chain(self):
        edit_bones = self.obj.data.edit_bones
        root = self.generator.root_bone
        source_parent = self.get_bone_parent(self.org_chain[0])

        # Resolve the ordinary metarig parent first. An invalid override falls
        # back to this exact behavior, as if Override Parent were disabled.
        if source_parent and source_parent != root:
            def_parent = make_deformer_name(strip_org(source_parent))
            default_parent = def_parent if def_parent in edit_bones else source_parent
        else:
            default_parent = root

        owned = set(self.org_chain)
        owned.update(self.bones.ctrl.joints)
        owned.update(self.bones.mch.tangents)
        owned.update(self.bones.mch.bbone_drivers)
        owned.update(self.bones.mch.intermediary)
        owned.update(self.bones.ctrl.tweaks)
        owned.update(self.bones.deform)
        owned.add(self.bones.mch.armature_pivot)
        for group in self._mirror_groups.values():
            owned.add(group['frame'])
            owned.update(group['anchors'].values())
            if group['control']:
                owned.add(group['control'])

        parent = default_parent
        if self.params.gr_chain_bendy_override_parent:
            requested = self.params.gr_chain_bendy_parent.strip()
            chain_name = self._label(self.org_chain[0])
            attempted_target = requested if requested else '<empty>'

            if not requested:
                self.raise_error(
                    "Chain '{}' Override Parent target '{}' is empty; "
                    "re-parenting was not applied.",
                    chain_name,
                    attempted_target,
                )
            elif requested.casefold() == self.none_parent_token.casefold():
                # NONE is an intentional no-parent request and suppresses warnings.
                parent = None
            elif requested not in edit_bones:
                self.raise_error(
                    "Chain '{}' Override Parent target '{}' was not found; "
                    "re-parenting was not applied.",
                    chain_name,
                    attempted_target,
                )
            else:
                # A target that is one of this chain's bones, or is beneath one,
                # would make the generated parenting graph cyclic.
                ancestor = edit_bones[requested]
                seen = set()
                cyclic = False
                while ancestor:
                    if ancestor.name in owned or ancestor.name in seen:
                        cyclic = True
                        break
                    seen.add(ancestor.name)
                    ancestor = ancestor.parent

                if cyclic:
                    self.raise_error(
                        "Chain '{}' Override Parent target '{}' would create a "
                        "cyclic dependency; re-parenting was not applied.",
                        chain_name,
                        attempted_target,
                    )
                else:
                    parent = requested

        self.resolved_parent = parent
        self.rig_parent_bone = parent or root

        # Main controls attach to the selected chain parent. Tangent bones
        # follow those controls; drivers and INT bones stay under the MCH pivot.
        # Each tweak is parented to its corresponding INT, while DEF parenting
        # is either sequential or flat under the selected chain parent.
        for control in self.bones.ctrl.joints:
            if any(group['control'] == control for group in self._mirror_groups.values()):
                continue
            self.set_bone_parent(control, parent, use_connect=False)
            self.get_bone(control).inherit_scale = 'NONE'

        # Omitted controls leave their tangent directly attached to the chain parent.
        for index, (tangent, control) in enumerate(zip(self.bones.mch.tangents, self._point_controls)):
            role = 'start' if index == 0 else 'end' if index == len(self._point_controls) - 1 else None
            group = self._mirror_groups.get(role)
            if group:
                self.set_bone_parent(tangent, group['control'] or group['frame'], use_connect=False)
                continue
            self.set_bone_parent(tangent, control or parent, use_connect=False)
            if control is None:
                self.get_bone(tangent).inherit_scale = 'NONE'
                if parent is None:
                    self.generator.disable_auto_parent(tangent)

        # The end control may follow a different bone to the rest of the chain,
        # so that bone drives the end of the chain.
        end_parent = parent
        if self.params.gr_chain_bendy_end_override_parent:
            end_group = self._mirror_groups.get('end')
            end_control = (end_group['anchors'][self] if end_group else
                           self._point_controls[-1] or self.bones.mch.tangents[-1])
            end_requested = self.params.gr_chain_bendy_end_parent.strip()
            chain_name = self._label(self.org_chain[0])

            if not end_requested:
                self.raise_error(
                    "Chain '{}' End Control Parent is empty; enter a generated bone "
                    "name, or NONE for no parent.",
                    chain_name,
                )
            elif end_requested.casefold() == self.none_parent_token.casefold():
                end_parent = None
            elif end_requested not in edit_bones:
                self.raise_error(
                    "Chain '{}' End Control Parent '{}' was not found.",
                    chain_name,
                    end_requested,
                )
            elif self._target_reaches_owned(end_requested, owned):
                self.raise_error(
                    "Chain '{}' End Control Parent '{}' is this chain's own bone or "
                    "beneath one, which would create a cyclic dependency.",
                    chain_name,
                    end_requested,
                )
            else:
                end_parent = end_requested

            self.set_bone_parent(end_control, end_parent, use_connect=False)
            if end_parent is None:
                self.generator.disable_auto_parent(end_control)

        for role, group in self._mirror_groups.items():
            endpoint_parent = parent if role == 'start' else end_parent
            anchor = group['anchors'][self]
            self.set_bone_parent(anchor, endpoint_parent, use_connect=False)
            if endpoint_parent is None:
                self.generator.disable_auto_parent(anchor)
            group['parents'][self] = endpoint_parent
            if group['owner'] is self:
                self.set_bone_parent(group['frame'], None, use_connect=False)
                self.generator.disable_auto_parent(group['frame'])
                if group['control']:
                    self.set_bone_parent(group['control'], group['frame'], use_connect=False)
                    self.get_bone(group['control']).inherit_scale = 'NONE'
            if len(group['parents']) == 2 and len(set(group['parents'].values())) > 1:
                names = ', '.join(f"{rig._label(rig.org_chain[0])}: {target or 'NONE'}"
                                  for rig, target in group['parents'].items())
                self._merge_warning(f'Mirror Merge {role.title()} has different parent targets ({names}); '
                                    'both parents contribute equally to the shared endpoint.')

        for tweak, intermediary in zip(
            self.bones.ctrl.tweaks, self.bones.mch.intermediary
        ):
            self.set_bone_parent(tweak, intermediary, use_connect=False)

        pivot = self.bones.mch.armature_pivot
        self.set_bone_parent(pivot, None, use_connect=False)
        self.generator.disable_auto_parent(pivot)

        for name in self.bones.mch.bbone_drivers + self.bones.mch.intermediary:
            self.set_bone_parent(name, pivot, use_connect=False)

        parent_defs_in_sequence = self.params.gr_chain_bendy_parent_def_sequence
        for index, deform in enumerate(self.bones.deform):
            deform_parent = (
                self.bones.deform[index - 1]
                if parent_defs_in_sequence and index > 0
                else parent
            )
            self.set_bone_parent(deform, deform_parent, use_connect=False)
            if deform_parent is None:
                self.generator.disable_auto_parent(deform)

        if parent is None:
            for name in self.bones.ctrl.joints:
                self.generator.disable_auto_parent(name)

    @stage.configure_bones
    def configure_bendy_chain(self):
        data_bones = self.obj.data.bones
        pose_bones = self.obj.pose.bones

        for index, driver_name in enumerate(self.bones.mch.bbone_drivers):
            driver = data_bones[driver_name]
            driver.display_type = 'BBONE'
            driver.bbone_segments = self.bbone_segments
            driver.bbone_custom_handle_start = data_bones[self.bones.mch.tangents[index]]
            driver.bbone_custom_handle_end = data_bones[self.bones.mch.tangents[index + 1]]
            driver.bbone_handle_type_start = 'TANGENT'
            driver.bbone_handle_type_end = 'TANGENT'
            driver.bbone_easein = 1.0
            driver.bbone_easeout = 1.0

        pivot_pose = pose_bones[self.bones.mch.armature_pivot]
        pivot_pose.lock_location = (True, True, True)
        pivot_pose.lock_rotation = (True, True, True)
        pivot_pose.lock_rotation_w = True
        pivot_pose.lock_scale = (True, True, True)

        # The main widget mesh has a fixed 0.5 radius. Scale relative to the
        # default setting so the current default appearance is preserved.
        # Disable bone-length scaling so equal settings look equal on every chain.
        for control in self.bones.ctrl.joints:
            control_pose = pose_bones[control]
            control_pose.use_custom_shape_bone_size = False
            style = next((group['style_rig'] for group in self._mirror_groups.values()
                          if group['control'] == control), self)
            control_pose.custom_shape_scale_xyz = (style.control_shape_size / 0.5,) * 3

        for tweak in self.bones.ctrl.tweaks:
            # Tweak shape size is an explicit widget size, independent of the
            # (short) tweak bone length.
            tweak_pose = pose_bones[tweak]
            tweak_pose.use_custom_shape_bone_size = False
            tweak_pose.custom_shape_scale_xyz = (self.tweak_shape_size,) * 3

    def create_selected_widget(self, bone_name, widget_type):
        old_widget = self.generator.old_widget_table.get(bone_name)
        force_new = (
            old_widget is None
            or old_widget.get('gr_chain_bendy_widget_type') != widget_type
        )

        if widget_type == 'arrow':
            widget = create_widget(
                self.obj, bone_name, widget_force_new=force_new
            )
            if widget is not None:
                widget.data.from_pydata(ARROW_VERTICES, ARROW_EDGES, [])
                widget.data.update()
        else:
            builder, kwargs = WIDGET_BUILDERS[widget_type]
            widget = builder(
                self.obj,
                bone_name,
                widget_force_new=force_new,
                **kwargs,
            )

        if widget is not None:
            widget['gr_chain_bendy_widget_type'] = widget_type

    @stage.rig_bones
    def rig_bendy_chain(self):
        for index, driver in enumerate(self.bones.mch.bbone_drivers):
            self.make_constraint(driver, 'COPY_LOCATION', self.bones.mch.tangents[index])
            self.make_constraint(driver, 'STRETCH_TO', self.bones.mch.tangents[index + 1])

        # Main controls retain the tangent orientation regardless of the sample
        # orientation override, so use the same driving constraints in both cases.
        for group in self._mirror_groups.values():
            if group['owner'] is self:
                constraint = self.obj.pose.bones[group['frame']].constraints.new('ARMATURE')
                constraint.name = 'Mirror Merge Parent Blend'
                constraint.use_current_location = True
                for rig in group['rigs']:
                    target = constraint.targets.new()
                    target.target = self.obj
                    target.subtarget = group['anchors'][rig]
                    target.weight = 0.5
        for index, (tangent, control) in enumerate(zip(self.bones.mch.tangents, self._point_controls)):
            role = 'start' if index == 0 else 'end' if index == len(self._point_controls) - 1 else None
            if role in self._mirror_groups:
                # Parenting preserves the opposite rest directions across the seam.
                continue
            if control is not None:
                self.make_constraint(tangent, 'COPY_TRANSFORMS', control)

        for intermediary, targets, (driver, head_tail) in zip(
            self.bones.mch.intermediary,
            self._intermediary_targets,
            self._intermediary_curve_targets,
        ):
            pose_bone = self.obj.pose.bones[intermediary]
            constraint = pose_bone.constraints.new('ARMATURE')
            constraint.name = 'Follow Nearest B-Bone'
            constraint.use_current_location = True
            for target_name, weight in targets:
                target = constraint.targets.new()
                target.target = self.obj
                target.subtarget = target_name
                target.weight = weight

            curve_location = self.make_constraint(
                intermediary,
                'COPY_LOCATION',
                driver,
                head_tail=head_tail,
                use_bbone_shape=True,
            )
            curve_location.name = 'Follow B-Bone Curve'

            self.make_constraint(
                intermediary,
                'COPY_SCALE',
                self.generator.root_bone,
            )

        for deform, tweak in zip(self.bones.deform, self.bones.ctrl.tweaks):
            self.make_constraint(deform, 'COPY_TRANSFORMS', tweak)

    @stage.generate_widgets
    def generate_bendy_widgets(self):
        for control in self.bones.ctrl.joints:
            style = next((group['style_rig'] for group in self._mirror_groups.values()
                          if group['control'] == control), self)
            self.create_selected_widget(control, style.main_widget_type)

        for tweak in self.bones.ctrl.tweaks:
            self.create_selected_widget(tweak, self.tweak_widget_type)

    @classmethod
    def add_parameters(cls, params):
        for role in ('start', 'end'):
            setattr(params, 'gr_chain_bendy_mirror_merge_' + role, BoolProperty(
                name='Mirror Merge ' + role.title(),
                description='Share this endpoint and smooth tangents with an opted-in mirrored chain at world X=0',
                default=False,
            ))
            setattr(params, 'gr_chain_bendy_ui_' + role, BoolProperty(
                name=role.title() + ' Point', default=False,
                description='Expand ' + role + ' point settings',
            ))
        params.gr_chain_bendy_bbone_segments = IntProperty(
            name='Bendy Bone Segments',
            description='Number of visual B-Bone segments on each generated B-Bone',
            default=3,
            min=1,
            max=32,
        )
        params.gr_chain_bendy_control_shape_size = FloatProperty(
            name='Main Shape Size',
            description='Radius of the start, end, and joint control widgets',
            default=0.5,
            min=0.001,
            max=50.0,
        )
        params.gr_chain_bendy_tweak_shape_size = FloatProperty(
            name='Tweak Shape Size',
            description='Size multiplier for the directional tweak widgets',
            default=0.25,
            min=0.001,
            max=5.0,
        )
        params.gr_chain_bendy_main_widget = EnumProperty(
            name='Main Widget',
            items=WIDGET_ITEMS,
            default='circle',
        )
        params.gr_chain_bendy_tweak_widget = EnumProperty(
            name='Tweak Widget',
            items=WIDGET_ITEMS,
            default='arrow',
        )
        params.gr_chain_bendy_deformers_per_bbone = IntProperty(
            name='Deformers Per B-Bone',
            description='Number of evenly spaced interior DEF samples per B-Bone',
            default=1,
            min=1,
            max=32,
        )
        params.gr_chain_bendy_parent_def_sequence = BoolProperty(
            name='Parent DEF Bones in Sequence',
            description='DEF bones are parented to each other in sequence',
            default=True,
        )
        params.gr_chain_bendy_override_parent = BoolProperty(
            name='Override Parent',
            description='Override the parent inherited from the metarig chain',
            default=False,
        )
        params.gr_chain_bendy_parent = StringProperty(
            name='Parent',
            description="Generated bone name; use NONE for no parent",
            default='',
        )
        params.gr_chain_bendy_end_override_parent = BoolProperty(
            name='Override End Control Parent',
            description='Parent the end control (or internal endpoint if omitted) to a named generated bone, '
                        'so that bone drives the end of the chain',
            default=False,
        )
        params.gr_chain_bendy_end_parent = StringProperty(
            name='End Parent',
            description="Exact generated bone name, e.g. DEF-hand.L; use NONE for no parent",
            default='',
        )
        params.gr_chain_bendy_skip_start_control = BoolProperty(
            name='Skip Generating Start Control',
            description='Omit the start main control; its internal tangent follows the chain parent',
            default=False,
        )
        params.gr_chain_bendy_skip_end_control = BoolProperty(
            name='Skip Generating End Control',
            description='Omit the end main control; its internal tangent follows the chain parent or End Parent override',
            default=False,
        )
        params.gr_chain_bendy_skip_first_def = BoolProperty(
            name='Skip Generating First DEF',
            description='Do not generate the first DEF bone of the chain (and its tweak control)',
            default=False,
        )
        params.gr_chain_bendy_skip_last_def = BoolProperty(
            name='Skip Generating Last DEF',
            description='Do not generate the last DEF bone of the chain (and its tweak control)',
            default=False,
        )
        params.gr_chain_bendy_override_orientation = BoolProperty(
            name='Override Bone Orientation',
            description='Orient the generated tweaks and DEF bones to match an '
                        'orientation bone instead of following the chain direction',
            default=False,
        )
        params.gr_chain_bendy_orient_bone = StringProperty(
            name='Orientation Bone',
            description='Metarig bone whose orientation the tweaks and DEF bones conform to',
            default='',
        )

    @classmethod
    def parameters_ui(cls, layout, params):
        layout.label(text='GameReady Bendy Chain — requires 2 or more connected bones')
        layout.prop(params, 'gr_chain_bendy_bbone_segments')
        layout.prop(params, 'gr_chain_bendy_deformers_per_bbone')
        layout.prop(params, 'gr_chain_bendy_parent_def_sequence')
        layout.separator()
        layout.prop(params, 'gr_chain_bendy_control_shape_size')
        layout.prop(params, 'gr_chain_bendy_tweak_shape_size')
        layout.prop(params, 'gr_chain_bendy_main_widget', text='Main Widget')
        layout.prop(params, 'gr_chain_bendy_tweak_widget', text='Tweak Widget')
        for role in ('start', 'end'):
            box = layout.box()
            expanded = getattr(params, 'gr_chain_bendy_ui_' + role)
            box.prop(params, 'gr_chain_bendy_ui_' + role,
                     icon='TRIA_DOWN' if expanded else 'TRIA_RIGHT', emboss=False)
            if expanded:
                box.prop(params, 'gr_chain_bendy_skip_' + role + '_control')
                box.prop(params, 'gr_chain_bendy_mirror_merge_' + role)
                box.prop(params, 'gr_chain_bendy_skip_first_def' if role == 'start'
                         else 'gr_chain_bendy_skip_last_def')
                override = 'gr_chain_bendy_override_parent' if role == 'start' else 'gr_chain_bendy_end_override_parent'
                target = 'gr_chain_bendy_parent' if role == 'start' else 'gr_chain_bendy_end_parent'
                box.prop(params, override)
                if getattr(params, override):
                    box.prop(params, target)

        row = layout.row(align=True)
        row.prop(params, 'gr_chain_bendy_override_orientation')
        if params.gr_chain_bendy_override_orientation:
            row.prop_search(
                params, 'gr_chain_bendy_orient_bone',
                bpy.context.object.pose, 'bones', text='',
            )


def create_sample(obj):
    """Create a minimal two-bone connected chain sample."""
    import bpy

    bpy.ops.object.mode_set(mode='EDIT')
    arm = obj.data
    first = arm.edit_bones.new('Bone')
    first.head = (0.0, 0.0, 0.0)
    first.tail = (0.0, 1.0, 0.0)
    second = arm.edit_bones.new('Bone.001')
    second.head = first.tail
    second.tail = (0.0, 2.0, 0.0)
    second.parent = first
    second.use_connect = True
    bpy.ops.object.mode_set(mode='OBJECT')
    obj.pose.bones['Bone'].rigify_type = 'game_ready.chain_bendy'
