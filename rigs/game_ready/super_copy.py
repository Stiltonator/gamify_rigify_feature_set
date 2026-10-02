"""GameReady super copy based on Rigify's basic.super_copy."""

import warnings

from bpy.props import BoolProperty, FloatVectorProperty, StringProperty

from rigify.base_rig import stage
from rigify.rigs.basic.super_copy import Rig as NativeSuperCopyRig
from rigify.utils import make_deformer_name, strip_org
from rigify.utils.widgets import layout_widget_dropdown
from ...viewport_preview import tag_view3d_redraw
from .def_parent import DefParentMixin


class Rig(DefParentMixin, NativeSuperCopyRig):
    """A super-copy rig with optional DEF parenting and widget transforms."""

    parent_override_param = 'gr_sc_override_parent'
    parent_name_param = 'gr_sc_def_parent'
    allow_root_def_parent = True

    def initialize(self):
        super().initialize()
        self.gr_widget_offset = self.params.gr_sc_widget_offset
        self.gr_widget_scale = self.params.gr_sc_widget_scale
        self.gr_source_parent = self.get_bone_parent(self._single_bone_name(self.bones.org))
        self.gr_def_parent = None
        self._gr_def_parent_resolved = False

    @staticmethod
    def _single_bone_name(bones):
        if isinstance(bones, str):
            return bones
        return bones[0] if bones else ''

    def _resolve_def_parent(self):
        if self._gr_def_parent_resolved or not self.make_deform:
            return

        root = self.generator.root_bone
        edit_bones = self.obj.data.edit_bones

        if self.gr_override_parent:
            requested = self.gr_parent_name.strip()
            if not requested:
                warnings.warn(
                    "DEF Parent field is empty. The DEF bone will use the rig root. "
                    "Enter 'NONE' to suppress this warning.",
                    RuntimeWarning,
                    stacklevel=2,
                )
                parent = root
            elif requested.casefold() == self.none_parent_token.casefold():
                parent = None
            elif requested not in edit_bones:
                warnings.warn(
                    f"DEF Parent '{requested}' not found. The DEF bone will use the rig root.",
                    RuntimeWarning,
                    stacklevel=2,
                )
                parent = root
            else:
                parent = requested
        elif self.gr_source_parent and self.gr_source_parent != root:
            source = self.gr_source_parent
            parent = source if source.startswith('DEF-') else make_deformer_name(strip_org(source))
            if parent not in edit_bones:
                warnings.warn(
                    f"Metarig parent '{source}' has no generated DEF bone. "
                    "The DEF bone will use the rig root.",
                    RuntimeWarning,
                    stacklevel=2,
                )
                parent = root
        else:
            parent = root

        org_name = self._single_bone_name(self.bones.org)
        deform_name = self._single_bone_name(self.bones.deform)
        if parent:
            target = edit_bones.get(parent)
            if target is None:
                self.raise_error("DEF Parent '{}' was not found in the generated armature.", parent)
            seen = set()
            while target:
                if target.name in {org_name, deform_name} or target.name in seen:
                    self.raise_error("DEF Parent cannot be this rig's own bone or one of its descendants.")
                seen.add(target.name)
                target = target.parent

        self.gr_def_parent = parent
        self.rig_parent_bone = parent or root
        self._gr_def_parent_resolved = True

    def _apply_def_parent(self):
        if not self.make_deform:
            return
        self._resolve_def_parent()
        deform_name = self._single_bone_name(self.bones.deform)
        self.set_bone_parent(deform_name, self.gr_def_parent, use_connect=False)
        if self.gr_def_parent is None:
            self.generator.disable_auto_parent(deform_name)

    def parent_bones(self):
        # Bypass DefParentMixin.parent_bones here: basic.super_copy stores its
        # single ORG and DEF bone names as strings, while the shared resolver is
        # designed around chain-style bone lists.
        super(DefParentMixin, self).parent_bones()
        self._resolve_def_parent()
        self._apply_def_parent()

    @stage.parent_bones
    def parent_deform_chain(self):
        # The mixin's chain callback indexes deform[0]; super_copy stores a
        # single deform name, so apply the same resolved policy safely here.
        native_callback = getattr(super(DefParentMixin, self), 'parent_deform_chain', None)
        if native_callback:
            native_callback()
        self._apply_def_parent()

    def finalize(self):
        # DefParentMixin.finalize also assumes a list of deform bone names.
        finalize = getattr(super(DefParentMixin, self), 'finalize', None)
        if finalize:
            finalize()

    @stage.configure_bones
    def configure_game_ready_control(self):
        if self.make_control and self.make_widget:
            control = self.get_bone(self.bones.ctrl)
            control.custom_shape_translation = self.gr_widget_offset
            control.custom_shape_scale_xyz = self.gr_widget_scale

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

        params.gr_sc_override_parent = BoolProperty(
            name='Override Parent', default=False,
            description='Override the DEF bone parent selected from the metarig hierarchy')
        params.gr_sc_def_parent = StringProperty(
            name='Parent', default='',
            description='Name of the generated bone that should parent the DEF bone')
        params.gr_sc_widget_offset = FloatVectorProperty(
            name='Widget Offset', size=3, default=(0.0, 0.0, 0.0), subtype='TRANSLATION',
            update=tag_view3d_redraw,
            description='Offset of the control bone custom shape')
        params.gr_sc_widget_scale = FloatVectorProperty(
            name='Widget Scale', size=3, default=(1.0, 1.0, 1.0), subtype='XYZ',
            update=tag_view3d_redraw,
            description='Scale of the control bone custom shape')
        params.gr_sc_widget_offset_expanded = BoolProperty(
            name='Widget Offset Expanded', default=False,
            options={'HIDDEN'},
            description='Expand or collapse the Widget Offset vector')
        params.gr_sc_widget_scale_expanded = BoolProperty(
            name='Widget Scale Expanded', default=False,
            options={'HIDDEN'},
            description='Expand or collapse the Widget Scale vector')

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
            offset_open = params.gr_sc_widget_offset_expanded
            layout.prop(
                params, 'gr_sc_widget_offset_expanded',
                text='Widget Offset',
                icon='TRIA_DOWN' if offset_open else 'TRIA_RIGHT',
                emboss=False,
            )
            if offset_open:
                layout.prop(params, 'gr_sc_widget_offset')

            scale_open = params.gr_sc_widget_scale_expanded
            layout.prop(
                params, 'gr_sc_widget_scale_expanded',
                text='Widget Scale',
                icon='TRIA_DOWN' if scale_open else 'TRIA_RIGHT',
                emboss=False,
            )
            if scale_open:
                layout.prop(params, 'gr_sc_widget_scale')

        layout.prop(params, 'make_deform')
        if params.make_deform:
            layout.prop(params, 'gr_sc_override_parent')
            if params.gr_sc_override_parent:
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
