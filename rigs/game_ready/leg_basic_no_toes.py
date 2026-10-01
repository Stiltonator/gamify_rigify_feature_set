"""GameReady Leg Basic No Toes: thigh -> shin -> foot, three DEF bones and FK/IK controls."""

import math

from bpy.props import BoolProperty, FloatProperty, StringProperty
from rigify.base_rig import BaseRig, stage
from rigify.utils.naming import make_derived_name
from rigify.utils.widgets_basic import create_circle_widget, create_cube_widget, create_sphere_widget
from rigify.rigs.widgets import create_foot_widget


class Rig(BaseRig):
    """A three-bone leg with FK/IK controls and a configurable DEF parent."""

    def find_org_bones(self, bone):
        names = [bone.name]
        current = bone.bone
        while True:
            children = [child for child in current.children if child.use_connect]
            if len(children) > 1:
                self.raise_error("GameReady Leg requires a single connected chain, without branches.")
            if not children:
                break
            current = children[0]
            if self.obj.pose.bones[current.name].rigify_type:
                self.raise_error("Only the first bone of GameReady Leg may have a Rigify Type.")
            names.append(current.name)
        return names

    def initialize(self):
        if len(self.bones.org) != 3:
            self.raise_error("GameReady Leg requires exactly 3 connected bones: thigh, shin, foot; found {}.", len(self.bones.org))
        self.reparent_def = self.params.gr_leg_reparent_def
        self.def_parent_name = self.params.gr_leg_def_parent.strip()
        if self.reparent_def and not self.def_parent_name:
            self.raise_error("Enter a generated bone name in Chain Parent, or disable Override Chain Parent.")

    @stage.generate_bones
    def generate_leg(self):
        org = self.bones.org
        ctrl = self.bones.ctrl
        self.bones.ctrl.fk = [self.copy_bone(name, make_derived_name(name, 'ctrl', '_fk'), parent=True) for name in org]
        self.bones.mch.ik = [self.copy_bone(name, make_derived_name(name, 'mch', '_ik'), parent=True) for name in org]
        self.bones.deform = [self.copy_bone(name, make_derived_name(name, 'def'), parent=True) for name in org]

        ctrl.ik_target = self.copy_bone(org[2], make_derived_name(org[2], 'ctrl', '_ik'))
        ctrl.pole = self.copy_bone(org[0], make_derived_name(org[0], 'ctrl', '_pole'))
        ctrl.settings = self.copy_bone(org[0], make_derived_name(org[0], 'ctrl', '_settings'), scale=0.2)

        thigh = self.get_bone(org[0])
        shin = self.get_bone(org[1])
        hip, knee, ankle = thigh.head.copy(), shin.head.copy(), shin.tail.copy()
        leg_axis = ankle - hip
        leg_length = thigh.length + shin.length
        if leg_axis.length < leg_length * 0.00001:
            self.raise_error("The hip and ankle cannot occupy the same position.")
        direction = leg_axis.normalized()
        bend = knee - hip - direction * (knee - hip).dot(direction)
        if bend.length < leg_length * 0.00001:
            self.raise_error("Give the knee a slight bend in the metarig so its IK bend direction is defined.")

        pole_position = knee + bend.normalized() * leg_length * self.params.gr_leg_pole_distance
        pole = self.get_bone(ctrl.pole)
        pole.head = pole_position
        pole.tail = pole_position + direction * leg_length * 0.15

        # Match Blender's pole-angle convention while preserving input bone rolls.
        normal = leg_axis.cross(pole_position - hip)
        projected_axis = normal.cross(thigh.vector).normalized()
        axis_x = thigh.x_axis.normalized()
        axis_y = thigh.vector.normalized()
        self.pole_angle = math.atan2(-axis_y.dot(axis_x.cross(projected_axis)), axis_x.dot(projected_axis))
        self.pole_angle += self.params.gr_leg_pole_angle

        settings = self.get_bone(ctrl.settings)
        offset = thigh.x_axis * thigh.length * 0.5
        settings.head += offset
        settings.tail += offset

    @stage.parent_bones
    def parent_leg(self):
        org = self.bones.org
        ctrl = self.bones.ctrl
        source_parent = self.get_bone_parent(org[0])

        if self.reparent_def:
            if self.def_parent_name not in self.obj.data.edit_bones:
                self.raise_error("Chain Parent '{}' does not exist in the generated rig. Use its exact generated name, e.g. DEF-pelvis.", self.def_parent_name)
            owned = set(org + ctrl.fk + self.bones.mch.ik + self.bones.deform + [ctrl.ik_target, ctrl.pole, ctrl.settings])
            target = self.get_bone(self.def_parent_name)
            seen = set()
            while target:
                if target.name in owned or target.name in seen:
                    self.raise_error("Chain Parent cannot be this leg's own bone or a descendant of it.")
                seen.add(target.name)
                target = target.parent
            source_parent = self.def_parent_name

        # The local-space blend requires the ORG, FK and IK roots to have the
        # same parent and rest basis. Moving only DEF leaves the controls behind.
        self.set_bone_parent(org[0], source_parent, use_connect=False)

        for chain in (ctrl.fk, self.bones.mch.ik, self.bones.deform):
            self.set_bone_parent(chain[0], source_parent, use_connect=False)
            self.parent_bone_chain(chain, use_connect=True)

        self.set_bone_parent(ctrl.settings, source_parent, use_connect=False)
        # Rigify attaches these loose controls to its generated root after
        # all parent_bones callbacks have completed.
        self.set_bone_parent(ctrl.ik_target, None, use_connect=False)
        self.set_bone_parent(ctrl.pole, None, use_connect=False)

        for name in org + ctrl.fk + self.bones.mch.ik + self.bones.deform + [ctrl.settings]:
            self.get_bone(name).use_inherit_rotation = True

        for name in org + ctrl.fk + self.bones.mch.ik + [ctrl.ik_target, ctrl.pole, ctrl.settings]:
            self.get_bone(name).use_deform = False
        for name in self.bones.deform:
            self.get_bone(name).use_deform = True
            self.get_bone(name).bbone_segments = 1

    @stage.configure_bones
    def configure_leg(self):
        ctrl = self.bones.ctrl
        for index, (org, fk) in enumerate(zip(self.bones.org, ctrl.fk)):
            self.copy_bone_properties(org, fk, props=False, widget=False)
            if index:
                self.get_bone(fk).lock_location = (True, True, True)

        for name in self.bones.mch.ik[:2]:
            self.get_bone(name).ik_stretch = 0.0
        self.get_bone(ctrl.ik_target).lock_scale = (True, True, True)
        pole = self.get_bone(ctrl.pole)
        pole.lock_rotation = (True, True, True)
        pole.lock_rotation_w = True
        pole.lock_scale = (True, True, True)
        settings = self.get_bone(ctrl.settings)
        settings.lock_location = (True, True, True)
        settings.lock_rotation = (True, True, True)
        settings.lock_rotation_w = True
        settings.lock_scale = (True, True, True)

        self.make_property(ctrl.settings, 'FK_IK', default=self.params.gr_leg_default_ik,
                           min=0.0, max=1.0, description='0 = FK, 1 = IK; intermediate values blend')
        controls = ctrl.fk + [ctrl.ik_target, ctrl.pole, ctrl.settings]
        panel = self.script.panel_with_selected_check(self, controls)
        panel.custom_prop(ctrl.settings, 'FK_IK', text='GameReady Leg: FK / IK', slider=True)

    @stage.rig_bones
    def rig_leg(self):
        ctrl = self.bones.ctrl
        mch = self.bones.mch.ik

        # Count from the shin (constraint owner) back to the thigh, inclusive.
        # The third input bone is the foot, whose orientation is controlled separately.
        count = 1
        current = self.get_bone(mch[1])
        while current.name != mch[0]:
            current = current.parent
            if current is None:
                self.raise_error("The generated IK chain is disconnected.")
            count += 1

        self.make_constraint(mch[1], 'IK', ctrl.ik_target, name='GameReady Leg IK',
                             chain_count=count, use_tail=True, use_stretch=False,
                             pole_target=self.obj, pole_subtarget=ctrl.pole, pole_angle=self.pole_angle)
        self.make_constraint(mch[2], 'COPY_ROTATION', ctrl.ik_target,
                             name='IK Foot Rotation', space='WORLD')

        # Blend the local poses on a separate result chain: never blend the IK
        # constraint's own influence, which is unsuitable with an active pole.
        for org, fk, ik, deform in zip(self.bones.org, ctrl.fk, mch, self.bones.deform):
            self.make_constraint(org, 'COPY_TRANSFORMS', fk, name='FK Pose', space='LOCAL')
            blend = self.make_constraint(org, 'COPY_TRANSFORMS', ik, name='IK Blend', space='LOCAL')
            self.make_driver(blend, 'influence', variables=[(ctrl.settings, 'FK_IK')])
            self.make_constraint(deform, 'COPY_TRANSFORMS', org, name='Deform Result', space='WORLD')

        self.validate_def_parent()

    def validate_def_parent(self):
        if not self.reparent_def:
            return
        root = self.get_bone(self.bones.deform[0])
        if root.parent is None or root.parent.name != self.def_parent_name:
            self.raise_error("Could not assign Chain Parent '{}'. Check for a parenting cycle.", self.def_parent_name)
        seen = {root.name}
        current = root.parent
        while current:
            if current.name in seen:
                self.raise_error("Chain Parent '{}' creates a parenting cycle.", self.def_parent_name)
            seen.add(current.name)
            current = current.parent

    @stage.generate_widgets
    def generate_leg_widgets(self):
        ctrl = self.bones.ctrl
        for name in ctrl.fk:
            create_circle_widget(self.obj, name, radius=0.35, head_tail=0.5)
        create_foot_widget(self.obj, ctrl.ik_target)
        create_sphere_widget(self.obj, ctrl.pole)
        create_cube_widget(self.obj, ctrl.settings)

    def finalize(self):
        self.validate_def_parent()

    @classmethod
    def add_parameters(cls, params):
        params.gr_leg_reparent_def = BoolProperty(
            name='Override Chain Parent', default=False,
            description='Parent the FK thigh, IK start, result chain and first DEF to the named bone')
        params.gr_leg_def_parent = StringProperty(
            name='Chain Parent', default='',
            description='Exact bone name in the GENERATED rig, for example DEF-pelvis or root')
        params.gr_leg_default_ik = FloatProperty(
            name='Initial FK / IK', default=0.0, min=0.0, max=1.0,
            description='Initial generated switch value: 0 = FK, 1 = IK')
        params.gr_leg_pole_distance = FloatProperty(
            name='Pole Distance', default=0.5, min=0.05, max=5.0,
            description='Distance of the knee pole from the knee, relative to thigh plus shin length')
        params.gr_leg_pole_angle = FloatProperty(
            name='Pole Angle Offset', default=0.0, subtype='ANGLE',
            description='Optional correction added to the automatically calculated pole angle')

    @classmethod
    def parameters_ui(cls, layout, params):
        layout.label(text='GameReady Leg — Basic No Toes')
        layout.label(text='Exactly 3 connected bones: thigh, shin, foot')
        layout.prop(params, 'gr_leg_default_ik', slider=True)
        layout.prop(params, 'gr_leg_pole_distance')
        layout.prop(params, 'gr_leg_pole_angle')
        layout.separator()
        layout.prop(params, 'gr_leg_reparent_def')
        column = layout.column()
        column.enabled = params.gr_leg_reparent_def
        column.prop(params, 'gr_leg_def_parent')
        if params.gr_leg_reparent_def:
            column.label(text='Use the exact generated bone name, e.g. DEF-pelvis.')
