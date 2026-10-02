# Gamify - Game Ready Rig Types — 0.402

Author: **Anthony Carter and Susan (ChatGPT)**  
Target: **Blender 5.0.1 / Rigify**

Ok this is my best attempt to explain/document this here.

###  What is this, and what does this do?
The primary purpose of this rigify feature set (an 'addon' for rigify)  is to make available 'rig_types' that are compatible with unity (and possibly other game engines).
For example, there should be no instances of 'stretch-to' constraints on deformer bones*.   The 'heirarchy' of the skeleton on export to fbx, should only exclusively include other deform bones**.

In order to keep general rigify functionality, that has required some switching around of things and some fun stuff may have been lost (although i am not currently aware of anything specifically, this is just a warning)  -since the primary goal here is for a working rig in unity.. and complete parity between blender visualization and unity final animation i choose that over 'ease of use' for the animator. (in mind of myself, sorry if you are reading this and you are not me - but thems the breaks).

Finally, there may be 'conveniences' added -such as..  i have stolen the idea from cloudrig, because it seemed very nice.. To have the ability to preview how the 'rig_type' will generate whilst manipulating the meta-rig. So, you can see where all the 'animation gizmos' will land on your skeleton before generation and you have the option to adjust these with offsets... This makes generation less of a 'guessing game' and allows you to set more up whilst generating.

Ideally, in my mind, this adds missing nicities that should allow to keep the metarig around and regenerate your rig and tweak it as you go... As i find more things missing that i require (currently there is no way to maintain linkage to shape keys and drivers or something like that.. which would be nice )   --if i can develop this features into this i may do so.


*Stretch-to constraints introduces non-uniform scaling, which is inherited down a bone chain and has a 'knock-on effect' on the child bones.. Therefore, animations appear differently in unity than they do in a game engine. (volume correction on the constraint compounds this issue).

** 'other bones' such as  mechanism/org bones are not wanted in unity, the root being the obvious exception... When you export to FBX with 'Deform only' turned on, if you have these bones sitting inbetween other deform bones they come along for the ride.  When these extra bones are 'missing' from the heirarchy (especially if they have kind of offset) i have seen instances of the visual parity breaking between blender and unity. This is being avoid by avoiding them entirely. (This issue itself is really the primary reason for this feature_set - a new field is introduced in all rig types that allows you to explictly set what bone the deform bone will be parented to.)

## Rig types

| Rigify type | Based on | Summary |
| --- | --- | --- |
| `game_ready.leg_basic_no_toes` | GameReady implementation | Existing three-bone FK/IK leg. |
| `game_ready.leg_toes` | `limbs.leg` | Full native leg controls, toes, foot roll, switching and pose matching with the established DEF hierarchy. |
| `game_ready.arm` | `limbs.arm` | Native arm controls, FK/IK, wrist pivot option and pose matching. |
| `game_ready.spine` | `spines.basic_spine` | Native basic spine controls and tweak chain. |
| `game_ready.finger` | `limbs.super_finger` | Native FK finger, optional IK control and matching tools. |
| `game_ready.super_copy` | `basic.super_copy` | Native single-bone copy rig, with configurable DEF parent and widget transforms. |

The three new rigs expose **Override Chain Parent** and **Chain Parent** on the starting bone. If enabled, enter the exact generated name of a DEF bone, such as `DEF-pelvis`. The start controls and first DEF bone follow that attachment. DEF chains parent only to DEF bones. With no source parent, the first DEF bone stays parentless; Rigify controls can still use its root as their control parent.

`game_ready.super_copy` adds a world-space Copy Transforms constraint from its generated DEF bone to its generated control bone when both Deform and Control are enabled. It displays a wire preview of the selected widget in Pose Mode while its bone is active. The preview follows **Widget Offset** as an absolute bone-space translation and **Widget Scale** with the selected bone's custom-shape bone-length scaling. It uses Rigify's registered widget geometry when the widget is a geometry generator. The viewport helper is reusable by adding another rig type's parameter names to `viewport_preview.py`'s `PREVIEW_CONFIGS` table.

`game_ready.spine` provides **Custom Shape Visuals** settings for the torso master cube, hip circle, chest circle, FK controls and tweak controls. Torso, hip and chest each have independent position, rotation and scale settings. Their previews use Rigify's native control lengths: 60% of the spine chain for the torso master, one quarter for hips and one third for chest. The torso preview is positioned at the center of the hip metarig bone while keeping the master control's armature-space +Y alignment. Hip-side FK previews reflect the FK widget geometry along local Y, matching Rigify. Matching wire previews appear in Pose Mode. The FK fields and preview are disabled when FK controls are turned off.

## Shared DEF rules

- Generated DEF bones use one B-Bone segment.
- No DEF bone receives a Stretch-To constraint.
- Where a native DEF Stretch-To previously pointed to the next tweak/chain target, it is replaced by Damped Track on +Y after Copy Transforms. This preserves direction without Stretch-To scale changes.
- DEF parent chains are checked after generation. A non-DEF parent is rejected.

The finger template uses Stretch-To only on its internal MCH driver chain for its optional IK mechanics; its DEF bones use Copy Transforms only. These MCH constraints are not deformation-bone constraints.

For the arm, the native multi-segment option is retained. Additional segments are unconnected; the first DEF bone for a child source bone parents to the first DEF bone for its source parent bone, and is unconnected so its rest position is preserved.

## Assigning the types

Start from the matching Rigify metarig type/sample, or use an existing chain with the template's expected bone count and shape. Assign the GameReady type only to the first bone of that component and leave the type blank on its other bones. The native template provides the relevant chain requirements and control layout. For the spine, use a chain accepted by `spines.basic_spine`; for arm and finger, preserve the source template's bone order and connected chain.

The new types inherit Rigify's native rig generation and animation UI rather than copying its snap operators. Native FK/IK switches, pose-matching buttons and other controls are retained where the source template provides them.

## Install/update

1. Save your Blender file.
2. Remove the installed GameReady feature set in Preferences > Add-ons > Rigify > Feature Sets.
3. Install this ZIP using Rigify's Feature Sets installer and restart Blender.
4. Regenerate the rig. Enable Force Widget Update in Rigify > Advanced if you need existing widgets replaced.

## Verification

The package passed Python syntax compilation, ZIP structure checks and static checks for identifiers, parent options and DEF Stretch-To exclusions. Blender is not installed in this authoring environment, so generation, arm/spine/finger motion, pose matching and snapping still need verification in Blender 5.0.1.
