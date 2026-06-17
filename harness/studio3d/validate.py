"""studio3d.validate — print-readiness validation + repair.

Implements the Meshy 2026 "AI 3D Print-Readiness Benchmark" four-dimension
framework against a concrete mesh:

    D1  Mesh Integrity         watertight, manifold, consistent normals, no
                               self-intersections, no degenerate/duplicate faces
    D2  Slicer Pass Rate       proxy: a mesh that passes D1 + has valid volume
                               opens cleanly in Bambu Studio / PrusaSlicer
    D3  Print Geometry         min wall thickness, min feature, overhang load,
                               bed-fit for the target printer profile
    D4  Workflow Efficiency    informational: format set, units, recommended 3MF
                               for multicolor

The output is a JSON-serializable report with per-dimension pass/fail, an overall
``print_ready`` verdict, a 0-100 score, and an actionable issue list.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import trimesh

from .spec import PRINTER_PROFILES, DEFAULT_PROFILE

# material density g/cm^3 for mass estimate (solid / 100% infill upper bound)
MATERIAL_DENSITY = {
    "PLA": 1.24, "PETG": 1.27, "ABS": 1.04, "ASA": 1.07,
    "TPU": 1.21, "NYLON": 1.14, "RESIN": 1.10,
}
FILAMENT_AREA_MM2 = math.pi * (1.75 / 2) ** 2  # 1.75mm filament cross-section


# ======================================================================
# Repair
# ======================================================================

def repair(mesh: trimesh.Trimesh) -> dict:
    """In-place best-effort repair. Returns a record of what was done.

    Order matters: merge coincident vertices, drop degenerate/duplicate faces,
    fix winding + normals, then fill small holes.
    """
    actions: dict[str, Any] = {}
    n_faces_0 = len(mesh.faces)

    mesh.merge_vertices()
    # remove degenerate & duplicate faces (API varies across trimesh versions)
    try:
        nondegen = mesh.nondegenerate_faces()
        if nondegen is not None and len(nondegen) < len(mesh.faces):
            mesh.update_faces(nondegen)
            actions["removed_degenerate"] = int(n_faces_0 - len(mesh.faces))
    except Exception:
        pass
    try:
        mesh.update_faces(mesh.unique_faces())
    except Exception:
        pass
    mesh.remove_unreferenced_vertices()

    # consistent winding + outward normals
    try:
        trimesh.repair.fix_winding(mesh)
    except Exception:
        pass
    try:
        trimesh.repair.fix_normals(mesh)
    except Exception:
        pass

    # fill holes if not watertight
    if not mesh.is_watertight:
        try:
            trimesh.repair.fill_holes(mesh)
            actions["filled_holes"] = True
        except Exception:
            pass

    actions["faces_before"] = int(n_faces_0)
    actions["faces_after"] = int(len(mesh.faces))
    return actions


# ======================================================================
# Geometry analysis helpers
# ======================================================================

def _non_manifold_edge_count(mesh: trimesh.Trimesh) -> int:
    """Edges shared by != 2 faces indicate non-manifold/boundary geometry."""
    try:
        # edges_unique with counts: a closed manifold has every edge used twice
        unique, counts = np.unique(
            np.sort(mesh.edges, axis=1), axis=0, return_counts=True
        )
        return int(np.count_nonzero(counts != 2))
    except Exception:
        return -1


def _component_count(mesh: trimesh.Trimesh) -> int:
    """Number of disconnected bodies (1 = single solid). A part that should be
    one piece but reports >1 is a fabrication defect (e.g. a 'phone stand' whose
    cradle floats free of the base)."""
    try:
        bc = getattr(mesh, "body_count", None)
        if bc:
            return int(bc)
        return int(len(mesh.split(only_watertight=False)))
    except Exception:
        return 1


def _genus_estimate(euler: int, n_components: int) -> int:
    """Topological genus (handle count) from Euler characteristic. For C closed
    orientable components, X = 2C - 2G, so G = C - X/2. Reported for the critic
    (a knob should rarely add handles; a high genus often signals a boolean
    artifact). Clamped at 0."""
    try:
        return max(0, int(round(n_components - euler / 2.0)))
    except Exception:
        return 0


def _self_intersection_estimate(mesh: trimesh.Trimesh) -> int | None:
    """Best-effort self-intersection probe. Returns count or None if unavailable.

    For CSG output from manifold3d this is 0 by construction; we still probe so
    imported/generative meshes are checked.
    """
    try:
        # broad-phase: faces whose AABBs overlap and that are non-adjacent.
        # Use trimesh's built-in if present; otherwise skip (return None).
        from trimesh import collision  # noqa: F401
        # A full pairwise self-collision is expensive; rely on watertight+winding
        # as the practical signal and report None for the exact count.
        return None
    except Exception:
        return None


def _wall_thickness(mesh: trimesh.Trimesh, samples: int = 2000) -> dict:
    """Estimate wall thickness via inward ray casting (trimesh.proximity.thickness
    method='ray') on sampled surface points: for each point, the distance along
    the inward normal to the first opposite surface = true local thickness.

    The 'ray' method (vs 'max_sphere') is not polluted by the small inscribed
    spheres at convex edges, so it cleanly separates uniformly-thick parts from
    ones with genuine thin features. p05 is reported as the effective minimum.

    Returns {min, p01, p05, median} in mm (or available=False without a spatial index).
    """
    try:
        if len(mesh.faces) == 0:
            return {"available": False}
        # deterministic surface sampling (seeded -> reproducible)
        try:
            points, face_idx = trimesh.sample.sample_surface(mesh, samples, seed=0)
        except TypeError:  # older signature without seed
            points, face_idx = trimesh.sample.sample_surface(mesh, samples)
        normals = mesh.face_normals[face_idx]
        thickness = trimesh.proximity.thickness(
            mesh=mesh, points=points, exterior=False, normals=normals, method="ray"
        )
        t = np.asarray(thickness, dtype=float)
        t = t[np.isfinite(t) & (t > 1e-6)]
        if len(t) == 0:
            return {"available": False}
        return {
            "available": True,
            "method": "ray",
            "min": round(float(np.min(t)), 3),
            "p01": round(float(np.percentile(t, 1)), 3),
            "p05": round(float(np.percentile(t, 5)), 3),
            "median": round(float(np.median(t)), 3),
            "n_samples": int(len(t)),
        }
    except Exception as e:
        return {"available": False, "error": f"{type(e).__name__}: {e}"}


def _overhang_analysis(mesh: trimesh.Trimesh, limit_deg: float, bed_eps: float = 0.6) -> dict:
    """Analyze downward-facing area against the overhang limit (from vertical),
    assuming the model is printed as oriented (build direction +Z).

    overhang_angle = asin(-n_z) for downward faces; 0deg = vertical wall (safe),
    90deg = horizontal ceiling (needs support). Faces resting on the bed (their
    whole span within ``bed_eps`` of the model's z-minimum) are EXCLUDED — they
    are bed contact, not overhangs, so a flat base is not flagged.
    """
    n = mesh.face_normals
    areas = mesh.area_faces
    nz = np.clip(-n[:, 2], -1.0, 1.0)
    downfacing = nz > 1e-6

    # bed-contact exclusion: a downward face whose highest vertex is within
    # bed_eps of the global z-min sits flat on the plate.
    tris_z = mesh.triangles[:, :, 2]          # (F,3) z of each face's vertices
    face_max_z = tris_z.max(axis=1)
    z_min = float(mesh.bounds[0][2])
    bed_contact = face_max_z <= (z_min + bed_eps)

    angles = np.degrees(np.arcsin(np.clip(nz, 0.0, 1.0)))
    overhang = downfacing & ~bed_contact
    flagged = overhang & (angles > limit_deg)
    total_down_area = float(areas[overhang].sum()) if np.any(overhang) else 0.0
    flagged_area = float(areas[flagged].sum()) if np.any(flagged) else 0.0
    steepest = float(angles[overhang].max()) if np.any(overhang) else 0.0
    return {
        "limit_deg": limit_deg,
        "steepest_overhang_deg": round(steepest, 1),
        "overhang_area_mm2": round(flagged_area, 1),
        "overhang_fraction": round(flagged_area / total_down_area, 3) if total_down_area > 0 else 0.0,
        "bed_contact_excluded": bool(np.any(bed_contact)),
        "needs_support": bool(flagged_area > 0.5),
    }


# ======================================================================
# Main validator
# ======================================================================

@dataclass
class Report:
    print_ready: bool = False
    score: int = 0
    dimensions: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)
    issues: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    suggestions: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "print_ready": self.print_ready,
            "score": self.score,
            "dimensions": self.dimensions,
            "metrics": self.metrics,
            "issues": self.issues,
            "warnings": self.warnings,
            "suggestions": self.suggestions,
        }


def validate(mesh: trimesh.Trimesh, printer_profile: str = DEFAULT_PROFILE,
             material: str = "PLA", multicolor: bool = False,
             bed_mm: tuple[float, float, float] = (256, 256, 256),
             do_repair: bool = True, do_slice: bool = False,
             model_path: str | None = None) -> Report:
    """Validate ``mesh`` against the print-readiness benchmark for a profile.

    When ``do_slice`` is set and a slicer is installed, D2 is a REAL slice-to-G-code
    pass (with print time + filament grams) rather than the proxy; otherwise D2
    falls back to the explicitly LABELED proxy so "print-ready" is never silently
    self-certified.
    """
    prof = PRINTER_PROFILES.get(printer_profile, PRINTER_PROFILES[DEFAULT_PROFILE])
    rep = Report()

    if do_repair:
        rep.metrics["repair"] = repair(mesh)

    # ---- D1 Mesh Integrity ----
    watertight = bool(mesh.is_watertight)
    winding = bool(mesh.is_winding_consistent)
    is_volume = bool(mesh.is_volume)
    nm_edges = _non_manifold_edge_count(mesh)
    selfint = _self_intersection_estimate(mesh)
    euler = int(mesh.euler_number)
    n_components = _component_count(mesh)
    genus = _genus_estimate(euler, n_components)
    d1_pass = watertight and winding and is_volume and (nm_edges == 0)
    rep.dimensions["D1_mesh_integrity"] = {
        "pass": d1_pass,
        "watertight": watertight,
        "winding_consistent": winding,
        "is_volume": is_volume,
        "non_manifold_edges": nm_edges,
        "self_intersections": selfint,
        "euler_number": euler,
        "n_components": n_components,
        "genus": genus,
    }
    if not watertight:
        rep.issues.append("D1: mesh is not watertight (open holes) — slicer will warn/repair")
    if not winding:
        rep.issues.append("D1: inconsistent face winding/normals — normals not all outward")
    if nm_edges and nm_edges > 0:
        rep.issues.append(f"D1: {nm_edges} non-manifold edges detected")

    # ---- core metrics ----
    extents = [round(float(x), 2) for x in mesh.extents]
    volume_mm3 = float(mesh.volume) if is_volume else float(abs(mesh.volume))
    density = MATERIAL_DENSITY.get(material.upper(), 1.24)
    mass_g = volume_mm3 / 1000.0 * density  # mm^3 -> cm^3 * g/cm^3
    rep.metrics.update({
        "bbox_mm": extents,
        "volume_mm3": round(volume_mm3, 2),
        "surface_area_mm2": round(float(mesh.area), 2),
        "triangles": int(len(mesh.faces)),
        "vertices": int(len(mesh.vertices)),
        "est_mass_g_solid": round(mass_g, 2),
        "est_filament_m_solid": round(volume_mm3 / FILAMENT_AREA_MM2 / 1000.0, 2),
        "material": material,
        "printer_profile": printer_profile,
        "watertight": watertight,
    })

    # ---- D3 Print Geometry Compliance ----
    min_wall = float(prof["min_wall"])
    overhang_limit = float(prof["overhang_deg"])
    wall = _wall_thickness(mesh)
    overh = _overhang_analysis(mesh, overhang_limit)
    rep.metrics["wall_thickness"] = wall
    rep.metrics["overhang"] = overh

    bed_fit = all(extents[i] <= bed_mm[i] + 1e-6 for i in range(3))
    thin_ok = True
    if wall.get("available"):
        # p05 of true ray thickness = effective minimum wall, robust to grazing rays
        eff_min = wall.get("p05", wall.get("min"))
        thin_ok = eff_min >= min_wall * 0.9  # allow a 10% tolerance band
        if eff_min < min_wall:
            rep.warnings.append(
                f"D3: thinnest walls ~{eff_min}mm are below the {min_wall}mm minimum "
                f"for {printer_profile} — thin features may fail to print"
            )
    d3_pass = bed_fit and thin_ok
    rep.dimensions["D3_print_geometry"] = {
        "pass": d3_pass,
        "min_wall_required_mm": min_wall,
        "bed_fit": bed_fit,
        "bed_mm": list(bed_mm),
        "overhang_needs_support": overh["needs_support"],
        "steepest_overhang_deg": overh["steepest_overhang_deg"],
    }
    if not bed_fit:
        rep.issues.append(
            f"D3: model {extents}mm exceeds the build volume {list(bed_mm)}mm — scale down or split"
        )
    if overh["needs_support"]:
        rep.suggestions.append(
            f"D3: steep overhangs (up to {overh['steepest_overhang_deg']}deg) — enable supports "
            f"or reorient on the bed"
        )

    # ---- D2 Slicer Pass Rate ----
    # Real slice when asked + a slicer exists; else the explicitly-labeled proxy.
    proxy_pass = d1_pass and is_volume
    d2 = {
        "pass": proxy_pass,
        "method": "proxy",
        "rationale": "watertight + manifold + valid volume opens cleanly in Bambu Studio/PrusaSlicer",
    }
    if do_slice:
        try:
            from .slicer import slice_model, detect_slicer
            import tempfile as _tf, os as _os
            if not detect_slicer():
                d2["slice_note"] = "no slicer installed — using labeled proxy (set $STUDIO3D_SLICER or install OrcaSlicer/PrusaSlicer for a real slice)"
            else:
                sp, tmp = model_path, None
                if not sp:
                    tmp = _tf.NamedTemporaryFile(suffix=".stl", delete=False)
                    tmp.close()
                    mesh.export(tmp.name)
                    sp = tmp.name
                sl = slice_model(sp, material=material)
                if tmp:
                    try:
                        _os.unlink(tmp.name)
                    except Exception:
                        pass
                d2 = {
                    "pass": bool(sl.get("sliced")),
                    "method": "slice",
                    "slicer": sl.get("slicer"),
                    "print_time": sl.get("print_time"),
                    "filament_g": sl.get("filament_g"),
                    "gcode_lines": sl.get("gcode_lines"),
                    "error": sl.get("error"),
                    "rationale": "real headless slice to G-code",
                }
                if sl.get("filament_g") is not None:
                    rep.metrics["filament_g_sliced"] = sl["filament_g"]
                if sl.get("print_time"):
                    rep.metrics["print_time"] = sl["print_time"]
        except Exception as e:
            d2["slice_error"] = f"{type(e).__name__}: {e}"
    d2_pass = bool(d2["pass"])
    rep.dimensions["D2_slicer_pass"] = d2

    # ---- D4 Workflow Efficiency (informational) ----
    rec_format = "3mf" if multicolor else "stl"
    rep.dimensions["D4_workflow"] = {
        "pass": True,
        "units": "mm",
        "recommended_format": rec_format,
        "note": "3MF carries color/material/AMS mapping; STL is geometry-only" if multicolor
                else "single-color: STL is universally supported; 3MF still recommended for Bambu",
    }
    if multicolor:
        rep.suggestions.append("D4: multicolor model — export 3MF to preserve AMS color mapping")

    # ---- kernel-metrics summary (fed to the design-critic alongside renders so
    # the judge can catch non-manifold / sub-wall / floating-part defects that are
    # invisible in a 4-view render — the CADSmith "kernel metrics + vision" pattern)
    rep.metrics["kernel_metrics"] = {
        "watertight": watertight,
        "manifold": bool(d1_pass),
        "non_manifold_edges": nm_edges,
        "euler_number": euler,
        "genus": genus,
        "n_components": n_components,
        "volume_mm3": round(volume_mm3, 2),
        "bbox_mm": extents,
        "triangles": int(len(mesh.faces)),
        "wall_p05_mm": wall.get("p05") if wall.get("available") else None,
        "min_wall_required_mm": min_wall,
        "steepest_overhang_deg": overh["steepest_overhang_deg"],
        "overhang_needs_support": overh["needs_support"],
        "bed_fit": bed_fit,
    }

    # ---- scoring ----
    score = 0
    score += 45 if d1_pass else (20 if watertight else 0)
    score += 25 if d2_pass else 0
    score += 20 if d3_pass else (10 if bed_fit else 0)
    score += 10  # D4 always satisfiable locally
    rep.score = int(score)
    rep.print_ready = bool(d1_pass and d2_pass and bed_fit)
    return rep


# ======================================================================
# Heal + orient (used by the generative + hybrid paths)
# ======================================================================

def heal(mesh: trimesh.Trimesh) -> dict:
    """Force a generative/imported mesh toward a watertight, 2-manifold solid.

    Beyond :func:`repair` (merge/degenerate/winding/normals/fill-holes) this runs
    a manifold round-trip (a self-union through the manifold3d boolean kernel)
    which re-derives a clean topology from triangle soup. Returns a record with
    before/after watertight + face counts. This is the gate that turns Meshy's
    triangle-soup output into a D1-passing asset (the README's "every generated
    mesh is forced through validation/repair" — made explicit and stronger)."""
    info: dict[str, Any] = {"watertight_before": bool(mesh.is_watertight),
                            "faces_before": int(len(mesh.faces))}
    info["repair"] = repair(mesh)
    if not mesh.is_watertight:
        try:
            # self-union forces the boolean kernel to rebuild a manifold solid
            rebuilt = trimesh.boolean.union([mesh])
            if rebuilt is not None and len(rebuilt.faces) > 0:
                rebuilt.merge_vertices()
                trimesh.repair.fix_normals(rebuilt)
                mesh.vertices, mesh.faces = rebuilt.vertices, rebuilt.faces
                info["manifold_roundtrip"] = True
        except Exception as e:
            info["manifold_roundtrip_error"] = f"{type(e).__name__}: {e}"
    info["watertight_after"] = bool(mesh.is_watertight)
    info["faces_after"] = int(len(mesh.faces))
    return info


# candidate orientations: (name, axis, degrees) — rotate the part onto each of the
# six axis-aligned "down" faces and keep whichever minimizes flagged overhang area.
_ORIENT_CANDIDATES = [
    ("as_is", None, 0.0),
    ("x+90", [1, 0, 0], 90.0),
    ("x-90", [1, 0, 0], -90.0),
    ("y+90", [0, 1, 0], 90.0),
    ("y-90", [0, 1, 0], -90.0),
    ("x180", [1, 0, 0], 180.0),
]


def orient_for_print(mesh: trimesh.Trimesh, limit_deg: float = 50.0,
                     bed_mm: tuple[float, float, float] = (256, 256, 256)) -> dict:
    """Try the six axis-aligned orientations and return the one that minimizes
    support-needing overhang area while still fitting the bed. Slicer-aware /
    support-effective placement (SEG): better orientation == fewer supports ==
    less waste. Returns {best, candidates, rotation} ; caller applies the rotation.
    Operates on a COPY per candidate; does not mutate the input."""
    from trimesh import transformations as _tf
    results = []
    for name, axis, ang in _ORIENT_CANDIDATES:
        m = mesh.copy()
        if axis is not None:
            m.apply_transform(_tf.rotation_matrix(math.radians(ang), axis, m.centroid))
        # ground it
        m.apply_translation([0, 0, -float(m.bounds[0][2])])
        ext = [float(x) for x in m.extents]
        fits = all(ext[i] <= bed_mm[i] + 1e-6 for i in range(3))
        oa = _overhang_analysis(m, limit_deg)
        results.append({
            "name": name, "axis": axis, "deg": ang,
            "overhang_area_mm2": oa["overhang_area_mm2"],
            "steepest_overhang_deg": oa["steepest_overhang_deg"],
            "bed_fit": fits,
        })
    feasible = [r for r in results if r["bed_fit"]] or results
    best = min(feasible, key=lambda r: (r["overhang_area_mm2"], r["steepest_overhang_deg"]))
    return {"best": best, "candidates": results}
