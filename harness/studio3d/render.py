"""studio3d.render — multi-view renders for the visual-critique loop.

The agent can only judge whether a model matches intent if it can *see* it. This
produces front/right/top/iso PNGs (Blender Workbench headless — fast, solid-shaded,
correctly oriented Z-up; matplotlib fallback if Blender is unavailable) that a
vision-capable agent inspects against the design request.
"""
from __future__ import annotations

import os
import shutil
import subprocess

DEFAULT_VIEWS = ("front", "right", "top", "iso")


def _blender_bin() -> str | None:
    return shutil.which("blender")


def render_views(mesh_path: str, out_dir: str, color: str = "#9aa7b2",
                 size: int = 720, views=DEFAULT_VIEWS, timeout: float = 180.0) -> dict:
    """Render the mesh from multiple angles. Returns {engine, views:{name:path}}."""
    os.makedirs(out_dir, exist_ok=True)
    blender = _blender_bin()
    if blender:
        try:
            return _render_blender(blender, mesh_path, out_dir, color, size, views, timeout)
        except Exception as e:
            res = _render_matplotlib(mesh_path, out_dir, color, size, views)
            res["blender_error"] = f"{type(e).__name__}: {e}"
            return res
    return _render_matplotlib(mesh_path, out_dir, color, size, views)


def _render_blender(blender, mesh_path, out_dir, color, size, views, timeout) -> dict:
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_blender_render.py")
    # blender's STL importer wants STL; if given GLB/3MF, convert to a temp STL
    work_mesh = _as_stl(mesh_path, out_dir)
    cmd = [
        blender, "--background", "--factory-startup", "--python", script, "--",
        work_mesh, out_dir, color, str(size), ",".join(views),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    rendered = {}
    for v in views:
        p = os.path.join(out_dir, f"view_{v}.png")
        if os.path.exists(p):
            rendered[v] = p
    if not rendered:
        raise RuntimeError("blender produced no views:\n" + (proc.stderr[-800:] or proc.stdout[-800:]))
    return {"engine": "blender-workbench", "views": rendered}


def _as_stl(mesh_path: str, out_dir: str) -> str:
    if mesh_path.lower().endswith(".stl"):
        return mesh_path
    import trimesh
    m = trimesh.load(mesh_path, force="mesh")
    if isinstance(m, trimesh.Scene):
        m = trimesh.util.concatenate([g for g in m.geometry.values()])
    tmp = os.path.join(out_dir, "_render_src.stl")
    m.export(tmp)
    return tmp


def _render_matplotlib(mesh_path, out_dir, color, size, views) -> dict:
    """Fallback: matplotlib 3D renders from a few azimuths (Z-up)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    import numpy as np
    import trimesh

    m = trimesh.load(mesh_path, force="mesh")
    if isinstance(m, trimesh.Scene):
        m = trimesh.util.concatenate([g for g in m.geometry.values()])
    verts, faces = np.asarray(m.vertices), np.asarray(m.faces)
    tris = verts[faces]
    nrm = m.face_normals
    light = np.array([0.3, -0.5, 0.8]); light = light / np.linalg.norm(light)
    shade = np.clip(nrm @ light, 0.15, 1.0)
    base = np.array([int((color.lstrip('#') + 'ffffff')[i:i+2], 16) / 255 for i in (0, 2, 4)])
    fc = np.clip(base[None, :] * shade[:, None], 0, 1)
    fc = np.concatenate([fc, np.ones((len(fc), 1))], axis=1)

    angles = {"front": (10, -90), "right": (10, 0), "top": (89, -90), "iso": (24, -55)}
    b = m.bounds; ctr = b.mean(0); span = float((b[1] - b[0]).max()) * 0.6 + 1e-6
    rendered = {}
    for v in views:
        elev, azim = angles.get(v, (24, -55))
        fig = plt.figure(figsize=(size / 100, size / 100), dpi=100)
        ax = fig.add_subplot(111, projection="3d")
        ax.add_collection3d(Poly3DCollection(tris, facecolors=fc, edgecolors=(0, 0, 0, 0.05), linewidths=0.2))
        for setlim, c in ((ax.set_xlim, ctr[0]), (ax.set_ylim, ctr[1]), (ax.set_zlim, ctr[2])):
            setlim(c - span, c + span)
        try: ax.set_box_aspect((1, 1, 1))
        except Exception: pass
        ax.view_init(elev=elev, azim=azim); ax.set_axis_off()
        fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
        p = os.path.join(out_dir, f"view_{v}.png")
        fig.savefig(p, transparent=True); plt.close(fig)
        rendered[v] = p
    return {"engine": "matplotlib", "views": rendered}
