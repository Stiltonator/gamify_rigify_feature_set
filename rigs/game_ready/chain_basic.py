"""GameReady point chain with the experimental super_chain backing and pivot."""

import re
import warnings

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, StringProperty

from rigify.base_rig import BaseRig, stage
from rigify.utils.bones import align_bone_x_axis, align_bone_y_axis
from rigify.utils.naming import org, strip_org
from rigify.utils.widgets import create_widget

from .chain_bendy import WIDGET_ITEMS, WIDGET_BUILDERS, ARROW_VERTICES, ARROW_EDGES
from .def_parent import resolve_generated_parent


class Rig(BaseRig):
    """Backing-driven point tweaks and unconnected, single-segment deform bones."""

    def find_org_bones(self, bone):
        names = [bone.name]
        current = bone.bone
        while True:
            children = [child for child in current.children if child.use_connect]
            if len(children) > 1:
                self.raise_error('Chain Basic requires one connected chain without branches.')
            if not children:
                return names
            current = children[0]
            if self.obj.pose.bones[current.name].rigify_type:
                self.raise_error('Only the first Chain Basic bone may have a Rigify Type.')
            names.append(current.name)

    def initialize(self):
        super().initialize()
        self.org_chain = list(self.bones.org)

    def _orientation(self, index):
        bones = self.obj.data.edit_bones
        if self.params.gr_cb_override_orientation:
            requested = self.params.gr_cb_orientation_bone.strip()
            if not requested:
                self.raise_error('Override Bone Orientation requires an orientation bone.')
            reference = bones.get(org(requested)) or bones.get(requested)
            if reference is None:
                self.raise_error("Orientation bone '{}' was not found.", requested)
            return reference.y_axis.normalized(), reference.x_axis.normalized()
        current = bones[self.org_chain[min(index, len(self.org_chain) - 1)]]
        if 0 < index < len(self.org_chain):
            previous = bones[self.org_chain[index - 1]]
            direction = previous.y_axis.normalized() + current.y_axis.normalized()
            roll = previous.x_axis.normalized() + current.x_axis.normalized()
            if direction.length < 1e-6:
                direction = current.y_axis.copy()
            if roll.length < 1e-6:
                roll = current.x_axis.copy()
            return direction.normalized(), roll.normalized()
        return current.y_axis.normalized(), current.x_axis.normalized()

    def _point_name(self, point, number):
        label = strip_org(self.org_chain[0])
        match = re.search(r'\.([LR])$', label, re.IGNORECASE)
        side = '.' + match[1].upper() if match else ''
        base = label[:match.start()] if match else label
        base = re.sub(r'\.\d{3}$', '', base)
        x = (self.obj.matrix_world @ point).x
        if abs(x) <= 1e-5:
            side = ''
        elif not side:
            side = '.L' if x > 0 else '.R'
        bones = self.obj.data.edit_bones
        while True:
            name = f'{base}.{number:03d}{side}'
            if name not in bones and 'DEF-' + name not in bones:
                return name
            number += 1

    @stage.generate_bones
    def generate_point_bones(self):
        bones = self.obj.data.edit_bones
        controls, deformers, tweaks, intermediates = [], [], [], []
        for index in range(len(self.org_chain) + 1):
            source = self.org_chain[min(index, len(self.org_chain) - 1)]
            point = (bones[source].tail if index == len(self.org_chain) else bones[source].head).copy()
            direction, roll = self._orientation(index)
            name = self._point_name(point, index)
            control = self.copy_bone(source, name)
            deform = self.copy_bone(source, 'DEF-' + name)
            for target in (control, deform):
                bone = bones[target]
                bone.head = point
                bone.tail = point + direction * max(bones[source].length * 0.25, 0.001)
                align_bone_y_axis(self.obj, target, direction)
                align_bone_x_axis(self.obj, target, roll)
                bone.use_connect = False
                bone.bbone_segments = 1
                bone.use_deform = target == deform
            # Endpoint controls drive the backing; interior point controls are tweaks.
            tweak = self.copy_bone(control, (control[:-2] + '.Tweak' + control[-2:] if control.endswith(('.L', '.R')) else control + '.Tweak'))
            intermediate = self.copy_bone(control, 'MCH-INT-' + name)
            tweaks.append(tweak)
            intermediates.append(intermediate)
            controls.append(control)
            deformers.append(deform)
        self.bones.ctrl = controls
        self.bones.deform = deformers
        self.tweaks = tweaks
        self.intermediates = intermediates
        first, last = bones[self.org_chain[0]], bones[self.org_chain[-1]]
        direction = last.tail - first.head
        if direction.length < 1e-6:
            self.raise_error('Chain Basic requires distinct start and end positions for its backing bone.')
        self.backing = self.copy_bone(self.org_chain[0], 'MCH-AUTO-' + strip_org(self.org_chain[0]))
        bones[self.backing].head = first.head
        bones[self.backing].tail = last.tail
        align_bone_x_axis(self.obj, self.backing, first.x_axis)
        middle = len(self.org_chain) // 2
        source = bones[self.org_chain[middle]]
        location = source.head + source.vector * (0.5 if len(self.org_chain) % 2 else 0.0)
        label = strip_org(self.org_chain[0])
        pivot_name = label[:-2] + '.Pivot' + label[-2:] if label.endswith(('.L', '.R')) else label + '.Pivot'
        self.pivot = self.copy_bone(self.backing, pivot_name)
        bones[self.pivot].head = location
        bones[self.pivot].tail = location + direction.normalized() * direction.length * 0.25
        # Common frames make LOCAL pivot transforms independent of tweak orientation.
        for name in intermediates:
            align_bone_y_axis(self.obj, name, direction)
            align_bone_x_axis(self.obj, name, bones[self.backing].x_axis)
        # Only endpoints need separate main controls. Interior point controls become tweaks.
        for name in controls[1:-1]:
            bones.remove(bones[name])
        self.bones.ctrl = [controls[0], controls[-1], self.pivot] + tweaks
        self.endpoints = [controls[0], controls[-1]]

    def _explicit_parent(self, requested, label):
        requested = requested.strip()
        if requested.casefold() == 'none':
            return None
        if not requested or requested not in self.obj.data.edit_bones:
            self.raise_error("{} parent '{}' was not found; enter an exact generated bone name or NONE.",
                             label, requested)
        return requested

    def _validate_parents(self, proposed):
        bones = self.obj.data.edit_bones
        for child, parent in proposed.items():
            seen = {child}
            while parent:
                if parent in seen:
                    self.raise_error("Chain Basic parenting would create a cycle involving '{}'.", parent)
                seen.add(parent)
                if parent in proposed:
                    parent = proposed[parent]
                else:
                    bone = bones[parent]
                    parent = bone.parent.name if bone.parent else None

    @stage.parent_bones
    def parent_point_bones(self):
        root = self.generator.root_bone
        source_parent = self.get_bone_parent(self.org_chain[0])
        if self.params.gr_cb_override_start_parent:
            start_parent = self._explicit_parent(self.params.gr_cb_start_parent, 'Start')
        elif source_parent and source_parent != root:
            start_parent = resolve_generated_parent(self.obj.data.edit_bones, source_parent)
            if start_parent is None:
                start_parent = root
                warnings.warn(f"Chain Basic: no DEF/control counterpart for '{source_parent}'; using root.",
                              RuntimeWarning, stacklevel=2)
        else:
            start_parent = root
        end_parent = (self._explicit_parent(self.params.gr_cb_end_parent, 'End')
                      if self.params.gr_cb_override_end_parent else start_parent)
        proposed = {self.endpoints[0]: start_parent, self.endpoints[1]: end_parent,
                    self.backing: start_parent, self.pivot: self.backing}
        for index, (frame, tweak, deform) in enumerate(zip(self.intermediates, self.tweaks, self.bones.deform)):
            proposed[frame] = (self.endpoints[0] if index == 0 else
                               self.endpoints[1] if index == len(self.tweaks) - 1 else self.backing)
            proposed[tweak] = frame
            proposed[deform] = (start_parent if index == 0 else
                               self.bones.deform[index - 1] if self.params.gr_cb_parent_in_sequence else self.bones.deform[0])
        dependency_graph = dict(proposed)
        dependency_graph.update(zip(self.bones.deform, self.tweaks))
        dependency_graph.update(zip(self.org_chain, self.tweaks))
        # Include the constraint dependencies so endpoint overrides cannot feed
        # the chain back into itself through a tweak, DEF, ORG, or pivot.
        for endpoint in self.endpoints:
            dependencies = dict(dependency_graph, **{self.backing: endpoint})
            self._validate_parents(dependencies)
        self._validate_parents(proposed)
        for name, parent in proposed.items():
            self.set_bone_parent(name, parent, use_connect=False)
            self.get_bone(name).inherit_scale = ('FULL' if name in self.intermediates[1:-1] else 'NONE')
            if parent is None:
                self.generator.disable_auto_parent(name)

    @stage.configure_bones
    def configure_point_controls(self):
        for name in self.bones.ctrl:
            bone = self.get_bone(name)
            size = self.params.gr_cb_tweak_size if name in self.tweaks else self.params.gr_cb_shape_size
            scale = self.params.gr_cb_shape_scale * size / 0.5
            bone.use_custom_shape_bone_size = False
            bone.custom_shape_scale_xyz = (scale,) * 3
        for name in self.bones.ctrl + self.bones.deform + self.intermediates + [self.backing]:
            bone = self.get_bone(name).bone
            bone.bbone_segments = 1
            bone.use_deform = name in self.bones.deform

    @stage.rig_bones
    def rig_point_bones(self):
        for deform, control in zip(self.bones.deform, self.tweaks):
            self.make_constraint(deform, 'COPY_TRANSFORMS', control, space='WORLD')
        for source, control in zip(self.org_chain, self.tweaks):
            self.make_constraint(source, 'COPY_TRANSFORMS', control, space='WORLD')

        self.make_constraint(self.backing, 'COPY_LOCATION', self.endpoints[0], space='WORLD')
        self.make_constraint(self.backing, 'STRETCH_TO', self.endpoints[1], volume='NO_VOLUME')
        count = len(self.org_chain)
        for index, frame in enumerate(self.intermediates[1:-1], 1):
            x = 2.0 * index / count
            self.make_constraint(frame, 'COPY_TRANSFORMS', self.pivot, space='LOCAL',
                                 influence=2.0 * x - x * x)
        for endpoint in self.endpoints:
            self.make_constraint(self.pivot, 'COPY_ROTATION', endpoint, space='LOCAL', influence=0.33)

    @stage.generate_widgets
    def generate_point_widgets(self):
        for name in self.bones.ctrl:
            widget_type = self.params.gr_cb_tweak_widget if name in self.tweaks else self.params.gr_cb_widget
            old = self.generator.old_widget_table.get(name)
            force = old is None or old.get('gr_cb_widget_type') != widget_type
            if widget_type == 'arrow':
                widget = create_widget(self.obj, name, widget_force_new=force)
                if widget:
                    widget.data.from_pydata(ARROW_VERTICES, ARROW_EDGES, [])
                    widget.data.update()
            else:
                builder, args = WIDGET_BUILDERS[widget_type]
                widget = builder(self.obj, name, widget_force_new=force, **args)
            if widget:
                widget['gr_cb_widget_type'] = widget_type

    @classmethod
    def add_parameters(cls, params):
        params.gr_cb_widget = EnumProperty(name='Widget', items=WIDGET_ITEMS, default='circle')
        params.gr_cb_tweak_widget = EnumProperty(name='Tweak Widget', items=WIDGET_ITEMS, default='sphere')
        params.gr_cb_tweak_size = FloatProperty(name='Tweak Shape Size', default=1, min=0.001, max=100, soft_min=0.01, soft_max=10, precision=3)
        params.gr_cb_shape_scale = FloatProperty(name='Shape Scale', default=0.1, min=0.001, max=100, precision=3)
        params.gr_cb_shape_size = FloatProperty(name='Shape Size', default=3, min=0.001, max=100,
                                               soft_min=0.01, soft_max=10, precision=3)
        params.gr_cb_parent_in_sequence = BoolProperty(
            name='Parent in Sequence', default=True,
            description='Parent DEF bones in sequence; otherwise parent all subsequent DEFs to the first DEF')
        params.gr_cb_override_start_parent = BoolProperty(name='Override Start Parent', default=False)
        params.gr_cb_start_parent = StringProperty(name='Start Parent', description='Exact generated bone name, or NONE')
        params.gr_cb_override_end_parent = BoolProperty(name='Override End Parent', default=False)
        params.gr_cb_end_parent = StringProperty(name='End Parent', description='Exact parent for the end control, or NONE')
        params.gr_cb_override_orientation = BoolProperty(name='Override Bone Orientation', default=False)
        params.gr_cb_orientation_bone = StringProperty(
            name='Orientation Bone', description='Metarig bone whose axes the controls and DEF bones use')

    @classmethod
    def parameters_ui(cls, layout, params):
        layout.label(text='GameReady Basic Chain — connected bones')
        layout.prop(params, 'gr_cb_parent_in_sequence')
        layout.prop(params, 'gr_cb_widget')
        layout.prop(params, 'gr_cb_tweak_widget')
        layout.prop(params, 'gr_cb_shape_scale')
        layout.prop(params, 'gr_cb_shape_size', slider=True)
        layout.prop(params, 'gr_cb_tweak_size', slider=True)
        for endpoint in ('start', 'end'):
            box = layout.box()
            box.label(text=endpoint.title() + ' Point')
            box.prop(params, 'gr_cb_override_' + endpoint + '_parent')
            if getattr(params, 'gr_cb_override_' + endpoint + '_parent'):
                box.prop(params, 'gr_cb_' + endpoint + '_parent')
        layout.prop(params, 'gr_cb_override_orientation')
        if params.gr_cb_override_orientation:
            layout.prop_search(params, 'gr_cb_orientation_bone', bpy.context.object.pose, 'bones')


def create_sample(obj):
    bpy.ops.object.mode_set(mode='EDIT')
    first = obj.data.edit_bones.new('Chain')
    first.head, first.tail = (0, 0, 0), (0, 1, 0)
    second = obj.data.edit_bones.new('Chain.001')
    second.head, second.tail = first.tail, (0.25, 2, 0)
    second.parent, second.use_connect = first, True
    first_name = first.name
    bpy.ops.object.mode_set(mode='OBJECT')
    obj.pose.bones[first_name].rigify_type = 'game_ready.chain_basic'
