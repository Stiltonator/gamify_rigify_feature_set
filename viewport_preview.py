"""Reusable viewport previews for GameReady rig-type widget transforms."""

import bpy
import gpu
import inspect
import math
from types import SimpleNamespace
from gpu_extras.batch import batch_for_shader
from mathutils import Euler, Matrix, Vector
from rigify.utils import widgets as rigify_widgets


# Add another entry or preview group here to reuse this system for other rigs.
# Property values refer to Rigify parameters on the active metarig bone.
PREVIEW_CONFIGS = {
    'game_ready.super_copy': {
        'widget_param': 'super_copy_widget_type',
        'offset': 'gr_sc_widget_offset',
        'scale': 'gr_sc_widget_scale',
        'enabled': ('make_control', 'make_widget'),
    },
    'game_ready.spine_unity_humanoid': {
        'groups': (
            {
                'widget': 'cube', 'offset': 'gr_spine_torso_widget_offset',
                'scale': 'gr_spine_torso_widget_scale',
                'rotation': 'gr_spine_torso_widget_rotation', 'anchors': 'root',
                'orientation': 'armature_y',
                'center_at_hip': True,
                'size_from_spine_length': 0.6,
                'color': (0.15, 0.8, 1.0, 0.95),
            },
            {
                'widget': 'circle',
                'widget_args': {'radius': 1.1, 'head_tail': 0.0, 'head_tail_x': 1.0},
                'offset': 'gr_spine_hips_widget_offset',
                'scale': 'gr_spine_hips_widget_scale',
                'rotation': 'gr_spine_hips_widget_rotation', 'anchors': 'hip',
                'size_from_spine_length': 0.25,
                'color': (0.15, 0.8, 1.0, 0.95),
            },
            {
                'widget': 'circle',
                'widget_args': {'radius': 1.1, 'head_tail': 0.0, 'head_tail_x': 1.0},
                'offset': 'gr_spine_chest_widget_offset',
                'scale': 'gr_spine_chest_widget_scale',
                'rotation': 'gr_spine_chest_widget_rotation', 'anchors': 'chest',
                'size_from_spine_length': 1.0 / 3.0,
                'color': (0.15, 0.8, 1.0, 0.95),
            },
            {
                'widget': 'circle', 'widget_args': {'radius': 1.0, 'head_tail': 0.5},
                'offset': 'gr_spine_fk_widget_offset', 'scale': 'gr_spine_fk_widget_scale',
                'anchors': 'fk', 'enabled': ('make_fk_controls',),
                'color': (0.3, 1.0, 0.55, 0.95),
            },
            {
                'widget': 'sphere', 'widget_args': {'radius': 0.5},
                'offset': 'gr_spine_tweak_widget_offset', 'scale': 'gr_spine_tweak_widget_scale',
                'anchors': 'tweaks', 'length_factor': 0.5,
                'color': (1.0, 0.65, 0.15, 0.95),
            },
        ),
    },
    'game_ready.leg_toes': {'generator': 'leg_toes'},
    'game_ready.finger': {'generator': 'finger'},
    'game_ready.super_chain': {'generator': 'super_chain'},
}

_draw_handle = None
_widget_edge_cache = {}


def tag_view3d_redraw(_self, context):
    """Redraw 3D views immediately after a preview parameter changes."""
    window_manager = context.window_manager if context else bpy.context.window_manager
    if not window_manager:
        return
    for window in window_manager.windows:
        if window.screen:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()


