"""Tests for the v3 "beat Meshy" capabilities: kernel metrics, heal, parametric
source + params, real-slice D2 (proxy fallback), certificate, domain-RAG, MUSE,
assembly interference, multi-object 3MF."""
import json
import os
import sys

import numpy as np
import pytest

HARNESS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "harness")
if HARNESS not in sys.path:
    sys.path.insert(0, HARNESS)

import trimesh  # noqa: E402
from studio3d import dsl, exporters, kb, muse  # noqa: E402
from studio3d.sandbox import run_script_text, execute_in_process  # noqa: E402
from studio3d.validate import validate, heal, orient_for_print  # noqa: E402
from studio3d.spec import ModelSpec  # noqa: E402


# ---------------------------------------------------------------- kernel metrics
def test_report_has_kernel_metrics():
    m = run_script_text("result = box(40,20,10) - cylinder(h=20,d=6)", timeout=40)
    rep = validate(m)
    km = rep.metrics["kernel_metrics"]
    for key in ("watertight", "manifold", "genus", "n_components", "wall_p05_mm",
                "steepest_overhang_deg", "bed_fit", "bbox_mm"):
        assert key in km
    assert km["n_components"] == 1
    assert rep.dimensions["D1_mesh_integrity"]["n_components"] == 1
    # a through-hole is a topological handle -> genus 1 (proves genus is computed)
    assert rep.dimensions["D1_mesh_integrity"]["genus"] == 1


def test_solid_part_is_genus_zero():
    m = run_script_text("result = box(30,20,10)", timeout=40)
    rep = validate(m)
    assert rep.dimensions["D1_mesh_integrity"]["genus"] == 0


def test_disconnected_parts_detected():
    # two boxes far apart -> 2 components (the floating-cradle defect)
    m = run_script_text("result = box(10,10,10) + box(10,10,10).at(50,0,0)", timeout=40)
    rep = validate(m)
    assert rep.metrics["kernel_metrics"]["n_components"] == 2


# ---------------------------------------------------------------- heal
def test_heal_makes_open_mesh_watertight():
    # an open box (missing a face) -> not watertight; heal should close it
    box = trimesh.creation.box(extents=[10, 10, 10])
    open_box = trimesh.Trimesh(vertices=box.vertices, faces=box.faces[:-2].copy(), process=True)
    assert not open_box.is_watertight
    info = heal(open_box)
    assert info["watertight_before"] is False
    assert open_box.is_watertight is True
    assert info["watertight_after"] is True


def test_orient_for_print_returns_best():
    m = run_script_text("result = box(80,10,40,center=False)", timeout=40)
    res = orient_for_print(m, limit_deg=50.0)
    assert "best" in res and len(res["candidates"]) == 6
    assert "overhang_area_mm2" in res["best"]


# ---------------------------------------------------------------- params (P dict)
def test_params_injected_as_P():
    code = "def build():\n    return box(P.get('w',10), P.get('d',10), P.get('h',10))"
    m_default = run_script_text(code, timeout=40)
    assert [round(float(x)) for x in m_default.extents] == [10, 10, 10]
    m_tweaked = run_script_text(code, timeout=40, params={"w": 50, "h": 30})
    assert [round(float(x)) for x in m_tweaked.extents] == [50, 10, 30]


def test_params_in_process():
    s = execute_in_process("result = box(P['a'], 10, 10)", params={"a": 25})
    assert round(float(s.size[0])) == 25


# ---------------------------------------------------------------- parametric source in bundle
def test_bundle_ships_parametric_source(tmp_path):
    m = run_script_text("def build():\n    return box(P.get('w',30),20,10)", timeout=40)
    spec = ModelSpec(prompt="param box", name="pbox", category="mechanical",
                     script="def build():\n    return box(P.get('w',30),20,10)",
                     parameters={"w": 30}, formats=["stl"])
    rep = validate(m)
    entry = exporters.write_bundle(m, str(tmp_path / "pbox"), spec, rep, ["stl"])
    assert (tmp_path / "pbox" / "model.py").exists()
    assert (tmp_path / "pbox" / "params.json").exists()
    assert entry["editable"] is True
    assert entry["files"]["source"] == "model.py"
    assert json.load(open(tmp_path / "pbox" / "params.json"))["w"] == 30


