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


# ---------------------------------------------------------------- MUSE benchmark
def test_muse_pipeline_scores_high():
    res = muse.run(do_slice=False, timeout=90)
    # deterministic CSG + validate should collapse the MUSE failure cascade
    assert res["muse_score"] >= 95.0, res
    assert res["dimensions_pct"]["geometry_valid"] == 100.0
    assert all(c.get("print_ready") for c in res["cases"]), [c["name"] for c in res["cases"] if not c.get("print_ready")]
