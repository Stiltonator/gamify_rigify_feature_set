"""Raw-copy rig preserving source names and metarig custom-shape settings."""

from rigify.base_generate import SubstitutionRig
from rigify.rigs.basic.raw_copy import Rig as NativeRawCopyRig
from rigify.rigs.basic.raw_copy import create_sample as native_create_sample
from rigify.utils.naming import make_original_name

from .custom_shapes import copy_custom_shape


class Rig(SubstitutionRig):
    def substitute(self):
        # Rigify only exempts basic.raw_copy from ORG prefixing. Rename during
        # substitution, before ownership and parent relationships are registered.
        source = next(bone for bone in self.generator.metarig.pose.bones
                      if make_original_name(bone.name) == self.base_bone)
        name = self.generator.rename_org_bone(self.base_bone, source.name)
        return [self.instantiate_rig(InstanceRig, name)]

    add_parameters = NativeRawCopyRig.add_parameters
    parameters_ui = NativeRawCopyRig.parameters_ui


class InstanceRig(NativeRawCopyRig):
    def generate_widgets(self):
        name = self.bones.org
        if name.startswith(('MCH-', 'DEF-')):
            self.get_bone(name).custom_shape = None
            self.generator.new_widget_table[name] = None
        elif self.params.optional_widget_type:
            super().generate_widgets()
        else:
            source = self.generator.metarig.pose.bones[name]
            copy_custom_shape(self, source, name)

    def finalize(self):
        # Rigify clears shapes on prefixed bones while assigning collections.
        name = self.bones.org
        if not name.startswith(('MCH-', 'DEF-')) and not self.params.optional_widget_type:
            copy_custom_shape(self, self.generator.metarig.pose.bones[name], name)


def create_sample(obj):
    bones = native_create_sample(obj)
    for name in bones.values():
        obj.pose.bones[name].rigify_type = 'game_ready.raw_copy'
    return bones