def _previews_for_bone(obj, bone, selected_bone_names, active_bone_name):
    """Return preview line batches for one Rigify metarig component."""
    config = PREVIEW_CONFIGS.get(bone.rigify_type)
    if not config:
        return []

    params = bone.rigify_parameters
    generator = config.get('generator')
    if generator == 'leg_toes':
        return _leg_toes_previews(obj, bone, params, selected_bone_names, active_bone_name)
    if generator == 'finger':
        return _finger_previews(obj, bone, params, selected_bone_names, active_bone_name)
    if generator == 'super_chain':
        return _super_chain_previews(obj, bone, params, selected_bone_names, active_bone_name)

    if 'groups' not in config:
        if not all(getattr(params, key, False) for key in config['enabled']):
            return []
        return [_preview_item(obj, bone, params, config, selected_bone_names=selected_bone_names, active_bone_name=active_bone_name)]

    chain = _connected_pose_chain(obj, bone)
    previews = []
    for group in config['groups']:
        if not all(getattr(params, key, False) for key in group.get('enabled', ())):
            continue

        if group['anchors'] == 'root':
            if group.get('center_at_hip'):
                hip = chain[0]
                hip_center = hip.matrix @ Vector((0.0, hip.bone.length * 0.5, 0.0))
                anchors = [(hip, hip_center - hip.matrix.translation, 1.0)]
            else:
                anchors = [(chain[0], Vector((0.0, 0.0, 0.0)), 1.0)]
        elif group['anchors'] == 'hip':
            anchors = [(chain[0], Vector((0.0, 0.0, 0.0)), 1.0)]
        elif group['anchors'] == 'chest':
            anchors = [(chain[-1], Vector((0.0, 0.0, 0.0)), 1.0)]
        elif group['anchors'] == 'fk':
            pivot = int(getattr(params, 'pivot_pos', 0))
            anchors = [
                (part, Vector((0.0, part.bone.length if index < pivot else 0.0, 0.0)),
                 1.0, index < pivot)
                for index, part in enumerate(chain)
            ]
        else:  # Tweak widgets occur at every connected joint and at the chain end.
            anchors = [(part, Vector((0.0, 0.0, 0.0)), group.get('length_factor', 1.0))
                       for part in chain]
            anchors.append((chain[-1], Vector((0.0, chain[-1].bone.length, 0.0)),
                            group.get('length_factor', 1.0)))

        widget_bone_length = None
        if 'size_from_spine_length' in group:
            widget_bone_length = sum(part.bone.length for part in chain) * group['size_from_spine_length']

        for anchor_data in anchors:
            anchor, local_shift, length_factor = anchor_data[:3]
            shape_flip_y = anchor_data[3] if len(anchor_data) > 3 else False
            previews.append(_preview_item(
                obj, anchor, params, group, local_shift, length_factor,
                widget_bone_length, shape_flip_y, selected_bone_names, active_bone_name))

    return previews


def _simple_preview(obj, anchor, params, widget, selected_bone_names, active_bone_name,
                    *, color, widget_args=None, local_shift=None, length_factor=1.0):
    config = {
        'widget': widget,
        'widget_args': widget_args or {},
        'offset': (0.0, 0.0, 0.0),
        'scale': (1.0, 1.0, 1.0),
        'color': color,
    }
    return _preview_item(
        obj, anchor, params, config, local_shift=local_shift,
        length_factor=length_factor, selected_bone_names=selected_bone_names,
        active_bone_name=active_bone_name,
    )


