---
name: model3d
description: Run an interactive 3D design session — turn a natural-language description (and optional reference images) into print-ready 3D files (STL + 3MF + GLB) in output/, validated for 3D printing and visually verified to match intent. Use whenever the user wants to model, design, generate, mock up, tweak, modify, or 3D-print an object — a bracket, enclosure, stand, holder, knob, gear, fixture, sign, figurine, vase, toy, or any physical part — for Bambu Studio, OrcaSlicer, PrusaSlicer, or MakerWorld. Also use to load and modify an existing STL/3MF/GLB. Triggers on "model a…", "design a…", "make me a printable…", "generate an STL of…", "tweak the…", "I want to 3D print a…".
argument-hint: <natural-language description of the object to model, or a tweak to an existing one>
user-invocable: true
allowed-tools: Read, Write, Edit, Bash, Glob, Agent
---

# /model3d — interactive design session → print-ready 3D

You run a **design session**: understand the request, build it, **look at it**,
critique it against intent, revise until it both *matches the design* and is
*print-ready*, then present it. The bundled CLI `studio3d` (on PATH) does the
fabrication, validation, rendering, and history.

Request: `$ARGUMENTS` (plus any attached images).

> **Capabilities load on demand (registry).** This plugin keeps only `model3d` and
> `grill-me` native to minimize always-on cost. The reference skills and specialist
> agents this guide names live in the **`3d-studio-registry`** MCP server. When a step
> says "see the **cad-authoring** / **print-readiness** / **printer-setup** /
> **3d-modeling-foundations** skill", load it with `load_skill(id="…")`. When it names
> "the **spec-analyst** / **cad-author** / **mesh-validator** / **design-critic**
> subagent", `load_agent(id="…")` to get its system prompt, then spawn it with the Agent
> tool. `list_skills` / `list_agents` enumerate what's available; `studio3d_reference` /
> `studio3d_styles` give the packaged design grounding.

## 0. Target the right printer (once per session)
Check the active printer profile so files target the user's real machine:
```bash
studio3d profile show        # active profile (bed size, nozzle, AMS, colors)
```
If there is no active profile, help set one up (see the **printer-setup** skill):
ask make/model, look it up (`studio3d printers --search "<model>"`), AMS yes/no,
and filament colors, then `studio3d profile add ...`. The active profile drives
bed-fit, wall minimums, and AMS color mapping automatically.

## 1. Understand → ModelSpec (+ the design plan, for non-trivial work)
Parse the request (and images) into intent: **category** (mechanical/functional →
CSG; organic/decorative → stylized CSG), key **dimensions in mm**, and the
**design cues that define success** (for an owl: round body, big eyes, beak, ear
tufts; for a phone stand: a cradle that actually holds a phone at a viewing angle).
Delegate to the **spec-analyst** subagent for non-trivial requests or when images
are attached. State any dimension you had to assume.

For **organic/figurative** or otherwise non-trivial requests, base the work on a
**design plan** (`design.json`) — the source of truth. Run the **grill-me** session
to interview the user and produce a validated plan, or build one directly with
`studio3d plan new …`. Tweaks then edit a plan field and regenerate (step 4).

## 1b. Look up the packaged REFERENCE + STYLE (organic/figurative)
Before authoring any organic/figurative model, pull the grounded brief and the style
params so you build to a known recipe, not by feel:
```bash
studio3d reference <subject> --style <style>   # BRIEF: silhouette cues, numeric
                                               # proportions by head-unit H, CSG recipe,
                                               # eye_rule, print_constraints (20 subjects)
studio3d styles <style>                        # head_body_ratio, eye_size_mult,
                                               # feature_exaggeration, facet_level, fillet
```
Or `studio3d plan brief <design.json>` to get the brief straight from the plan.

