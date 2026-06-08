---
name: cad-authoring
description: How to author parametric 3D geometry with the studio3d CSG DSL — a manifold-by-construction Python API (box, cylinder, sphere, cone, prism, extrude, revolve, text, rounded_box, hull + boolean union/difference/intersection + transforms) that exports watertight STL/3MF/GLB. Use when writing a geometry script for the studio3d harness to build a mechanical or functional part. Covers the full API, operator overloads, transform chaining, common part recipes, and print-safe construction patterns.
---

# Authoring geometry with the studio3d DSL

You write a Python script that builds a solid from primitives and boolean
operations. Because every op is backed by `manifold3d`, the result is **watertight
and 2-manifold by construction** — it passes print-readiness D1 without repair.

**Units are millimeters. Z is up. The build plate is the XY plane (z = 0).**

## Contract
Define `build()` returning a `Solid`, **or** assign a module-level `result`:

```python
def build():
    base = box(40, 30, 4)
    boss = cylinder(h=10, d=8).at(0, 0, 7)
    hole = cylinder(h=20, d=4).at(0, 0, 5)
    return base + boss - hole
```

Run it: `studio3d gen-script --script model.py --name my-part --out output`
(or `studio3d run-script --script model.py --out part.stl` for a bare mesh).

Only the DSL + `math`/`numpy`/`random` are importable — the sandbox blocks file,
network, and OS access. CPU time and wall-clock are capped.

## Primitives (all return `Solid`, dimensions in mm)

| Call | Makes |
|---|---|
| `box(x, y, z, center=True)` | box; `center=False` → corner at origin, in +octant |
| `cube(s)` | cube |
| `rounded_box(x, y, z, radius=2)` | box with rounded edges (fillet = radius) |
| `cylinder(h, d=…\|r=…, sections=64, center=True)` | Z-axis cylinder |
| `cone(h, d=…, d_top=0, …)` | (truncated) cone; `d_top>0` ⇒ frustum |
| `sphere(d=…\|r=…, subdivisions=3)` | icosphere |
| `ellipsoid(dx, dy, dz)` | sphere scaled per axis — organic/stylized bodies |
| `capsule(h, d=…\|r=…)` | pill |
| `torus(major_d, minor_d)` | ring in XY |
| `prism(sides, d=…\|r=…, h=…)` | regular n-gon prism (hex = `prism(6, …)`) |
| `tube(h, d_outer, d_inner)` | hollow cylinder (pipe) |
| `slot(length, width, height)` | rounded-end (stadium) slot — channels, grips |
| `teardrop(d, h)` | teardrop hole for HORIZONTAL bores (no top overhang) |
| `wedge(x, y, z)` | right-triangular prism (gusset) |
| `extrude(points2d, h)` | extrude a 2D polygon along Z |
| `revolve(profile_xy, angle_deg=360)` | revolve a profile (x=radius, y=height) about Z |
| `twist_extrude(points2d, height, turns)` | extrude a profile while rotating — real spiral/twist (twisted vases, augers) |
| `loft(sections)` | loft through `(points2d, z)` cross-sections — tapered/curved bodies |
| `text(string, size, height, font=None)` | extruded 3D text (keep strokes ≥1mm) |

`d=` diameter or `r=` radius — give one. `polygon(points).extrude(h)` /
`.revolve(deg)` is the fluent form.

**Modify an existing mesh:** `load_mesh("path.stl")` returns a `Solid` you can
boolean/transform — for editing imported STL/3MF/GLB (cut holes, add mounts, scale).

## Boolean ops & operators
```python
a + b      a.union(b)          # fuse
a - b      a.difference(b)     # cut b out of a
a & b      a.intersection(b)   # common volume
union(*solids)   difference(base, *cuts)   intersection(*solids)
hull(*solids)    # convex hull
```

## Transforms (chainable; each returns a new Solid)
```python
.translate(x, y, z) / .move(x, y, z)
.at(x, y, z)                 # place CURRENT center at (x,y,z)
.rotate(deg, axis, about=None)  .rotate_x(d) .rotate_y(d) .rotate_z(d)
.scale(factor)               # scalar or [sx,sy,sz]
.mirror("x"|"y"|"z")
.on_bed()                    # drop so min-z sits at z=0 (ready to slice)
.center_xy()                 # center over the origin in XY
```
Introspection: `.size` ([dx,dy,dz]), `.bounds`, `.center`, `.volume`, `.is_manifold`.

