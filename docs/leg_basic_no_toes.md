# GameReady Leg

Feature set: **GameReady Rig Types**, version 4.0.1

Author: **Anthony Carter and Susan (ChatGPT)**

Rigify type: **game_ready.leg** (category `game_ready`, rig `leg`).
The parameter panel is labelled **GameReady Leg**. This is the renamed former `game_ready.leg` type. Rigify identifiers use
Python package/module names rather than display names containing spaces.

## Install or upgrade

Enable Rigify in Preferences > Add-ons. Expand Rigify and install this ZIP in
its Feature Sets section, not through Blender's general add-on installer.

If GameReady Rig Types (or the earlier Custom Chain Starter) is installed,
remove that feature set first,
install this updated ZIP, and restart Blender. Before regenerating an existing
rig, enable **Force Widget Update** in Rigify > Advanced so the old cube widget
is replaced by the new foot shape. The package folder is now `gameready_rig_types_feature_set`. The `custom.basic_chain` type has been removed entirely. Replace any old
assignments with `game_ready.leg_basic_no_toes` on compatible three-bone chains.

## Metarig setup

1. Create exactly three connected bones: thigh -> shin -> foot.
2. Give the knee a slight bend in Edit Mode. A completely straight leg has no
   defined pole direction and is rejected with an explanatory error.
3. In Pose Mode, select the thigh and set Bone Properties > Rigify Type to
   `game_ready.leg_basic_no_toes`. Leave Rigify Type empty on the shin and foot.
4. Set the options that appear immediately below the type field.
5. Click Generate Rig under Armature Data Properties > Rigify.

Additional connected bones or connected branches are rejected. Separate parts,
such as toes, should be disconnected children with their own rig component.

## Options on the metarig's first bone

- **Initial FK / IK:** default value of the generated switch; 0 = FK, 1 = IK.
- **Pole Distance:** knee pole placement, as a fraction of thigh + shin length.
- **Pole Angle Offset:** optional correction to the automatically computed pole
  angle. Normally leave at zero.
- **Override Chain Parent:** enables an explicit parent for the entire leg chain.
- **Chain Parent:** exact GENERATED bone name, e.g. `DEF-pelvis` or `root`.
  This is a text field because generated bones may not yet exist on the metarig.

These are generation settings. Change them on the metarig, then regenerate.
An enabled override with an empty or nonexistent name raises an error.
Self-parenting and parenting the first DEF to its own DEF chain are rejected.
Use an independent bone; a target driven by this leg can cause a dependency cycle.

The chosen parent drives the FK thigh, IK chain start, ORG result root, first
DEF bone and settings control. Rotation inheritance is explicitly enabled.
Without an override, they use the metarig thigh's parent (or Rigify's root when
there is no parent). The shin DEF remains under the thigh DEF, and the foot DEF
under the shin DEF. The IK target and pole always remain under Rigify's root.
Existing saved parent settings carry over; the old property identifiers are
retained even though their labels now say Override Chain Parent / Chain Parent.

## Generated controls

For inputs named thigh.L, shin.L, foot.L:

- `thigh_fk.L`, `shin_fk.L`, `foot_fk.L`: FK rotation controls.
- `foot_ik.L`: move to position the ankle; rotate to orient the foot. Uses the
  same foot-shaped widget generator as Blender 5.0.1 Rigify's built-in `limbs.leg`.
- `thigh_pole.L`: knee bend direction.
- `thigh_settings.L`: holder for the `FK_IK` custom property.

Select any of these controls and use **GameReady Leg: FK / IK** in the generated
rig's Rig Main Properties panel (3D Viewport sidebar). The same value is under
Custom Properties on the settings bone. 0 = FK, 1 = IK; intermediate values blend.
The property can be keyframed. This version does not include automatic
pose-matching/snapping buttons: align the two control sets before switching if
you need a transition without a pose change. Both sets of controls stay visible.

The IK target and pole are left loose during component parenting, so Rigify
parents them to its generated root normally. Moving the rig root moves them.

## IK chain length

The solver acts on the thigh and shin. Its constraint is on `MCH-shin_ik.L`,
and the code counts back to `MCH-thigh_ik.L`, producing **Chain Length = 2**.
It cannot include the pelvis or root. The third input is the foot, controlled
by a separate rotation constraint. IK stretching is disabled.

The FK/IK blend is applied to a separate result chain, with local-space poses,
so it does not rely on varying the pole IK constraint's influence.

## Deform/export hierarchy

Exactly three DEF bones are created for this component:
`DEF-thigh.L`, `DEF-shin.L`, `DEF-foot.L` (using your input names).
Each has one B-Bone segment. Controls, ORG and MCH bones are non-deforming.
This is an animation rig; engine export still needs appropriate animation baking
and skeleton/export settings. Override Chain Parent lets you join the leg to the
intended skeleton hierarchy.

## Source and compatibility

The full implementation is `rigs/game_ready/leg_basic_no_toes.py`.
It targets Blender 5.0.1. Its Rigify API usage was checked against Blender's
v5.0.1 source (BaseRig, bone utilities, constraints/drivers, widgets, generated
UI and the generator's root-parenting stage).
Blender is not available in the authoring environment: Python syntax and a
mocked generation contract were checked, but actual Blender generation and
IK motion have not been validated. Confirm behaviour in your Blender version.

Sources:
- https://developer.blender.org/docs/features/animation/rigify/feature_sets/
- https://developer.blender.org/docs/features/animation/rigify/rig_class/
- https://developer.blender.org/docs/features/animation/rigify/utils/mechanism/
- https://docs.blender.org/manual/en/latest/animation/constraints/tracking/ik_solver.html