def _leg_toes_previews(obj, bone, params, selected_bone_names, active_bone_name):
    '''Preview the main FK/IK and tweak widgets generated by limbs.leg.'''
    chain = _connected_pose_chain(obj, bone)
    if len(chain) < 4:
        return []

    previews = []
    fk_color = (0.3, 1.0, 0.55, 0.95)
    ik_color = (0.15, 0.8, 1.0, 0.95)
    tweak_color = (1.0, 0.65, 0.15, 0.95)

    for index, anchor in enumerate(chain[:4]):
        if index < 2:
            shape, args = 'limb', {}
        else:
            shape = 'circle'
            args = {'radius': 0.4, 'head_tail': 0.0 if index == 2 else 0.5}
        previews.append(_simple_preview(
            obj, anchor, params, shape, selected_bone_names, active_bone_name,
            color=fk_color, widget_args=args,
        ))

    # Native tweaks are at each thigh/shin segment start and the foot start.
    segments = max(1, int(getattr(params, 'segments', 1)))
    for org_index in (0, 1):
        anchor = chain[org_index]
        for segment_index in range(segments):
            local_shift = Vector((0.0, anchor.bone.length * segment_index / segments, 0.0))
            previews.append(_simple_preview(
                obj, anchor, params, 'sphere', selected_bone_names, active_bone_name,
                color=tweak_color, local_shift=local_shift,
                length_factor=1.0 / (2.0 * segments),
            ))
    previews.append(_simple_preview(
        obj, chain[2], params, 'sphere', selected_bone_names, active_bone_name,
        color=tweak_color, length_factor=0.5,
    ))

    thigh, shin, foot, toe = chain[:4]
    previews.append(_simple_preview(
        obj, thigh, params, 'game_ready_ik_arrow', selected_bone_names, active_bone_name,
        color=ik_color,
    ))

    # Match Rigify's pole location from the projected shin vector.
    thigh_head = thigh.matrix.translation
    thigh_tail = thigh.matrix @ Vector((0.0, thigh.bone.length, 0.0))
    shin_head = shin.matrix.translation
    shin_tail = shin.matrix @ Vector((0.0, shin.bone.length, 0.0))
    total_vector = shin_tail - thigh_head
    shin_vector = shin_tail - shin_head
    elbow_vector = shin_vector.project(total_vector) - shin_vector
    if total_vector.length > 1e-8 and elbow_vector.length > 1e-8:
        pole_position = thigh_tail + elbow_vector.normalized() * total_vector.length
        pole_shift = thigh.matrix.to_3x3().inverted() @ (pole_position - thigh_head)
        previews.append(_simple_preview(
            obj, thigh, params, 'sphere', selected_bone_names, active_bone_name,
            color=ik_color, local_shift=pole_shift,
        ))

    # Rigify offsets this foot widget to the metarig foot tail.
    previews.append(_simple_preview(
        obj, foot, params, 'game_ready_foot', selected_bone_names, active_bone_name,
        color=ik_color, local_shift=Vector((0.0, foot.bone.length, 0.0)),
    ))

    heel = next((obj.pose.bones[child.name] for child in foot.bone.children
                 if not child.use_connect and not child.children), None)
    if heel:
        previews.append(_simple_preview(
            obj, heel, params, 'sphere', selected_bone_names, active_bone_name,
            color=ik_color, length_factor=0.5,
        ))

    if getattr(params, 'foot_pivot_type', 'ANKLE') == 'ANKLE_TOE':
        previews.append(_simple_preview(
            obj, toe, params, 'sphere', selected_bone_names, active_bone_name,
            color=ik_color, local_shift=Vector((0.0, toe.bone.length, 0.0)),
            length_factor=0.5,
        ))

    if getattr(params, 'extra_ik_toe', False):
        previews.append(_simple_preview(
            obj, toe, params, 'circle', selected_bone_names, active_bone_name,
            color=ik_color, widget_args={'radius': 0.4, 'head_tail': 0.5},
        ))
    return previews


def _finger_previews(obj, bone, params, selected_bone_names, active_bone_name):
    '''Preview FK circles, the tip and optional IK control for super_finger.'''
    chain = _connected_pose_chain(obj, bone)
    if not chain:
        return []

    previews = []
    fk_color = (0.3, 1.0, 0.55, 0.95)
    ik_color = (0.15, 0.8, 1.0, 0.95)
    for anchor in chain:
        previews.append(_simple_preview(
            obj, anchor, params, 'circle', selected_bone_names, active_bone_name,
            color=fk_color, widget_args={'radius': 0.3, 'head_tail': 0.5},
        ))

    last = chain[-1]
    previews.append(_simple_preview(
        obj, last, params, 'circle', selected_bone_names, active_bone_name,
        color=fk_color, widget_args={'radius': 0.3, 'head_tail': 0.0},
        local_shift=Vector((0.0, last.bone.length, 0.0)), length_factor=0.5,
    ))
    axis = str(getattr(params, 'primary_rotation_axis', 'automatic'))
    previews.append(_simple_preview(
        obj, chain[0], params, 'game_ready_finger_master', selected_bone_names,
        active_bone_name, color=ik_color, widget_args={'flip_xz': 'Z' in axis},
    ))

    if getattr(params, 'make_extra_ik_control', False):
        previews.append(_simple_preview(
            obj, last, params, 'sphere', selected_bone_names, active_bone_name,
            color=ik_color, local_shift=Vector((0.0, last.bone.length, 0.0)),
            length_factor=0.7,
        ))
    return previews


