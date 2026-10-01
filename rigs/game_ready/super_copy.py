"""GameReady super copy based on Rigify's basic.super_copy."""

from bpy.props import FloatVectorProperty, StringProperty

from rigify.base_rig import stage
from rigify.rigs.basic.super_copy import Rig as NativeSuperCopyRig
from rigify.utils.widgets import layout_widget_dropdown
from ...viewport_preview import tag_view3d_redraw


class Rig(NativeSuperCopyRig):
    """A super-copy rig with optional DEF parenting and widget transforms."""

    def initialize(self):
        super().initialize()
        self.gr_def_parent_name = self.params.gr_sc_def_parent.strip()
        self.gr_widget_offset = self.params.gr_sc_widget_offset
        self.gr_widget_scale = self.params.gr_sc_widget_scale

        if self.gr_def_parent_name and not self.make_deform:
            self.raise_error("DEF Parent can only be set when Deform is enabled.")

    @stage.parent_bones
    def parent_bones(self):
        super().parent_bones()

        if not self.make_deform:
            return

        deform = self.bones.deform
        if not self.gr_def_parent_name:
            return

        if self.gr_def_parent_name not in self.obj.data.edit_bones:
            self.raise_error("DEF Parent '{}' does not exist in the generated rig.", self.gr_def_parent_name)

        target = self.obj.data.edit_bones[self.gr_def_parent_name]
        owned = {self.bones.org, deform}
        seen = set()
        while target:
            if target.name in owned or target.name in seen:
                self.raise_error("DEF Parent cannot be this rig's own bone or one of its descendants.")
            seen.add(target.name)
            target = target.parent

        self.set_bone_parent(deform, self.gr_def_parent_name, use_connect=False)

    @stage.configure_bones
    def configure_game_ready_control(self):
        if self.make_control and self.make_widget:
            control = self.get_bone(self.bones.ctrl)
            control.custom_shape_translation = self.gr_widget_offset
            control.custom_shape_scale_xyz = self.gr_widget_scale

    @stage.rig_bones
    def rig_bones(self):
        super().rig_bones()

        if self.make_deform and self.make_control:
            self.make_constraint(
                self.bones.deform,
                'COPY_TRANSFORMS',
                self.bones.ctrl,
                name='GameReady DEF follows Control',
                space='WORLD',
            )

    @classmethod
    def add_parameters(cls, params):
        super().add_parameters(params)

        params.gr_sc_def_parent = StringProperty(
            name='DEF Parent', default='',
            description='Exact name of the generated bone that should parent the DEF bone')
        params.gr_sc_widget_offset = FloatVectorProperty(
            name='Widget Offset', size=3, default=(0.0, 0.0, 0.0), subtype='TRANSLATION',
            update=tag_view3d_redraw,
            description='Offset of the control bone custom shape')
        params.gr_sc_widget_scale = FloatVectorProperty(
            name='Widget Scale', size=3, default=(1.0, 1.0, 1.0), subtype='XYZ',
            update=tag_view3d_redraw,
            description='Scale of the control bone custom shape')

    @classmethod
    def parameters_ui(cls, layout, params):
        layout.prop(params, 'make_control')

        row = layout.split(factor=0.3)
        row.prop(params, 'make_widget')
        row.enabled = params.make_control

        widget_row = row.row(align=True)
        widget_row.enabled = params.make_widget
        layout_widget_dropdown(widget_row, params, 'super_copy_widget_type', text='')

        if params.make_control and params.make_widget:
            layout.prop(params, 'gr_sc_widget_offset')
            layout.prop(params, 'gr_sc_widget_scale')

        layout.prop(params, 'make_deform')
        if params.make_deform:
            layout.prop(params, 'gr_sc_def_parent')

        cls.add_relink_constraints_ui(layout, params)
        if params.relink_constraints and (params.make_control or params.make_deform):
            column = layout.column()
            if params.make_control:
                column.label(text="'CTRL:...' constraints are moved to the control bone.", icon='INFO')
            if params.make_deform:
                column.label(text="'DEF:...' constraints are moved to the deform bone.", icon='INFO')


def create_sample(obj):
    """Create a sample metarig bone for this rig type."""
    import bpy

    bpy.ops.object.mode_set(mode='EDIT')
    bone = obj.data.edit_bones.new('Bone')
    bone.head = (0.0, 0.0, 0.0)
    bone.tail = (0.0, 0.0, 0.2)
    bone.use_connect = False
    name = bone.name

    bpy.ops.object.mode_set(mode='OBJECT')
    obj.pose.bones[name].rigify_type = 'game_ready.super_copy'

    bpy.ops.object.mode_set(mode='EDIT')
    for edit_bone in obj.data.edit_bones:
        edit_bone.select = False
    obj.data.edit_bones[name].select = True
    obj.data.edit_bones.active = obj.data.edit_bones[name]
