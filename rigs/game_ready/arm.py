"""GameReady arm adapter based on Rigify's limbs.arm."""

from bpy.props import BoolProperty
from rigify.base_rig import stage
from rigify.utils.layers import ControlLayersOption
from rigify.rigs.limbs.arm import Rig as NativeArmRig

from .def_parent import DefParentMixin


class Rig(DefParentMixin, NativeArmRig):
    """Native FK/IK arm with DEF-only hierarchy and no DEF Stretch-To."""

    parent_override_param = 'gr_arm_override_parent'
    parent_name_param = 'gr_arm_parent'

    def initialize(self):
        super().initialize()
        self.bbone_segments = 1

    @stage.parent_bones
    def parent_deform_chain(self):
        super().parent_deform_chain()
        # Segment rows are grouped by source bone. New segments stay movable,
        # and the first forearm/hand DEF attaches to the first DEF of its parent
        # source bone instead of the last segment of that bone.
        entries = self.segment_table_full
        deform = self.bones.deform
        for index, (name, entry) in enumerate(zip(deform, entries)):
            if entry.seg_idx is not None and entry.seg_idx > 0 and index > 0:
                self.set_bone_parent(name, deform[index - 1], use_connect=False)

        first_by_org = {}
        for name, entry in zip(deform, entries):
            if entry.seg_idx in (None, 0):
                first_by_org.setdefault(entry.org_idx, name)
        for org_idx in range(1, len(self.bones.org.main)):
            child = first_by_org.get(org_idx)
            parent = first_by_org.get(org_idx - 1)
            if child and parent:
                self.set_bone_parent(child, parent, use_connect=False)

        if self.gr_def_parent is None:
            self.generator.disable_auto_parent(deform[0])

    def rig_deform_bone(self, i, deform, entry, next_entry, tweak, next_tweak):
        self.make_constraint(deform, 'COPY_LOCATION', tweak or entry.org)
        self.make_constraint(deform, 'COPY_ROTATION', tweak or entry.org)
        target = next_tweak or (next_entry.org if next_entry else None)
        if target:
            self.make_constraint(deform, 'DAMPED_TRACK', target, track_axis='TRACK_Y')

    @classmethod
    def add_parameters(cls, params):
        super().add_parameters(params)
        cls.add_parent_parameters(params, 'gr_arm')

    @classmethod
    def parameters_ui(cls, layout, params):
        layout.label(text='GameReady Arm — based on limbs.arm')
        layout.prop(params, 'make_ik_wrist_pivot')
        layout.prop(params, 'rotation_axis')
        if 'auto' not in params.rotation_axis.lower():
            layout.prop(params, 'auto_align_extremity', text='Auto Align Hand')
        layout.prop(params, 'segments')
        layout.prop(params, 'limb_uniform_scale')
        layout.prop(params, 'make_custom_pivot', text='Custom IK Pivot')
        layout.prop(params, 'ik_local_location')
        ControlLayersOption.FK.parameters_ui(layout, params)
        ControlLayersOption.TWEAK.parameters_ui(layout, params)
        cls.draw_parent_parameters(layout, params, 'gr_arm')
