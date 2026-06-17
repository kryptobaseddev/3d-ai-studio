# CSG / DSL authoring errors → fixes (studio3d manifold kernel)

## Result is not watertight after a boolean
Cause: a degenerate boolean — exactly coplanar faces or a zero-thickness cut/join.
Fix: nudge one dimension by 0.01mm so faces are not exactly coincident; add an eps
(~0.01mm) overlap to union/difference operands. Never "fix" by disabling validation.

## Thin walls below the minimum (D3 warning)
Cause: outer decoration cut through the wall, or wall thinner than 2x nozzle.
Fix: model a SMOOTH inner bore (plain cylinder/revolve) inside a separately decorated
outer shell so the wall stays >= 0.8mm everywhere; thicken the base/wall; raise the
parameter. Never cut decoration through to the bore.

## Disconnected parts (n_components > 1 when it should be one piece)
Cause: sub-shapes placed without enough overlap to fuse under union.
Fix: increase overlap between adjacent primitives before union (organic blends want
heavy overlap), or add a connecting strut/fillet; verify with hull() for soft necks.

## Steep overhang needs support (D3 suggestion)
Cause: a face steeper than ~45-50deg from vertical that is not bed contact.
Fix: reorient the part (the orient pass tries 6 axis-aligned poses), add a 45deg
chamfer/gusset, or convert a flat ceiling to a sloped/teardrop profile.

## Horizontal round hole sags
Fix: subtract a teardrop() instead of a cylinder for horizontal bores, or keep the
bore >= 2mm. Orient the teardrop apex toward +Z (the build direction).

## High genus / unexpected handles
Cause: a boolean artifact created an internal tunnel/void.
Fix: simplify the construction; check for a cutter that punched all the way through
when it should have stopped; rebuild the region from cleaner primitives.

## Sandbox: import blocked / NameError on open/os
Cause: the script tried to import a non-whitelisted module or use a blocked builtin.
Fix: use only the injected DSL symbols + math/numpy; never open files or import os.
Read inputs via load_mesh(path) (the only file entry point) and parameters via P.

## twist_extrude / loft not watertight
Cause: open profile or mismatched point counts across loft sections.
Fix: give a closed star-convex profile; ensure every loft section has the SAME number
of points; the centroid-cap fan handles lobed profiles automatically.
