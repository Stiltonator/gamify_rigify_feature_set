"""GameReady finger adapter based on Rigify's limbs.super_finger."""

from rigify.base_rig import stage
from rigify.utils.layers import ControlLayersOption
from rigify.rigs.limbs.super_finger import Rig as NativeSuperFingerRig

from .def_parent import DefParentMixin


class Rig(DefParentMixin, NativeSuperFingerRig):
    """Native FK finger, optional IK, matching tools, with a clean DEF chain."""

    parent_override_param = 'gr_finger_override_parent'
    parent_name_param = 'gr_finger_parent'

    def initialize(self):
        super().initialize()
        # Keep generated DEF bones rigid and remove the native curvature option.
        self.bbone_segments = 1

    @stage.parent_bones
    def parent_master_control(self):
        # The native master control is copied from the ORG start bone. Reparent
        # it to the resolved DEF attachment so the FK chain follows that bone.
        self.set_bone_parent(self.bones.ctrl.master, self.rig_parent_bone, use_connect=False)

    def rig_deform_bone(self, i, deform, org):
        # Follow position and rotation without copying source scale. Stretch-To
        # constraints remain confined to the MCH driver chain for IK.
        self.make_constraint(deform, 'COPY_LOCATION', org)
        self.make_constraint(deform, 'COPY_ROTATION', org)

    @classmethod
    def add_parameters(cls, params):
        super().add_parameters(params)
        cls.add_parent_parameters(params, 'gr_finger')

    @classmethod
    def parameters_ui(cls, layout, params):
        row = layout.row()
        row.label(text='Bend rotation axis:')
        row.prop(params, 'primary_rotation_axis', text='')
        layout.prop(params, 'make_extra_ik_control', text='IK Control')
        if params.make_extra_ik_control:
            layout.prop(params, 'ik_local_location')
        ControlLayersOption.TWEAK.parameters_ui(layout, params)
        if params.make_extra_ik_control:
            ControlLayersOption.EXTRA_IK.parameters_ui(layout, params)
        cls.draw_parent_parameters(layout, params, 'gr_finger')
