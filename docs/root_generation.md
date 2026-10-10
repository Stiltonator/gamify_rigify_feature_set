# Generated root defaults

The Gamify menu's **Root Bone Z Forward** option is disabled by default and saved
with the scene. Immediately after Rigify creates or selects its root bone,
Gamify orients its local Y axis along Blender +Z (up), and its local +Z along
Blender -Y (forward), in armature space. Root position and length are preserved.
The orientation is applied before rig bone generation and parenting.
When enabled, the root's pose-mode custom shape is rotated -90 degrees on X
to compensate for the bone orientation. This is assigned on each generation,
so repeated regeneration does not accumulate rotations.
When an existing target rig has its own object rotation (for example +90 on X
for export), regeneration builds in the metarig's rotation and compensates the
fresh armature data before restoring that target rotation. The existing object
rotation therefore does not rotate the regenerated skeleton a second time.

Disable the option to retain Rigify's original root orientation. Regenerate the
rig after changing the option. Existing custom root bones also receive the
selected orientation when the option is on.

The root's scale channels remain locked after generation, independently of this
orientation option.

**Root Flip Y**, in the same separate root-options menu section, defaults off.
It reverses the root's local X and Y axes by rotating 180 degrees around its
local Z, leaving Z facing the same direction. When both options are on, the
Z-forward orientation is applied first, followed by the Y flip.

After generation, Root Flip Y also rotates the generated armature -90 degrees
around world X, applies its rotation in Object Mode, and rotates it back +90
degrees around X. The object position and scale are retained. For an initially
unrotated rig, the resulting object X rotation is +90 degrees with the -90
rotation baked into the armature data. The rig's world-space rest geometry stays
in place. Regeneration removes the previous final +90 before generating fresh
data so the adjustment does not accumulate, including when the option is disabled.
Only the generated rig receives the rotation/apply operation.
Its direct child objects are temporarily unparented during this operation, then
reparented with their original parenting settings and world transforms preserved.
Objects parented to bones are restored to the same bones; deeper descendants
remain parented to their immediate parents throughout.
