# Print-Readiness — full reference tables

Detailed thresholds, rationale, and citations behind the `print-readiness` skill.
Sourced from Bambu Lab Wiki, Prusa Knowledge Base, Protolabs Network (Hubs) design
guides, Formlabs, and the Meshy 2026 AI 3D Print-Readiness Benchmark.

## Printer profiles (studio3d)

| profile   | nozzle | min wall | min feature | overhang limit | min hole | clearance |
|-----------|--------|----------|-------------|----------------|----------|-----------|
| `fdm_0.4` | 0.4 mm | 0.8 mm   | 0.4 mm      | ~50° (45° safe)| 2.0 mm   | 0.2 mm    |
| `fdm_0.2` | 0.2 mm | 0.4 mm   | 0.2 mm      | ~50°           | 1.0 mm   | 0.15 mm   |
| `resin`   | 0.05mm | 0.3 mm   | 0.1 mm      | ~45°           | 0.5 mm   | 0.1 mm    |

`MIN_WALL = max(2 × nozzle, 0.8)` for FDM. Walls SHOULD be `k × nozzle`.

## FDM design rules (0.4 mm nozzle)

| Feature | Minimum | Recommended | Why |
|---|---|---|---|
| Wall thickness | 0.8 mm | 1.2–2.0 mm (k×0.4) | <2 perimeters = weak; non-multiples leave voids |
| Embossed line width | 1.0 mm | 1.5 mm+ | must be ≥ ~2 extrusion lines to render |
| Embossed height | 0.5 mm | 0.8 mm+ | shorter washes out |
| Engraved line width | 0.5 mm | 0.8 mm+ | nozzle can't trace finer |
| Engraved depth | 0.3 mm | 0.5 mm+ | shallower disappears |
| Character height | 4 mm (emboss) / 3 mm (engrave) | 6 mm / 5 mm | readability |
| Vertical pin/peg dia | 5 mm | 5 mm + base fillet | sub-5 mm is fragile, no infill |
| Unsupported overhang | 45° from vertical | ≤ 45° (≤ 60–75° on 360° cooling) | each layer needs ≥50% support below |
| Unsupported bridge | ≤ 10 mm | ≤ 5 mm cosmetic | sag beyond; up to 30–100 mm tuned |
| Horizontal hole | teardrop or ≥ 2 mm dia | teardrop (45° apex) | kills 90° top overhang |
| Vertical hole | +0.1–0.25 mm oversize | model undersize + ream for fit | layers compress holes inward |
| Build-plate edge | 45° chamfer 0.4–0.6 mm | chamfer or EFC 0.1–0.25 mm | elephant's foot |
| Mating clearance | 0.2 mm snug | 0.3–0.5 mm moving | thermal + extrusion tolerance |

## Resin (SLA/MSLA) rules

| Feature | Minimum | Notes |
|---|---|---|
| Supported wall | 0.2–0.4 mm | thinnest of any process but fragile under cyclic load |
| Unsupported wall | 0.6 mm | |
| Embossed detail | 0.1 mm | |
| Engraved detail | 0.4 mm wide × 0.4 mm deep | |
| Min hole dia | 0.5–0.8 mm | <0.5 mm may close (Form3) |
| Hollow wall | ≥ 2.0 mm | mandatory for hollowed parts |
| Drain holes | ≥ 2 × ≥ 3.5 mm | drain + air vent at lowest local minimum; prevents cupping/explosion |
| Clearance | 0.1 press / 0.2 assembly / 0.5 moving | |
| Tolerance (Protolabs) | XY ±0.05 mm + 0.1% · Z ±0.13 mm + 0.1% | |
| Orientation | tilt flats 30–60° | reduces peel forces; support nubs leave 0.3–0.5 mm dimples |

## Anisotropy (FDM)
Z (inter-layer) tensile strength is ~30–50% of XY (sometimes as low as 15%). Orient
so primary load is parallel to layers. This is the single biggest strength lever and
competes with support-minimization — surface the tradeoff.

## Format: STL vs 3MF

| | STL | 3MF |
|---|---|---|
| Geometry | ✅ | ✅ |
| Units | ❌ (assumed mm) | ✅ (explicit) |
| Color / per-face | ❌ | ✅ |
| Materials / AMS mapping | ❌ | ✅ (≤ 32 colors auto-map) |
| Print settings | ❌ | ✅ |
| File size | baseline | 30–60% smaller |

For Bambu AMS multicolor → 3MF is mandatory. STL always imports as one uncolored
object requiring manual painting.

## Citations
- Bambu Lab Wiki — wall thickness, overhang, AMS/3MF
- Prusa Knowledge Base — overhangs (45–60°), bridging, hole compensation
- Protolabs Network (Hubs) — FDM & SLA design rules, tolerances
- Formlabs — resin wall/hole minimums, hollowing & drain holes
- Meshy 2026 AI 3D Print-Readiness Benchmark — D1–D4 framework, slicer pass rate
