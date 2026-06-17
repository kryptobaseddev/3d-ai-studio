"""studio3d.dsl — a manifold-by-construction CSG geometry DSL.

This is the surface the `cad-author` agent writes against. Every operation is
backed by trimesh + the manifold3d boolean engine, so results are watertight and
manifold by construction. All units are MILLIMETERS.

Author a model by defining either:

    def build():
        base = box(40, 20, 10)
        hole = cylinder(d=6, h=40).rotate_x(90).at(0, 0, 5)
        return base - hole          # difference via operator overload

or by assigning a module-level ``result``:

    result = box(10, 10, 10) + sphere(d=8).at(5, 5, 10)

The sandbox executes the script, retrieves the resulting :class:`Solid`, and
hands it to the validator/exporter.
"""
from __future__ import annotations

import math
from typing import Iterable, Sequence

import numpy as np
import trimesh
from trimesh import transformations as tf

__all__ = [
    "Solid",
    "box",
    "cube",
    "rounded_box",
    "cylinder",
    "cone",
    "sphere",
    "ellipsoid",
    "capsule",
    "torus",
    "wedge",
    "prism",
    "tube",
    "slot",
    "teardrop",
    "polygon",
    "extrude",
    "revolve",
    "twist_extrude",
    "loft",
    "text",
    "union",
    "difference",
    "intersection",
    "hull",
    "linear_pattern",
    "circular_pattern",
    "load_mesh",
    "interference",
    "arrange_on_bed",
    "paint",
    "multicolor_union",
    "deg",
    "PI",
]

PI = math.pi


def deg(d: float) -> float:
    """Convenience: degrees -> radians."""
    return math.radians(d)


def _as_mesh(obj) -> trimesh.Trimesh:
    if isinstance(obj, Solid):
        return obj.mesh
    if isinstance(obj, trimesh.Trimesh):
        return obj
    raise TypeError(f"expected Solid/Trimesh, got {type(obj)!r}")


