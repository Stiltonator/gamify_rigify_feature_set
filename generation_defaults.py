"""Gamify defaults applied after successful Rigify generation."""

from functools import wraps
from math import radians
import bpy
from mathutils import Matrix, Vector


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
        if _enabled and generator.scene.gamify_root_flip_y:
            root = generator.obj.data.edit_bones[generator.root_bone]
            orientation = root.matrix.copy()
            # Rotate about local Z: reverse X and Y, retaining local Z and head.
            root.matrix = orientation @ Matrix.Rotation(radians(180), 4, 'Z')
        return result

    _wrapped_create_root = create_root_with_orientation
    generate.Generator._Generator__create_root_bone = _wrapped_create_root


def _apply_root_flip_object_rotation(context, rig):
    """Bake -90 degrees world X, then leave the object rotated +90 degrees X."""
    def rotate_x(angle):
        location = rig.matrix_world.translation.copy()
        rig.matrix_world = Matrix.Rotation(radians(angle), 4, 'X') @ rig.matrix_world
        rig.matrix_world.translation = location
        context.view_layer.update()

    context.view_layer.update()
    children = [(child, child.parent_type, child.parent_bone,
                 tuple(child.parent_vertices), child.matrix_parent_inverse.copy(),
                 child.matrix_world.copy()) for child in rig.children]
    try:
        for child, _, _, _, _, world in children:
            child.parent = None
            child.matrix_world = world
        context.view_layer.update()
        # Only the generated armature is transformed, regardless of selection.
        with context.temp_override(object=rig, active_object=rig,
                                   selected_objects=[rig], selected_editable_objects=[rig]):
            bpy.ops.object.mode_set(mode='OBJECT')
            rotate_x(-90)
            bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
            context.view_layer.update()
            rotate_x(90)
    finally:
        # Restore object and bone parenting even if applying rotation fails.
        for child, parent_type, parent_bone, vertices, inverse, _ in children:
            child.parent = rig
            child.parent_type = parent_type
            child.parent_bone = parent_bone
            child.parent_vertices = vertices
            child.matrix_parent_inverse = inverse
        context.view_layer.update()
        for child, _, _, _, _, world in children:
            child.matrix_world = world
        context.view_layer.update()
    rig['gamify_root_flip_applied'] = True


def register():
    global _enabled, _original_generate, _wrapped_generate
    from rigify import generate
    _enabled = True
    if not hasattr(bpy.types.Scene, 'gamify_root_z_forward'):
        bpy.types.Scene.gamify_root_z_forward = bpy.props.BoolProperty(
            name='Root Bone Z Forward', default=False,
            description='Orient the generated root immediately after creation: local Y up (Blender +Z), local Z forward (Blender -Y)')
    if not hasattr(bpy.types.Scene, 'gamify_root_flip_y'):
        bpy.types.Scene.gamify_root_flip_y = bpy.props.BoolProperty(
            name='Root Flip Y', default=False,
            description='Reverse root local X/Y while keeping Z; after generation rotate the rig -90 degrees on X, apply rotation, then rotate it back +90 degrees')
    _register_root_orientation(generate)
    if _wrapped_generate is not None:
        return
    _original_generate = generate.generate_rig

    @wraps(_original_generate)
    def generate_with_defaults(context, metarig):
        from .nla_preservation import snapshot_animation, restore_animation
        previous = metarig.data.rigify_target_rig
        animation = snapshot_animation(previous) if _enabled else None
        if _enabled and previous and previous.get('gamify_root_flip_applied', False):
            # Rigify reuses the target object's transform on regeneration. Undo
            # our previous final +90 before it copies fresh metarig bone data.
            location = previous.matrix_world.translation.copy()
            previous.matrix_world = Matrix.Rotation(radians(-90), 4, 'X') @ previous.matrix_world
            previous.matrix_world.translation = location
            del previous['gamify_root_flip_applied']
            context.view_layer.update()
        target_matrix = None
        if _enabled and previous:
            # Rigify copies metarig-space bones but retains the target object's
            # rotation. Generate in the metarig's rotation, then rebase the new
            # armature data into the retained target rotation below.
            target_matrix = previous.matrix_world.copy()
            location, _, scale = target_matrix.decompose()
            previous.matrix_world = Matrix.LocRotScale(
                location, metarig.matrix_world.to_quaternion(), scale)
            context.view_layer.update()
        try:
            result = _original_generate(context, metarig)
            if _enabled:
                rig = metarig.data.rigify_target_rig
                if rig and rig.type == 'ARMATURE':
                    if target_matrix is not None:
                        rig.data.transform(target_matrix.inverted() @ rig.matrix_world)
                        rig.matrix_world = target_matrix
                        context.view_layer.update()
                        target_matrix = None
                    from .rigs.game_ready.bone_colors import restore_metarig_colors
                    restore_metarig_colors(metarig, rig)
                    root = rig.pose.bones.get('root')
                    if root:
                        root.lock_scale = (True, True, True)
                        if context.scene.gamify_root_z_forward:
                            root.custom_shape_rotation_euler.x = radians(-90)
                    if context.scene.gamify_root_flip_y:
                        _apply_root_flip_object_rotation(context, rig)
            return result
        finally:
            if target_matrix is not None:
                previous.matrix_world = target_matrix
                context.view_layer.update()
            if animation:
                try:
                    rig = metarig.data.rigify_target_rig or previous
                    restore_animation(context, rig, animation)
                finally:
                    bpy.data.objects.remove(animation, do_unlink=True)

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
    if hasattr(bpy.types.Scene, 'gamify_root_flip_y'):
        del bpy.types.Scene.gamify_root_flip_y
    if generate.generate_rig is _wrapped_generate:
        generate.generate_rig = _original_generate
        _original_generate = None
        _wrapped_generate = None
