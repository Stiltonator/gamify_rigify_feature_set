"""GameReady staged port of Rigify's experimental.super_chain rig."""

import bpy
import warnings
from bpy.props import BoolProperty, EnumProperty, IntProperty, StringProperty, FloatProperty
from mathutils import Vector

from rigify.base_rig import BaseRig, stage
from rigify.utils import (
    align_bone_x_axis,
    align_bone_y_axis,
    align_bone_z_axis,
    connected_children_names,
    create_chain_widget,
    make_deformer_name,
    make_mechanism_name,
    org,
    put_bone,
    strip_org,
)
from rigify.utils.layers import ControlLayersOption
from rigify.rigs.limbs.limb_utils import get_bone_name

from .def_parent import DefParentMixin


class Rig(DefParentMixin, BaseRig):
    """A staged Rigify chain with endpoint controls and an optional pivot."""

    parent_override_param = 'gr_schain_override_parent'
    parent_name_param = 'gr_schain_parent'
    allow_root_def_parent = True

    def find_org_bones(self, bone):
        """Return the connected ORG chain beginning at the rig bone."""
        return [bone.name] + connected_children_names(self.obj, bone.name)

    def initialize(self):
        super().initialize()

        self.org_bones = list(self.bones.org)
        self.spine_length = sum(self.get_bone(name).length for name in self.org_bones)
        self.bbone_segments = self.params.gr_sc_bbone_segments
        self.single_bone = len(self.org_bones) == 1

        org_start = self.obj.data.bones[self.org_bones[0]]
        self.source_parent = org_start.parent.name if org_start.parent else None

    def get_bone_parent(self, bone_name):
        if bone_name == self.org_bones[0] and hasattr(self, '_gr_parent_source_override'):
            return self._gr_parent_source_override
        return super().get_bone_parent(bone_name)

    def parent_bones(self):
        """Prepare fallbacks, then use the shared DefParentMixin resolver."""
        root = self.generator.root_bone
        edit_bones = self.obj.data.edit_bones

        if self.gr_override_parent:
            requested = self.gr_parent_name.strip()
            if not requested:
                warnings.warn(
                    "Chain Parent field is empty. The first DEF bone will use the rig root. "
                    "Enter 'NONE' to suppress this warning.",
                    RuntimeWarning,
                    stacklevel=2,
                )
                self.gr_parent_name = root
            elif requested.casefold() != self.none_parent_token.casefold() and requested not in edit_bones:
                warnings.warn(
                    f"Parent '{requested}' not found. The first DEF bone will use the rig root.",
                    RuntimeWarning,
                    stacklevel=2,
                )
                self.gr_parent_name = root
        else:
            source = self.source_parent
            if source and source != root:
                # DEF bones are created during generate_bones, after this
                # parent_bones stage begins. Resolve from the metarig parent
                # name without checking for the DEF bone in edit_bones here.
                self._gr_parent_source_override = (
                    source if source.startswith('DEF-')
                    else make_deformer_name(strip_org(source))
                )
            else:
                # A metarig chain with no parent attaches to the generated root.
                self._gr_parent_source_override = root

        return super().parent_bones()

    @stage.parent_bones
    def parent_deform_chain(self):
        deform = self.bones.deform
        if not deform:
            return

        self.set_bone_parent(deform[0], self.gr_def_parent, use_connect=False)
        if len(deform) > 1:
            self.parent_bone_chain(
                deform,
                use_connect=self.params.gr_sc_connect_deformers,
            )

        if self.gr_def_parent is None:
            self.generator.disable_auto_parent(deform[0])

    def finalize(self):
        # DefParentMixin enforces one B-Bone segment, while this rig exposes its
        # own segment count. Preserve the common no-Stretch-To validation here.
        finalize = getattr(super(DefParentMixin, self), 'finalize', None)
        if finalize:
            finalize()
        for name in self.bones.deform:
            if any(con.type == 'STRETCH_TO' for con in self.obj.pose.bones[name].constraints):
                self.raise_error("DEF bone '{}' must not have a Stretch-To constraint.", name)

    def orient_bone(self, edit_bone, axis, scale, reverse=False):
        vector = Vector((0.0, 0.0, 0.0))
        setattr(vector, axis, scale)
        tail_vector = vector @ self.obj.matrix_world

        if reverse:
            edit_bone.head[:] = edit_bone.tail
            edit_bone.tail[:] = edit_bone.head + tail_vector
        else:
            edit_bone.tail[:] = edit_bone.head + tail_vector

    def orient_to_tweak_axis(self, bone_name, chain_vector, side_vector):
        if self.params.gr_sc_tweak_axis == 'auto':
            align_bone_y_axis(self.obj, bone_name, chain_vector)
            align_bone_z_axis(self.obj, bone_name, -side_vector)
        elif self.params.gr_sc_tweak_axis == 'x':
            align_bone_y_axis(self.obj, bone_name, Vector((1, 0, 0)))
            align_bone_x_axis(self.obj, bone_name, Vector((0, 0, 1)))
        elif self.params.gr_sc_tweak_axis == 'y':
            align_bone_y_axis(self.obj, bone_name, Vector((0, 1, 0)))
            align_bone_x_axis(self.obj, bone_name, Vector((1, 0, 0)))
        elif self.params.gr_sc_tweak_axis == 'z':
            align_bone_y_axis(self.obj, bone_name, Vector((0, 0, 1)))
            align_bone_x_axis(self.obj, bone_name, Vector((1, 0, 0)))

    def chain_orientation_vectors(self):
        edit_bones = self.obj.data.edit_bones
        chain_vector = edit_bones[self.org_bones[-1]].tail - edit_bones[self.org_bones[0]].head
        chain_vector.normalize()

        first_bone = edit_bones[self.org_bones[0]]
        projected = first_bone.y_axis.dot(chain_vector) * chain_vector
        side_vector = first_bone.y_axis - projected
        if side_vector.magnitude < first_bone.y_axis.magnitude * 1.0e-3:
            side_vector = first_bone.x_axis.copy()

        return chain_vector, side_vector

    @stage.generate_bones
    def generate_deform_bones(self):
        # Match the native rig's generation order: detach the ORG chain before
        # copying it, so controls/mechanisms do not inherit connected parenting.
        edit_bones = self.obj.data.edit_bones
        for org_name in self.org_bones:
            edit_bones[org_name].use_connect = False
            edit_bones[org_name].parent = None

        deform = []
        for org_name in self.org_bones:
            name = make_deformer_name(strip_org(org_name))
            deform.append(self.copy_bone(org_name, name))
        self.bones.deform = deform

        conv_def = ''
        # if self.params.gr_sc_conv_bone and self.params.gr_sc_conv_def:
        #     conv_org = org(self.params.gr_sc_conv_bone)
        #     conv_def = copy_bone(
        #         self.obj,
        #         conv_org,
        #         make_deformer_name(strip_org(conv_org)),
        #     )
        # self.bones.conv_def = conv_def

    @stage.generate_bones
    def generate_pivot_bone(self):
        if len(self.org_bones) <= 2:
            self.bones.ctrl.pivot = ''
            return

        edit_bones = self.obj.data.edit_bones
        pivot_index = int(len(self.org_bones) / 2)
        pivot_org = self.org_bones[pivot_index]
        base_name = strip_org(pivot_org).split('.')[0]
        if '.L' in pivot_org:
            prefix = base_name + '.L'
        elif '.R' in pivot_org:
            prefix = base_name + '.R'
        else:
            prefix = base_name

        pivot = self.copy_bone(
            pivot_org,
            get_bone_name(prefix, 'ctrl', 'pivot'),
        )
        self.orient_bone(edit_bones[pivot], 'y', self.spine_length / 2.5)

        pivot_location = edit_bones[pivot_org].head + (
            (edit_bones[pivot_org].tail - edit_bones[pivot_org].head) / 2
        ) * (len(self.org_bones) % 2)
        put_bone(self.obj, pivot, pivot_location)

        chain_vector, side_vector = self.chain_orientation_vectors()
        self.orient_to_tweak_axis(pivot, chain_vector, side_vector)
        self.bones.ctrl.pivot = pivot

    @stage.generate_bones
    def generate_chain_bones(self):
        edit_bones = self.obj.data.edit_bones
        tweaks = []
        mechanisms = []
        mechanism_controls = []
        controls = []
        suffix = '.L' if '.L' in self.org_bones[0] else ('.R' if '.R' in self.org_bones[0] else '')

        auto_mechanism = ''
        if not self.single_bone:
            auto_mechanism = self.copy_bone(
                org(self.org_bones[0]),
                'MCH-AUTO-' + strip_org(self.org_bones[0]).split('.')[0] + suffix,
            )
            edit_bones[auto_mechanism].head = edit_bones[self.org_bones[0]].head
            edit_bones[auto_mechanism].tail = edit_bones[self.org_bones[-1]].tail

        for org_name in self.org_bones:
            if self.single_bone:
                mechanism = self.copy_bone(org(org_name), make_mechanism_name(strip_org(org_name)))
                edit_bones[mechanism].length /= 4
                put_bone(self.obj, mechanism, edit_bones[org_name].head - (edit_bones[mechanism].tail - edit_bones[mechanism].head))
                align_bone_z_axis(self.obj, mechanism, edit_bones[org_name].z_axis)
                mechanisms.append(mechanism)

                mechanism = self.copy_bone(org(org_name), make_mechanism_name(strip_org(org_name)))
                edit_bones[mechanism].length /= 4
                put_bone(self.obj, mechanism, edit_bones[org_name].tail)
                mechanisms.append(mechanism)
                break

            mechanism = self.copy_bone(org(org_name), make_mechanism_name(strip_org(org_name)))
            edit_bones[mechanism].length /= 4
            mechanisms.append(mechanism)

            if org_name == self.org_bones[-1]:
                mechanism = self.copy_bone(org(org_name), make_mechanism_name(strip_org(org_name)))
                edit_bones[mechanism].length /= 4
                put_bone(self.obj, mechanism, edit_bones[org_name].tail)
                mechanisms.append(mechanism)

        chain_vector, side_vector = self.chain_orientation_vectors()
        for org_name in self.org_bones:
            side = '.L' if '.L' in org_name else ('.R' if '.R' in org_name else '')
            if org_name == self.org_bones[0]:
                control = self.copy_bone(
                    org(org_name),
                    get_bone_name(org_name.split('.')[0] + side, 'ctrl', 'ctrl'),
                )
                align_bone_x_axis(self.obj, control, edit_bones[org(org_name)].x_axis)
                controls.append(control)
            else:
                tweak = self.copy_bone(org(org_name), 'tweak_' + strip_org(org_name))
                tweaks.append(tweak)

            shape_name = controls[-1] if org_name == self.org_bones[0] else tweaks[-1]
            self.orient_bone(edit_bones[shape_name], 'y', edit_bones[shape_name].length / 2)
            self.orient_to_tweak_axis(shape_name, chain_vector, side_vector)

            if org_name == self.org_bones[-1]:
                end_control = self.copy_bone(
                    org(org_name),
                    get_bone_name(org_name.split('.')[0] + side, 'ctrl', 'ctrl'),
                )
                self.orient_bone(edit_bones[end_control], 'y', edit_bones[end_control].length / 2)

                # if self.params.gr_sc_conv_bone:
                #     conv_org = org(self.params.gr_sc_conv_bone)
                #     align_bone_y_axis(self.obj, end_control, edit_bones[conv_org].y_axis)
                #     align_bone_x_axis(self.obj, end_control, edit_bones[conv_org].x_axis)
                #     align_bone_z_axis(self.obj, end_control, edit_bones[conv_org].z_axis)
                # else:
                last_control = tweaks[-1] if tweaks else controls[-1]
                align_bone_y_axis(self.obj, end_control, edit_bones[last_control].y_axis)
                align_bone_x_axis(self.obj, end_control, edit_bones[last_control].x_axis)

                put_bone(self.obj, end_control, edit_bones[org_name].tail)
                controls.append(end_control)

        conv_tweak = ''
        # if self.params.gr_sc_conv_bone:
        #     conv_org = org(self.params.gr_sc_conv_bone)
        #     conv_tweak = 'tweak_' + strip_org(conv_org)
        #     if conv_tweak not in edit_bones:
        #         conv_tweak = self.copy_bone(conv_org, conv_tweak)

        if not self.single_bone:
            for org_name in self.org_bones:
                side = '.L' if '.L' in org_name else ('.R' if '.R' in org_name else '')
                mechanism_control = self.copy_bone(
                    tweaks[0] if tweaks else controls[0],
                    'MCH-CTRL-' + strip_org(org_name).split('.')[0] + side,
                )
                edit_bones[mechanism_control].length /= 6
                put_bone(self.obj, mechanism_control, edit_bones[org_name].head)
                mechanism_controls.append(mechanism_control)

                if org_name == self.org_bones[-1]:
                    mechanism_control = self.copy_bone(
                        tweaks[0] if tweaks else controls[0],
                        'MCH-CTRL-' + strip_org(org_name).split('.')[0] + side,
                    )
                    edit_bones[mechanism_control].length /= 6
                    put_bone(self.obj, mechanism_control, edit_bones[org_name].tail)
                    mechanism_controls.append(mechanism_control)

        self.bones.mch.chain = mechanisms
        self.bones.mch.controls = mechanism_controls
        self.bones.mch.auto = auto_mechanism
        self.bones.ctrl.chain = controls
        self.bones.ctrl.tweak = tweaks
        self.bones.ctrl.convergence = conv_tweak

    @stage.parent_bones
    def parent_super_chain(self):
        edit_bones = self.obj.data.edit_bones
        deform = self.bones.deform
        mechanisms = self.bones.mch.chain
        mechanism_controls = self.bones.mch.controls
        controls = self.bones.ctrl.chain
        tweaks = self.bones.ctrl.tweak
        auto_mechanism = self.bones.mch.auto

        # The native rig uses its ORG chain only as constraint sources.
        for org_name in self.org_bones:
            edit_bones[org_name].use_connect = False
            edit_bones[org_name].parent = None

        for index, tweak in enumerate(tweaks):
            edit_bones[tweak].parent = edit_bones[mechanism_controls[index + 1]]
            edit_bones[tweak].use_connect = False
            edit_bones[tweak].inherit_scale = 'NONE'

        edit_bones[controls[0]].parent = edit_bones[mechanism_controls[0]] if mechanism_controls else None
        edit_bones[controls[0]].use_connect = False
        edit_bones[controls[0]].inherit_scale = 'NONE'
        edit_bones[controls[-1]].parent = edit_bones[mechanism_controls[-1]] if mechanism_controls else None
        edit_bones[controls[-1]].use_connect = False
        edit_bones[controls[-1]].inherit_scale = 'NONE'

        if self.bones.ctrl.pivot:
            edit_bones[self.bones.ctrl.pivot].use_connect = False
            edit_bones[self.bones.ctrl.pivot].inherit_scale = 'NONE'

        for index, mechanism in enumerate(mechanisms):
            if mechanism == mechanisms[0]:
                edit_bones[mechanism].parent = edit_bones[controls[0]]
            elif mechanism == mechanisms[-1]:
                edit_bones[mechanism].parent = edit_bones[controls[-1]]
            else:
                edit_bones[mechanism].parent = edit_bones[tweaks[index - 1]]

        if self.source_parent:
            parent_name = self.source_parent
            # if self.params.gr_sc_def_parenting:
            #     preferred_def = make_deformer_name(strip_org(parent_name))
            #     if preferred_def in edit_bones:
            #         parent_name = preferred_def

            if self.single_bone:
                edit_bones[controls[0]].parent = edit_bones[parent_name]
                edit_bones[controls[-1]].parent = edit_bones[parent_name]
            else:
                edit_bones[auto_mechanism].parent = edit_bones[parent_name]
                edit_bones[mechanism_controls[0]].parent = edit_bones[parent_name]
                edit_bones[mechanism_controls[-1]].parent = edit_bones[parent_name]

        if mechanism_controls and auto_mechanism:
            for mechanism_control in mechanism_controls[1:-1]:
                edit_bones[mechanism_control].parent = edit_bones[auto_mechanism]

        if self.bones.ctrl.pivot:
            edit_bones[self.bones.ctrl.pivot].parent = edit_bones[auto_mechanism]

        conv_tweak = self.bones.ctrl.convergence
        if conv_tweak:
            edit_bones[controls[-1]].parent = edit_bones[conv_tweak]

        if self.single_bone:
            edit_bones[mechanisms[0]].parent = edit_bones[controls[0]]
            edit_bones[mechanisms[1]].parent = edit_bones[controls[-1]]

    @stage.configure_bones
    def configure_deform_bones(self):
        deform = self.bones.deform
        for name in deform:
            self.obj.data.bones[name].bbone_segments = self.bbone_segments

        if len(deform) > 1:
            self.obj.data.bones[deform[0]].bbone_easein = 0.0
            self.obj.data.bones[deform[-1]].bbone_easeout = 0.0
        else:
            self.obj.data.bones[deform[0]].bbone_easein = 1.0
            self.obj.data.bones[deform[-1]].bbone_easeout = 1.0

    @stage.configure_bones
    def configure_bendy_handles(self):
        deform = self.bones.deform
        if len(deform) > 1:
            return

        def_bone = self.obj.data.bones[deform[0]]
        controls = self.bones.ctrl.chain
        mechanisms = self.bones.mch.chain
        mechanism_controls = self.bones.mch.controls

        if not self.single_bone:
            start_handle = self.obj.data.bones[controls[0]]
            end_handle = self.obj.data.bones[controls[-1]]
        else:
            start_handle = self.obj.data.bones[mechanisms[0]]
            end_handle_name = mechanism_controls[-1] if mechanism_controls else mechanisms[-1]
            end_handle = self.obj.data.bones[end_handle_name]

        def_bone.bbone_custom_handle_start = start_handle
        def_bone.bbone_custom_handle_end = end_handle
        def_bone.bbone_handle_type_start = 'ABSOLUTE'
        def_bone.bbone_handle_type_end = 'ABSOLUTE'

    @stage.configure_bones
    def configure_control_locks(self):
        pose_bones = self.obj.pose.bones
        for name in self.bones.mch.controls:
            pose_bones[name].lock_rotation = (False, False, False)
            pose_bones[name].lock_location = (False, False, False)
            pose_bones[name].lock_scale = (False, False, False)

        for name in self.bones.ctrl.tweak + self.bones.ctrl.chain:
            pose_bones[name].lock_rotation = (True, False, True)

        if self.bones.ctrl.pivot:
            pose_bones[self.bones.ctrl.pivot].lock_rotation = (True, False, True)

    @stage.rig_bones
    def rig_super_chain(self):
        deform = self.bones.deform
        mechanisms = self.bones.mch.chain
        mechanism_controls = self.bones.mch.controls
        controls = self.bones.ctrl.chain
        tweaks = [controls[0]] + self.bones.ctrl.tweak + [controls[-1]]
        pivot = self.bones.ctrl.pivot
        #conv_def = self.bones.conv_def
        #conv_tweak = self.bones.ctrl.convergence

        for index, org_name in enumerate(self.org_bones):
            self.make_constraint(
                org_name, 'COPY_TRANSFORMS', tweaks[index],
                space='WORLD',
            )

        for index, deform_name in enumerate(deform):
            if len(deform) > 1:
                self.make_constraint(
                    deform_name, 'COPY_TRANSFORMS', mechanisms[index],
                    space='POSE',
                )
            self.make_constraint(deform_name, 'DAMPED_TRACK', tweaks[index + 1])

        # if conv_def:
        #     self.make_constraint(
        #         conv_def, 'COPY_TRANSFORMS', conv_tweak,
        #         space='POSE',
        #     )

        if pivot:
            step = 2.0 / len(self.org_bones)
            for index, mechanism_control in enumerate(mechanism_controls):
                x_value = index * step
                influence = 2.0 * x_value - x_value ** 2
                if index not in (0, len(mechanism_controls) - 1):
                    self.make_constraint(
                        mechanism_control, 'COPY_TRANSFORMS', pivot,
                        influence=influence,
                        space='LOCAL',
                    )

        auto_mechanism = self.bones.mch.auto
        if auto_mechanism:
            self.make_constraint(
                auto_mechanism, 'COPY_LOCATION', mechanisms[0],
                space='WORLD',
            )
            self.make_constraint(auto_mechanism, 'STRETCH_TO', tweaks[-1])

        if pivot:
            self.make_constraint(
                pivot, 'COPY_ROTATION', tweaks[0], influence=0.33,
                space='LOCAL',
            )
            self.make_constraint(
                pivot, 'COPY_ROTATION', tweaks[-1], influence=0.33,
                space='LOCAL',
            )

    @stage.generate_widgets
    def generate_super_chain_widgets(self):
        controls = self.bones.ctrl.chain
        tweaks = self.bones.ctrl.tweak
        pivot = self.bones.ctrl.pivot
        #conv_tweak = self.bones.ctrl.convergence
        pose_bones = self.obj.pose.bones
        axis = self.params.gr_sc_widget_axis
        offset = float(self.params.gr_schain_widget_offset) * pose_bones[controls[0]].length

        if pivot:
            create_chain_widget(
                self.obj, pivot, cube=True, radius=0.15,
                bone_transform_name=None, axis=axis, offset=offset,
            )

        for tweak in tweaks:
            create_chain_widget(
                self.obj, tweak, cube=True, radius=0.2,
                bone_transform_name=None, axis=axis, offset=offset,
            )

        create_chain_widget(
            self.obj, controls[0], invert=False, radius=0.3,
            bone_transform_name=None, axis=axis, offset=offset,
        )

        invert_last = axis in {'y', '-y'}
        create_chain_widget(
            self.obj, controls[-1], invert=invert_last, radius=0.3,
            bone_transform_name=None, axis=axis, offset=offset,
        )

        # if conv_tweak:
        #     create_chain_widget(
        #         self.obj, conv_tweak, cube=True, radius=0.5,
        #         bone_transform_name=None, axis=axis, offset=offset,
        #     )

        ControlLayersOption.TWEAK.assign(
            self.params, pose_bones, tweaks,
        )

    @classmethod
    def add_parameters(cls, params):
        params.gr_sc_tweak_axis = EnumProperty(
            name='Orient Y-axis to',
            description='Target control Y-axes to the selected global axis',
            items=[
                ('auto', 'Auto', ''),
                ('x', 'X-Global', ''),
                ('y', 'Y-Global', ''),
                ('z', 'Z-Global', ''),
            ],
            default='auto',
        )
        params.gr_sc_widget_axis = EnumProperty(
            name='Custom Widget Orient',
            description='Orient custom widgets to the selected global axis',
            items=[
                ('x', 'X', ''), ('y', 'Y', ''), ('z', 'Z', ''),
                ('-x', '-X', ''), ('-y', '-Y', ''), ('-z', '-Z', ''),
            ],
            default='y',
        )
        # params.gr_sc_conv_bone = StringProperty(name='Convergence Bone', default='')
        # params.gr_sc_conv_def = BoolProperty(
        #     name='Add DEF on Convergence', default=False,
        # )
        # params.gr_sc_def_parenting = BoolProperty(
        #     name='Prefer DEF Parenting', default=False,
        # )
        cls.add_parent_parameters(params, 'gr_schain')
        params.gr_sc_bbone_segments = IntProperty(
            name='B-Bone Segments', default=10, min=1,
        )
        params.gr_sc_connect_deformers = BoolProperty(
            name='Connect Deformers', default=True,
        )
        params.gr_schain_widget_offset = FloatProperty(
            name='Widget Offset', default=0.0, min=-10.0, max=10.0,
        )
        ControlLayersOption.TWEAK.add_parameters(params)

    @classmethod
    def parameters_ui(cls, layout, params):
        layout.label(text='GameReady Super Chain — staged port of experimental.super_chain')
        cls.draw_parent_parameters(layout, params, 'gr_schain')
        layout.prop(params, 'gr_sc_tweak_axis')
        layout.prop(params, 'gr_sc_widget_axis')
        layout.prop(params, 'gr_schain_widget_offset')
        layout.prop(params, 'gr_sc_bbone_segments')
        layout.prop(params, 'gr_sc_connect_deformers')

        pose = bpy.context.object.pose
        #layout.prop_search(params, 'gr_sc_conv_bone', pose, 'bones', text='Convergence Bone')
        #layout.prop(params, 'gr_sc_conv_def')
        #layout.prop(params, 'gr_sc_def_parenting')
        ControlLayersOption.TWEAK.parameters_ui(layout, params)