def _super_chain_previews(obj, bone, params, selected_bone_names, active_bone_name):
    '''Preview custom endpoint, pivot and tweak widgets made by super_chain.'''
    chain = _connected_pose_chain(obj, bone)
    if not chain:
        return []

    axis = getattr(params, 'gr_sc_widget_axis', 'y')
    offset = float(getattr(params, 'gr_schain_widget_offset', 0.0)) * chain[0].bone.length * 0.5
    previews = []
    main_color = (0.15, 0.8, 1.0, 0.95)
    tweak_color = (1.0, 0.65, 0.15, 0.95)

    def add_shape(anchor, radius, cube, invert=False, local_shift=None, is_main=False):
        previews.append(_simple_preview(
            obj, anchor, params, 'game_ready_chain', selected_bone_names,
            active_bone_name,
            color=main_color if is_main else tweak_color,
            widget_args={'radius': radius, 'cube': cube, 'invert': invert,
                         'axis': axis, 'offset': offset},
            local_shift=local_shift,
        ))

    if len(chain) > 2:
        pivot_index = len(chain) // 2
        pivot_shift = Vector((0.0, chain[pivot_index].bone.length * 0.5, 0.0)) if len(chain) % 2 else None
        add_shape(chain[pivot_index], 0.15, True, local_shift=pivot_shift)
    for anchor in chain[1:]:
        add_shape(anchor, 0.2, True)

    add_shape(chain[0], 0.3, False, is_main=True)
    last = chain[-1]
    add_shape(last, 0.3, False, invert=axis in {'y', '-y'},
              local_shift=Vector((0.0, last.bone.length, 0.0)), is_main=True)
    return previews


def _active_preview(context):
    """Return previews for the active component or all preview-capable components."""
    obj = context.active_object
    if not obj or obj.type != 'ARMATURE' or obj.mode != 'POSE':
        return []

    # Widget previews are metarig editing aids. Rigify-generated armatures can
    # retain rig-type metadata, so require a valid metarig and reject rig IDs.
    if not _is_rigify_metarig(context, obj):
        return []

    scene = context.scene
    if scene and getattr(scene, 'gamify_preview_all_gizmos', False):
        bones = (bone for bone in obj.pose.bones if bone.rigify_type)
    else:
        bone = context.active_pose_bone
        bones = (bone,) if bone else ()

    selected_pose_bones = getattr(context, 'selected_pose_bones', None) or ()
    selected_bone_names = {pose_bone.name for pose_bone in selected_pose_bones}
    active_pose_bone = context.active_pose_bone
    active_bone_name = (
        active_pose_bone.name
        if active_pose_bone and active_pose_bone.name in selected_bone_names
        else None
    )

    previews = []
    for bone in bones:
        previews.extend(_previews_for_bone(obj, bone, selected_bone_names, active_bone_name))
    return previews


def _is_rigify_metarig(context, obj):
    """Return true only for a Rigify metarig, never a generated rig."""
    if obj.get('rig_id') or obj.data.get('rig_id'):
        return False

    try:
        from rigify.utils.rig import is_valid_metarig
        return bool(is_valid_metarig(context))
    except (ImportError, AttributeError, RuntimeError, TypeError):
        return False


