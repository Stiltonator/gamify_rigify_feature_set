# Chain Bendy endpoint settings

**Shape Scale** multiplies both widget sizes and defaults to 0.1, with hard limits
of 0.001–100. Main Shape Size defaults to 3; Tweak Shape Size defaults to 1.
Both size sliders have soft limits of 0.01–10, and manual entry supports
0.001–100. The default main radius is therefore 0.3 and the default tweak widget
multiplier is 0.1. These settings affect widget display only, including merged
controls and tweaks. Existing saved size values remain saved; the new multiplier
also applies to them when regenerating.

The **Start Point** and **End Point** rollouts contain the respective main-control
omission, DEF omission, parent override, and mirror merge settings. The Start Point
parent override still sets the attachment for the whole chain, as before.

Enable **Mirror Merge Start** or **Mirror Merge End** on both mirrored chains.
The corresponding endpoints must coincide on world X=0, including matching Y/Z
positions. Each chain must extend onto the opposite side of that plane near the
selected endpoint. Interior geometry and bone counts can differ. Matching uses
a world-space tolerance of 0.00001 Blender units and does not depend on .L/.R names.
An unmatched or ambiguous pair generates independently and reports a warning.

A merged pair generates one main endpoint control if either chain enables it.
If both chains skip that control, only internal mechanism bones remain. Each
chain retains its joint controls and interior tweak/DEF samples.

Each successfully merged endpoint also has one shared centre tweak and DEF bone.
Their names omit the .L/.R side marker. For a chain starting on `Scarf.L` / `Scarf.R`,
the merged start control is `Scarf.000`, the tweak is `Scarf.000.Tweak`, and the
deformer is `DEF-Scarf.000`. A merged end uses the lowest free centre number
starting at 001. Existing names are checked explicitly to prevent collisions.
Independent main controls use `Scarf.001.L`, `Scarf.002.L`, etc. Tweak and DEF
samples have their own sequential numbering, with names such as
`Scarf.001.Tweak.L` and `DEF-Scarf.001.L`. The side suffix stays last, and points
on world X=0 omit it even without merging. Interior samples can outnumber the
main controls, so their numbering runs independently. Internal MCH names retain
their descriptive mechanism labels.
The tweak drives that DEF and follows the shared endpoint frame. If both sides
skip their endpoint DEF, neither the shared tweak nor DEF is generated; if either
side keeps it, the shared sample remains for both branches.

The seam uses the average of the two endpoint directions after reversing one
side's direction. Both internal tangents follow the same frame with opposite
local Y directions, preserving a smooth seam when the shared control rotates.
The tweak/DEF orientation override does not change these tangents.

Both endpoint parent targets are retained through internal parent anchors. Their
motion contributes equally to the shared endpoint. Different targets produce a
warning rather than preventing generation; DEF parenting retains each chain's
own parent settings for interior bones. A shared start DEF parents both outgoing
sequential branches. A shared end DEF uses the preceding DEF from the first
enabled side in source-bone name order when sequential parenting is enabled.
Otherwise the shared DEF uses that side's chain parent. This gives the shared
bone one deterministic hierarchy parent while both endpoint parent targets
continue to contribute to its motion. The same side supplies the centre sample's
orientation override and tweak appearance. With different main widget settings, the first enabled control
in source-bone name order supplies the shared control's appearance.

Warnings appear in Blender's console and in the generated armature object's
`gamify_bendy_merge_warnings` custom property. Gamify regeneration also reports
them through Blender's operator feedback.

Blender-free regression tests cover pairing, world-space eligibility, omission
combinations, generation order, opposite rest tangents, constraint wiring, and
parent mismatch feedback. Evaluated B-Bone deformation and rollout appearance
still require verification in Blender 5.0.1.
