# DFAM rules — design for additive manufacturing (FDM, 0.4mm nozzle)

## Walls and thickness
Minimum wall is 2x the nozzle: 0.8mm for a 0.4mm nozzle. Prefer multiples of the
nozzle width (0.8 / 1.2 / 1.6mm) so the slicer fills walls with whole perimeters.
Resin: 0.3mm min wall. 0.2mm nozzle: 0.4mm min wall. Vertical walls are stronger
than top/bottom skins; thin unsupported spans sag.

## Overhangs and bridges
Unsupported overhangs must stay within ~45 degrees of vertical (modern printers
reach 50-70 degrees with cooling). Steeper needs supports or a reorientation.
Unsupported horizontal bridges should be <= ~10mm. Chamfer or fillet steep
transitions to make them self-supporting. A 45-degree gusset between perpendicular
plates is self-supporting and adds stiffness.

## Holes
Horizontal holes print as a teardrop (45-degree apex) or be >= 2mm diameter — a
bare horizontal round hole sags at the top (the unsupported 90-degree arc). Vertical
holes print slightly undersized; add ~0.1-0.25mm or model oversize. Min hole ~2mm
(FDM 0.4). Min printable feature ~0.4mm.

## Tolerances and fits (tune per printer; drive every fit from ONE clearance var)
Press / interference fit: ~0.1mm. Snug fit: ~0.2mm. Sliding / loose fit: ~0.3-0.4mm.
Print a tolerance test once per printer/material before committing fits.

## Elephant's foot
The first layers squish out. Chamfer build-plate edges ~0.4-0.6mm, or rely on the
slicer's elephant-foot compensation (~0.2mm).

## Threads and inserts
Model threads only >= M5 (or use a thread library tuned via slop). Below that prefer
heat-set inserts or tapped holes. Heat-set insert pilot holes (CNC Kitchen):
M3 ~= 4.0mm, M4 ~= 5.6mm, M5 ~= 6.4mm, M6 ~= 8.0mm diameter.

## Anisotropy / orientation
FDM parts are anisotropic: the Z (layer-to-layer) bond is only ~30-55% as strong as
in-plane. Orient so loads run ALONG layers, like wood grain. This competes with
minimizing supports — surface the tradeoff, don't silently pick.

## Text
Embossed text >= 1.0mm wide x >= 0.5mm tall, bold sans-serif. Engraved >= 0.5mm wide.

## Boolean hygiene (manifold by construction)
Add a small eps overlap (~0.01mm) to boolean cuts/joins so coincident faces don't
create zero-thickness walls or z-fighting. Exactly-coplanar faces or zero-thickness
cuts produce a degenerate (non-watertight) boolean — nudge a dimension by 0.01mm.