class Solid:
    """An immutable manifold solid. Transform/CSG ops return new ``Solid``s.

    Operators:
        a + b   union
        a | b   union (alias)
        a - b   difference (cut b out of a)
        a & b   intersection
    """

    __slots__ = ("mesh", "_name", "_color")

    def __init__(self, mesh: trimesh.Trimesh, name: str = "solid", color: str | None = None):
        if not isinstance(mesh, trimesh.Trimesh):
            raise TypeError("Solid wraps a trimesh.Trimesh")
        # always work on a copy so transforms never mutate a shared mesh
        self.mesh = mesh.copy()
        self._name = name
        self._color = color

    # ---- color (for per-part / AMS multicolor) -------------------------
    def paint(self, color: str) -> "Solid":
        """Tag this solid with a hex color (e.g. '#e23b3b'). Used by
        :func:`multicolor_union` to assign per-face colors on a single union so
        the 3MF carries AMS multicolor. Returns a new colored Solid."""
        return Solid(self.mesh, self._name, color=color)

    # ---- introspection -------------------------------------------------
    @property
    def bounds(self) -> np.ndarray:
        """2x3 array: [[minx,miny,minz],[maxx,maxy,maxz]] in mm."""
        return self.mesh.bounds

    @property
    def size(self) -> np.ndarray:
        """Bounding-box dimensions [dx, dy, dz] in mm."""
        return self.mesh.extents

    @property
    def center(self) -> np.ndarray:
        """Bounding-box center point."""
        return self.mesh.bounds.mean(axis=0)

    @property
    def centroid(self) -> np.ndarray:
        return self.mesh.centroid

    @property
    def volume(self) -> float:
        return float(self.mesh.volume)

    @property
    def is_manifold(self) -> bool:
        return bool(self.mesh.is_watertight and self.mesh.is_winding_consistent)

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        s = self.size
        return f"<Solid {self._name} size=({s[0]:.1f},{s[1]:.1f},{s[2]:.1f})mm faces={len(self.mesh.faces)}>"

    # ---- transforms ----------------------------------------------------
    def _xform(self, matrix: np.ndarray, name: str | None = None) -> "Solid":
        m = self.mesh.copy()
        m.apply_transform(matrix)
        return Solid(m, name or self._name, color=self._color)

    def translate(self, x: float = 0, y: float = 0, z: float = 0) -> "Solid":
        return self._xform(tf.translation_matrix([x, y, z]))

    # ergonomic alias
    def move(self, x: float = 0, y: float = 0, z: float = 0) -> "Solid":
        return self.translate(x, y, z)

    def at(self, x: float = 0, y: float = 0, z: float = 0) -> "Solid":
        """Place this solid's CURRENT center at (x, y, z)."""
        c = self.center
        return self.translate(x - c[0], y - c[1], z - c[2])

    def rotate(self, angle_deg: float, axis: Sequence[float], about: Sequence[float] | None = None) -> "Solid":
        point = about if about is not None else self.center
        return self._xform(tf.rotation_matrix(math.radians(angle_deg), axis, point))

    def rotate_x(self, angle_deg: float, about: Sequence[float] | None = None) -> "Solid":
        return self.rotate(angle_deg, [1, 0, 0], about)

    def rotate_y(self, angle_deg: float, about: Sequence[float] | None = None) -> "Solid":
        return self.rotate(angle_deg, [0, 1, 0], about)

    def rotate_z(self, angle_deg: float, about: Sequence[float] | None = None) -> "Solid":
        return self.rotate(angle_deg, [0, 0, 1], about)

    def scale(self, factor: float | Sequence[float]) -> "Solid":
        if np.isscalar(factor):
            mat = tf.scale_matrix(float(factor), self.center)
        else:
            f = np.asarray(factor, dtype=float)
            mat = np.eye(4)
            mat[0, 0], mat[1, 1], mat[2, 2] = f
        return self._xform(mat)

    def mirror(self, axis: str = "x") -> "Solid":
        idx = {"x": 0, "y": 1, "z": 2}[axis]
        mat = np.eye(4)
        mat[idx, idx] = -1.0
        out = self._xform(mat)
        trimesh.repair.fix_normals(out.mesh)
        return out

    # place so the bounding box minimum sits on z=0 (ready for the print bed)
    def on_bed(self) -> "Solid":
        b = self.bounds
        return self.translate(0, 0, -b[0][2])

    def center_xy(self) -> "Solid":
        c = self.center
        return self.translate(-c[0], -c[1], 0)

    # ---- CSG -----------------------------------------------------------
    def union(self, *others: "Solid") -> "Solid":
        meshes = [self.mesh] + [_as_mesh(o) for o in others]
        return Solid(trimesh.boolean.union(meshes), "union")

    def difference(self, *others: "Solid") -> "Solid":
        meshes = [self.mesh] + [_as_mesh(o) for o in others]
        return Solid(trimesh.boolean.difference(meshes), "difference")

    def intersection(self, *others: "Solid") -> "Solid":
        meshes = [self.mesh] + [_as_mesh(o) for o in others]
        return Solid(trimesh.boolean.intersection(meshes), "intersection")

    def __add__(self, other) -> "Solid":
        return self.union(other)

    def __or__(self, other) -> "Solid":
        return self.union(other)

    def __sub__(self, other) -> "Solid":
        return self.difference(other)

    def __and__(self, other) -> "Solid":
        return self.intersection(other)

    # ---- export helpers (used by the harness) --------------------------
    def export(self, path: str) -> str:
        self.mesh.export(path)
        return path


# ======================================================================
# Primitive factories — all dimensions in millimeters
# ======================================================================

def _norm_d_r(d, r, default_r=5.0):
    """Accept either diameter (d=) or radius (r=)."""
    if d is not None:
        return float(d) / 2.0
    if r is not None:
        return float(r)
    return default_r


def box(x: float, y: float, z: float, center: bool = True) -> Solid:
    """Axis-aligned box of size (x, y, z) mm. Centered at origin by default;
    if ``center=False`` the box sits in the +octant with a corner at origin."""
    m = trimesh.creation.box(extents=[x, y, z])
    if not center:
        m.apply_translation([x / 2, y / 2, z / 2])
    return Solid(m, "box")


def cube(s: float, center: bool = True) -> Solid:
    return box(s, s, s, center=center)


