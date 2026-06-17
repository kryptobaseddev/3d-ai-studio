"""studio3d.step — dependency-free STEP (ISO 10303-21, AP214) export.

The plugin runs on CPython 3.14 where OpenCASCADE (OCP/CadQuery) has no wheels, so
we cannot use a B-Rep kernel. Our geometry is already a watertight 2-manifold mesh,
so STEP export is necessarily *faceted* (mesh-derived) — but it is REAL, standard
STEP: a ``MANIFOLD_SOLID_BREP`` of planar ``ADVANCED_FACE``s over a sewn
``CLOSED_SHELL`` (shared ``CARTESIAN_POINT``s, ``VERTEX_POINT``s, and ``EDGE_CURVE``s
with consistent orientation), wrapped in the AP214 product/shape/context boilerplate.

It imports as a solid body into FreeCAD, Fusion 360, SolidWorks, Onshape, etc. This is
the lossless CSG→B-Rep upgrade path the 2026 report calls out (boolean ops map to B-Rep
boolean algorithms) made available without a native kernel; it is faceted, not
parametric — clearly labeled as such.
"""
from __future__ import annotations

import numpy as np
import trimesh


def _f(x: float) -> str:
    # compact, locale-independent float for STEP reals
    return repr(round(float(x), 6))


def export_step(mesh: trimesh.Trimesh, path: str, name: str = "studio3d_part") -> str:
    mesh = mesh.copy()
    mesh.merge_vertices()
    verts = np.asarray(mesh.vertices, dtype=float)
    faces = np.asarray(mesh.faces, dtype=int)
    fnormals = np.asarray(mesh.face_normals, dtype=float)
    if len(faces) == 0:
        raise ValueError("export_step: mesh has no faces")

    lines: list[str] = []
    nid = [0]

    def E(body: str) -> int:
        nid[0] += 1
        lines.append(f"#{nid[0]} = {body};")
        return nid[0]

    # ---- AP214 product / context preamble -----------------------------------
    app_ctx = E("APPLICATION_CONTEXT('automotive design')")
    E(f"APPLICATION_PROTOCOL_DEFINITION('international standard',"
      f"'automotive_design',2010,#{app_ctx})")
    prod_ctx = E(f"PRODUCT_CONTEXT('',#{app_ctx},'mechanical')")
    pdc = E(f"PRODUCT_DEFINITION_CONTEXT('part definition',#{app_ctx},'design')")
    product = E(f"PRODUCT('{name}','{name}','',(#{prod_ctx}))")
    pdf = E(f"PRODUCT_DEFINITION_FORMATION('','',#{product})")
    pd = E(f"PRODUCT_DEFINITION('design','',#{pdf},#{pdc})")
    pds = E(f"PRODUCT_DEFINITION_SHAPE('','',#{pd})")

    # units: mm, radian, steradian + uncertainty -> combined context
    len_unit = E("( LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.) )")
    ang_unit = E("( NAMED_UNIT(*) PLANE_ANGLE_UNIT() SI_UNIT($,.RADIAN.) )")
    sol_unit = E("( NAMED_UNIT(*) SI_UNIT($,.STERADIAN.) SOLID_ANGLE_UNIT() )")
    unc = E(f"UNCERTAINTY_MEASURE_WITH_UNIT(LENGTH_MEASURE(1.E-06),#{len_unit},"
            f"'distance_accuracy_value','confusion accuracy')")
    geo_ctx = E(
        f"( GEOMETRIC_REPRESENTATION_CONTEXT(3) "
        f"GLOBAL_UNCERTAINTY_ASSIGNED_CONTEXT((#{unc})) "
        f"GLOBAL_UNIT_ASSIGNED_CONTEXT((#{len_unit},#{ang_unit},#{sol_unit})) "
        f"REPRESENTATION_CONTEXT('Context','3D') )"
    )
    # world origin axis placement (for the shape representation)
    o_pt = E("CARTESIAN_POINT('',(0.,0.,0.))")
    o_z = E("DIRECTION('',(0.,0.,1.))")
    o_x = E("DIRECTION('',(1.,0.,0.))")
    origin_ax = E(f"AXIS2_PLACEMENT_3D('',#{o_pt},#{o_z},#{o_x})")

    # ---- geometry: points, vertices, shared edges, faces --------------------
    pt_id = [E(f"CARTESIAN_POINT('',({_f(v[0])},{_f(v[1])},{_f(v[2])}))") for v in verts]
    vp_id = [E(f"VERTEX_POINT('',#{pid})") for pid in pt_id]

    edge_id: dict[tuple[int, int], int] = {}

    def edge(a: int, b: int) -> int:
        key = (a, b) if a < b else (b, a)
        if key in edge_id:
            return edge_id[key]
        lo, hi = key
        d = verts[hi] - verts[lo]
        L = float(np.linalg.norm(d)) or 1.0
        dn = d / L
        did = E(f"DIRECTION('',({_f(dn[0])},{_f(dn[1])},{_f(dn[2])}))")
        vec = E(f"VECTOR('',#{did},{_f(L)})")
        ln = E(f"LINE('',#{pt_id[lo]},#{vec})")
        ec = E(f"EDGE_CURVE('',#{vp_id[lo]},#{vp_id[hi]},#{ln},.T.)")
        edge_id[key] = ec
        return ec

    face_ids: list[int] = []
    for fi, tri in enumerate(faces):
        i, j, k = int(tri[0]), int(tri[1]), int(tri[2])
        oes = []
        for a, b in ((i, j), (j, k), (k, i)):
            ec = edge(a, b)
            same = a < b  # EDGE_CURVE was defined low->high
            oes.append(E(f"ORIENTED_EDGE('',*,*,#{ec},{'.T.' if same else '.F.'})"))
        loop = E(f"EDGE_LOOP('',({','.join('#' + str(o) for o in oes)}))")
        bound = E(f"FACE_OUTER_BOUND('',#{loop},.T.)")
        n = fnormals[fi]
        nn = n / (float(np.linalg.norm(n)) or 1.0)
        r = verts[j] - verts[i]
        r = r / (float(np.linalg.norm(r)) or 1.0)
        nd = E(f"DIRECTION('',({_f(nn[0])},{_f(nn[1])},{_f(nn[2])}))")
        rd = E(f"DIRECTION('',({_f(r[0])},{_f(r[1])},{_f(r[2])}))")
        ax = E(f"AXIS2_PLACEMENT_3D('',#{pt_id[i]},#{nd},#{rd})")
        pl = E(f"PLANE('',#{ax})")
        face_ids.append(E(f"ADVANCED_FACE('',(#{bound}),#{pl},.T.)"))

    shell = E(f"CLOSED_SHELL('',({','.join('#' + str(f) for f in face_ids)}))")
    brep = E(f"MANIFOLD_SOLID_BREP('{name}',#{shell})")
    brep_shape = E(
        f"ADVANCED_BREP_SHAPE_REPRESENTATION('{name}',(#{origin_ax},#{brep}),#{geo_ctx})"
    )
    E(f"SHAPE_DEFINITION_REPRESENTATION(#{pds},#{brep_shape})")

    body = "\n".join(lines)
    text = (
        "ISO-10303-21;\n"
        "HEADER;\n"
        "FILE_DESCRIPTION(('studio3d faceted (mesh-derived) STEP'),'2;1');\n"
        f"FILE_NAME('{name}.step','',(''),(''),'studio3d','studio3d','');\n"
        "FILE_SCHEMA(('AUTOMOTIVE_DESIGN { 1 0 10303 214 1 1 1 1 }'));\n"
        "ENDSEC;\n"
        "DATA;\n"
        f"{body}\n"
        "ENDSEC;\n"
        "END-ISO-10303-21;\n"
    )
    with open(path, "w", encoding="ascii") as fh:
        fh.write(text)
    return path