# ---------------------------------------------------------------- D2 slicer / proxy
def test_d2_proxy_is_labeled_without_slicer(monkeypatch):
    import studio3d.slicer as S
    monkeypatch.setattr(S, "detect_slicer", lambda: None)
    m = run_script_text("result = box(30,20,10)", timeout=40)
    rep = validate(m, do_slice=True)
    d2 = rep.dimensions["D2_slicer_pass"]
    assert d2["method"] == "proxy"
    assert "slice_note" in d2  # honestly labeled as proxy, not silently self-certified


def test_slice_model_no_slicer_returns_unavailable(monkeypatch):
    import studio3d.slicer as S
    monkeypatch.setattr(S, "detect_slicer", lambda: None)
    res = S.slice_model("/nonexistent.stl")
    assert res["available"] is False and res["method"] == "proxy"


# ---------------------------------------------------------------- certificate
def test_certificate_records_provenance(tmp_path):
    from studio3d.certify import build_certificate
    script = "def build():\n    return box(20,20,20)"
    m = run_script_text(script, timeout=40)
    spec = ModelSpec(prompt="cube", name="c", category="mechanical", script=script, formats=["stl"])
    rep = validate(m)
    bdir = tmp_path / "c"
    exporters.write_bundle(m, str(bdir), spec, rep, ["stl"])
    cert = build_certificate(spec, rep, str(bdir), {"engine": "csg"}, timestamp="2026-06-17T00:00:00Z")
    assert cert["deterministic"] is True
    assert len(cert["script_sha256"]) == 64
    assert cert["dimensions"]["D1_mesh_integrity"] is True
    assert cert["file_sha256"].get("model.stl")
    assert cert["human_approved"] is None


# ---------------------------------------------------------------- assembly interference
def test_interference_detects_collision():
    a = dsl.box(20, 20, 20)
    b = dsl.box(20, 20, 20).translate(5, 0, 0)   # overlaps a
    far = dsl.box(20, 20, 20).translate(100, 0, 0)
    assert dsl.interference(a, b) > 0.0
    assert dsl.interference(a, far) == 0.0


def test_arrange_on_bed_no_overlap_and_grounded():
    parts = dsl.arrange_on_bed([dsl.cube(20), dsl.cube(20), dsl.cube(20)], gap=5)
    for p in parts:
        assert abs(float(p.bounds[0][2])) < 1e-6  # grounded
    # adjacent parts do not collide
    assert dsl.interference(parts[0], parts[1]) == 0.0
    assert dsl.interference(parts[1], parts[2]) == 0.0


# ---------------------------------------------------------------- multi-object 3MF (AMS)
def test_export_3mf_multi_two_objects(tmp_path):
    a = dsl.cube(20).mesh
    b = dsl.cube(20).translate(30, 0, 0).mesh
    path = str(tmp_path / "asm.3mf")
    exporters.export_3mf_multi([(a, "#ff0000", "red"), (b, "#0000ff", "blue")], path, name="asm")
    loaded = trimesh.load(path)
    geoms = list(loaded.geometry.values()) if hasattr(loaded, "geometry") else [loaded]
    assert len(geoms) == 2


# ---------------------------------------------------------------- domain RAG
def test_kb_search_finds_overhang_rule():
    hits = kb.search("overhang angle support 45 degrees", k=3)
    assert hits and any("overhang" in (h["title"] + h["text"]).lower() for h in hits)
    st = kb.stats()
    assert st["chunks"] > 10 and st["vocab"] > 100


