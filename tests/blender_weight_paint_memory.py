"""Run in Blender with --background --factory-startup --python-exit-code 1."""
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import bpy
from gamify import weight_paint_memory as memory


def activate(name):
    bpy.ops.brush.asset_activate(
        asset_library_type='ESSENTIALS',
        relative_asset_identifier='brushes/essentials_brushes-mesh_weight.blend/Brush/' + name)
    memory._sync()
    return bpy.context.scene.tool_settings.weight_paint.brush


memory.register()
memory.register()
assert bpy.context.scene.gamify_remember_weight_accumulate
assert bpy.app.handlers.save_pre.count(memory._save_pre) == 1
bpy.ops.mesh.primitive_plane_add()
bpy.context.object.vertex_groups.new(name='Weights')
bpy.ops.object.mode_set(mode='WEIGHT_PAINT')
brush = activate('Paint')
assert brush.use_accumulate
brush.use_accumulate = False
memory._sync()
other = activate('Blur')
assert other.use_accumulate
assert not activate('Paint').use_accumulate
assert activate('Blur').use_accumulate
activate('Paint')
bpy.ops.object.mode_set(mode='OBJECT')
memory._sync()
bpy.ops.object.mode_set(mode='WEIGHT_PAINT')
memory._sync()
assert not bpy.context.scene.tool_settings.weight_paint.brush.use_accumulate

with tempfile.TemporaryDirectory(prefix='gamify_brush_test_') as directory:
    path = str(Path(directory) / 'brush_memory.blend')
    # Save immediately after toggling: save_pre must capture it without a timer tick.
    bpy.context.scene.tool_settings.weight_paint.brush.use_accumulate = True
    bpy.ops.wm.save_as_mainfile(filepath=path)
    bpy.context.scene.tool_settings.weight_paint.brush.use_accumulate = False
    bpy.ops.wm.open_mainfile(filepath=path)
    assert activate('Paint').use_accumulate
    bpy.context.scene.tool_settings.weight_paint.brush.use_accumulate = False
    bpy.ops.wm.save_as_mainfile(filepath=path)
    bpy.ops.wm.open_mainfile(filepath=path)
    assert not activate('Paint').use_accumulate
    assert activate('Blur').use_accumulate
    # Disabled memory must neither restore values nor save brush changes.
    brush = activate('Paint')
    assert not brush.use_accumulate
    bpy.context.scene.gamify_remember_weight_accumulate = False
    brush.use_accumulate = True
    memory._sync()
    assert brush.use_accumulate
    paint = bpy.context.scene.tool_settings.weight_paint
    assert not memory._read(memory._brush_key(paint, brush))
    bpy.ops.wm.save_as_mainfile(filepath=path)
    bpy.ops.wm.open_mainfile(filepath=path)
    assert not bpy.context.scene.gamify_remember_weight_accumulate
    brush = activate('Paint')
    brush.use_accumulate = True
    memory._sync()
    assert brush.use_accumulate
    bpy.context.scene.gamify_remember_weight_accumulate = True
    assert not brush.use_accumulate
    # New scenes share file preferences.
    scene = bpy.data.scenes.new('Another Scene')
    memory._remember('test', False)
    assert not scene[memory.STORAGE_KEY]['test']

memory.unregister()
assert not bpy.app.timers.is_registered(memory._tick)
assert memory._save_pre not in bpy.app.handlers.save_pre
assert not hasattr(bpy.types.Scene, 'gamify_remember_weight_accumulate')
print('WEIGHT_PAINT_MEMORY_OK')
