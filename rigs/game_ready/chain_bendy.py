"""GameReady B-Bone chain with tangent controls and sampled deform bones.

The B-Bones are mechanism drivers (MCH-BBone-*). Skinning DEF bones are
created at the chain joints and at evenly spaced samples inside each B-Bone.
"""

from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, StringProperty

from rigify.base_rig import BaseRig, stage
from rigify.utils import (
    align_bone_x_axis,
    align_bone_y_axis,
    connected_children_names,
    make_deformer_name,
    make_mechanism_name,
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

    @staticmethod
    def _label(name):
        return strip_org(name)

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
        edit_bones = self.obj.data.edit_bones
        bbone_drivers = []
        tangent_bones = []
        controls = []

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

            control = self.copy_bone(
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
            self._place_bone(control, point, direction, point_length, roll_axis)
            self._place_bone(tangent, point, direction, point_length, roll_axis)
            controls.append(control)
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
        for sample_index, spec in enumerate(sample_specs):
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
            tweak_name = self.copy_bone(int_name, tweak_name)
            self._place_bone(
                tweak_name,
                point,
                direction,
                self._bone_length(source_name) * 0.2,
                roll_axis,
            )
            def_name = deform_name_base + '.' + str(sample_index).zfill(3)
            def_name = self.copy_bone(int_name, def_name)
            self._place_bone(
                def_name,
                point,
                direction,
                self._bone_length(source_name) * 0.12,
                roll_axis,
            )
            edit_bones[def_name].use_deform = True
            sample_names.append(int_name)
            tweak_names.append(tweak_name)
            deform_names.append(def_name)

        self.bones.ctrl.joints = controls
        self.bones.mch.tangents = tangent_bones
        self.bones.mch.bbone_drivers = bbone_drivers
        self.bones.mch.intermediary = sample_names
        self.bones.mch.armature_pivot = pivot
        self.bones.ctrl.tweaks = tweak_names
        self.bones.deform = deform_names

        # Map each intermediary to its nearest B-Bone driver(s). A joint is
        # intentionally shared 50/50 by the two adjacent drivers.
        targets = []
        for spec in sample_specs:
            _, segment_index, t, kind = spec
            if kind == 'joint' and segment_index + 1 < len(bbone_drivers):
                targets.append(((bbone_drivers[segment_index], 0.5),
                                (bbone_drivers[segment_index + 1], 0.5)))
            else:
                targets.append(((bbone_drivers[segment_index], 1.0),))
        self._intermediary_targets = targets
        self._intermediary_curve_targets = [
            (bbone_drivers[segment_index], t)
            for _, segment_index, t, _ in sample_specs
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
            self.set_bone_parent(control, parent, use_connect=False)
            self.get_bone(control).inherit_scale = 'NONE'

        for tweak, intermediary in zip(
            self.bones.ctrl.tweaks, self.bones.mch.intermediary
        ):
            self.set_bone_parent(tweak, intermediary, use_connect=False)

        for tangent, control in zip(self.bones.mch.tangents, self.bones.ctrl.joints):
            self.set_bone_parent(tangent, control, use_connect=False)

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
        main_widget_scale = self.control_shape_size / 0.5
        for control in self.bones.ctrl.joints:
            control_pose = pose_bones[control]
            control_pose.use_custom_shape_bone_size = False
            control_pose.custom_shape_scale_xyz = (main_widget_scale,) * 3

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

        for tangent, control in zip(self.bones.mch.tangents, self.bones.ctrl.joints):
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
            self.create_selected_widget(control, self.main_widget_type)

        for tweak in self.bones.ctrl.tweaks:
            self.create_selected_widget(tweak, self.tweak_widget_type)

    @classmethod
    def add_parameters(cls, params):
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
        row = layout.row(align=True)
        row.prop(params, 'gr_chain_bendy_override_parent')
        if params.gr_chain_bendy_override_parent:
            row.prop(params, 'gr_chain_bendy_parent', text='')


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