# ---------------------------------------------------------------- per-face AMS color
def test_paint_and_multicolor_union_face_colors():
    code = (
        "def build():\n"
        "    body = ellipsoid(40,36,52).at(0,0,26).paint('#8d6e63')\n"
        "    eyeL = sphere(d=12).at(-9,16,34).paint('#ffffff')\n"
        "    eyeR = sphere(d=12).at(9,16,34).paint('#ffffff')\n"
        "    beak = cone(h=8,d=7).rotate_x(90).at(0,20,28).paint('#e8a33b')\n"
        "    return multicolor_union(body, eyeL, eyeR, beak).on_bed()\n"
    )
    m = run_script_text(code, timeout=90)            # through the sandbox (PLY handoff)
    assert m.is_watertight and m.is_volume
    palette, idx = exporters.face_color_palette(m)
    assert palette is not None and len(palette) == 3   # brown, white, orange
    assert len(idx) == len(m.faces)


def test_export_3mf_painted_has_colorgroup_and_per_triangle(tmp_path):
    import zipfile
    code = ("def build():\n"
            "    a = box(20,20,20).paint('#ff0000')\n"
            "    b = cylinder(h=30,d=8).paint('#0000ff')\n"
            "    return multicolor_union(a, b)\n")
    m = run_script_text(code, timeout=60)
    p = str(tmp_path / "m.3mf")
    exporters.export_3mf_painted(m, p, "twocolor")
    xml = zipfile.ZipFile(p).read("3D/3dmodel.model").decode()
    assert '<m:colorgroup id="1">' in xml
    assert xml.count("<m:color ") == 2            # two distinct colors
    assert xml.count('p1="') == len(m.faces)      # every triangle colored
    # still loads as a watertight solid
    loaded = trimesh.load(p)
    g = list(loaded.geometry.values())[0] if hasattr(loaded, "geometry") else loaded
    g.merge_vertices()
    assert g.is_watertight


def test_write_bundle_uses_painted_3mf(tmp_path):
    code = ("def build():\n"
            "    return multicolor_union(box(20,20,20).paint('#ff0000'),"
            " sphere(d=12).at(0,0,16).paint('#00ff00'))\n")
    m = run_script_text(code, timeout=60)
    spec = ModelSpec(prompt="two color", name="tc", category="decorative",
                     script=code, multicolor=True, formats=["stl", "3mf", "glb"])
    rep = validate(m)
    entry = exporters.write_bundle(m, str(tmp_path / "tc"), spec, rep, ["stl", "3mf", "glb"])
    assert entry["multicolor"] is True
    assert len(entry["palette"]) == 2


# ---------------------------------------------------------------- STEP export
def test_step_export_is_well_formed(tmp_path):
    import re
    from studio3d.step import export_step
    m = run_script_text("result = box(30,20,10) - cylinder(h=20,d=6)", timeout=40)
    p = str(tmp_path / "part.step")
    export_step(m, p, "part")
    txt = open(p).read()
    defs = set(int(x) for x in re.findall(r"#(\d+)\s*=", txt))
    refs = set(int(x) for x in re.findall(r"#(\d+)", txt))
    assert refs - defs == set()                      # no dangling references
    assert "10303 214" in txt                        # AP214 schema
    assert txt.count("MANIFOLD_SOLID_BREP(") == 1
    assert txt.count("CLOSED_SHELL(") == 1
    assert txt.count("ADVANCED_FACE(") == len(m.faces)
    assert txt.strip().endswith("END-ISO-10303-21;")


def test_bundle_can_emit_step(tmp_path):
    m = run_script_text("result = cube(20)", timeout=40)
    spec = ModelSpec(prompt="cube", name="c", category="mechanical", script="result=cube(20)",
                     formats=["stl", "step"])
    rep = validate(m)
    entry = exporters.write_bundle(m, str(tmp_path / "c"), spec, rep, ["stl", "step"])
    assert entry["files"].get("step") == "model.step"
    assert (tmp_path / "c" / "model.step").exists()


# ---------------------------------------------------------------- MUSE benchmark
def test_muse_pipeline_scores_high():
    res = muse.run(do_slice=False, timeout=90)
    # deterministic CSG + validate should collapse the MUSE failure cascade
    assert res["muse_score"] >= 95.0, res
    assert res["dimensions_pct"]["geometry_valid"] == 100.0
    assert all(c.get("print_ready") for c in res["cases"]), [c["name"] for c in res["cases"] if not c.get("print_ready")]
