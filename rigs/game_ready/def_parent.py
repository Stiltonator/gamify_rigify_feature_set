"""Shared generated-DEF parenting rules for GameReady Rigify adapters."""

from rigify.base_rig import stage
from rigify.utils.naming import make_derived_name


class DefParentMixin:
    """Resolve a configurable DEF attachment and keep generated DEF roots clean."""

    parent_override_param = ''
    parent_name_param = ''
    allow_empty_chain_parent = False
    default_parent_to_root = False
    allow_root_def_parent = False
    none_parent_token = 'NONE'

    def initialize(self):
        super().initialize()
        self.gr_override_parent = getattr(self.params, self.parent_override_param)
        self.gr_parent_name = getattr(self.params, self.parent_name_param).strip()
        #if self.gr_override_parent and not self.gr_parent_name:
        #    self.raise_error("Enter an exact generated DEF bone name, or disable Override Chain Parent.")
        if self.gr_override_parent and not self.gr_parent_name and not self.allow_empty_chain_parent:
            self.raise_error("Enter an exact generated DEF bone name, or disable Override Chain Parent.")
        
        if hasattr(self, 'bbone_segments'):
            self.bbone_segments = 1

    def _game_ready_org_chain(self):
        orgs = self.bones.org
        return getattr(orgs, 'main', orgs)

    def parent_bones(self):
        super().parent_bones()
        orgs = self._game_ready_org_chain()
        source = self.get_bone_parent(orgs[0])
        root = self.generator.root_bone

        # if self.gr_override_parent:
        #     parent = self.gr_parent_name
        # elif source and source != root:
        #     parent = source if source.startswith('DEF-') else make_derived_name(source, 'def')
        # else:
        #     parent = None
        if self.gr_override_parent:
            if not self.gr_parent_name or self.gr_parent_name.casefold() == self.none_parent_token.casefold():
                parent = None
            else:
                parent = self.gr_parent_name
        elif self.default_parent_to_root:
            parent = root
        elif source and source != root:
            parent = source if source.startswith('DEF-') else make_derived_name(source, 'def')
        else:
            parent = None

        edit_bones = self.obj.data.edit_bones
        if parent:
            if parent not in edit_bones:
                self.raise_error("DEF chain parent '{}' was not found. Enter the exact generated DEF bone name.", parent)
            # if not parent.startswith('DEF-'):
            #     self.raise_error("Chain Parent '{}' must be a DEF bone; GameReady DEF bones cannot parent to ORG, MCH, control or root bones.", parent)
            if not parent.startswith('DEF-') and not (
                self.allow_root_def_parent and parent == root
            ):
                self.raise_error("Chain Parent '{}' must be a DEF bone or an explicitly allowed rig root.", parent)

            owned = set(orgs)
            owned.update(getattr(self.bones, 'deform', []))
            ancestor = edit_bones[parent]
            seen = set()
            while ancestor:
                if ancestor.name in owned or ancestor.name in seen:
                    self.raise_error("Chain Parent cannot be this rig's own bone or one of its descendants.")
                seen.add(ancestor.name)
                ancestor = ancestor.parent

        self.gr_def_parent = parent
        # Native FK/IK base and master controls use this field. Controls under a
        # standalone rig still attach to Rigify root; the DEF root does not.
        self.rig_parent_bone = parent or root

    @stage.parent_bones
    def parent_deform_chain(self):
        super().parent_deform_chain()
        deform = self.bones.deform
        if not deform:
            return

        self.set_bone_parent(deform[0], self.gr_def_parent, use_connect=False)
        if len(deform) > 1:
            self.parent_bone_chain(deform, use_connect=True)

        if self.gr_def_parent is None:
            self.generator.disable_auto_parent(deform[0])

    def finalize(self):
        finalize = getattr(super(), 'finalize', None)
        if finalize:
            finalize()

        edit_bones = self.obj.data.bones
        deform = getattr(self.bones, 'deform', [])
        for name in deform:
            bone = edit_bones[name]
            parent = bone.parent
#            if parent and (not parent.name.startswith('DEF-') or not parent.use_deform):
#                self.raise_error("DEF hierarchy violation: '{}' has non-DEF parent '{}'.", name, parent.name)
            if parent and (not parent.name.startswith('DEF-') or not parent.use_deform):
                is_allowed_root_parent = (
                    self.allow_root_def_parent
                    and name == deform[0]
                    and parent.name == self.generator.root_bone
                )
                if not is_allowed_root_parent:
                    self.raise_error("DEF hierarchy violation: '{}' has non-DEF parent '{}'.", name, parent.name)
            if bone.bbone_segments != 1:
                self.raise_error("DEF bone '{}' must use one B-Bone segment.", name)
            if any(con.type == 'STRETCH_TO' for con in self.obj.pose.bones[name].constraints):
                self.raise_error("DEF bone '{}' must not have a Stretch-To constraint.", name)

    @classmethod
    def add_parent_parameters(cls, params, prefix):
        from bpy.props import BoolProperty, StringProperty
        setattr(params, prefix + '_override_parent', BoolProperty(
            name='Override Chain Parent', default=False,
            description='Attach the FK/IK chain start and first DEF bone to a named generated DEF bone'))
        setattr(params, prefix + '_parent', StringProperty(
            name='Chain Parent', default='',
            description='Exact generated DEF bone name, e.g. DEF-pelvis'))

    @classmethod
    def draw_parent_parameters(cls, layout, params, prefix):
        layout.separator()
        layout.prop(params, prefix + '_override_parent')
        column = layout.column()
        column.enabled = getattr(params, prefix + '_override_parent')
        column.prop(params, prefix + '_parent')
        layout.label(text='DEF bones parent only to DEF bones; an unparented chain stays parentless.')
