# 3D Studio — Council + Skill Evaluation (v2)

Record of the two evaluations run on the v2 work, per the design-review request.

## Council review (5-advisor stress test)
Run: `.cleo/council-runs/20260608T174643Z-08a67c44/` (structurally validated).
Verdict (high confidence): **adopt the visual-critique loop, but as a *bounded
convergence wrapper* — the primary fidelity lever is an expressive DSL + a defined
intent rubric.**

| Advisor | Gate score | Sharpest point (carried into the build) |
|---|---|---|
| First Principles | 4/4 | Fidelity is bounded by DSL expressiveness — the loop can't exceed the grammar floor. → **Enriched the DSL** (twist_extrude, ellipsoid, loft, tube, slot, teardrop, load_mesh). |
| Outsider | 4/4 | "99% fidelity" was undefined/unfalsifiable. → **Defined a 5-criterion intent rubric** (feature presence, proportion, function, silhouette, print-readiness) in the model3d skill + design-critic agent. |
| Executor | 4/4 | First, prove the critic detects known defects. → **Did exactly that**: rendered the two known-bad meshes via Blender and confirmed the critic flags "no twist" / "disconnected plates" before relying on the loop. |
| Expansionist | 3/4 | The loop's records double as a regression harness + template library. → examples now serve as both. |
| Contrarian | 2/4 | The loop has no termination guarantee. → **Bounded loop** (≤4 passes, best-so-far, stop-on-plateau) baked into the model3d skill. |

Also adopted: git history = ONE evolving bundle in an isolated store (never touches
the user's VCS); live update = polling (least moving parts).

## Skill evaluation (skill-evaluator)
Method: auto-generated skill-unique test cases for `model3d` + the evaluator's
quality rubric (triggers? helps? broken? fixable? real?).

**Top finding (fixed):** the `cad-authoring` skill listed only the v1 primitive set —
out of sync with the enriched DSL. The `cad-author` agent reads that skill, so it
would not have known about `twist_extrude`/`ellipsoid`/`load_mesh` — exactly the
primitives needed to fix the broken models. → **Updated cad-authoring** with every new
primitive, `load_mesh`, a D-shaft-knob recipe, a twisted-vase recipe, the organic
ellipsoid-composition pattern, the import-and-modify recipe, and a "render and look
before you ship" step. All recipes were run through the harness and verified
watertight.

**Triggering:** the generated probes (cable comb → 6 slots; import + add a 12.5mm
hole; D-shaft knob; and a *negative* "fix my stringing in OrcaSlicer" that should NOT
generate geometry) confirmed the skill set is well-targeted: `model3d` triggers on
create/modify/print, stays out of pure slicer-tuning questions, and the new
import/modify + design-session capabilities map directly to real user needs.

**Result:** descriptions are specific and within budget; bodies are dense and
actionable; progressive disclosure is used where it pays (print-readiness reference
tables). The plugin's skills give the agent enough to run a full design session.