def _connected_pose_chain(obj, root):
    chain = [root]
    current = root
    while True:
        children = [child for child in current.bone.children if child.use_connect]
        if len(children) != 1:
            break
        current = obj.pose.bones[children[0].name]
        chain.append(current)
    return chain


def _preview_item(obj, anchor, params, config, local_shift=None, length_factor=1.0,
                  widget_bone_length=None, shape_flip_y=False, selected_bone_names=None,
                  active_bone_name=None):
    offset_value = config.get('offset', (0.0, 0.0, 0.0))
    scale_value = config.get('scale', (1.0, 1.0, 1.0))
    offset = Vector(getattr(params, offset_value) if isinstance(offset_value, str) else offset_value)
    scale = Vector(getattr(params, scale_value) if isinstance(scale_value, str) else scale_value)
    widget_param = config.get('widget_param')
    widget_type = getattr(params, widget_param, 'circle') if widget_param else config['widget']
    widget_type = widget_type or 'circle'

    # Bone-size scaling changes widget geometry; widget translation remains
    # an absolute offset in the shape transform's bone space.
    if widget_bone_length is not None:
        scale *= widget_bone_length
    elif anchor.use_custom_shape_bone_size:
        scale *= anchor.bone.length * length_factor

    shift = local_shift if local_shift is not None else Vector((0.0, 0.0, 0.0))
    if config.get('orientation') == 'armature_y':
        # Rigify aligns the master control to armature-space +Y, independently
        # of the source hips bone's rotation. Keep the preview on that axis.
        anchor_transform = Matrix.Translation(anchor.matrix.translation + shift)
    else:
        anchor_transform = anchor.matrix.copy() @ Matrix.Translation(shift)

    rotation_name = config.get('rotation')
    rotation = Euler(getattr(params, rotation_name), 'XYZ') if rotation_name else Euler((0.0, 0.0, 0.0))
    transform = (obj.matrix_world @ anchor_transform @ Matrix.LocRotScale(offset, rotation, scale))
    if shape_flip_y:
        transform @= Matrix.Diagonal((1.0, -1.0, 1.0, 1.0))
    color = _selection_tinted_color(
        anchor, config.get('color', (0.15, 0.8, 1.0, 0.95)),
        selected_bone_names or set(), active_bone_name)
    return (transform, _shape_edges(widget_type, config.get('widget_args')), color)


def _selection_tinted_color(anchor, base_color, selected_bone_names, active_bone_name):
    """Dim preview colors for selected and unselected bones like Pose Mode bones."""
    if active_bone_name == anchor.name:
        intensity = 1.0
        alpha = 0.95
    elif anchor.name in selected_bone_names:
        intensity = 0.68
        alpha = 0.85
    else:
        intensity = 0.24
        alpha = 0.65

    return (
        base_color[0] * intensity,
        base_color[1] * intensity,
        base_color[2] * intensity,
        min(base_color[3], alpha),
    )


