---
name: print-readiness
description: Authoritative 3D-printing design rules and the print-readiness checklist for FDM and resin (SLA/MSLA). Use when modeling, reviewing, or validating any part destined for a 3D printer — wall thickness, overhangs, supports, bridging, holes, text/emboss, pins, fillets, clearances, orientation/anisotropy, elephant's-foot, units, and STL-vs-3MF choice. Encodes the 2026 AI 3D Print-Readiness Benchmark (D1 Mesh Integrity → D2 Slicer Pass → D3 Print Geometry → D4 Workflow) with hard numeric thresholds sourced from Bambu Lab, Prusa, Protolabs Network, and Formlabs.
---

# Print-Readiness Rules (FDM + Resin)

These rules use RFC-2119 language (MUST / SHOULD / MAY). Numeric constants are the
constraints the `studio3d` validator enforces. Apply them **while authoring**, not
just at the end — geometry that respects them passes the slicer the first time.

The model is scored on four independent dimensions (a model can pass one and fail
another). Full tables, rationale, and citations: see `reference/rules.md`.

```
D1 Mesh Integrity → D2 Slicer Pass → D3 Print Geometry → D4 Workflow
(prerequisite)      (core metric)    (physical limits)   (efficiency)
```

## D1 — Mesh Integrity (hard gate, blocks export)
- The mesh **MUST** be **watertight** (no open boundaries/holes).
- The mesh **MUST** be **2-manifold**: every edge shared by exactly 2 faces; no
  edges shared by >2 faces; no non-manifold vertices.
- Normals **MUST** be consistent and point **outward** (`is_volume == true`).
- There **MUST** be no self-intersections and no degenerate (zero-area) triangles.
- **Prefer manifold-by-construction CSG** (the studio3d DSL / manifold3d): boolean
  ops never emit non-manifold output, so D1 passes without repair. Validate with
  `is_watertight && is_winding_consistent && is_volume` and **reject** (don't
  silently repair) a model with residual self-intersections or open boundaries.

## D2 — Slicer Pass
- The model **MUST** open in Bambu Studio / OrcaSlicer / PrusaSlicer with no repair
  dialog and produce valid G-code. In practice, **D1 pass + valid volume ⇒ D2 pass**.

## D3 — Print Geometry Compliance (FDM, 0.4 mm nozzle default)
- **Walls MUST be ≥ 0.8 mm** (`max(2 × nozzle, 0.8)`), and SHOULD be integer
  multiples of the nozzle width (0.8 / 1.2 / 1.6 / 2.0 mm). Non-multiples force
  internal voids / weak spots.
- **Unsupported overhangs SHOULD stay ≤ 45° from vertical** (≤ 50–60° on
  360°-cooling printers). Steeper ⇒ enable supports or **reorient**.
- **Unsupported bridges SHOULD be ≤ 10 mm** (≤ 5 mm for cosmetic). Prefer
  reorienting to eliminate bridges.
- **Min printable feature ≈ 0.4 mm** (slicer auto-thickens below ~0.34 mm).
- **Holes**: vertical-axis holes print undersized — enlarge by ~½ the expected
  deviation (+0.1–0.25 mm) or model undersized and drill. **Horizontal holes MUST
  use a teardrop profile** (45° apex) or be ≥ 2 mm to avoid the 90° top overhang.
- **Pins/pegs < 5 mm diameter** are weak — add a **base fillet** or use an inserted
  metal pin. Fillet sharp internal corners (stress risers); **chamfer**, don't
  fillet, downward-facing edges.
- **Elephant's foot**: add a **45° chamfer (≈ 0.4–0.6 mm) on build-plate edges**, or
  rely on slicer elephant-foot compensation (0.1–0.25 mm).
- **Text/emboss**: embossed strokes **MUST be ≥ 1.0 mm wide × ≥ 0.5 mm tall**
  (recommend 1.5 / 0.8); engraved **≥ 0.5 mm wide × ≥ 0.3 mm deep**; char height
  ≥ 4 mm. Use bold sans-serif.
- **Mating clearance**: 0.2 mm snug, 0.3–0.5 mm moving (FDM).

### Resin (SLA/MSLA)
- Supported wall ≥ 0.3 mm; unsupported wall ≥ 0.6 mm; min feature ≈ 0.1 mm.
- **Hollowed parts MUST have ≥ 2 mm walls and ≥ 1 drain hole (ideally 2: drain +
  vent) of ≥ 3.5 mm at the lowest point** — trapped resin causes cupping/cracking.
- Clearance tiers: 0.5 mm moving, 0.2 mm assembly, 0.1 mm press-fit. Tilt flats 30–60°.

## Strength & orientation (anisotropy — the biggest lever)
- FDM parts are anisotropic: **Z (inter-layer) strength is only ~30–50% of XY.**
- **Orient so the primary load runs PARALLEL to layer lines** (in the strong XY
  plane) and the weak Z bond is out of the main tensile/bending path — "treat layers
  like wood grain." This often **competes** with support-minimization; when they
  conflict, surface the tradeoff to the user rather than choosing silently.

## D4 — Workflow / Units / Format
- **Geometry MUST be authored and emitted in millimeters.** STL is unitless; a model
  authored in inches imports 25.4× too small.
- **Default export = 3MF** (carries mm units + color + materials + print settings;
  30–60% smaller than STL). For **Bambu AMS multicolor, MUST use 3MF** with per-face
  color, ≤ 32 distinct colors. Emit **STL** as a secondary/legacy artifact.

## Quick checklist before declaring a model done
1. Watertight + manifold + outward normals (D1) — `studio3d validate <file>`.
2. Walls ≥ profile minimum; no features below min size (D3).
3. Overhangs ≤ limit, or supports/reorientation noted.
4. Build-plate edges chamfered; horizontal holes teardropped; pins ≥ 5 mm or filleted.
5. Units = mm; correct format (3MF for color/Bambu, STL for legacy).
6. Load orientation aligned with layer lines for the expected load.