def rounded_box(x: float, y: float, z: float, radius: float = 2.0) -> Solid:
    """Box with rounded corners/edges, built as the convex hull of 8 corner
    spheres (manifold by construction). ``radius`` is the corner fillet."""
    r = min(radius, x / 2 - 1e-3, y / 2 - 1e-3, z / 2 - 1e-3)
    hx, hy, hz = x / 2 - r, y / 2 - r, z / 2 - r
    pts = []
    sph = trimesh.creation.icosphere(subdivisions=2, radius=r)
    for sx in (-hx, hx):
        for sy in (-hy, hy):
            for sz in (-hz, hz):
                s = sph.copy()
                s.apply_translation([sx, sy, sz])
                pts.append(s)
    hull = trimesh.boolean.union(pts).convex_hull
    return Solid(hull, "rounded_box")


def cylinder(h: float, d: float | None = None, r: float | None = None,
             sections: int = 64, center: bool = True) -> Solid:
    """Z-axis cylinder of height ``h`` mm. Give diameter ``d`` or radius ``r``."""
    rad = _norm_d_r(d, r)
    m = trimesh.creation.cylinder(radius=rad, height=h, sections=sections)
    if not center:
        m.apply_translation([0, 0, h / 2])
    return Solid(m, "cylinder")


def cone(h: float, d: float | None = None, r: float | None = None,
         d_top: float = 0.0, sections: int = 64, center: bool = True) -> Solid:
    """Z-axis (truncated) cone. ``d``/``r`` = base, ``d_top`` = top diameter."""
    r0 = _norm_d_r(d, r)
    r1 = float(d_top) / 2.0
    # build via a revolved/lofted profile -> use a linear-section approach
    from trimesh.creation import cone as _cone
    if r1 <= 1e-6:
        m = _cone(radius=r0, height=h, sections=sections)
        if center:
            m.apply_translation([0, 0, -h / 2])
    else:
        # truncated cone via 2D polygon revolve
        prof = np.array([[0, 0], [r0, 0], [r1, h], [0, h]])
        path = trimesh.load_path(np.column_stack([prof[:, 0], prof[:, 1]]))
        m = _revolve_profile(prof, sections)
        if center:
            m.apply_translation([0, 0, -h / 2])
    return Solid(m, "cone")


def sphere(d: float | None = None, r: float | None = None, subdivisions: int = 3) -> Solid:
    rad = _norm_d_r(d, r)
    m = trimesh.creation.icosphere(subdivisions=subdivisions, radius=rad)
    return Solid(m, "sphere")


def capsule(h: float, d: float | None = None, r: float | None = None, sections: int = 32) -> Solid:
    rad = _norm_d_r(d, r)
    m = trimesh.creation.capsule(height=h, radius=rad, count=[sections, sections])
    return Solid(m, "capsule")


