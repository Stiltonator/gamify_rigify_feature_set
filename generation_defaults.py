"""Gamify defaults applied after successful Rigify generation."""

from functools import wraps
from math import radians
import bpy
from mathutils import Vector


_enabled = False
_original_generate = None
_wrapped_generate = None
_original_create_root = None
_wrapped_create_root = None


def _register_root_orientation(generate):
    global _original_create_root, _wrapped_create_root
    if _wrapped_create_root is not None:
        return
    original = generate.Generator._Generator__create_root_bone
    _original_create_root = original

    @wraps(original)
    def create_root_with_orientation(generator):
        result = original(generator)
        if _enabled and generator.scene.gamify_root_z_forward:
            from rigify.utils.bones import align_bone_z_axis
            root = generator.obj.data.edit_bones[generator.root_bone]
            root.tail = root.head + Vector((0, 0, root.length))
            align_bone_z_axis(generator.obj, root.name, Vector((0, -1, 0)))
        return result

    _wrapped_create_root = create_root_with_orientation
    generate.Generator._Generator__create_root_bone = _wrapped_create_root


def register():
    global _enabled, _original_generate, _wrapped_generate
    from rigify import generate
    _enabled = True
    if not hasattr(bpy.types.Scene, 'gamify_root_z_forward'):
        bpy.types.Scene.gamify_root_z_forward = bpy.props.BoolProperty(
            name='Root Bone Z Forward', default=False,
            description='Orient the generated root immediately after creation: local Y up (Blender +Z), local Z forward (Blender -Y)')
    _register_root_orientation(generate)
    if _wrapped_generate is not None:
        return
    _original_generate = generate.generate_rig

    @wraps(_original_generate)
    def generate_with_defaults(context, metarig):
        result = _original_generate(context, metarig)
        if _enabled:
            rig = metarig.data.rigify_target_rig
            if rig and rig.type == 'ARMATURE':
                from .rigs.game_ready.bone_colors import restore_metarig_colors
                restore_metarig_colors(metarig, rig)
                root = rig.pose.bones.get('root')
                if root:
                    root.lock_scale = (True, True, True)
                    if context.scene.gamify_root_z_forward:
                        root.custom_shape_rotation_euler.x = radians(-90)
        return result

    _wrapped_generate = generate_with_defaults
    generate.generate_rig = _wrapped_generate


def unregister():
    global _enabled, _original_generate, _wrapped_generate
    global _original_create_root, _wrapped_create_root
    from rigify import generate
    _enabled = False
    if generate.Generator._Generator__create_root_bone is _wrapped_create_root:
        generate.Generator._Generator__create_root_bone = _original_create_root
        _original_create_root = None
        _wrapped_create_root = None
    if hasattr(bpy.types.Scene, 'gamify_root_z_forward'):
        del bpy.types.Scene.gamify_root_z_forward
    if generate.generate_rig is _wrapped_generate:
        generate.generate_rig = _original_generate
        _original_generate = None
        _wrapped_generate = None
