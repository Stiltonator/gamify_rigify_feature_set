"""Remember Weight Paint Accumulate per brush asset in the current blend file."""

import hashlib
import json

import bpy
from bpy.app.handlers import persistent


STORAGE_KEY = 'gamify_weight_paint_accumulate_v1'
_owner = object()
_active = None


def _brush_key(paint, brush):
    reference = paint.brush_asset_reference
    if reference and reference.relative_asset_identifier:
        identity = ('asset', reference.asset_library_type,
                    reference.asset_library_identifier, reference.relative_asset_identifier)
    else:
        identity = ('brush', brush.library.filepath if brush.library else '', brush.name)
    # Blender IDProperty keys have a 63-character limit.
    return hashlib.sha256(json.dumps(identity).encode('utf-8')).hexdigest()[:40]


def _read(key):
    for scene in bpy.data.scenes:
        values = scene.get(STORAGE_KEY)
        if values is not None and key in values:
            return bool(values[key])
    return True


def _remember(key, value):
    # Replicate across scenes so changing/deleting a scene doesn't lose file preferences.
    for scene in bpy.data.scenes:
        if scene.library:
            continue
        if STORAGE_KEY not in scene:
            scene[STORAGE_KEY] = {}
        values = scene[STORAGE_KEY]
        if key not in values or bool(values[key]) != value:
            values[key] = value


def _capture():
    if _active and bpy.context.scene and bpy.context.scene.gamify_remember_weight_accumulate:
        key, brush = _active
        try:
            _remember(key, bool(brush.use_accumulate))
        except ReferenceError:
            pass  # The brush may have been deleted or replaced by undo.


def _sync():
    global _active
    context = bpy.context
    if not context.scene or not context.scene.gamify_remember_weight_accumulate:
        _active = None
        return
    paint = context.scene.tool_settings.weight_paint if context.scene else None
    brush = paint.brush if paint and context.object and context.object.mode == 'WEIGHT_PAINT' else None
    if brush is None:
        _capture()
        _active = None
        return
    key = _brush_key(paint, brush)
    if _active and _active[0] == key and _active[1] == brush:
        _capture()
    else:
        _capture()
        brush.use_accumulate = _read(key)
        _active = (key, brush)
        _capture()


def _tick():
    _sync()
    return 0.25


def _subscribe():
    bpy.msgbus.clear_by_owner(_owner)
    bpy.msgbus.subscribe_rna(key=(bpy.types.Brush, 'use_accumulate'),
                             owner=_owner, args=(), notify=_sync)


@persistent
def _load_pre(_):
    global _active
    _active = None


@persistent
def _load_post(_):
    _subscribe()
    _sync()


@persistent
def _save_pre(_):
    _sync()


def _enabled_changed(scene, context):
    global _active
    # Drop tracking without recording changes made while memory is disabled.
    _active = None
    if scene == context.scene and scene.gamify_remember_weight_accumulate:
        _sync()


def register():
    if not hasattr(bpy.types.Scene, 'gamify_remember_weight_accumulate'):
        bpy.types.Scene.gamify_remember_weight_accumulate = bpy.props.BoolProperty(
            name='Remember Weight-Brush Accumulate Setting',
            description='Remember Accumulate per Weight Paint brush in this file; new brushes default to on. Disable to stop recording and restoring settings',
            default=True, update=_enabled_changed)
    for handlers, callback in ((bpy.app.handlers.load_pre, _load_pre),
                               (bpy.app.handlers.load_post, _load_post),
                               (bpy.app.handlers.save_pre, _save_pre)):
        if callback not in handlers:
            handlers.append(callback)
    _subscribe()
    if not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick, first_interval=0.25, persistent=True)


def unregister():
    global _active
    _capture()
    _active = None
    bpy.msgbus.clear_by_owner(_owner)
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    for handlers, callback in ((bpy.app.handlers.load_pre, _load_pre),
                               (bpy.app.handlers.load_post, _load_post),
                               (bpy.app.handlers.save_pre, _save_pre)):
        if callback in handlers:
            handlers.remove(callback)
    if hasattr(bpy.types.Scene, 'gamify_remember_weight_accumulate'):
        del bpy.types.Scene.gamify_remember_weight_accumulate
