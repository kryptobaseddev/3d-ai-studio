---
name: printer-setup
description: Set up and manage the user's 3D printer profile(s) so generated files target their real machine — make/model, AMS/multi-material, and filament colors. Use when the user mentions their printer (e.g. "I have a Bambu A1"), asks to configure printing, set filament colors, switch printers, or when no active profile exists at the start of a design session. Profiles are stored cross-platform in the XDG config dir and drive bed-fit, wall minimums, and 3MF/AMS color mapping.
---

# printer-setup — manage printer profiles

Generated files must match the user's actual printer. studio3d keeps a **printer
database** (in-repo, `studio3d printers`) and the user's **profiles** (YAML in the OS
config dir; one active). The active profile sets the build volume (bed-fit), the
process profile (nozzle → wall minimums), and AMS color mapping for 3MF.

## When there is no active profile
Walk the user through setup conversationally:

1. **Which printer?** Ask the make/model, then look it up:
   ```bash
   studio3d printers --search "bambu a1"
   ```
   Show the matches (build volume, nozzle, AMS capacity, available quality presets)
   and confirm the right one.
2. **AMS / multi-material?** Ask whether they have the AMS/MMU/CFS unit and how many
   filaments are loaded. (e.g. Bambu A1 → AMS lite, up to 4 colors.)
3. **Filament colors.** Ask for the loaded colors (names or hex). Map them to slots.
4. **Create the profile:**
   ```bash
   studio3d profile add --name "my-a1" --printer "Bambu Lab A1" \
     --ams true --colors "#1a1a1a,#f5f5f5,#e23b3b,#2b6cd4" --material PLA
   ```
   This becomes the active profile (it is written to the XDG config dir, e.g.
   `~/.config/studio3d/profiles/my-a1.yaml` on Linux — editable by hand).

## Managing profiles
```bash
studio3d profile list                 # all profiles + which is active + config dir
studio3d profile show [--name <n>]    # full details of a profile
studio3d profile use <name>           # switch the active printer
studio3d profile add ...              # add another printer (the user can have several)
```

## What the active profile changes
- **Bed-fit**: a model that exceeds the printer's build volume is flagged (D3).
- **Wall minimums**: a 0.2mm-nozzle machine allows finer walls than a 0.4mm one.
- **Color / AMS**: when the user wants multicolor, the 3MF is written with the
  profile's palette mapped to AMS slots (≤ the printer's max color count).

## Keeping the printer database current
The in-repo database (`harness/studio3d/data/printers.json`, 29 printers across
Bambu, Prusa, Creality, Elegoo, Anycubic, Formlabs) is the maintained ground truth.
To refresh or add models, update that JSON (build volume, nozzle, AMS capacity, and
the slicer quality presets by name) — it is plain JSON, versioned with the repo.
