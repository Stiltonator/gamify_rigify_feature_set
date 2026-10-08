"""Gamify defaults applied after successful Rigify generation."""

from functools import wraps


_enabled = False
_original_generate = None
_wrapped_generate = None


def register():
    global _enabled, _original_generate, _wrapped_generate
    from rigify import generate
    _enabled = True
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
        return result

    _wrapped_generate = generate_with_defaults
    generate.generate_rig = _wrapped_generate


def unregister():
    global _enabled, _original_generate, _wrapped_generate
    from rigify import generate
    _enabled = False
    if generate.generate_rig is _wrapped_generate:
        generate.generate_rig = _original_generate
        _original_generate = None
        _wrapped_generate = None
