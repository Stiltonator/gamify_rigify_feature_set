# Generated root defaults

The Gamify menu's **Root Bone Z Forward** option is disabled by default and saved
with the scene. Immediately after Rigify creates or selects its root bone,
Gamify orients its local Y axis along Blender +Z (up), and its local +Z along
Blender -Y (forward), in armature space. Root position and length are preserved.
The orientation is applied before rig bone generation and parenting.
When enabled, the root's pose-mode custom shape is rotated -90 degrees on X
to compensate for the bone orientation. This is assigned on each generation,
so repeated regeneration does not accumulate rotations.

Disable the option to retain Rigify's original root orientation. Regenerate the
rig after changing the option. Existing custom root bones also receive the
selected orientation when the option is on.

The root's scale channels remain locked after generation, independently of this
orientation option.
