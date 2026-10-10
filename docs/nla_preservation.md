# Animation preservation on regeneration

Gamify automatically preserves the generated rig object's NLA tracks and clips
when regenerating that metarig's existing target rig. Track order, names, mute
and solo settings, strip timing, action slots, blending, strip animation and
modifiers are copied using Blender's native animation-data copy operation.
The active action and its playback settings are also restored. Actions are
reused, not duplicated. Newly generated rig drivers are retained instead of
restoring obsolete drivers from the previous rig.

Animation is restored after generation and the optional Root Flip Y adjustment.
The backup also allows restoration if generation raises an exception. Temporary
backup objects are removed afterward. First-time generation is unaffected.

This preserves the animation setup; it does not retarget animation when control
bone names or the rig structure change. Action paths must still match the new rig.
