# GameReady Chain Basic

Assign `game_ready.chain_basic` to the first bone of a connected, unbranched
chain. Leave its connected children's rig types blank.

The mechanism follows Rigify's experimental `super_chain`: a hidden
`MCH-AUTO-<source name>` backing bone spans the endpoints and preserves the
rest offsets of the chain's intersections as the endpoints move. A visible
`<source name>.Pivot` control moves the middle of the chain, with its influence
falling toward the ends. Each point has an `MCH-INT-` frame parenting its tweak.
Endpoint frames follow the start/end main controls; interior frames inherit the
backing's length and orientation and blend the pivot's local transform.

There are N+1 tweaks and N+1 DEF bones for N source bones, plus start/end main
controls and a pivot. A one-bone chain is supported, although it has no interior
points for the pivot to influence. Start and end must occupy distinct positions.

DEF bones copy the corresponding tweak's world transform. All generated bones
have one segment; DEF bones are unconnected and have no Stretch-To constraints.
The backing alone uses Stretch-To, with volume preservation disabled. It is an
internal mechanism, not a deform bone. The original bones follow the tweaks.

**Parent in Sequence** selects the DEF hierarchy: sequential, or all subsequent
DEFs under the first DEF. Tweaks always use their MCH-INT parents.

**Override Start Parent** attaches the start main control, backing and first DEF
to the exact entered name. Otherwise automatic parenting prefers the metarig
parent's DEF counterpart, then its original name, then root with a warning.
Automatic parenting never chooses an ORG counterpart.

**Override End Parent** attaches the end main control to the exact entered name.
Without it, both endpoint main controls share the resolved start parent. The
final DEF retains its chosen DEF hierarchy. Overrides accept `NONE` for no
parent, and explicit ORG names are allowed. Missing targets and dependency
cycles raise generation errors.

**Override Bone Orientation** sets the endpoint controls, tweaks and DEF axes
from the reference metarig bone. Otherwise these use their original segment
axes, averaged at intersections. Backing, pivot and interior frames keep their
common chain frame so pivot blending remains consistent.

Main and tweak widgets have separate shape choices and sizes. **Shape Scale**
defaults to 0.1; main size to 3; tweak size to 1. Scale multiplies each size.
Sizes have a 0.01–10 soft slider and allow manual values up to 100. Widgets are
independent of bone length and replaced when their shape changes on regeneration.

Names derive from the source metarig name: `Chain.000`, `Chain.001.Tweak.L`,
and `DEF-Chain.001.L`, for example. Points on world X=0 omit the side suffix.

`tests/blender_chain_basic.py` checks generation and regeneration in Blender,
rest positions, pivot and endpoint motion, hierarchy modes, orientation, widgets,
parent overrides, invalid parents and automatic parent fallback. It runs in a
separate factory-startup scene without saving files or preferences.