def _shape_edges(widget_type, widget_args=None):
    """Get exact edge geometry when the widget is a Rigify geometry generator."""
    args_key = tuple(sorted((widget_args or {}).items()))
    cache_key = (widget_type, args_key)
    if cache_key in _widget_edge_cache:
        return _widget_edge_cache[cache_key]

    if widget_type == 'game_ready_chain':
        args = widget_args or {}
        radius = float(args.get('radius', 0.3))
        rh = radius if args.get('cube', False) else radius / 2.0
        if args.get('invert', False):
            verts = [(rh, rh, rh), (radius, -radius, radius), (-radius, -radius, radius),
                     (-rh, rh, rh), (rh, rh, -rh), (radius, -radius, -radius),
                     (-radius, -radius, -radius), (-rh, rh, -rh)]
        else:
            verts = [(radius, radius, radius), (rh, -rh, rh), (-rh, -rh, rh),
                     (-radius, radius, radius), (radius, radius, -radius),
                     (rh, -rh, -rh), (-rh, -rh, -rh), (-radius, radius, -radius)]
        edges = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6),
                 (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)]
        axis = args.get('axis', 'y')
        sign = -1.0 if axis.startswith('-') else 1.0
        axis_name = axis[-1]
        if axis_name == 'x':
            rotation = Matrix.Rotation(-sign * math.pi / 2.0, 4, 'Z')
            translation = Vector((float(args.get('offset', 0.0)), 0.0, 0.0))
        elif axis_name == 'z':
            rotation = Matrix.Rotation(sign * math.pi / 2.0, 4, 'X')
            translation = Vector((0.0, 0.0, float(args.get('offset', 0.0))))
        else:
            rotation = Matrix.Diagonal((1.0, sign, 1.0, 1.0))
            translation = Vector((0.0, float(args.get('offset', 0.0)), 0.0))
        transform = Matrix.Translation(translation) @ rotation
        result = [(tuple(transform @ Vector(verts[a])), tuple(transform @ Vector(verts[b])))
                  for a, b in edges]
        _widget_edge_cache[cache_key] = result
        return result

    if widget_type == 'game_ready_foot':
        verts = [(-0.7, -0.5242649, 0.0), (-0.7, 1.225735, 0.0),
                 (0.7, 1.225735, 0.0), (0.7, -0.5242649, 0.0),
                 (-0.7, 0.252735, 0.0), (0.7, 0.252735, 0.0),
                 (-0.7, 0.975735, 0.0), (0.7, 0.975735, 0.0)]
        edges = [(1, 2), (0, 3), (0, 4), (3, 5), (4, 6), (1, 6), (5, 7), (2, 7)]
        result = [(verts[a], verts[b]) for a, b in edges]
        _widget_edge_cache[cache_key] = result
        return result

    if widget_type == 'game_ready_ik_arrow':
        verts = [(0.1, 0.0, -0.3), (0.1, 0.7, -0.3), (-0.1, 0.0, -0.3),
                 (-0.1, 0.7, -0.3), (0.2, 0.7, -0.3), (0.0, 1.0, -0.3),
                 (-0.2, 0.7, -0.3), (0.1, 0.0, 0.3), (0.1, 0.7, 0.3),
                 (-0.1, 0.0, 0.3), (-0.1, 0.7, 0.3), (0.2, 0.7, 0.3),
                 (0.0, 1.0, 0.3), (-0.2, 0.7, 0.3)]
        edges = [(0, 1), (2, 3), (1, 4), (4, 5), (3, 6), (5, 6), (0, 2),
                 (7, 8), (9, 10), (8, 11), (11, 12), (10, 13), (12, 13), (7, 9)]
        result = [(verts[a], verts[b]) for a, b in edges]
        _widget_edge_cache[cache_key] = result
        return result

    if widget_type == 'game_ready_finger_master':
        verts = [(0.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.05, 1.0, 0.0),
                 (0.05, 1.1, 0.0), (-0.05, 1.1, 0.0), (-0.05, 1.0, 0.0)]
        if (widget_args or {}).get('flip_xz', False):
            verts = [(z, y, x) for x, y, z in verts]
        edges = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 1)]
        result = [(verts[a], verts[b]) for a, b in edges]
        _widget_edge_cache[cache_key] = result
        return result

    entry = rigify_widgets._registered_widgets.get(widget_type)
    if entry:
        callback, _valid_args, default_args = entry
        generator = inspect.unwrap(callback)
        try:
            first_arg = next(iter(inspect.signature(generator).parameters))
            if first_arg in {'geom', 'geometry'}:
                geom = SimpleNamespace(verts=[], edges=[], faces=[])
                generator(geom, **(default_args | (widget_args or {})))
                edges = {tuple(edge) for edge in geom.edges}
                for face in geom.faces:
                    edges.update((face[i], face[(i + 1) % len(face)]) for i in range(len(face)))
                points = [tuple(v) for v in geom.verts]
                result = [(points[a], points[b]) for a, b in edges]
                _widget_edge_cache[cache_key] = result
                return result
        except (TypeError, ValueError, AttributeError, IndexError):
            pass

    return _fallback_shape_edges(widget_type)