def torus(major_d: float, minor_d: float, sections: int = 48) -> Solid:
    """Torus in the XY plane. ``major_d`` = ring diameter, ``minor_d`` = tube."""
    R = major_d / 2.0
    rr = minor_d / 2.0
    m = trimesh.creation.torus(major_radius=R, minor_radius=rr,
                               major_sections=sections, minor_sections=max(16, sections // 2))
    return Solid(m, "torus")


def wedge(x: float, y: float, z: float) -> Solid:
    """A right-triangular prism (gusset). Triangle in the YZ plane extruded in X.
    Useful as a support gusset between two perpendicular plates."""
    tri = np.array([[0, 0], [y, 0], [0, z]])
    m = _extrude_polygon(tri, x)
    # tri extruded along Z by default -> reorient so triangle is in YZ, length in X
    m.apply_transform(tf.rotation_matrix(math.radians(90), [0, 1, 0]))
    return Solid(m, "wedge")


def prism(sides: int, d: float | None = None, r: float | None = None, h: float = 10.0) -> Solid:
    """Regular n-gon prism (hex nut blank, etc.). ``d``/``r`` = circumscribed."""
    rad = _norm_d_r(d, r)
    ang = np.linspace(0, 2 * np.pi, sides, endpoint=False)
    poly = np.column_stack([rad * np.cos(ang), rad * np.sin(ang)])
    m = _extrude_polygon(poly, h)
    m.apply_translation([0, 0, -h / 2])
    return Solid(m, "prism")


def polygon(points: Sequence[Sequence[float]]) -> "Polygon2D":
    """A 2D polygon you can ``.extrude(h)`` or ``.revolve(angle)``."""
    return Polygon2D(np.asarray(points, dtype=float))


class Polygon2D:
    """A 2D profile in the XY plane, awaiting extrusion or revolution."""

    def __init__(self, pts: np.ndarray):
        self.pts = pts

    def extrude(self, h: float, center: bool = True) -> Solid:
        m = _extrude_polygon(self.pts, h)
        if center:
            m.apply_translation([0, 0, -h / 2])
        return Solid(m, "extrude")

    def revolve(self, angle_deg: float = 360.0, sections: int = 64) -> Solid:
        return Solid(_revolve_profile(self.pts, sections, angle_deg), "revolve")


def extrude(points: Sequence[Sequence[float]], h: float, center: bool = True) -> Solid:
    return Polygon2D(np.asarray(points, dtype=float)).extrude(h, center)


def revolve(points: Sequence[Sequence[float]], angle_deg: float = 360.0, sections: int = 64) -> Solid:
    return Polygon2D(np.asarray(points, dtype=float)).revolve(angle_deg, sections)


def ellipsoid(dx: float, dy: float, dz: float, subdivisions: int = 3) -> Solid:
    """An ellipsoid with full diameters (dx, dy, dz) mm — a sphere scaled per axis.
    The workhorse for organic/stylized bodies (animal torsos, busts, eggs)."""
    m = trimesh.creation.icosphere(subdivisions=subdivisions, radius=0.5)
    m.apply_scale([dx, dy, dz])
    return Solid(m, "ellipsoid")


def tube(h: float, d_outer: float, d_inner: float, sections: int = 64, center: bool = True) -> Solid:
    """A hollow cylinder (pipe) of height ``h`` — outer minus inner bore."""
    outer = trimesh.creation.cylinder(radius=d_outer / 2, height=h, sections=sections)
    inner = trimesh.creation.cylinder(radius=d_inner / 2, height=h * 1.05, sections=sections)
    m = trimesh.boolean.difference([outer, inner])
    if not center:
        m.apply_translation([0, 0, h / 2])
    return Solid(m, "tube")


def slot(length: float, width: float, height: float, center: bool = True) -> Solid:
    """A rounded-end slot (stadium prism): two end-caps joined — ideal for cable
    channels, finger grips, and obround holes. ``length`` is tip-to-tip."""
    r = width / 2.0
    span = max(length - width, 1e-3)
    a = trimesh.creation.cylinder(radius=r, height=height, sections=48)
    b = a.copy()
    a.apply_translation([-span / 2, 0, 0])
    b.apply_translation([span / 2, 0, 0])
    bar = trimesh.creation.box(extents=[span, width, height])
    m = trimesh.boolean.union([a, b, bar])
    if not center:
        m.apply_translation([0, 0, height / 2])
    return Solid(m, "slot")


def teardrop(d: float, h: float, sections: int = 48, center: bool = True) -> Solid:
    """A teardrop cylinder (45-degree apex on top) for HORIZONTAL holes — printing
    a teardrop avoids the unsupported 90-degree overhang at the top of a round hole.
    Subtract this (axis along Z by default; rotate to orient the bore)."""
    r = d / 2.0
    circ = trimesh.creation.cylinder(radius=r, height=h, sections=sections)
    # apex: a square rotated 45 deg sitting on top of the circle
    apex = trimesh.creation.box(extents=[r * 1.414, r * 1.414, h])
    apex.apply_transform(tf.rotation_matrix(math.radians(45), [0, 0, 1]))
    apex.apply_translation([0, r, 0])
    m = trimesh.boolean.union([circ, apex])
    if not center:
        m.apply_translation([0, 0, h / 2])
    return Solid(m, "teardrop")


def twist_extrude(points: Sequence[Sequence[float]], height: float, turns: float = 1.0,
                  layers: int = 96, center: bool = False) -> Solid:
    """Extrude a closed 2D profile along Z while rotating it ``turns`` full turns —
    a genuine spiral/twist (twisted vases, spiral columns, augers). Manifold by
    construction (rings stitched + triangulated caps)."""
    poly = np.asarray(points, dtype=float)
    if np.allclose(poly[0], poly[-1]):
        poly = poly[:-1]
    n = len(poly)
    if n < 3:
        raise ValueError("twist_extrude needs a polygon of >= 3 points")

    verts = []
    for i in range(layers + 1):
        t = i / layers
        ang = turns * 2 * math.pi * t
        c, s = math.cos(ang), math.sin(ang)
        z = height * t
        for x, y in poly:
            verts.append([x * c - y * s, x * s + y * c, z])
    verts = [list(v) for v in verts]

    faces = []
    for i in range(layers):
        base = i * n
        nxt = (i + 1) * n
        for j in range(n):
            j2 = (j + 1) % n
            a, b = base + j, base + j2
            c, d = nxt + j, nxt + j2
            faces.append([a, b, d])
            faces.append([a, d, c])
    # caps: fan from a centroid vertex (robust for any star-convex profile)
    bottom = list(range(n))
    top = list(range(layers * n, layers * n + n))
    faces.extend(_centroid_cap(verts, bottom, reverse=True))
    faces.extend(_centroid_cap(verts, top, reverse=False))

    m = trimesh.Trimesh(vertices=np.asarray(verts), faces=np.asarray(faces), process=True)
    trimesh.repair.fix_normals(m)
    if center:
        m.apply_translation([0, 0, -height / 2])
    return Solid(m, "twist_extrude")


def loft(sections: Sequence, sections_closed: bool = True) -> Solid:
    """Loft through a sequence of cross-sections. Each section is
    ``(points2d, z)`` with the SAME number of points; consecutive loops are
    stitched and the ends capped. Great for tapered/curved bodies and nozzles."""
    rings = []
    counts = set()
    for pts, z in sections:
        p = np.asarray(pts, dtype=float)
        if np.allclose(p[0], p[-1]):
            p = p[:-1]
        counts.add(len(p))
        rings.append((p, float(z)))
    if len(counts) != 1:
        raise ValueError("loft sections must all have the same point count")
    n = counts.pop()

    verts = []
    for p, z in rings:
        for x, y in p:
            verts.append([x, y, z])

    faces = []
    for i in range(len(rings) - 1):
        base, nxt = i * n, (i + 1) * n
        for j in range(n):
            j2 = (j + 1) % n
            faces.append([base + j, base + j2, nxt + j2])
            faces.append([base + j, nxt + j2, nxt + j])
    faces.extend(_centroid_cap(verts, list(range(n)), reverse=True))
    last = (len(rings) - 1) * n
    faces.extend(_centroid_cap(verts, list(range(last, last + n)), reverse=False))

    m = trimesh.Trimesh(vertices=np.asarray(verts), faces=np.asarray(faces), process=True)
    trimesh.repair.fix_normals(m)
    return Solid(m, "loft")


def _centroid_cap(verts: list, loop_indices, reverse: bool) -> list:
    """Cap a profile loop by fanning from an appended centroid vertex — watertight
    for any star-convex polygon (lobed/fluted profiles included). Mutates ``verts``
    to append the centroid point and returns the cap faces."""
    pts = [verts[i] for i in loop_indices]
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    cz = sum(p[2] for p in pts) / len(pts)
    c = len(verts)
    verts.append([cx, cy, cz])
    out = []
    n = len(loop_indices)
    for k in range(n):
        a, b = loop_indices[k], loop_indices[(k + 1) % n]
        tri = [c, a, b]
        if reverse:
            tri = tri[::-1]
        out.append(tri)
    return out


def text(string: str, size: float = 10.0, height: float = 2.0, font: str | None = None) -> Solid:
    """Extruded 3D text (best-effort; requires matplotlib for glyph outlines).
    Raises a clear error if glyph extraction is unavailable."""
    polys = _text_polygons(string, size, font)
    solids = []
    for poly in polys:
        try:
            solids.append(_extrude_shapely(poly, height))
        except Exception:
            continue
    if not solids:
        raise RuntimeError("text(): could not build glyph geometry (matplotlib required)")
    m = trimesh.boolean.union(solids) if len(solids) > 1 else solids[0]
    return Solid(m, "text")


# ======================================================================
# Free functions
# ======================================================================

def load_mesh(path: str, repair: bool = True) -> Solid:
    """Load an existing STL / 3MF / GLB / OBJ / PLY as a Solid so the agent can
    MODIFY it (boolean with new CSG, scale, reorient, emboss, hollow). Optionally
    repairs to a watertight manifold so subsequent CSG is well-defined."""
    loaded = trimesh.load(path, force="mesh")
    if isinstance(loaded, trimesh.Scene):
        loaded = trimesh.util.concatenate([g for g in loaded.geometry.values()])
    loaded.merge_vertices()
    if repair:
        try:
            trimesh.repair.fix_normals(loaded)
            if not loaded.is_watertight:
                trimesh.repair.fill_holes(loaded)
        except Exception:
            pass
    return Solid(loaded, "imported")


def union(*solids: Solid) -> Solid:
    meshes = [_as_mesh(s) for s in _flatten(solids)]
    return Solid(trimesh.boolean.union(meshes), "union")


def difference(base: Solid, *cuts: Solid) -> Solid:
    meshes = [_as_mesh(base)] + [_as_mesh(s) for s in _flatten(cuts)]
    return Solid(trimesh.boolean.difference(meshes), "difference")


def intersection(*solids: Solid) -> Solid:
    meshes = [_as_mesh(s) for s in _flatten(solids)]
    return Solid(trimesh.boolean.intersection(meshes), "intersection")


def hull(*solids: Solid) -> Solid:
    """Convex hull of one or more solids."""
    meshes = [_as_mesh(s) for s in _flatten(solids)]
    combined = trimesh.util.concatenate(meshes)
    return Solid(combined.convex_hull, "hull")


def paint(solid: Solid, color: str) -> Solid:
    """Free-function form of :meth:`Solid.paint`."""
    return solid.paint(color)


def _hex_rgba(hex_color: str):
    h = (hex_color or "#9aa7b2").strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) == 8:
        h = h[:6]
    if len(h) != 6:
        h = "9aa7b2"
    return [int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255]


def multicolor_union(*parts: Solid, default: str = "#9aa7b2") -> Solid:
    """Union painted parts into ONE watertight solid and assign per-FACE colors so
    a single CSG body carries AMS multicolor (each face takes the color of the
    painted part whose surface it lies on — nearest-surface assignment).

    Usage:
        body = ellipsoid(40,36,52).paint('#8d6e63')
        eyes = (sphere(d=12).at(-8,16,34) + sphere(d=12).at(8,16,34)).paint('#ffffff')
        beak = cone(h=8,d=7).rotate_x(90).at(0,20,30).paint('#e8a33b')
        result = multicolor_union(body, eyes, beak)

    Exporters then write a per-triangle-colored 3MF (AMS) + a colored GLB. The
    geometry is a single, watertight, sliceable solid — not a loose part set."""
    plist = _flatten(list(parts))
    if not plist:
        raise ValueError("multicolor_union needs at least one part")
    meshes = [_as_mesh(p) for p in plist]
    colors = [getattr(p, "_color", None) or default for p in plist]

    union_mesh = trimesh.boolean.union(meshes)
    union_mesh.merge_vertices()
    trimesh.repair.fix_normals(union_mesh)

    centroids = union_mesh.triangles_center  # (F,3)
    # distance from each union face centroid to each part's surface; the part that
    # contributed the face has ~0 distance there -> argmin picks the right color.
    best = np.full(len(centroids), 0, dtype=int)
    best_d = np.full(len(centroids), np.inf)
    for idx, m in enumerate(meshes):
        try:
            d = np.abs(trimesh.proximity.signed_distance(m, centroids))
        except Exception:
            # fallback: nearest-point distance
            _, d, _ = trimesh.proximity.closest_point(m, centroids)
            d = np.abs(d)
        closer = d < best_d
        best[closer] = idx
        best_d[closer] = d[closer]

    palette = [_hex_rgba(c) for c in colors]
    face_colors = np.array([palette[i] for i in best], dtype=np.uint8)
    union_mesh.visual = trimesh.visual.ColorVisuals(union_mesh, face_colors=face_colors)
    s = Solid(union_mesh, "multicolor")
    # carry the first color as the solid's nominal color
    s._color = colors[0]
    return s


def linear_pattern(solid: Solid, count: int, dx: float = 0, dy: float = 0, dz: float = 0) -> list[Solid]:
    """Return ``count`` copies translated incrementally. Union them yourself."""
    return [solid.translate(dx * i, dy * i, dz * i) for i in range(count)]


def circular_pattern(solid: Solid, count: int, radius: float = 0,
                     axis: str = "z", start_deg: float = 0) -> list[Solid]:
    """Return ``count`` copies arranged around a circle in the given plane."""
    out = []
    for i in range(count):
        a = math.radians(start_deg + 360.0 * i / count)
        if axis == "z":
            out.append(solid.translate(radius * math.cos(a), radius * math.sin(a), 0)
                       .rotate_z(math.degrees(a), about=[0, 0, 0]))
        elif axis == "y":
            out.append(solid.translate(radius * math.cos(a), 0, radius * math.sin(a)))
        else:
            out.append(solid.translate(0, radius * math.cos(a), radius * math.sin(a)))
    return out


def interference(a: Solid, b: Solid) -> float:
    """Overlap (intersection) volume between two solids, in mm^3 — assembly
    interference / collision detection. 0.0 = no collision (parts only touch or
    are clear). Uses an AABB broad-phase before the (expensive) boolean so a
    no-overlap pair returns instantly. This is the automated print-readiness
    backstop for multi-part assemblies that no mesh-soup tool provides."""
    ma, mb = _as_mesh(a), _as_mesh(b)
    amin, amax = ma.bounds
    bmin, bmax = mb.bounds
    if bool((amin > bmax).any() or (bmin > amax).any()):
        return 0.0  # AABBs disjoint -> cannot intersect
    try:
        inter = trimesh.boolean.intersection([ma, mb])
        if inter is None or len(inter.faces) == 0:
            return 0.0
        return float(abs(inter.volume))
    except Exception:
        return 0.0


def arrange_on_bed(solids: Sequence[Solid], gap: float = 5.0) -> list[Solid]:
    """Lay parts out along +X on the build plate (each grounded to z=0) with a
    ``gap`` between them — a printable bed layout for an assembly's parts in one
    job. Returns the repositioned solids; union or export them per-part."""
    out: list[Solid] = []
    x = 0.0
    for s in _flatten(list(solids)):
        s2 = s.on_bed()
        b = s2.bounds
        w = float(b[1][0] - b[0][0])
        out.append(s2.translate(x - float(b[0][0]), 0, 0))
        x += w + gap
    return out


# ======================================================================
# Internal geometry helpers
# ======================================================================

def _flatten(items: Iterable) -> list:
    out = []
    for it in items:
        if isinstance(it, (list, tuple)):
            out.extend(_flatten(it))
        else:
            out.append(it)
    return out


def _extrude_polygon(pts2d: np.ndarray, h: float) -> trimesh.Trimesh:
    from shapely.geometry import Polygon as ShapelyPolygon
    poly = ShapelyPolygon(pts2d)
    if not poly.is_valid:
        poly = poly.buffer(0)
    return trimesh.creation.extrude_polygon(poly, height=h)


def _extrude_shapely(poly, h: float) -> trimesh.Trimesh:
    return trimesh.creation.extrude_polygon(poly, height=h)


def _revolve_profile(profile_xy: np.ndarray, sections: int, angle_deg: float = 360.0) -> trimesh.Trimesh:
    """Revolve a 2D profile (x=radius, y=height) about the Z axis."""
    linestring = np.asarray(profile_xy, dtype=float)
    return trimesh.creation.revolve(linestring, angle=math.radians(angle_deg), sections=sections)


def _text_polygons(string: str, size: float, font: str | None):
    """Return a list of shapely polygons for the glyphs of ``string``."""
    from matplotlib.textpath import TextPath
    from matplotlib.font_manager import FontProperties
    from shapely.geometry import Polygon as ShapelyPolygon
    from shapely.ops import unary_union

    fp = FontProperties(family=font) if font else FontProperties()
    tp = TextPath((0, 0), string, size=size, prop=fp)
    polys = []
    for poly in tp.to_polygons():
        if len(poly) >= 3:
            sp = ShapelyPolygon(poly)
            if sp.is_valid and sp.area > 1e-6:
                polys.append(sp)
    if not polys:
        return []
    # combine overlapping contours (handles glyph holes via even-odd union)
    merged = unary_union(polys)
    if merged.geom_type == "Polygon":
        return [merged]
    return list(merged.geoms)
