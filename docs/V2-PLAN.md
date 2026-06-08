# 3D Studio v2 — design proposal (for council review)

v1 shipped a working local-CSG → validate → export → web-preview pipeline. User
feedback exposed real gaps. This plan addresses them. **Goal: generation hits 99%+
of requested design intent and is fully packaged, repeatable, and interactive.**

## Problems observed (v1)
1. **Viewer coordinate frame** — Z-up models rendered in a Y-up scene → models sat
   half-below the grid / lay on their side. (FIXED: Z-up scene, grid in XY at z=0,
   model grounded.)
2. **Design fidelity** — example parts didn't fulfill intent (cable clip can't grip,
   phone stand disconnected, vase had no twist, "organic" owl was a bare mock).
3. No **visual self-verification** — the agent never *looked* at what it made.
4. No **printer profiles / config** — bed size, AMS, filament colors not modeled.
5. No **import** of existing STL/3MF/GLB to modify.
6. No **git-tracked change history** for point-in-time recovery.
7. No **live update** loop into the viewer during a design session.

## v2 architecture

### A. Closed visual-feedback loop (the key to 99% fidelity)
The agent must *see* its output and iterate. Add `studio3d render` producing
multi-view PNGs (front/right/top/iso) via **Blender headless** (installed; far better
than matplotlib) with a matplotlib fallback. The `model3d` flow becomes:

```
author → fabricate → validate → RENDER → agent inspects views vs intent →
critique (does it match? is it usable?) → revise script → repeat until it matches
AND print_ready. A `design-critic` subagent scores intent-match 0–100.
```

This is how we reach 99%: not one-shot, but generate-look-critique-revise, with the
vision-capable agent as the judge.

### B. Richer parametric DSL
Add primitives/ops the broken parts needed: `ellipsoid`, `helix`/`twist` (swept &
rotated profile → real twisted vases), `loft`/`sweep`, `shell` (hollow to wall t),
`fillet_edges`/`chamfer_edges` (approx via offset), `slot`, `teardrop` hole,
`text_emboss` with min-stroke enforcement. Redesign the 4 broken examples to work.

### C. Printer profiles + config (XDG, cross-platform)
- **Printer DB** committed in-repo: `harness/studio3d/data/printers.json` (29
  researched printers: Bambu A1/A1mini/P1/X1/H2D, Prusa MK4S/CORE One/XL/MINI,
  Creality K1/K2/Ender V3, Elegoo, Anycubic, resin) — build volume, nozzle, AMS
  color count, exact slicer presets (e.g. all 10 "@BBL A1" presets). Maintainable.
- **User profiles** in XDG config (`$XDG_CONFIG_HOME/studio3d/` →
  `~/.config/studio3d/` Linux, `~/Library/Application Support/studio3d/` macOS,
  `%APPDATA%\studio3d\` Windows): YAML per profile (make/model, AMS yes/no, filament
  colors) + a `profiles.json` manifest with the active profile.
- `studio3d profile` CLI (list/show/add/use/import-from-db) and a `printer-setup`
  skill so the agent guides setup ("I have a Bambu A1" → fills bed 256³, AMS lite,
  asks colors). The active profile drives bed-fit checks and 3MF (units + AMS color).

### D. Import & modify existing models
`studio3d import <file.stl|3mf|glb>` → load, repair, validate, register as a bundle.
`studio3d edit` applies mesh ops (scale, reorient, hollow/shell, boolean with new
CSG, emboss text) to an imported or generated mesh. The agent can load a user's STL
and modify it in a design session.

### E. Git-tracked change history (single evolving file set)
Each accepted change commits the model bundle to a git repo (in `output/` or a
dedicated history store) with a descriptive message → point-in-time recovery via
`studio3d history` / `revert`. **One evolving bundle per design**, not version
spam — revisions overwrite in place and are captured as commits, unless the user
explicitly asks to fork/branch a variant.

### F. Live updates to the viewer
The viewer polls `manifest.json` (and per-model mtime) on an interval / via a small
dev SSE endpoint, so when the agent regenerates a model the user sees it update live
during the session. A `studio3d watch`/sync keeps `web/public/output` in step.

### G. Packaging & repeatability
Deterministic seeds, pinned deps, profile-driven config, evidence in `report.json`,
git history. `studio3d doctor` checks Blender + venv + profile.

## Open questions for the council
1. Is the **visual-critique loop** the right primary mechanism for 99% fidelity, or
   should we lean harder on a hosted generative API for organic shapes?
2. Git history: commit to a repo *inside* `output/` vs a separate history store —
   which avoids surprising the user's own VCS while giving clean recovery?
3. Live update: simple polling vs a dev SSE/websocket — what's the least-moving-parts
   choice that still feels "live"?
4. Profiles in XDG: is a YAML-per-profile + JSON manifest the right shape, and how do
   we keep the in-repo printer DB current without manual drift?
5. Scope/sequencing: what is the minimum that delivers "meets/exceeds expectations"
   without overbuilding?
