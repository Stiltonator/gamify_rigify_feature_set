"""Preserve object animation across Rigify's animation-data reset."""

import bpy


def snapshot_animation(rig):
    """Use Blender's native copy to retain strips, slots, curves and modifiers."""
    if not rig or not rig.animation_data:
        return None
    if not rig.animation_data.nla_tracks and not rig.animation_data.action:
        return None
    snapshot = bpy.data.objects.new('Gamify animation backup', None)
    context = bpy.context
    context.scene.collection.objects.link(snapshot)
    try:
        with context.temp_override(object=rig, active_object=rig,
                                   selected_objects=[rig, snapshot],
                                   selected_editable_objects=[rig, snapshot]):
            bpy.ops.object.make_links_data(type='ANIMATION')
    except Exception:
        bpy.data.objects.remove(snapshot, do_unlink=True)
        raise
    context.scene.collection.objects.unlink(snapshot)
    for driver in list(snapshot.animation_data.drivers):
        snapshot.animation_data.drivers.remove(driver)
    return snapshot


def restore_animation(context, rig, snapshot):
    """Restore saved animation without replacing newly generated drivers."""
    # from_existing copies drivers without remapping their rig target IDs to a
    # temporary object, unlike making a copy of the entire generated object.
    drivers = bpy.data.objects.new('Gamify generated drivers', None)
    try:
        if rig.animation_data:
            target = drivers.animation_data_create()
            for driver in rig.animation_data.drivers:
                target.drivers.from_existing(src_driver=driver)

        # Native animation linking copies all NLA strip types, including meta
        # strips, and their nested animation. RNA reconstruction loses details.
        context.scene.collection.objects.link(snapshot)
        with context.temp_override(object=snapshot, active_object=snapshot,
                                   selected_objects=[snapshot, rig],
                                   selected_editable_objects=[snapshot, rig]):
            bpy.ops.object.make_links_data(type='ANIMATION')

        animation = rig.animation_data_create()
        for driver in list(animation.drivers):
            animation.drivers.remove(driver)
        if drivers.animation_data:
            for driver in drivers.animation_data.drivers:
                animation.drivers.from_existing(src_driver=driver)
    finally:
        bpy.data.objects.remove(drivers, do_unlink=True)
