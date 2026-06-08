---
name: grill-me
description: Run an interactive "Grill-me" design session that pins down an underspecified 3D model through focused questions, then produces a validated design plan (design.json) — the project's base design — and hands off to generation + a vision-grounded fidelity loop. Use when the user says "grill me", "design session", "help me design", "let's design a <thing>", "spec out my model", "interview me about my model", or gives a vague modeling request that needs nailing down before building. The session grounds every question in the packaged reference brief and artistic style system, asks only what is genuinely ambiguous, proposes sensible defaults, and emits a complete design plan you regenerate from on every tweak.
argument-hint: <what you want to design — a sentence and/or reference images>
user-invocable: true
allowed-tools: Read, Write, Bash, AskUserQuestion, Agent
---

# /grill-me — interactive design session → validated design plan

You interview the user to turn a fuzzy idea into a **complete, validated design plan**
(`design.json`) — the **source of truth** for the model. Then you hand off to generation
and a vision-grounded fidelity loop. The bundled CLI `studio3d` (on PATH) grounds your
questions and builds the plan.

Request: `$ARGUMENTS` (plus any attached images).

> **Capabilities load on demand (registry).** Only `grill-me` and `model3d` are native;
> the reference skills (**cad-authoring**, **print-readiness**, **printer-setup**,
> **3d-modeling-foundations**) and specialist agents (**cad-author**, **design-critic**,
> **spec-analyst**, **mesh-validator**) live in the **`3d-studio-registry`** MCP server —
> load a skill with `load_skill(id="…")`, get an agent's prompt with `load_agent(id="…")`
> then spawn it with the Agent tool.

## (a) Ground yourself before asking anything
1. **Read** every attached reference image — note silhouette, proportions, colors, parts.
2. Identify the **subject** (owl, cat, dog, fox, rabbit, bear, dragon, trex, fish, bird,
   frog, robot, human_bust, snowman, ghost, mushroom, tree, rocket, car, generic_figurine)
   and a likely **style**. Look them up so questions are grounded, not generic:
   ```bash
   studio3d reference <subject> --style <style>   # BRIEF: silhouette cues, numeric
                                                  # proportions by head-unit H, CSG recipe,
                                                  # eye_rule, print_constraints
   studio3d styles                                # list the 8 styles
   studio3d styles <style>                        # one style's numeric params
   ```
   `studio3d reference` (no arg) lists subjects. If nothing matches, use `generic_figurine`.

## (b) GRILL — ask only what's genuinely ambiguous (AskUserQuestion)
Use the reference + images to propose **defaults**; ask focused questions only where intent
is truly underspecified. Pin down these essentials:
- **Artistic style** — offer the style list (clean, realistic, cartoonish, chibi, anime,
  low-poly, geometric, stylized); default from the look of the images.
- **Overall size** — height in mm (default from category; figurines ~60–90mm).
- **Key characteristics / unique details** — the cues that make it *this* thing
  (ear tufts? scarf? open mouth? a specific pose?).
- **Colors** — hex per part; which parts are which color; AMS/multicolor or single.
- **Function / constraints** — must it hold water (watertight vessel)? stand unaided?
  mate with/clip onto something? be purely decorative?
- **Target printer** — confirm the active profile (`studio3d profile show`) or which printer.

Batch related questions; don't interrogate. Where the reference gives a confident answer,
state the default and move on rather than asking.

## (c) Produce a complete, validated design plan
Create the base plan, then enrich and re-validate:
```bash
studio3d plan new --subject <s> --name "<n>" --style <st> --category <c> \
  --height <mm> --color "#hex" --out <slug>.design.json
```
Then edit `<slug>.design.json` to fill in the gathered intent — `characteristics[]`,
`unique_details[]`, `colors[{name,hex,part}]`, `parts[{name,approach,size_mm,position_mm,
purpose}]`, `constraints{min_feature_mm,must_stand,watertight_vessel,functional}`,
`reference_images[]`, `notes` — then:
```bash
studio3d plan validate <slug>.design.json     # must pass
studio3d plan show <slug>.design.json          # confirm the plan reads right
```

## (d) Hand off to generation + the fidelity loop
The design.json is the **base design** — author FROM it, never around it:
```bash
studio3d plan brief <slug>.design.json         # grounded brief (proportions by head-unit H)
```
1. Author a studio3d DSL script **by proportion** from the brief (head-unit H and the CSG
   recipe — not ad-hoc mm). See the **cad-authoring** skill; delegate to the **cad-author**
   subagent for non-trivial geometry.
2. Fabricate from the plan (it sets style/size/color/category and persists design.json into
   the bundle):
   ```bash
   studio3d gen-script --script model.py --plan <slug>.design.json --out output
   ```
3. **Vision-grounded fidelity loop** (≤4 passes, keep best): render and compare to BOTH the
   reference's silhouette cues and the user's images.
   ```bash
   studio3d render output/<slug>/model.stl --color "#hex" --views front,right,top,iso
   ```
   Read the views; score silhouette / proportion / feature / style (each 0–100) vs the
   reference + images. Revise the script and regenerate (same `--plan`) until it matches,
   or delegate a blind judgement to the **design-critic** subagent. See the **model3d**
   skill for the full loop.

## Tweaks edit the plan, then regenerate in place
Every later change ("taller", "add a scarf", "make the eyes bigger") **edits a field in
design.json** and regenerates from it — the plan stays the single source of truth. Bump
`revision`. Only branch to a new design.json when the user wants a separate variant.
