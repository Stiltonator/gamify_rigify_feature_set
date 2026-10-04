"""Blender 5.0.1 Rigify leg, with a DEF-only leg hierarchy and shared chain parent.

The native rig supplies the mechanics, widgets, animation UI and snap operators.
This adapter customizes parenting, rotation following and rigid DEF segments.
"""

from bpy.props import BoolProperty, StringProperty
from rigify.base_rig import stage
from rigify.rigs.limbs.leg import Rig as NativeLegRig, create_sample as native_create_sample
from rigify.utils.layers import ControlLayersOption

from .def_parent import DefParentMixin


class Rig(DefParentMixin, NativeLegRig):
    """Full-featured GameReady leg with toes, built on Rigify's limbs.leg."""

    parent_override_param = 'gr_toes_override_parent'
    parent_name_param = 'gr_toes_parent'

    def build_ik_parent_switch(self, pbuilder):
        # The established hierarchy fixes these controls under root, so do not
        # build native switch-parent MCH bones/constraints or misleading selectors.
        pass

    @stage.parent_bones
    def parent_ik_controls(self):
        super().parent_ik_controls()
        self.set_bone_parent(self.bones.ctrl.ik, self.generator.root_bone)
        self.set_bone_parent(self.bones.ctrl.ik_pole, self.generator.root_bone)

    @stage.parent_bones
    def parent_mch_follow_bone(self):
        super().parent_mch_follow_bone()
        self.get_bone(self.bones.mch.follow).use_inherit_rotation = True

    @stage.configure_bones
    def configure_mch_follow_bone(self):
        # Always follow the chosen chain parent. Omit the native rotation
        # isolation slider, which could otherwise override this requirement.
        pass

    ### Added this to make leg pole target visible on generation
    @stage.configure_bones
    def configure_ik_mch_panel(self):
        super().configure_ik_mch_panel()
        self.obj.pose.bones[self.prop_bone]['pole_vector'] = True


    @stage.rig_bones
    def rig_mch_follow_bone(self):
        # Retain native scale handling, without its root COPY_ROTATION override.
        follow = self.bones.mch.follow
        self.make_constraint(follow, 'COPY_SCALE', self.generator.root_bone, use_make_uniform=True)
        if self.use_uniform_scale:
            self.make_constraint(follow, 'COPY_SCALE', self.bones.ctrl.master,
                                 use_make_uniform=True, use_offset=True, space='LOCAL')

    @stage.parent_bones
    def parent_org_chain(self):
        super().parent_org_chain()
        self.set_bone_parent(self.bones.org.main[0], self.rig_parent_bone)
        self.get_bone(self.bones.org.main[0]).use_inherit_rotation = True

    @stage.parent_bones
    def parent_deform_chain(self):
        # First let DefParentMixin resolve the start parent and establish the
        # standard DEF chain. Then restore this leg type's special hierarchy.
        super().parent_deform_chain()

        # Extra thigh/shin segments are unconnected; their parent bones are
        # reassigned to the matching start DEF bones just below.
        for name, entry in zip(self.bones.deform, self.segment_table_full):
            if entry.org_idx in (0, 1) and entry.seg_idx is not None and entry.seg_idx > 0:
                self.get_bone(name).use_connect = False
        # Segment-table metadata identifies the shin without relying on names
        # or Blender's suffix allocation. Do not connect: the knee must retain
        # its rest position even though the first thigh segment ends above it.
        self.gr_first_thigh_def = self.bones.deform[0]
        self.gr_first_shin_def = next(
            name for name, entry in zip(self.bones.deform, self.segment_table_full)
            if entry.org_idx == 1 and entry.seg_idx == 0
        )
        self.set_bone_parent(self.gr_first_shin_def, self.gr_first_thigh_def, use_connect=False)

        # Parent every additional thigh segment to the first thigh DEF, and
        # every additional shin segment to the first shin DEF. The foot and
        # toe DEF hierarchy below remains native apart from the existing foot
        # attachment to the first shin.
        for name, entry in zip(self.bones.deform, self.segment_table_full):
            if entry.seg_idx is None or entry.seg_idx == 0:
                continue
            if entry.org_idx == 0:
                self.set_bone_parent(name, self.gr_first_thigh_def, use_connect=False)
            elif entry.org_idx == 1:
                self.set_bone_parent(name, self.gr_first_shin_def, use_connect=False)

        self.gr_foot_def = next(
            name for name, entry in zip(self.bones.deform, self.segment_table_full)
            if entry.org_idx == 2
        )
        # The first shin segment may end above the ankle. Keep the foot's
        # rest position rather than snapping it to that segment's tail.
        self.set_bone_parent(self.gr_foot_def, self.gr_first_shin_def, use_connect=False)
        for name in self.bones.deform:
            self.get_bone(name).use_inherit_rotation = True

    def make_deform_bone(self, i, entry):
        name = super().make_deform_bone(i, entry)
        self.get_bone(name).bbone_segments = 1
        return name

    def rig_deform_bone(self, i, deform, entry, next_entry, tweak, next_tweak):
        # Preserve the native pose source and constraint order. Replace each
        # native Stretch-To with rotation-only tracking of the same target.
        self.make_constraint(deform, 'COPY_TRANSFORMS', tweak or entry.org)
        if tweak:
            target = next_tweak or (next_entry.org if next_entry else None)
            if target:
                self.make_constraint(deform, 'DAMPED_TRACK', target, track_axis='TRACK_Y')

    def finalize(self):
        super().finalize()
        first_deform_name = self.bones.deform[0]
        for name in self.bones.deform:
            bone = self.obj.data.bones[name]
            if bone.bbone_segments != 1:
                self.raise_error("DEF bone '{}' must have one B-Bone segment.", name)
            if any(con.type == 'STRETCH_TO' for con in self.obj.pose.bones[name].constraints):
                self.raise_error("DEF bone '{}' must not have a Stretch-To constraint.", name)
            is_override_start = self.gr_override_parent and name == first_deform_name
            if bone.parent and not is_override_start and (
                not bone.parent.name.startswith('DEF-') or not bone.parent.use_deform
            ):
                self.raise_error("DEF hierarchy violation: '{}' has non-DEF parent '{}'.", name, bone.parent.name)
        first = self.obj.data.bones[first_deform_name]
        actual_parent = first.parent.name if first.parent else None
        if actual_parent != self.gr_def_parent:
            self.raise_error("The generated DEF chain parent changed unexpectedly: '{}'.", actual_parent)
        shin = self.obj.data.bones[self.gr_first_shin_def]
        if shin.parent != first or shin.use_connect:
            self.raise_error("The first DEF shin must parent to the first DEF thigh without connecting.")
        for name, entry in zip(self.bones.deform, self.segment_table_full):
            if entry.seg_idx is None or entry.seg_idx == 0:
                continue
            bone = self.obj.data.bones[name]
            if entry.org_idx == 0 and (bone.parent != first or bone.use_connect):
                self.raise_error("Additional thigh DEF '{}' must parent to the first DEF thigh without connecting.", name)
            if entry.org_idx == 1 and (bone.parent != shin or bone.use_connect):
                self.raise_error("Additional shin DEF '{}' must parent to the first DEF shin without connecting.", name)
        foot = self.obj.data.bones[self.gr_foot_def]
        if foot.parent != shin or foot.use_connect:
            self.raise_error("The DEF foot must parent to the first DEF shin without connecting.")
        for name in (self.bones.ctrl.ik, self.bones.ctrl.ik_pole):
            parent = self.obj.data.bones[name].parent
            if parent is None or parent.name != self.generator.root_bone:
                self.raise_error("IK control '{}' must be parented to the rig root.", name)

    @classmethod
    def add_parameters(cls, params):
        super().add_parameters(params)
        params.gr_toes_override_parent = BoolProperty(
            name='Override Chain Parent', default=False,
            description='Use the named existing bone for the DEF chain, FK thigh and IK chain start')
        params.gr_toes_parent = StringProperty(
            name='Start', default='',
            description='Exact target bone name (MCH.thigh_parent and DEF-thigh parented to this).')

    @classmethod
    def parameters_ui(cls, layout, params):
        layout.label(text='GameReady Leg — Toes')
        layout.label(text='Thigh / shin / foot / toe, plus heel marker')
        layout.prop(params, 'gr_toes_override_parent')
        if params.gr_toes_override_parent:
            layout.prop(params, 'gr_toes_parent')
        layout.separator()
        # Native leg options, excluding B-Bone Segments. Calling the native
        # panel here would reintroduce that field.
        layout.prop(params, 'foot_pivot_type')
        layout.prop(params, 'extra_ik_toe')
        layout.prop(params, 'extra_toe_roll')
        layout.prop(params, 'rotation_axis')
        if 'auto' not in params.rotation_axis.lower():
            layout.prop(params, 'auto_align_extremity', text='Auto Align Foot')
        layout.prop(params, 'segments')
        layout.prop(params, 'limb_uniform_scale')
        layout.prop(params, 'make_custom_pivot', text='Custom IK Pivot')
        layout.prop(params, 'ik_local_location')
        ControlLayersOption.FK.parameters_ui(layout, params)
        ControlLayersOption.TWEAK.parameters_ui(layout, params)


def create_sample(obj):
    """Use the native sample geometry, tagged for this adapter."""
    bones = native_create_sample(obj)
    thigh = obj.pose.bones[bones['thigh.L']]
    thigh.rigify_type = 'game_ready.leg_toes'
    thigh.rigify_parameters.extra_ik_toe = True
    thigh.rigify_parameters.extra_toe_roll = True
    # Sample defaults: one DEF per input chain bone, retaining all native
    # controls and snap operations. Users can increase native segmentation.
    thigh.rigify_parameters.segments = 1
    return bones
