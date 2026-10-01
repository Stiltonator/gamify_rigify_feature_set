"""GameReady spine adapter based on Rigify's splines.basic_spine."""

from bpy.props import FloatVectorProperty

from rigify.base_rig import stage
from rigify.rigs.spines.basic_spine import Rig as NativeBasicSpineRig

from .def_parent import DefParentMixin
from ...viewport_preview import tag_view3d_redraw


class Rig(DefParentMixin, NativeBasicSpineRig):
    """Native basic spine with DEF-only hierarchy and rotation-only tracking."""

    parent_override_param = 'gr_spine_override_parent'
    parent_name_param = 'gr_spine_parent'

    def rig_deform_bone(self, i, deform, tweak, next_tweak):
        self.make_constraint(deform, 'COPY_TRANSFORMS', tweak)
        if next_tweak:
            self.make_constraint(deform, 'DAMPED_TRACK', next_tweak, track_axis='TRACK_Y')

    @stage.generate_widgets
    def configure_game_ready_custom_shapes(self):
        params = self.params
        ctrl = self.bones.ctrl

        self.set_custom_shape_visuals(
            [ctrl.master],
            params.gr_spine_torso_widget_offset,
            params.gr_spine_torso_widget_scale,
            params.gr_spine_torso_widget_rotation,
        )
        self.set_custom_shape_visuals(
            [ctrl.hips],
            params.gr_spine_hips_widget_offset,
            params.gr_spine_hips_widget_scale,
            params.gr_spine_hips_widget_rotation,
        )
        self.set_custom_shape_visuals(
            [ctrl.chest],
            params.gr_spine_chest_widget_offset,
            params.gr_spine_chest_widget_scale,
            params.gr_spine_chest_widget_rotation,
        )
        self.set_custom_shape_visuals(
            ctrl.fk.hips + ctrl.fk.chest if self.params.make_fk_controls else [],
            params.gr_spine_fk_widget_offset,
            params.gr_spine_fk_widget_scale,
        )
        self.set_custom_shape_visuals(
            ctrl.tweak,
            params.gr_spine_tweak_widget_offset,
            params.gr_spine_tweak_widget_scale,
        )

    def set_custom_shape_visuals(self, bone_names, offset, scale, rotation=None):
        for name in bone_names:
            pose_bone = self.obj.pose.bones[name]
            pose_bone.custom_shape_translation = offset
            pose_bone.custom_shape_scale_xyz = scale
            if rotation is not None:
                pose_bone.custom_shape_rotation_euler = rotation

    @classmethod
    def add_parameters(cls, params):
        super().add_parameters(params)
        cls.add_parent_parameters(params, 'gr_spine')

        params.gr_spine_torso_widget_offset = FloatVectorProperty(
            name='Position', size=3, default=(0.0, 0.0, 0.0), subtype='TRANSLATION',
            update=tag_view3d_redraw,
            description='Absolute custom shape translation for the torso master control')
        params.gr_spine_torso_widget_scale = FloatVectorProperty(
            name='Scale', size=3, default=(1.0, 1.0, 1.0), subtype='XYZ',
            update=tag_view3d_redraw,
            description='Custom shape scale for the torso master control')
        params.gr_spine_torso_widget_rotation = FloatVectorProperty(
            name='Rotation', size=3, default=(0.0, 0.0, 0.0), subtype='EULER',
            update=tag_view3d_redraw,
            description='Custom shape Euler rotation for the torso master control')
        params.gr_spine_hips_widget_offset = FloatVectorProperty(
            name='Position', size=3, default=(0.0, 0.0, 0.0), subtype='TRANSLATION',
            update=tag_view3d_redraw,
            description='Absolute custom shape translation for the hip control')
        params.gr_spine_hips_widget_scale = FloatVectorProperty(
            name='Scale', size=3, default=(1.0, 1.0, 1.0), subtype='XYZ',
            update=tag_view3d_redraw,
            description='Custom shape scale for the hip control')
        params.gr_spine_hips_widget_rotation = FloatVectorProperty(
            name='Rotation', size=3, default=(0.0, 0.0, 0.0), subtype='EULER',
            update=tag_view3d_redraw,
            description='Custom shape Euler rotation for the hip control')
        params.gr_spine_chest_widget_offset = FloatVectorProperty(
            name='Position', size=3, default=(0.0, 0.0, 0.0), subtype='TRANSLATION',
            update=tag_view3d_redraw,
            description='Absolute custom shape translation for the chest control')
        params.gr_spine_chest_widget_scale = FloatVectorProperty(
            name='Scale', size=3, default=(1.0, 1.0, 1.0), subtype='XYZ',
            update=tag_view3d_redraw,
            description='Custom shape scale for the chest control')
        params.gr_spine_chest_widget_rotation = FloatVectorProperty(
            name='Rotation', size=3, default=(0.0, 0.0, 0.0), subtype='EULER',
            update=tag_view3d_redraw,
            description='Custom shape Euler rotation for the chest control')
        params.gr_spine_fk_widget_offset = FloatVectorProperty(
            name='FK Controls Position', size=3, default=(0.0, 0.0, 0.0), subtype='TRANSLATION',
            update=tag_view3d_redraw,
            description='Absolute custom shape translation for the FK controls')
        params.gr_spine_fk_widget_scale = FloatVectorProperty(
            name='FK Controls Scale', size=3, default=(1.0, 1.0, 1.0), subtype='XYZ',
            update=tag_view3d_redraw,
            description='Custom shape scale for the FK controls')
        params.gr_spine_tweak_widget_offset = FloatVectorProperty(
            name='Tweak Controls Position', size=3, default=(0.0, 0.0, 0.0), subtype='TRANSLATION',
            update=tag_view3d_redraw,
            description='Absolute custom shape translation for the tweak controls')
        params.gr_spine_tweak_widget_scale = FloatVectorProperty(
            name='Tweak Controls Scale', size=3, default=(1.0, 1.0, 1.0), subtype='XYZ',
            update=tag_view3d_redraw,
            description='Custom shape scale for the tweak controls')

    @classmethod
    def parameters_ui(cls, layout, params):
        layout.label(text='GameReady Spine — based on splines.basic_spine')
        super().parameters_ui(layout, params)
        cls.draw_parent_parameters(layout, params, 'gr_spine')

        layout.separator()
        layout.label(text='Custom Shape Visuals')

        torso_box = layout.box()
        torso_box.label(text='Torso Control')
        torso_box.prop(params, 'gr_spine_torso_widget_offset')
        torso_box.prop(params, 'gr_spine_torso_widget_rotation')
        torso_box.prop(params, 'gr_spine_torso_widget_scale')

        hips_box = layout.box()
        hips_box.label(text='Hip Control')
        hips_box.prop(params, 'gr_spine_hips_widget_offset')
        hips_box.prop(params, 'gr_spine_hips_widget_rotation')
        hips_box.prop(params, 'gr_spine_hips_widget_scale')

        chest_box = layout.box()
        chest_box.label(text='Chest Control')
        chest_box.prop(params, 'gr_spine_chest_widget_offset')
        chest_box.prop(params, 'gr_spine_chest_widget_rotation')
        chest_box.prop(params, 'gr_spine_chest_widget_scale')

        fk_box = layout.box()
        fk_box.label(text='FK Controls')
        fk_box.enabled = params.make_fk_controls
        fk_box.prop(params, 'gr_spine_fk_widget_offset')
        fk_box.prop(params, 'gr_spine_fk_widget_scale')

        tweak_box = layout.box()
        tweak_box.label(text='Tweak Controls')
        tweak_box.prop(params, 'gr_spine_tweak_widget_offset')
        tweak_box.prop(params, 'gr_spine_tweak_widget_scale')
