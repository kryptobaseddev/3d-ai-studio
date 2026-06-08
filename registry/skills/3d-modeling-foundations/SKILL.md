---
name: 3d-modeling-foundations
description: Core concepts for agent-driven 3D modeling — constructive solid geometry (CSG), what manifold/watertight means and why it matters, coordinate systems and millimeter units, mesh vs B-rep, file formats (STL/3MF/GLB/STEP), and how to ROUTE a request to the right engine (local CSG for mechanical/functional parts vs a generative backend for organic shapes). Use to ground any 3D-generation decision before authoring.
---

# 3D Modeling Foundations

## Constructive Solid Geometry (CSG)
Build complex solids by combining primitives (box, cylinder, sphere, cone, prism)
with boolean operations — **union** (∪, fuse), **difference** (−, cut), and
**intersection** (∩, common volume) — plus transforms. CSG is the natural language
of an LLM modeler: each step is explicit, parametric, and inspectable. With a robust
boolean kernel (`manifold3d`), CSG output is **watertight and 2-manifold by
construction**, which is exactly what a slicer needs.

## Manifold & watertight (why it's the #1 prerequisite)
A printable solid must be a closed 2-manifold:
- **Watertight**: the surface fully encloses a volume — no open boundaries/holes.
- **2-manifold**: every edge is shared by exactly two faces; no edge touched by 3+
  faces; no pinch-point (non-manifold) vertices.
- **Outward normals**: faces consistently orient "outside" (`is_volume == true`).
Without these, the slicer cannot decide what is inside vs outside, and G-code
generation fails or needs repair. CSG via manifold3d gives this for free; imported
or generative meshes must be validated (and possibly repaired) before printing.

## Units & coordinate frame
- **Everything is millimeters.** STL is unitless and slicers assume mm — a part
  authored in inches imports 25.4× too small. Always think and emit in mm.
- **Z is up; the build plate is the XY plane at z = 0.** Place models on the bed
  (`min z = 0`) before slicing. Build direction is +Z, which is why overhangs and
  layer-anisotropy are measured against Z.

## Mesh vs B-rep
- **Mesh** (triangles): STL, 3MF, GLB, OBJ, PLY — what printers/slicers consume.
- **B-rep / solid** (exact surfaces): STEP — true CAD, editable, but must be
  tessellated to a mesh for printing. The studio3d engine works in meshes and
  exports STL/3MF/GLB; manifold guarantees come from the boolean kernel.

## File formats
| Format | Use | Carries |
|---|---|---|
| **STL** | universal slicer input | geometry only (unitless) |
| **3MF** | Bambu/Orca/Prusa, multicolor | geometry + mm units + color + materials + settings |
| **GLB** | web/AR preview | geometry + PBR materials + color |
| **STEP** | CAD interchange | exact B-rep solids |

## Engine routing (which path to take)
| Request shape | Examples | Engine |
|---|---|---|
| **Mechanical / functional** | brackets, enclosures, mounts, holders, gears, knobs, fixtures, jigs, adapters, stands | **Local CSG** (default) — deterministic, free, ~100% slicer-safe, parametric |
| **Organic / decorative** | figurines, characters, animals, busts, ornate sculpture | **Generative backend** (Meshy/Tripo/etc.; mock fallback) — then validate/repair |
| **Hybrid** | a stylized object with functional mounting features | CSG for the functional features; generative for the organic shell; combine |

Default to **CSG** unless the form is genuinely organic — CSG is reproducible,
needs no GPU/API, and is manifold-by-construction. Generative output is great for
shapes you can't easily express parametrically but only ~55–97% watertight, so it
**must** pass validation/repair before printing.
