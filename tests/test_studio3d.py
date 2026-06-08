"""End-to-end test suite for the studio3d harness.

Run:  cd harness && ../.venv/bin/python -m pytest ../tests -q
Or:   ./.venv/bin/python -m pytest tests -q   (with PYTHONPATH=harness)

Covers: DSL primitives, CSG manifold guarantees, sandbox security/isolation, the
print-readiness validator (D1-D4), exporters (STL/3MF/GLB round-trips), and every
bundled example script fabricated end-to-end.
"""
import glob
import json
import os
import sys

import pytest

HARNESS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "harness")
EXAMPLES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples")
if HARNESS not in sys.path:
    sys.path.insert(0, HARNESS)

import trimesh  # noqa: E402
from studio3d import dsl  # noqa: E402
from studio3d.sandbox import run_script_text, execute_in_process  # noqa: E402
from studio3d.validate import validate, repair  # noqa: E402
from studio3d.spec import ModelSpec  # noqa: E402
from studio3d import exporters  # noqa: E402


# ---------------------------------------------------------------- DSL

import math as _math

PRIMITIVES = {
    "box": lambda: dsl.box(20, 10, 5),
    "cube": lambda: dsl.cube(10),
    "rounded_box": lambda: dsl.rounded_box(30, 20, 10, radius=3),
    "cylinder": lambda: dsl.cylinder(h=20, d=10),
    "cone": lambda: dsl.cone(h=20, d=14),
    "cone_frustum": lambda: dsl.cone(h=20, d=14, d_top=6),
    "sphere": lambda: dsl.sphere(d=12),
    "ellipsoid": lambda: dsl.ellipsoid(40, 25, 60),
    "capsule": lambda: dsl.capsule(h=20, d=8),
    "torus": lambda: dsl.torus(major_d=30, minor_d=8),
    "prism": lambda: dsl.prism(6, d=12, h=8),
    "tube": lambda: dsl.tube(h=30, d_outer=40, d_inner=34),
    "slot": lambda: dsl.slot(40, 10, 8),
    "teardrop": lambda: dsl.teardrop(d=8, h=30),
    "extrude": lambda: dsl.extrude([[0, 0], [20, 0], [20, 5], [5, 5], [5, 20], [0, 20]], h=4),
    "revolve": lambda: dsl.revolve([[0, 0], [8, 0], [8, 2], [3, 2], [3, 10], [0, 10]]),
    "twist_extrude": lambda: dsl.twist_extrude(
        [[20 * _math.cos(a), 20 * _math.sin(a)] for a in [i * _math.pi / 4 for i in range(8)]],
        height=60, turns=0.5),
    "loft": lambda: dsl.loft([
        ([[20 * _math.cos(a), 20 * _math.sin(a)] for a in [i * _math.pi / 2 for i in range(4)]], 0),
        ([[12 * _math.cos(a), 12 * _math.sin(a)] for a in [i * _math.pi / 2 for i in range(4)]], 40),
    ]),
    "text": lambda: dsl.text("3D", size=10, height=2),
}


@pytest.mark.parametrize("name", list(PRIMITIVES))
def test_primitive_is_manifold_volume(name):
    m = PRIMITIVES[name]().mesh
    assert m.is_watertight, f"{name} not watertight"
    assert m.is_winding_consistent, f"{name} inconsistent winding"
    assert m.is_volume, f"{name} not a valid volume"


def test_csg_operators_preserve_manifold():
    a = dsl.box(20, 20, 10)
    b = dsl.cylinder(h=30, d=6)
    for op in (a + b, a - b, a & b):
        assert op.mesh.is_watertight and op.mesh.is_volume


def test_units_are_mm_and_bbox_exact():
    m = dsl.box(70, 40, 60).mesh
    assert [round(float(x)) for x in m.extents] == [70, 40, 60]


def test_transform_chaining_and_on_bed():
    s = dsl.box(10, 10, 10).rotate_z(45).translate(5, 0, 0).on_bed()
    assert abs(float(s.bounds[0][2])) < 1e-6  # sits on z=0


# ---------------------------------------------------------------- sandbox

def test_sandbox_runs_build_form():
    m = run_script_text("def build():\n    return box(30,30,10) - cylinder(h=20,d=8)", timeout=40)
    assert m.is_watertight and m.is_volume


def test_sandbox_runs_result_form():
    m = run_script_text("result = cube(20) + sphere(d=10).at(10,10,20)", timeout=40)
    assert m.is_watertight


def test_sandbox_blocks_os_import():
    with pytest.raises(RuntimeError):
        run_script_text("import os\nos.system('echo pwned')\nresult = box(1,1,1)", timeout=40)


