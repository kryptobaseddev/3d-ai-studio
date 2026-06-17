"""studio3d.slicer — real, headless slice-to-G-code for D2 (slicer pass rate).

D2 was a *proxy* (a watertight + valid-volume mesh "opens cleanly"). That is a
self-certification a generative competitor can also claim. This module turns the
print-readiness claim into ground truth: it detects an installed slicer
(OrcaSlicer / PrusaSlicer / Bambu Studio / SuperSlicer / CuraEngine), runs it
headless on the exported model, and reports a real slice-or-fail plus print time
and filament grams parsed from the G-code.

When no slicer is present, callers fall back to the explicit, LABELED proxy
(``d2_method="proxy"``) — the pipeline still runs offline, but "print-ready" is
never silently self-certified again.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile

# CLI candidates in priority order. Each: (name, [executable names], slice_args_fn).
# slice_args_fn(infile, outdir) -> (argv, gcode_path)
_DENSITY = {"PLA": 1.24, "PETG": 1.27, "ABS": 1.04, "ASA": 1.07, "TPU": 1.21,
            "NYLON": 1.14, "RESIN": 1.10}


def detect_slicer() -> dict | None:
    """Return {name, exe} for the first slicer found on PATH, else None.

    Honors ``$STUDIO3D_SLICER`` (an explicit executable path) first.
    """
    override = os.environ.get("STUDIO3D_SLICER")
    if override and (shutil.which(override) or os.path.exists(override)):
        return {"name": os.path.basename(override), "exe": override}
    candidates = [
        ("orcaslicer", ["orcaslicer", "orca-slicer", "OrcaSlicer"]),
        ("prusaslicer", ["prusa-slicer", "prusaslicer", "PrusaSlicer"]),
        ("bambustudio", ["bambu-studio", "bambustudio", "BambuStudio"]),
        ("superslicer", ["superslicer", "SuperSlicer"]),
        ("curaengine", ["CuraEngine", "curaengine"]),
    ]
    for name, exes in candidates:
        for exe in exes:
            found = shutil.which(exe)
            if found:
                return {"name": name, "exe": found}
    return None


def _parse_gcode_metadata(gcode_path: str, material: str = "PLA") -> dict:
    """Pull print-time + filament estimates from slicer G-code comments. Orca/
    Prusa/Bambu all embed these as ``; ...`` comment lines near the file head/tail."""
    out: dict = {}
    try:
        with open(gcode_path, "r", errors="ignore") as f:
            head = f.read(200_000)  # comments live in the header/footer region
    except Exception:
        return out
    # filament used (mm or g)
    m = re.search(r"filament used \[g\]\s*=\s*([\d.]+)", head)
    if m:
        out["filament_g"] = round(float(m.group(1)), 2)
    m = re.search(r"filament used \[mm\]\s*=\s*([\d.]+)", head)
    if m and "filament_g" not in out:
        # mm of 1.75mm filament -> grams
        vol_mm3 = float(m.group(1)) * 3.14159 * (1.75 / 2) ** 2
        out["filament_g"] = round(vol_mm3 / 1000.0 * _DENSITY.get(material.upper(), 1.24), 2)
    # print time
    m = re.search(r"estimated printing time.*?=\s*(.+)", head)
    if m:
        out["print_time"] = m.group(1).strip()
    m = re.search(r"model printing time:\s*(.+?);", head)
    if m and "print_time" not in out:
        out["print_time"] = m.group(1).strip()
    return out


def slice_model(model_path: str, material: str = "PLA", timeout: float = 120.0) -> dict:
    """Slice ``model_path`` (STL/3MF) to G-code with a detected slicer.

    Returns a dict:
        {available: bool, method: 'slice'|'proxy', sliced: bool, slicer, gcode_lines,
         print_time, filament_g, error}
    ``available=False`` means no slicer was found — the caller uses the labeled proxy.
    """
    slicer = detect_slicer()
    if not slicer:
        return {"available": False, "method": "proxy",
                "reason": "no slicer on PATH (set $STUDIO3D_SLICER or install OrcaSlicer/PrusaSlicer)"}

    exe, name = slicer["exe"], slicer["name"]
    with tempfile.TemporaryDirectory(prefix="studio3d_slice_") as td:
        gcode = os.path.join(td, "out.gcode")
        if name in ("orcaslicer", "prusaslicer", "bambustudio", "superslicer"):
            # PrusaSlicer-family CLI: --export-gcode -o OUT IN  (--slice for some forks)
            argv = [exe, "--export-gcode", "-o", gcode, model_path]
        else:  # curaengine — needs a definition; best-effort
            argv = [exe, "slice", "-l", model_path, "-o", gcode]
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                                  env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})
        except subprocess.TimeoutExpired:
            return {"available": True, "method": "slice", "sliced": False,
                    "slicer": name, "error": f"slicer timed out after {timeout}s"}
        except Exception as e:
            return {"available": True, "method": "slice", "sliced": False,
                    "slicer": name, "error": f"{type(e).__name__}: {e}"}

        ok = proc.returncode == 0 and os.path.exists(gcode) and os.path.getsize(gcode) > 0
        result = {"available": True, "method": "slice", "sliced": bool(ok), "slicer": name}
        if ok:
            try:
                with open(gcode, errors="ignore") as f:
                    result["gcode_lines"] = sum(1 for _ in f)
            except Exception:
                pass
            result.update(_parse_gcode_metadata(gcode, material))
        else:
            tail = (proc.stderr or proc.stdout or "").strip()[-600:]
            result["error"] = tail or "slicer produced no g-code"
        return result