def create_sample(obj):
    """Create the native four-bone sample and assign the GameReady type."""
    bpy.ops.object.mode_set(mode='EDIT')
    arm = obj.data
    names = []
    points = [
        ((0.0, 0.0, 0.0), (0.0, 0.0625, 0.125)),
        ((0.0, 0.0625, 0.125), (0.0, 0.09375, 0.25)),
        ((0.0, 0.09375, 0.25), (0.0, 0.0625, 0.375)),
        ((0.0, 0.0625, 0.375), (0.0, 0.0, 0.5)),
    ]

    for index, (head, tail) in enumerate(points):
        bone = arm.edit_bones.new('spine' if index == 0 else f'spine.{index:03d}')
        bone.head = head
        bone.tail = tail
        bone.use_connect = index > 0
        if index:
            bone.parent = arm.edit_bones[names[-1]]
        names.append(bone.name)

    bpy.ops.object.mode_set(mode='OBJECT')
    for index, name in enumerate(names):
        pose_bone = obj.pose.bones[name]
        pose_bone.rigify_type = 'game_ready.super_chain' if index == 0 else ''
        pose_bone.rotation_mode = 'QUATERNION'

    bpy.ops.object.mode_set(mode='EDIT')
    for bone in arm.edit_bones:
        bone.select = False
        bone.select_head = False
        bone.select_tail = False
    for name in names:
        bone = arm.edit_bones[name]
        bone.select = True
        bone.select_head = True
        bone.select_tail = True
        arm.edit_bones.active = bone
        if arm.collections.active:
            arm.collections.active.assign(bone)


# Rigify category: game_ready
