# Custom shapes on copy rigs

With **Control** enabled and **Widget** disabled, `game_ready.super_copy`
copies the metarig bone's custom shape onto its generated control. It preserves
scale, translation, rotation, bone-size scaling, wire width, wire display and
custom-shape transform settings. Without a source shape, the control uses
ordinary bone display. Enabling Widget still creates the selected widget and
uses Gamify's widget offset/scale settings.

`game_ready.raw_copy` preserves the original bone name and native raw-copy
constraint/parent relinking options. It carries the source custom shape and its
display settings into the generated rig unless an optional widget is selected.
Bones whose original names start with `MCH-` or `DEF-` receive no custom shape
or generated widget, since Rigify puts them in hidden collections.

Custom-shape transform references are mapped into the generated armature,
preferring the referenced bone's generated control. Self references point to
the generated bone itself. Shape objects are reused, rather than duplicated.
Regeneration honours changed or removed source shapes.

Blender's generator reserves a bone named `root` for either an untyped bone or
`basic.raw_copy`; use the native type for that special bone.
