"""Transfer metarig custom-shape display settings without creating a widget."""

from rigify.utils.naming import choose_derived_bone, make_original_name


def copy_custom_shape(rig, source, target_name):
    target = rig.get_bone(target_name)
    for prop in source.bl_rna.properties:
        name = prop.identifier
        if ('custom_shape' in name and not prop.is_readonly
                and name != 'custom_shape_transform'):
            setattr(target, name, getattr(source, name))
    target.bone.show_wire = source.bone.show_wire
    transform = source.custom_shape_transform
    target.custom_shape_transform = None
    if transform:
        if transform == source:
            mapped = target_name
        else:
            original = rig.generator.org_rename_table.get(
                make_original_name(transform.name), make_original_name(transform.name))
            mapped = (choose_derived_bone(rig.generator, original, 'ctrl', by_owner=False)
                      or (transform.name if transform.name in rig.obj.pose.bones else original))
        target.custom_shape_transform = rig.obj.pose.bones.get(mapped)
    # Rigify assigns widget objects after finalize. Preserve this exact object,
    # including None, so stale WGT objects cannot replace it on regeneration.
    rig.generator.new_widget_table[target_name] = source.custom_shape
