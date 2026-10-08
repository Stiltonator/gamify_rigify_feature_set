"""Copy source bone and pose colours, including custom RGB palettes."""

SOURCE_KEY = 'gamify_metarig_color_source'


def _copy_color(source, target):
    target.palette = source.palette
    if source.palette == 'CUSTOM':
        for name in ('normal', 'select', 'active'):
            setattr(target.custom, name, getattr(source.custom, name))
        target.custom.show_colored_constraints = source.custom.show_colored_constraints


def apply_source_color(source, target):
    _copy_color(source.bone.color, target.bone.color)
    _copy_color(source.color, target.color)


def copy_metarig_color(rig, source_name, target_name):
    source = rig.generator.metarig.pose.bones[source_name]
    target = rig.get_bone(target_name)
    target[SOURCE_KEY] = source_name
    apply_source_color(source, target)


def restore_metarig_colors(metarig, generated):
    # Rigify applies collection colours after all rig configure/finalize hooks.
    # Restore explicit source colours at the end of generation so they prevail.
    for target in generated.pose.bones:
        source = metarig.pose.bones.get(target.get(SOURCE_KEY, ''))
        if source:
            apply_source_color(source, target)
