"""studio3d.exporters — emit print-ready artifacts + a web manifest.

Outputs, per model bundle:
    model.stl   binary STL (geometry, mm) — universal slicer input
    model.3mf   3MF with millimeter units + base-material color — Bambu/Orca/Prusa
    model.glb   glTF binary for the web viewer
    thumb.png   headless 3/4-view render (matplotlib Agg)
    spec.json   the ModelSpec that produced it
    report.json the print-readiness report

A top-level output/manifest.json indexes every bundle so the static web UI needs
no live backend.
"""
from __future__ import annotations

import json
import os
import zipfile
from typing import Iterable

import numpy as np
import trimesh


# ======================================================================
# Geometry formats
# ======================================================================

def export_stl(mesh: trimesh.Trimesh, path: str) -> str:
    mesh.export(path, file_type="stl")  # trimesh writes binary STL
    return path


def export_glb(mesh: trimesh.Trimesh, path: str, color: str | None = None) -> str:
    m = mesh.copy()
    if color:
        rgba = _hex_to_rgba(color)
        m.visual = trimesh.visual.ColorVisuals(m, face_colors=np.tile(rgba, (len(m.faces), 1)))
    scene = trimesh.Scene(m)
    glb = trimesh.exchange.gltf.export_glb(scene)
    with open(path, "wb") as f:
        f.write(glb)
    return path


def export_3mf(mesh: trimesh.Trimesh, path: str, color: str | None = "#9aa7b2",
               name: str = "model") -> str:
    """Write a spec-compliant 3MF (OPC zip) with millimeter units and a base
    material color. Compatible with Bambu Studio / OrcaSlicer / PrusaSlicer."""
    verts = np.asarray(mesh.vertices, dtype=float)
    faces = np.asarray(mesh.faces, dtype=int)

    v_lines = "".join(
        f'<vertex x="{x:.5f}" y="{y:.5f}" z="{z:.5f}"/>' for x, y, z in verts
    )
    t_lines = "".join(
        f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in faces
    )
    col = (color or "#9aa7b2").upper()
    if len(col) == 7:
        col = col + "FF"  # add alpha

    model_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<model unit="millimeter" xml:lang="en-US" '
        'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
        'xmlns:m="http://schemas.microsoft.com/3dmanufacturing/material/2015/02">\n'
        f'  <metadata name="Title">{_xml_escape(name)}</metadata>\n'
        '  <metadata name="Application">studio3d</metadata>\n'
        '  <resources>\n'
        f'    <m:colorgroup id="1"><m:color color="{col}"/></m:colorgroup>\n'
        '    <object id="2" type="model" pid="1" pindex="0">\n'
        f'      <mesh><vertices>{v_lines}</vertices>'
        f'<triangles>{t_lines}</triangles></mesh>\n'
        '    </object>\n'
        '  </resources>\n'
        '  <build><item objectid="2"/></build>\n'
        '</model>\n'
    )

    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
        '</Types>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Target="/3D/3dmodel.model" Id="rel0" '
        'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
        '</Relationships>'
    )

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("3D/3dmodel.model", model_xml)
    return path


# ======================================================================
# Thumbnail (headless)
# ======================================================================