def test_sandbox_blocks_open():
    # `open` is not in the safe-builtins allowlist -> NameError (in-process) or
    # RuntimeError (subprocess wrapper). Either proves it is blocked.
    with pytest.raises((NameError, RuntimeError)):
        execute_in_process("result = open('/etc/passwd').read()")


def test_sandbox_timeout():
    with pytest.raises(RuntimeError):
        run_script_text("def build():\n    while True: pass", timeout=4)


# ---------------------------------------------------------------- validate

def test_validate_clean_part_is_print_ready():
    m = run_script_text("result = box(70,40,3,center=False) + box(70,3,60,center=False)", timeout=40)
    rep = validate(m, printer_profile="fdm_0.4", material="PLA")
    assert rep.print_ready is True
    assert rep.dimensions["D1_mesh_integrity"]["pass"] is True
    assert rep.score >= 90


def test_validate_thin_wall_warns():
    m = run_script_text("result = box(40,40,0.5)", timeout=40)
    rep = validate(m, printer_profile="fdm_0.4")
    assert any("below the 0.8mm" in w for w in rep.warnings)


def test_validate_oversize_fails_bed_fit():
    m = run_script_text("result = box(400,40,40)", timeout=40)
    rep = validate(m, printer_profile="fdm_0.4", bed_mm=(256, 256, 256))
    assert rep.dimensions["D3_print_geometry"]["bed_fit"] is False
    assert rep.print_ready is False


def test_overhang_excludes_bed_contact():
    # vertical tube on the bed: bottom rim is bed-contact, not an overhang
    m = run_script_text("def build():\n o=prism(6,d=80,h=90).translate(0,0,45)\n i=prism(6,d=72,h=86).translate(0,0,48)\n return o-i", timeout=40)
    rep = validate(m, printer_profile="fdm_0.4")
    assert rep.metrics["overhang"]["needs_support"] is False


def test_wall_thickness_ray_accuracy():
    m = run_script_text("result = box(70,40,3,center=False) + box(70,3,60,center=False)", timeout=40)
    rep = validate(m, printer_profile="fdm_0.4")
    wt = rep.metrics["wall_thickness"]
    assert wt["available"] and abs(wt["median"] - 3.0) < 0.2


# ---------------------------------------------------------------- exporters

def test_exporters_write_all_and_3mf_roundtrips(tmp_path):
    m = run_script_text("result = box(30,20,10) - cylinder(h=20,d=6)", timeout=40)
    spec = ModelSpec(prompt="test box", name="tbox", category="mechanical",
                     color="#3a86ff", formats=["stl", "3mf", "glb"])
    rep = validate(m, printer_profile="fdm_0.4")
    out = tmp_path / "tbox-001"
    entry = exporters.write_bundle(m, str(out), spec, rep, spec.formats)
    for f in ("model.stl", "model.3mf", "model.glb", "thumb.png", "report.json", "spec.json"):
        assert (out / f).exists(), f"missing {f}"
    # 3MF must round-trip back to a watertight mesh with mm units preserved
    loaded = trimesh.load(str(out / "model.3mf"))
    geoms = list(loaded.geometry.values()) if hasattr(loaded, "geometry") else [loaded]
    g = geoms[0]
    g.merge_vertices()
    assert g.is_watertight
    assert abs(float(g.extents[0]) - 30.0) < 0.1
    assert entry["files"]["3mf"] == "model.3mf"


def test_manifest_aggregates(tmp_path):
    m = run_script_text("result = cube(10)", timeout=40)
    spec = ModelSpec(prompt="cube", name="c", formats=["stl"])
    rep = validate(m)
    exporters.write_bundle(m, str(tmp_path / "c-001"), spec, rep, ["stl"])
    path = exporters.write_manifest(str(tmp_path))
    data = json.load(open(path))
    assert data["count"] == 1 and data["models"][0]["id"] == "c-001"


# ---------------------------------------------------------------- examples

EXAMPLE_FILES = sorted(glob.glob(os.path.join(EXAMPLES, "*.py")))


@pytest.mark.parametrize("path", EXAMPLE_FILES, ids=[os.path.basename(p) for p in EXAMPLE_FILES])
def test_example_fabricates_watertight(path):
    code = open(path).read()
    m = run_script_text(code, timeout=120)
    assert m.is_watertight, f"{os.path.basename(path)} not watertight"
    assert m.is_volume, f"{os.path.basename(path)} not a valid volume"


# ---------------------------------------------------------------- profiles + DB

