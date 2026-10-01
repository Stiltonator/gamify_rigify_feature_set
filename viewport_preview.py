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
    'game_ready.spine': {
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


def _active_preview(context):
    obj = context.object
    bone = context.active_pose_bone
    if not obj or obj.type != 'ARMATURE' or obj.mode != 'POSE' or not bone:
        return None

    config = PREVIEW_CONFIGS.get(bone.rigify_type)
    if not config:
        return None

    params = bone.rigify_parameters
    if 'groups' not in config:
        if not all(getattr(params, key, False) for key in config['enabled']):
            return None
        return [_preview_item(obj, bone, params, config)]

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
                widget_bone_length, shape_flip_y))

    return previews


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
                  widget_bone_length=None, shape_flip_y=False):
    offset = Vector(getattr(params, config['offset']))
    scale = Vector(getattr(params, config['scale']))
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
    return (transform, _shape_edges(widget_type, config.get('widget_args')),
            config.get('color', (0.15, 0.8, 1.0, 0.95)))


def _shape_edges(widget_type, widget_args=None):
    """Get exact edge geometry when the widget is a Rigify geometry generator."""
    args_key = tuple(sorted((widget_args or {}).items()))
    cache_key = (widget_type, args_key)
    if cache_key in _widget_edge_cache:
        return _widget_edge_cache[cache_key]

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
    gpu.state.depth_test_set('LESS_EQUAL')
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
    if _draw_handle is None:
        _draw_handle = bpy.types.SpaceView3D.draw_handler_add(
            _draw_preview, (), 'WINDOW', 'POST_VIEW')


def unregister():
    global _draw_handle
    if _draw_handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handle, 'WINDOW')
        _draw_handle = None
    _widget_edge_cache.clear()
