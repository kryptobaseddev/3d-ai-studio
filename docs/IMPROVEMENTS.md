# 3D Studio — optimization & improvement assessment

## 1. Loading optimization (DONE this pass)

**Question: was the plugin optimized to load skills/agents on demand (MCP) rather
than always-on?** It wasn't — it shipped **6 native skills + 4 native agents**, each
injecting its name+description into *every* session and adding `/`-menu entries
(cost scales with count). It is now a **hybrid**:

| | Before | After |
|---|---|---|
| Native (always-on) skills | 6 | **2** (`model3d`, `grill-me` — the user-invocable entry points) |
| Native agents | 4 | **0** |
| On-demand (MCP registry) | — | 4 skills + 4 agents, loaded via `load_skill`/`load_agent` |
| Always-on blocks | ~10 descriptions | 2 skill descriptions + ~7 MCP tool names |

The `3d-studio-registry` MCP server (`mcp/server.py`, zero-dependency stdlib,
auto-started from `.mcp.json` via `${CLAUDE_PLUGIN_ROOT}`) serves the registry on
demand and also exposes packaged grounding as tools (`studio3d_reference`,
`studio3d_styles`, `studio3d_subjects`). The entry-point skills now instruct the
agent to `load_skill`/`load_agent` from the registry. Estimated always-on saving:
~8 description blocks (~1.5–2k tokens) per session, with the catalog free to grow
flat. Verified: `claude plugin validate` ✔, MCP smoke test ✔ (stdout clean).

> The user-facing slash commands stay native on purpose — you can't type `/model3d`
> if it lives only in an MCP registry. Everything else is deferred.

## 2. The plugin IS built to extend (low-friction growth points)

| Add a… | Where | Cost |
|---|---|---|
| reference subject | `harness/studio3d/data/reference_library.json` (one entry) | data-only |
| artistic style | `harness/studio3d/data/styles.json` | data-only |
| printer | `harness/studio3d/data/printers.json` | data-only |
| DSL primitive | `harness/studio3d/dsl/__init__.py` + 1 test | small |
| reference skill / agent | `registry/skills/` or `registry/agents/` | **0 always-on** (auto-served) |
| MCP tool | `mcp/server.py` `TOOLS` + `call_tool` | small |
| CLI command | `harness/studio3d/cli.py` | small |

## 3. Prioritized roadmap (not yet built)

### P0 — biggest "print-ready" credibility wins
- **Real slicer integration.** D2 (slicer pass) is currently a proxy. Bundle/call a
  headless slicer (PrusaSlicer/OrcaSlicer CLI) to actually slice the 3MF → G-code,
  and report **real** print time + filament grams + a true slice-or-fail. (`studio3d slice`.)
- **Multi-color 3MF / AMS.** The design plan already captures per-part `colors`; emit
  a per-face-colored 3MF mapped to AMS slots (needs per-part face tagging in the CSG
  builder — tag faces as parts are unioned, then color by tag on export).
- **Verified-template library** (council's Expansionist point). Persist each accepted
  `(prompt, design.json, script, score)` as a growing library; new requests start from
  the closest known-good base → higher first-pass fidelity, cheaper iterations.

### P1 — fidelity & UX
- **Real generative backend** for *realistic/scanned* organic (Meshy API or local
  Hunyuan3D/TRELLIS) to complement the stylized-CSG path; always run through
  validate→repair. (Plumbing exists in `generative.py`; only the mock is wired.)
- **Reference-image grounding.** When the user gives no image, fetch a reference
  image (web image search) so the vision critique compares to real imagery, not just
  the agent's memory.
- **Auto-orientation optimizer.** `validate` already finds overhangs; add a pass that
  rotates the model to minimize support area / put load along layers.
- **Web parametric customizer.** Surface the design plan's numeric params as sliders in
  the viewer; edit → regenerate live (the live-update channel already exists).

### P2 — capability breadth
- True edge **fillets/chamfers** (not just `rounded_box`), **gears/threads**, **lattice
  infill**, **sweep-along-path**.
- **STEP export** (true B-rep CAD interchange) — needs an OCP/OpenCascade path
  (blocked on CPython 3.14 wheels today; revisit with a pinned 3.12 venv option).
- **Assembly / multi-part** prints (the schema reserves `assembly`): bed layout,
  mating parts with clearances, print-in-place joints.
- **Batch generation** (a set / variants) and a **studio3d config** for default
  style/profile/units.

### Hardening
- The sandbox's `load_mesh` can read arbitrary mesh paths — fine for a trusted local
  agent, but constrain to the project/output tree for defense-in-depth.
- Pin a CI workflow (`pytest` + `claude plugin validate` + MCP smoke) so the 48-test
  suite + packaging stay green.

## 4. Summary
The plugin is now **loading-optimized** (hybrid native + MCP registry) and is
**architected for growth** — most new capability is a data-file entry or a zero-
always-on registry file. The highest-leverage next step is **real slicer
integration** (turns the print-readiness claim from a strong proxy into ground
truth) followed by **multi-color 3MF** and the **verified-template library**.
