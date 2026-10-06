# Chain Bendy endpoint settings

The **Start Point** and **End Point** rollouts contain the respective main-control
omission, DEF omission, parent override, and mirror merge settings. The Start Point
parent override still sets the attachment for the whole chain, as before.

Enable **Mirror Merge Start** or **Mirror Merge End** on both mirrored chains.
The corresponding endpoints must coincide on world X=0. Chain geometry must be
mirrored across that plane, with the same bone order and count. Matching uses a
world-space tolerance of 0.00001 Blender units and does not depend on .L/.R names.
An unmatched or ambiguous pair generates independently and reports a warning.

A merged pair generates one main endpoint control if either chain enables it.
If both chains skip that control, only internal mechanism bones remain. Each
chain retains its joint controls, tweaks, and independently configured DEF bones.

The seam uses the average of the two endpoint directions after reversing one
side's direction. Both internal tangents follow the same frame with opposite
local Y directions, preserving a smooth seam when the shared control rotates.
The tweak/DEF orientation override does not change these tangents.

Both endpoint parent targets are retained through internal parent anchors. Their
motion contributes equally to the shared endpoint. Different targets produce a
warning rather than preventing generation; DEF parenting retains each chain's
own parent settings. With different widget settings, the first enabled control
in source-bone name order supplies the shared control's appearance.

Warnings appear in Blender's console and in the generated armature object's
`gamify_bendy_merge_warnings` custom property. Gamify regeneration also reports
them through Blender's operator feedback.

Blender-free regression tests cover pairing, world-space eligibility, omission
combinations, generation order, opposite rest tangents, constraint wiring, and
parent mismatch feedback. Evaluated B-Bone deformation and rollout appearance
still require verification in Blender 5.0.1.