## 2. Author the geometry (CSG) — BY PROPORTION, with NAMED PARAMETERS
First **ground in the knowledge base**: `studio3d kb "<what you're building>"` returns
the DFAM numerics + the proven CSG recipe (e.g. "wall bracket gusset", "vessel inner
bore wall", "teardrop horizontal hole"). Then write a script in the **studio3d DSL**
(see the **cad-authoring** skill for the full API: box, cylinder, sphere, ellipsoid,
cone, prism, tube, slot, teardrop, extrude, revolve, twist_extrude, loft, hull, text,
**interference**, **arrange_on_bed** + booleans + transforms).

**Parameterize every key dimension** by reading it from the injected `P` dict with a
default — `wall = P.get("wall", 2.0)` — NOT magic numbers. The bundle ships `model.py`
+ `params.json`, so the model is **forever-editable** (`studio3d tweak --set wall=3`
regenerates it deterministically). A hardcoded dimension is a defect.

For organic/figure models, **author by proportion**: define a head-unit **H** from the
reference recipe and place/size every part as a multiple of H (per the brief's numeric
ratios and `eye_rule`) — **not** ad-hoc mm. Apply the **print-readiness** rules while
modeling (mm, ≥0.8mm walls, ≥45° overhangs, base chamfers, teardrop horizontal holes,
mating clearance). Delegate complex parts to the **cad-author** subagent. End with `.on_bed()`.

For **multi-part assemblies**, build each part, lay them out with `arrange_on_bed([...])`,
and assert no collision with `interference(a, b) == 0` before returning — then capture the
mates + one `clearance_mm` knob in the design plan's `assembly` block.

## 3. THE FIDELITY LOOP — fabricate, look, critique, revise (≤4 passes)
This is how the result actually matches the request. **Do not ship a model you have
not looked at.** It is **vision-grounded**: you compare renders against BOTH the
subject's reference silhouette cues AND any 2D images the user gave you.

```bash
# from a plan (preferred for organic/figure work):
studio3d gen-script --script model.py --plan <slug>.design.json --out output
# or ad-hoc:
studio3d gen-script --script model.py --name "<slug>" --prompt "$ARGUMENTS" \
  --category <cat> --color "<hex>" --out output
studio3d render output/<slug>/model.stl --color "<hex>" --views front,right,top,iso
```
Pull the ground truth, then **Read** the rendered views (`output/<slug>/views/view_*.png`)
**and** the user's reference images side by side:
```bash
studio3d reference <subject> --style <style>   # silhouette cues + numeric proportions
```
Score each criterion **0–100** against that ground truth:

| Criterion | Scored against |
|---|---|
| **Silhouette** | Do the renders read as the subject's silhouette cues / the user's images? |
| **Proportion** | Do part ratios match the reference head-unit (H) ratios? |
| **Feature** | Is every reference cue present + identifiable (eyes, beak, ear tufts…)? |
| **Style** | Does it match the style params (head_body_ratio, eye_size_mult, facet_level)? |

Also **read the kernel metrics** in `report.json` → `metrics.kernel_metrics` (or the
`summary.kernel_metrics` from gen-script): `n_components` must be **1** for a single
part (2+ = a floating/disconnected piece a render can hide), `genus` as expected, and
`wall_p05_mm` ≥ the minimum. Vision alone is contextually blind — fuse it with these
numbers. Require **print-readiness** (`print_ready: true`, no blocking D1/D3).

**Revise** the script for any low score and regenerate (same `--plan`/`--name` →
overwrites in place, git captures the change). **Stop** when all axes are ≥ ~95 AND
`print_ready` is true, **or** after 4 passes keeping the **best-so-far**. If the SAME
issue persists across two passes, do NOT repeat the fix — **escalate**: switch to a
fundamentally different construction (decompose into sub-parts, hull/loft for blobby
forms, change the proportion anchor).

For a fresh, frame-isolated, STRONGER judgement, delegate scoring to the **design-critic**
subagent (it runs on a strong model, renders + critiques blind, fuses the kernel metrics,
and returns a rubric score + fixes, with a `ship`/`revise`/`escalate`/`reject` verdict).

## 4. Tweak / modify / iterate
The user will refine ("make it taller", "add a lid", "round the corners"). When the
model has a design plan, **edit the relevant field in `design.json`** (it is the base
design), bump `revision`, re-`plan validate`, and regenerate from the same plan. Either
way edit the **same** script and regenerate with the **same `--name`**/`--plan` so it
overwrites in place (git history preserves every revision — `studio3d history --bundle
<slug>`; recover with `studio3d history --bundle <slug> --revert <sha>`). Only pass
`--variant`, or branch to a new design.json, when the user wants a separate copy.

## 5. Modify an EXISTING model file
If the user provides an STL/3MF/GLB:
```bash
studio3d import path/to/their.stl --name <slug> --reorient --out output
```
Then modify it by authoring a script that calls `load_mesh("output/<slug>/model.stl")`
and applies booleans/transforms (cut a hole, add a mount, scale, emboss), and run it
through `gen-script` — the fidelity loop applies the same way.

## 6. Present + live preview
Report what was built, the intent-match and print-readiness scores, the bundle path,
the recommended slicer format (3MF for Bambu/AMS color, STL otherwise), key metrics
(mm, mass), and print advice (supports/orientation). Mention that the bundle ships an
**auditable Print-Readiness Certificate** (`certificate.json`: prompt → script hash →
D1–D4 → slice → human approval) and **editable source** (`model.py` + `params.json`).

Real extras the user can run:
- `studio3d slice <bundle>/model.3mf` — REAL slice-to-G-code (D2 ground truth): print
  time + filament grams (needs a slicer installed; otherwise D2 is the labeled proxy).
- `studio3d orient <bundle>/model.stl --out reoriented.stl` — support-minimizing pose.
- `studio3d tweak --plan <slug>.design.json --set <k>=<v> --script model.py` — change one
  knob and regenerate deterministically.
- `studio3d certify <bundle> --approve` — record human sign-off in the certificate.

The user can watch every change **live** in the viewer (3D view, print-readiness report,
and a parametric **Customizer** that surfaces the knobs):
```bash
cd web && npm install && npm run dev    # http://localhost:5173 — auto-refreshes
```

## Guardrails
- **Always millimeters.** **Manifold is non-negotiable** (the CSG engine guarantees
  it; if a result isn't watertight, a boolean was degenerate — nudge a dimension by
  0.01mm).
- **Always look before you ship** (step 3). Validation proves it *prints*; the render
  proves it *matches*. Both must pass.
- Prefer the local CSG path; organic shapes are authored as stylized CSG by default.
- Don't silently invent safety- or fit-critical dimensions — confirm.