def test_printer_db_loads_and_has_bambu_a1():
    from studio3d.profiles import load_printer_db, get_printer
    db = load_printer_db()
    assert db["count"] >= 20
    a1 = get_printer("bambu-a1")
    assert a1 and a1["build_volume_mm"] == [256, 256, 256]
    assert len(a1["presets"]) == 10  # the 10 @BBL A1 quality presets
    assert a1["ams"]["max_colors"] == 4


def test_profile_roundtrip_in_tmp_xdg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "linux")
    import importlib
    from studio3d import profiles as P
    importlib.reload(P)
    printer = P.get_printer("Bambu Lab A1")
    prof = P.Profile.from_printer(printer, name="test-a1", ams_enabled=True,
                                  colors=["#000000", "#ffffff"], material="PETG")
    P.save_profile(prof, make_active=True)
    assert P.active_profile().name == "test-a1"
    assert P.active_profile().build_volume_mm == [256, 256, 256]
    assert P.active_profile().process_profile == "fdm_0.4"
    assert P.active_profile().multicolor_capable is True


# ---------------------------------------------------------------- history

def test_git_history_single_bundle_no_root_dotgit(tmp_path):
    from studio3d import history as H
    out = str(tmp_path / "out")
    os.makedirs(out)
    bundle = os.path.join(out, "thing")
    os.makedirs(bundle)
    open(os.path.join(bundle, "model.stl"), "w").write("v1")
    open(os.path.join(out, "manifest.json"), "w").write("{}")
    sha1 = H.commit_bundle(bundle, "rev1")
    open(os.path.join(bundle, "model.stl"), "w").write("v2-changed")
    sha2 = H.commit_bundle(bundle, "rev2")
    assert sha1 and sha2 and sha1 != sha2
    log = H.history(out, bundle="thing")
    assert len(log) == 2
    # isolated store: no stray .git at the output root (never touches user VCS)
    assert not os.path.exists(os.path.join(out, ".git"))
    assert os.path.isdir(os.path.join(out, ".studio3d-history"))


# ---------------------------------------------------------------- import + modify

def test_load_mesh_import_and_modify(tmp_path):
    from studio3d.dsl import box, cylinder
    # make a source STL, then import + modify it via load_mesh in the sandbox
    src = tmp_path / "src.stl"
    box(40, 40, 20).export(str(src))
    code = f"result = load_mesh({str(src)!r}) - cylinder(h=40, d=10)"
    m = run_script_text(code, timeout=60)
    assert m.is_watertight and m.is_volume
    assert len(m.faces) > 12  # the hole added geometry


# ---------------------------------------------------------------- library (style + reference)

def test_reference_library_has_subjects_and_owl_proportions():
    from studio3d.library import load_reference_library, get_reference, list_subjects
    subs = list_subjects()
    assert len(subs) >= 18 and "owl" in subs and "cat" in subs
    owl = get_reference("a cute owl figurine")  # token match -> 'owl'
    assert owl and owl["subject"] == "owl"
    assert "silhouette_cues" in owl and "csg_recipe" in owl


def test_styles_loaded_with_numeric_params():
    from studio3d.library import list_styles, get_style
    assert "cartoonish" in list_styles()
    c = get_style("cartoon")  # alias -> cartoonish
    assert c and c["name"] == "cartoonish"
    assert "eye_size_mult" in c or "head_body_ratio" in c


def test_design_brief_merges_reference_and_style():
    from studio3d.library import design_brief
    b = design_brief("owl", "cartoonish")
    assert b["have_reference"] and b["reference"]["subject"] == "owl"
    assert b["style_params"] is not None
    assert b["eye_rule"]  # _meta guidance present


# ---------------------------------------------------------------- design plan

def test_design_plan_new_validates_and_bridges_to_spec():
    from studio3d.design_plan import DesignPlan
    plan = DesignPlan.new(subject="owl", name="owl", style="cartoonish",
                          category="organic", dimensions_mm={"height": 88},
                          colors=[{"hex": "#8d6e63", "name": "body", "part": "body"}])
    assert plan.validate() == []           # schema-valid
    spec = plan.to_spec(script="result = sphere(d=30)")
    assert spec.style == "cartoonish" and spec.category == "organic"
    assert spec.color == "#8d6e63" and spec.name == "owl"


def test_design_plan_roundtrip(tmp_path):
    from studio3d.design_plan import DesignPlan
    p = DesignPlan.new(subject="vase", name="vase", style="clean",
                       category="decorative", dimensions_mm={"height": 120})
    path = tmp_path / "vase.design.json"
    p.save(str(path))
    loaded = DesignPlan.load(str(path))
    assert loaded.validate() == [] and loaded.name == "vase"
