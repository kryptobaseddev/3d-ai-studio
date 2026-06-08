# design.json -> DSL script (deterministic lowering)

`design.json` is the regenerable source of truth. The harness lowers it into a
studio3d DSL `build()` script with a pure, deterministic function
`plan_to_script(plan) -> str`. Same plan in => byte-identical script out. This is
what makes a "tweak" (edit one field, regenerate) reproducible.

## Pipeline

```
Grill-me session ──> design.json ──> plan_to_script() ──> model.py (build())
                          │                                      │
                       (tweak edits a field)            studio3d gen-script
                          │                                      │
                          └────────── regenerate ────────> validate ─> RENDER
                                                                 │
                                          design-critic vs reference_images + reference_guide
                                                                 │
                                              ship / revise (edit design.json) / reject
```

## Field -> DSL emission rules

| plan field | emitted DSL |
|---|---|
| `parts[].approach` + `size_mm` | the matching factory call; `size_mm` is spread positionally in factory-native order (see below) |
| `parts[].params` | extra kwargs (`sections`, `subdivisions`, `turns`, `d_top`, `points`, `string`, `radius`, ...) |
| `rotation_deg [rx,ry,rz]` | `.rotate_x(rx).rotate_y(ry).rotate_z(rz)` (only non-zero axes emitted) |
| `anchor.at [x,y,z]` | `.at(x,y,z)` |
| `anchor.relative_to` | `.at(bx+x, by+y, bz+z)` where `(bx,by,bz)` = referenced part center |
| `anchor.mirror_x` | wrap in `for sx in (-1,1):` and negate the X of `at`/rotation |
| `op:add` | `model = model + part` |
| `op:cut` | `model = model - part` (emitted AFTER all adds, in declared order) |
| `op:intersect` | `model = model & part` |
| `assembly.on_bed` | `.on_bed()` at the end |
| `assembly.fit_to_envelope` + `dimensions_mm` | `.scale(...)` to fit the bbox to width/depth/height (uniform if `lock_aspect`) |
| `style.facet_level` | default `subdivisions`/`sections` when a part omits them (0->1, 1->2, 2->2, 3->3, 4->4 subdiv; sections 8/16/24/48/64) |
| `style.intensity` | proportion multiplier applied to parts tagged via `unique_details` (e.g. eyes scale up with intensity for cartoonish/chibi) |
| `${param}` in any numeric field | resolved from `parameters[param].value` before emission |

## `size_mm` arity per approach (factory-native order)

- `box/rounded_box`: `[x, y, z]` (rounded_box radius via `params.radius`)
- `cube`: `[s]`
- `sphere`: `[d]`
- `ellipsoid`: `[dx, dy, dz]`
- `cylinder`: `[h, d]`
- `cone`: `[h, d, d_top]`
- `capsule`: `[h, d]`
- `torus`: `[major_d, minor_d]`
- `prism`: `[d, h]` (+ `params.sides`)
- `tube`: `[h, d_outer, d_inner]`
- `slot`: `[length, width, height]`
- `teardrop`: `[d, h]`
- `wedge`: `[x, y, z]`
- `extrude`: `[h]` (+ `params.points`)
- `revolve`: `[angle_deg]` (+ `params.points`)
- `twist_extrude`: `[height]` (+ `params.points`, `params.turns`)
- `text`: `[size, height]` (+ `params.string`)

The mapper MUST assert arity matches `approach`; a mismatch is a plan error
surfaced before geometry runs.

## Determinism guarantees

1. Parts emit in declared order; cuts deferred but order-stable.
2. No randomness: facet/section counts come from `style.facet_level`, never RNG.
3. Tweaks are JSON-pointer edits; `history[]` records pointer + before/after +
   resulting critic score + git sha for point-in-time recovery (one evolving
   bundle, not version spam).
4. Stable `parts[].id` lets the mapper diff two plan revisions and (optionally)
   regenerate only changed sub-solids.

## Lowering into the existing ModelSpec

`design.json` is the layer above `ModelSpec`. The harness derives a `ModelSpec`
for the existing `gen-script` path:

- `ModelSpec.prompt`        <- `subject.prompt`
- `ModelSpec.name`          <- `id`
- `ModelSpec.description`   <- `subject.description`
- `ModelSpec.category`      <- `category`
- `ModelSpec.engine`        <- `engine`
- `ModelSpec.script`        <- `plan_to_script(plan)`
- `ModelSpec.target_size_mm`<- `[dimensions_mm.width, depth, height]`
- `ModelSpec.printer_profile`<- `printer_profile`
- `ModelSpec.material`      <- `material`
- `ModelSpec.multicolor`    <- `multicolor` (or derived from >1 color slot)
- `ModelSpec.color`         <- first `colors[].hex` (single-color fallback)
- `ModelSpec.reference_images` <- `reference_images[].path`
- `ModelSpec.parameters`    <- `parameters` (flattened name->value)

The critic reads `reference_images` + `reference_guide.feature_checklist` +
`unique_details` as its grounded intent rubric, comparing renders to the known
2D reference imagery so the result truly looks like the subject.
