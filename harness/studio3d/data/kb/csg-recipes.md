# Proven CSG recipes (studio3d DSL — manifold by construction)

All units mm. Read named parameters from the injected `P` dict with defaults, e.g.
`w = P.get("width", 40)`, so the model is regenerable/tweakable from design.json.

## Parametric box with friction-fit lid
Outer box, hollow via difference of an inner box (walls = P.get("wall",2)); lid is a
shallow box with a lip sized to the inner opening minus 2*clearance (P.get("clearance",0.2)).
Drive every mating gap from the one clearance parameter.

## Wall bracket with gusset (self-supporting)
Two perpendicular plates (box) unioned with a 45-degree wedge() gusset between them so
no supports are needed. Mounting holes: subtract cylinders through each plate; for a
horizontal bolt hole use teardrop() so it prints clean.

## Hex standoff / nut blank
prism(6, d=across_corners, h=H) minus a central cylinder bore. For a heat-set insert,
size the bore to the pilot diameter (M3 ~4.0, M4 ~5.6mm).

## Knob with D-shaft
cylinder (knurl by unioning a circular_pattern of thin boxes around the rim) minus a
shaft: a cylinder intersected with a box to cut the flat (D profile); add clearance.

## Twisted vase (real twist)
twist_extrude(profile, height=H, turns=P.get("turns",1.5)). Keep the wall via a smooth
inner bore: build the outer twisted shell, then difference a plain revolve/cylinder bore
leaving wall = P.get("wall",1.6). Never twist the bore.

## Tapered / curved body
loft([(profile_at_z0, 0), (profile_at_zmid, mid), (profile_at_top, H)]) — same point
count per section. Great for nozzles, vases, organic torsos.

## Stylized organic (animal/figure) — author BY PROPORTION
Define a head-unit H from the reference brief; place/size every part as a multiple of H.
Blend overlapping ellipsoid()/sphere() with heavy overlap so they fuse under union; use
hull(head, body) for a soft neck. Eyes/beak/ears sized from the reference eye_rule.

## Cable clip / comb (must actually grip)
A C-channel: a slot() (stadium) cut from a block, with the opening narrower than the
cable diameter by an interference amount so it snaps and holds. Min wall >= 0.8mm.

## Phone stand (cradle must hold the phone)
A back rest at a viewing angle (rotated box) joined to a base lip that captures the
phone's bottom edge; ensure the lip + back form ONE connected solid (union, enough
overlap) — verify n_components == 1.