def render_thumbnail(mesh: trimesh.Trimesh, path: str, size: int = 640,
                     color: str | None = "#3a86ff", max_faces: int = 60000) -> str:
    """Headless 3/4-view shaded render via matplotlib Agg (no GPU needed)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    m = mesh
    faces = np.asarray(m.faces)
    verts = np.asarray(m.vertices)
    # subsample faces for very dense meshes to keep render fast
    if len(faces) > max_faces:
        idx = np.linspace(0, len(faces) - 1, max_faces).astype(int)
        faces = faces[idx]

    tris = verts[faces]  # (F,3,3)

    # simple lambert shading from face normals
    nrm = m.face_normals[: len(faces)] if len(m.face_normals) >= len(faces) else _compute_normals(tris)
    light = np.array([0.3, -0.5, 0.8])
    light = light / np.linalg.norm(light)
    shade = np.clip(nrm @ light, 0.15, 1.0)
    base = np.array(_hex_to_rgba(color or "#3a86ff")[:3]) / 255.0
    facecolors = np.clip(base[None, :] * shade[:, None], 0, 1)
    facecolors = np.concatenate([facecolors, np.ones((len(facecolors), 1))], axis=1)

    fig = plt.figure(figsize=(size / 100, size / 100), dpi=100)
    ax = fig.add_subplot(111, projection="3d")
    coll = Poly3DCollection(tris, facecolors=facecolors, edgecolors=(0, 0, 0, 0.06), linewidths=0.2)
    ax.add_collection3d(coll)

    b = m.bounds
    ctr = b.mean(axis=0)
    span = float((b[1] - b[0]).max()) * 0.6 + 1e-6
    ax.set_xlim(ctr[0] - span, ctr[0] + span)
    ax.set_ylim(ctr[1] - span, ctr[1] + span)
    ax.set_zlim(ctr[2] - span, ctr[2] + span)
    try:
        ax.set_box_aspect((1, 1, 1))
    except Exception:
        pass
    ax.view_init(elev=22, azim=-55)
    ax.set_axis_off()
    fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
    fig.savefig(path, transparent=True)
    plt.close(fig)
    return path


# ======================================================================
# Bundle + manifest
# ======================================================================

def write_bundle(mesh: trimesh.Trimesh, out_dir: str, spec, report, formats: Iterable[str]) -> dict:
    """Write all requested artifacts for one model into ``out_dir``.

    Returns a manifest entry dict.
    """
    os.makedirs(out_dir, exist_ok=True)
    color = getattr(spec, "color", None)
    files: dict[str, str] = {}

    fmts = set(f.lower() for f in formats)
    if "stl" in fmts:
        files["stl"] = os.path.basename(export_stl(mesh, os.path.join(out_dir, "model.stl")))
    if "3mf" in fmts:
        files["3mf"] = os.path.basename(export_3mf(mesh, os.path.join(out_dir, "model.3mf"),
                                                   color=color or "#9aa7b2", name=spec.name))
    if "glb" in fmts:
        files["glb"] = os.path.basename(export_glb(mesh, os.path.join(out_dir, "model.glb"), color=color))
    # always render a thumbnail
    try:
        files["thumb"] = os.path.basename(render_thumbnail(mesh, os.path.join(out_dir, "thumb.png"), color=color))
    except Exception as e:
        files["thumb_error"] = f"{type(e).__name__}: {e}"

    # spec + report
    with open(os.path.join(out_dir, "spec.json"), "w", encoding="utf-8") as f:
        f.write(spec.to_json())
    with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as f:
        json.dump(report.to_dict() if hasattr(report, "to_dict") else report, f, indent=2)

    entry = {
        "id": os.path.basename(out_dir.rstrip("/")),
        "name": spec.name,
        "prompt": spec.prompt,
        "category": spec.category,
        "engine": spec.resolved_engine,
        "printer_profile": spec.printer_profile,
        "files": files,
        "print_ready": report.print_ready if hasattr(report, "print_ready") else None,
        "score": report.score if hasattr(report, "score") else None,
        "bbox_mm": report.metrics.get("bbox_mm") if hasattr(report, "metrics") else None,
        "bed_mm": report.dimensions.get("D3_print_geometry", {}).get("bed_mm") if hasattr(report, "dimensions") else None,
        "est_mass_g": report.metrics.get("est_mass_g_solid") if hasattr(report, "metrics") else None,
        "color": color,
    }
    return entry


def write_manifest(output_root: str) -> str:
    """Scan ``output_root`` for bundles (dirs with report.json) and write a
    manifest.json the web UI consumes. Returns the manifest path."""
    bundles = []
    for name in sorted(os.listdir(output_root)):
        d = os.path.join(output_root, name)
        rep_path = os.path.join(d, "report.json")
        spec_path = os.path.join(d, "spec.json")
        if not (os.path.isdir(d) and os.path.exists(rep_path)):
            continue
        try:
            with open(rep_path) as f:
                rep = json.load(f)
            spec = {}
            if os.path.exists(spec_path):
                with open(spec_path) as f:
                    spec = json.load(f)
            files = {}
            for fn, key in (("model.stl", "stl"), ("model.3mf", "3mf"),
                            ("model.glb", "glb"), ("thumb.png", "thumb")):
                if os.path.exists(os.path.join(d, fn)):
                    files[key] = fn
            bundles.append({
                "id": name,
                "name": spec.get("name", name),
                "prompt": spec.get("prompt", ""),
                "category": spec.get("category"),
                "printer_profile": spec.get("printer_profile"),
                "files": files,
                "print_ready": rep.get("print_ready"),
                "score": rep.get("score"),
                "bbox_mm": rep.get("metrics", {}).get("bbox_mm"),
                "bed_mm": rep.get("dimensions", {}).get("D3_print_geometry", {}).get("bed_mm"),
                "est_mass_g": rep.get("metrics", {}).get("est_mass_g_solid"),
                "color": spec.get("color"),
            })
        except Exception:
            continue
    manifest = {"generator": "studio3d", "count": len(bundles), "models": bundles}
    path = os.path.join(output_root, "manifest.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    return path


# ======================================================================
# helpers
# ======================================================================

def _hex_to_rgba(hex_color: str) -> list[int]:
    h = (hex_color or "#9aa7b2").lstrip("#")
    if len(h) == 6:
        h += "ff"
    return [int(h[i:i + 2], 16) for i in (0, 2, 4, 6)]


def _xml_escape(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _compute_normals(tris: np.ndarray) -> np.ndarray:
    v0, v1, v2 = tris[:, 0], tris[:, 1], tris[:, 2]
    n = np.cross(v1 - v0, v2 - v0)
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    ln[ln == 0] = 1
    return n / ln