def _circle_points(radius=0.5, segments=48, plane='XZ'):
    points = []
    for index in range(segments):
        angle = index * 2.0 * math.pi / segments
        a, b = radius * math.cos(angle), radius * math.sin(angle)
        points.append((a, 0.0, b) if plane == 'XZ' else (a, b, 0.0))
    return points


def _fallback_shape_edges(widget_type):
    """Approximate non-geometry widget callbacks using a familiar wire shape."""
    name = (widget_type or 'circle').lower()
    if name in {'circle', 'ring'}:
        points = _circle_points()
        return [(points[i], points[(i + 1) % len(points)]) for i in range(len(points))]

    if name in {'sphere', 'ball'}:
        edges = []
        for plane in ('XZ', 'XY', 'YZ'):
            points = _circle_points(plane=plane)
            edges.extend((points[i], points[(i + 1) % len(points)]) for i in range(len(points)))
        return edges

    verts = [
        (-0.5, -0.5, -0.5), (0.5, -0.5, -0.5), (0.5, 0.5, -0.5), (-0.5, 0.5, -0.5),
        (-0.5, -0.5, 0.5), (0.5, -0.5, 0.5), (0.5, 0.5, 0.5), (-0.5, 0.5, 0.5),
    ]
    return [(verts[a], verts[b]) for a, b in (
        (0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4),
        (0, 4), (1, 5), (2, 6), (3, 7),
    )]


def _draw_preview():
    context = bpy.context
    if not context.region or context.region.type != 'WINDOW':
        return

    previews = _active_preview(context)
    if not previews:
        return

    shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    draw_in_front = bool(context.scene and context.scene.gamify_gizmos_draw_in_front)
    gpu.state.depth_test_set('NONE' if draw_in_front else 'LESS_EQUAL')
    try:
        shader.bind()
        shader.uniform_float('viewportSize', (context.region.width, context.region.height))
        shader.uniform_float('lineWidth', 2.0)
        for transform, edges, color in previews:
            coords = []
            for start, end in edges:
                coords.extend((transform @ Vector(start), transform @ Vector(end)))
            if coords:
                batch = batch_for_shader(shader, 'LINES', {'pos': coords})
                shader.uniform_float('color', color)
                batch.draw(shader)
    finally:
        gpu.state.depth_test_set('NONE')
        gpu.state.blend_set('NONE')



def register():
    global _draw_handle
    if not hasattr(bpy.types.Scene, 'gamify_preview_all_gizmos'):
        bpy.types.Scene.gamify_preview_all_gizmos = bpy.props.BoolProperty(
            name="Preview All Gizmos",
            description="Show previews for all metarig components supported by the preview system",
            default=False,
            update=tag_view3d_redraw,
        )
    if not hasattr(bpy.types.Scene, 'gamify_gizmos_draw_in_front'):
        bpy.types.Scene.gamify_gizmos_draw_in_front = bpy.props.BoolProperty(
            name="Gizmos Draw In Front",
            description="Draw widget previews over scene geometry",
            default=False,
            update=tag_view3d_redraw,
        )
    if _draw_handle is None:
        _draw_handle = bpy.types.SpaceView3D.draw_handler_add(
            _draw_preview, (), 'WINDOW', 'POST_VIEW')


def unregister():
    global _draw_handle
    if hasattr(bpy.types.Scene, 'gamify_preview_all_gizmos'):
        del bpy.types.Scene.gamify_preview_all_gizmos
    if hasattr(bpy.types.Scene, 'gamify_gizmos_draw_in_front'):
        del bpy.types.Scene.gamify_gizmos_draw_in_front
    if _draw_handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handle, 'WINDOW')
        _draw_handle = None
    _widget_edge_cache.clear()