## Patterns / helpers
```python
linear_pattern(solid, count, dx=…, dy=…, dz=…)   # list of copies → union(*...)
circular_pattern(solid, count, radius=…, axis="z")
```

## Print-safe construction (apply the print-readiness skill)
- Keep walls ≥ 0.8 mm (FDM 0.4 nozzle). When carving cavities, leave ≥ 0.8 mm.
- Add a base chamfer to fight elephant's foot:
  `part - cone(h=0.6, d=base_w+2, d_top=base_w).at(0,0,0.3)` or subtract a 45° ring.
- Horizontal holes: model a teardrop, not a bare cylinder, or keep ≥ 2 mm.
- Pins < 5 mm: add a fillet at the base (`+ cone` flare) or avoid.
- Round sharp internal corners with `rounded_box`/`hull` to cut stress risers.
- Finish with `.on_bed()` so the model sits on z=0 for the slicer.

## Worked recipes

**Bracket (plate + shelf + gusset + mounting holes):**
```python
def build():
    back  = box(70, 3, 60, center=False)
    shelf = box(70, 40, 3, center=False)
    gusset = wedge(64, 36, 56).translate(3, 3, 3)
    body = back + shelf + gusset
    holes = union(*[cylinder(h=12, d=4.5).rotate_x(90).translate(70*sx, 1.5, 42)
                    for sx in (0.25, 0.75)])
    return (body - holes).on_bed()
```

**Hollow holder (tube with floor):**
```python
def build():
    outer = cylinder(h=90, d=80, center=False)
    bore  = cylinder(h=86, d=74, center=False).translate(0, 0, 4)  # 3mm wall, 4mm floor
    return outer - bore
```

**Knurled knob with a D-shaft bore (6mm D-shaft):**
```python
def build():
    body = cone(h=18, d=28, d_top=24).on_bed()
    knurl = union(*circular_pattern(cylinder(h=20, d=2.4), 20, radius=14))
    # D-shaft bore: a round bore with a flat cut (cylinder minus a box on one side)
    bore = cylinder(h=16, d=6.2).at(0, 0, 8)
    flat = box(8, 1.4, 16).translate(0, 6.2/2 - 0.45, 8)   # the flat of the "D"
    return body - knurl - (bore - flat)
```

**Twisted fluted vase (real spiral via twist_extrude):**
```python
import math
def build():
    prof = [[ (30+2.2*math.cos(12*a))*math.cos(a), (30+2.2*math.cos(12*a))*math.sin(a) ]
            for a in [2*math.pi*i/120 for i in range(120)]]
    outer = twist_extrude(prof, height=120, turns=0.5)
    inner = twist_extrude([[x*0.92,y*0.92] for x,y in prof], height=120, turns=0.5).translate(0,0,4)
    return (outer - inner).on_bed()
```

**Organic figure via ellipsoid composition (the owl pattern):**
build a body from an `ellipsoid`, add a `sphere` head, `cone` beak/tufts, raised
`sphere` eyes (subtract small spheres for pupils), flattened `ellipsoid` wings, and
little `ellipsoid` feet — then `.on_bed()`. Stylized organic shapes read from a few
strong cues; compose them and **look at the render** to confirm it's recognizable.

**Modify an imported model (add a hole to a downloaded enclosure):**
```python
def build():
    box_in = load_mesh("output/enclosure/model.stl")
    hole = cylinder(h=40, d=12.5).rotate_x(90).at(0, 0, 30)   # 12.5mm panel hole
    return box_in - hole
```

## Always look before you ship
After generating, **render and inspect** — geometry that validates can still miss the
intent:
```bash
studio3d render output/<slug>/model.stl --color "<hex>"   # then Read view_*.png
```
Score it on feature presence, proportion, function, silhouette. Revise and regenerate
(same `--name`) until it matches AND `print_ready` is true.
