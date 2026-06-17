# CLAUDE.md — 3D Studio

Guidance for Claude Code working in this repository.

## What this is
A Claude Code **plugin + agent harness** that turns natural language (+ images) into
**print-ready 3D files** (STL/3MF/GLB). Default engine is a local, manifold-by-
construction **CSG** kernel the agent authors; an optional generative backend handles
organic shapes. Every model is validated against the 4-dimension print-readiness
benchmark. A static React + three.js app previews results.

## Layout
- `harness/studio3d/` — the Python harness (the real engine). Package home; run via
  `PYTHONPATH=harness ./.venv/bin/python -m studio3d.cli …` or `./bin/studio3d …`.
  - `dsl/__init__.py` — the CSG DSL. Primitives: box/cube/rounded_box/cylinder/cone/
    sphere/**ellipsoid**/capsule/torus/prism/**tube**/**slot**/**teardrop**/wedge +
    extrude/revolve/**twist_extrude**/**loft**/text/hull + booleans + transforms +
    **load_mesh** (import existing STL/3MF/GLB to modify). twist_extrude/loft cap with
    a centroid fan (`_centroid_cap`) so lobed profiles stay watertight.
  - `sandbox.py` — runs authored scripts in an isolated subprocess (restricted
    builtins, rlimits, timeout). Mesh handed back as **PLY** (preserves topology).
  - `validate.py` — D1–D4 validator. Wall thickness uses `proximity.thickness(method="ray")` (NOT max_sphere — that's edge-polluted). Overhang excludes bed-contact faces.
  - `render.py` + `_blender_render.py` — multi-view renders for the **visual-critique
    loop** (Blender Workbench headless; matplotlib fallback). `studio3d render <stl>`.
  - `profiles.py` + `data/printers.json` — printer DB (29 machines) + user profiles
    (YAML in XDG config). Active profile drives bed-fit, wall mins, AMS color.
  - `history.py` — git-tracked design history in an ISOLATED store
    (`output/.studio3d-history`, never a `.git` at root). One evolving bundle per
    design (overwrite in place); revisions are commits. No version spam.
  - `exporters.py` — STL/3MF/GLB/thumbnail/manifest. 3MF is a hand-authored OPC zip (mm units + color) so it carries AMS color; trimesh's 3MF can't.
  - `generative.py` — Meshy async backend + deterministic mock fallback (no key needed)
  - `spec.py` — `ModelSpec` + `PRINTER_PROFILES`
- **Loading model (hybrid, optimized for ~0 always-on cost):**
  - `skills/` — ONLY the native user-invocable entry points: `model3d`, `grill-me`.
    (Skills live at repo root, NOT in `.claude-plugin/` — only plugin.json/marketplace.json go there.)
  - `registry/skills/` + `registry/agents/` — the reference skills (print-readiness,
    cad-authoring, 3d-modeling-foundations, printer-setup) + specialist agents
    (spec-analyst, cad-author, mesh-validator, design-critic). These are NOT loaded
    natively; they are served **on demand** by the MCP server.
  - `mcp/server.py` + `.mcp.json` — the `3d-studio-registry` MCP server (zero-dep stdlib,
    auto-started via `${CLAUDE_PLUGIN_ROOT}`). Tools: `list_skills`/`load_skill`,
    `list_agents`/`load_agent`, `studio3d_reference`/`styles`/`subjects`. The entry-point
    skills tell the agent to `load_skill`/`load_agent` from here. Smoke-test:
    `python3 ~/.claude/skills/plugin-creator/scripts/smoke_test_mcp.py … python3 mcp/server.py`.
- `web/` — React 19 + Vite 8 + three.js viewer (versions are pinned & coupled:
  fiber@9 needs react ≥19 <19.3 — do not bump react past 19.2 without bumping the quad)
- `examples/` — print-safe DSL scripts (also used as test fixtures)
- `tests/test_studio3d.py` — pytest end-to-end

## Environment (verified)
CPython **3.14**. `.venv/` at repo root has the full stack: trimesh 4.12, manifold3d,
numpy 2.4, scipy 1.17, shapely 2.1, rtree, matplotlib, Pillow, lxml, networkx.
**CadQuery/build123d were intentionally NOT used** — they lack 3.14 wheels (OCP).
The trimesh + manifold3d CSG path is the deliberate, verified choice.

## Run things
```bash
PYTHONPATH=harness ./.venv/bin/python -m pytest tests -q     # tests (64)
./bin/studio3d doctor                                         # env + blender + profile
./bin/studio3d gen-script --script examples/cable_clip.py --name clip --out output
./bin/studio3d render output/clip/model.stl                   # multi-view (visual loop)
./bin/studio3d printers --search "bambu a1"                   # printer DB
./bin/studio3d profile add --name my-a1 --printer "Bambu Lab A1" --ams true --colors "#000,#fff"
./bin/studio3d import some.stl --name thing                   # import to modify
./bin/studio3d history --bundle clip                          # change history
cd web && npm install && npm run dev                          # live viewer (port 5173)
```

## CLI commands
`gen` · `gen-script` (`--params`/`--no-slice`) · `run-script` · `validate` (`--slice`) ·
`slice` · `tweak` · `orient` · `certify` · `kb` · `muse` · `render` · `manifest` ·
`printers` · `profile {list,show,use,add}` · `import` · `history` · `examples` · `doctor`

## v0.4 modules (the "beat Meshy" moat — see docs/V3-COMPETE-WITH-MESHY.md)
- `slicer.py` — real headless slice-to-G-code for D2 (Orca/Prusa/Bambu/Cura); labeled proxy fallback.
- `certify.py` — Print-Readiness Certificate (prompt→script/file hashes→D1-D4→slice→human approval).
- `kb.py` + `data/kb/` — offline BM25 DFAM/CSG domain-RAG over bundled rules + registry skills.
- `muse.py` — internal MUSE benchmark (5 cascade dims); `studio3d muse` scores 100.
- `validate.heal()` (generative path), `validate.orient_for_print()` (SEG), `metrics.kernel_metrics`.
- `dsl.interference()` / `dsl.arrange_on_bed()` — assemblies. `P` dict = named params (sandbox).
- exporters ship `model.py`+`params.json` per bundle; `export_3mf_multi` = per-part AMS colorgroups.

## The fidelity loop (how 99% intent-match is reached)
Generate → `studio3d render` → **Read the view PNGs** → score on the intent rubric
(feature presence, proportion, function, silhouette, print-readiness) → revise the
script → regenerate (same `--name` = overwrite in place, git captures it) → stop at
≥~95 + print_ready or after 4 passes keeping best-so-far. The `design-critic` agent
does this blind. **A model that validates can still miss intent — always look.**

## Conventions / gotchas
- **Everything is millimeters.** Z up. Models `.on_bed()` (min-z = 0) before slicing.
- The CSG kernel is manifold-by-construction; a non-watertight result usually means a
  **degenerate boolean** (exactly coplanar faces / zero-thickness cut) — nudge a dim
  by 0.01mm. Don't "fix" by disabling validation.
- STL loses vertex sharing (triangle soup) → looks non-watertight on reload; always
  `merge_vertices()` after loading STL, or hand meshes around as PLY/GLB.
- The web app's `output/manifest.json` is **our** schema, not Vite's build manifest.
- CLI emits one JSON object on stdout (logs → stderr) so agents can parse results.
