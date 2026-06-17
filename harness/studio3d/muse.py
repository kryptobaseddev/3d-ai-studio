"""studio3d.muse — INTERNAL fabrication-reliability self-check (NOT the MUSE benchmark).

HONESTY NOTE (read this): this is **not** the real MUSE benchmark (HK PolyU, 2026) and
its number is **not comparable** to MUSE's 68→54→42→35→28 cascade. It runs a fixed set
of REFERENCE scripts that ship with the tool through the fabricate→validate pipeline and
reports how reliably the deterministic CSG kernel + validator produce watertight,
print-passing solids. Because the reference scripts are the answer key (the hard
text→CAD step is NOT exercised — a human/agent wrote the geometry), a high score here
measures FABRICATION RELIABILITY, not generation quality. The real text→CAD ability must
be measured by having the agent author from prompts blind, and "print_ready" is necessary
but not sufficient for design-intent correctness. Treat this as a regression check, not a
benchmark score to quote.

Dimensions (each 0..1 per case):
    D1 syntax_exec      script runs in the sandbox and yields a mesh
    D2 geometry_valid   watertight + 2-manifold + valid volume (validator D1)
    D3 functionality    structural intent proxy: expected #components + bbox in range
    D4 manufacturability validator D3 (walls/overhang/bed) AND D2 slice (proxy or real)
    D5 assemblability   single part: trivially OK; assembly: zero interference + all parts

Composite MUSE score (0..100) = weighted mean over cases. Functionality here is a
STRUCTURAL proxy (the agent's vision-critique loop judges true design intent); the
harness reports it as such.
"""
from __future__ import annotations

import json

# ---- benchmark cases: (prompt, DSL script, expectations) -------------------
# Reference scripts represent what the cad-author should produce. They exercise
# mechanical, functional, organic-stylized, vessel, and assembly paths.
CASES = [
    {
        "name": "wall_bracket",
        "prompt": "an L wall bracket 60mm with a 45-degree gusset and two M4 holes",
        "script": (
            "def build():\n"
            "    t=P.get('thick',4); H=P.get('h',50); L=P.get('len',60)\n"
            "    vert = box(t,H,L,center=False)\n"
            "    horiz = box(H,t,L,center=False)\n"
            "    gus = extrude([[t,t],[H*0.6,t],[t,H*0.6]], L, center=False)\n"
            "    body = vert + horiz + gus\n"
            "    holes = None\n"
            "    for z in (L*0.3, L*0.7):\n"
            "        h = teardrop(d=4.5,h=t+4).rotate_y(90).translate(-2, H*0.55, z)\n"
            "        holes = h if holes is None else holes+h\n"
            "    return (body - holes).on_bed()\n"
        ),
        "expects": {"components": 1, "min_bbox": [40, 40, 50], "max_bbox": [60, 60, 70]},
    },
    {
        "name": "parts_box",
        "prompt": "a small parts box with 2mm walls, 60x40x30mm",
        "script": (
            "def build():\n"
            "    w=P.get('wall',2); W=P.get('W',60); D=P.get('D',40); H=P.get('H',30)\n"
            "    outer = box(W,D,H,center=False)\n"
            "    inner = box(W-2*w, D-2*w, H, center=False).translate(w,w,w)\n"
            "    return (outer-inner).on_bed()\n"
        ),
        "expects": {"components": 1, "min_bbox": [55, 35, 25], "max_bbox": [65, 45, 35]},
    },
    {
        "name": "hex_standoff",
        "prompt": "a hex standoff 12mm across, 20mm tall, M4 bore",
        "script": (
            "def build():\n"
            "    H=P.get('h',20)\n"
            "    return (prism(6,d=12,h=H) - cylinder(h=H+2,d=5.6)).on_bed()\n"
        ),
        "expects": {"components": 1, "min_bbox": [8, 8, 18], "max_bbox": [14, 14, 22]},
    },
    {
        "name": "twisted_vase",
        "prompt": "a twisted hexagonal vase 100mm tall with a 1.6mm wall that holds water",
        "script": (
            "import math\n"
            "def build():\n"
            "    H=P.get('h',100); turns=P.get('turns',1.0); wall=P.get('wall',2.2)\n"
            "    R=P.get('R',20); amp=P.get('amp',3); lobes=P.get('lobes',6); n=72\n"
            "    prof=[]\n"
            "    for i in range(n):\n"
            "        a=2*math.pi*i/n; r=R+amp*math.cos(lobes*a)\n"
            "        prof.append([r*math.cos(a), r*math.sin(a)])\n"
            "    outer = twist_extrude(prof, height=H, turns=turns)\n"
            "    bore_r = (R-amp) - wall   # thinnest outer radius minus the wall\n"
            "    bore = cylinder(h=H, d=2*bore_r, center=False).translate(0,0,wall+1)\n"
            "    return (outer - bore).on_bed()\n"
        ),
        "expects": {"components": 1, "min_bbox": [38, 38, 95], "max_bbox": [55, 55, 105]},
    },
    {
        "name": "cable_clip",
        "prompt": "a snap cable clip that grips a 5mm cable",
        "script": (
            "def build():\n"
            "    body = rounded_box(16,14,10,radius=2)\n"
            "    bore = cylinder(h=20,d=5).rotate_x(90)\n"
            "    mouth = box(3.5,20,10).translate(0,6,0)\n"
            "    return (body - bore - mouth).on_bed()\n"
        ),
        "expects": {"components": 1, "min_bbox": [10, 10, 8], "max_bbox": [20, 20, 14]},
    },
    {
        "name": "stylized_owl",
        "prompt": "a cute cartoon owl figurine ~70mm tall with big eyes and ear tufts",
        "script": (
            "def build():\n"
            "    H=P.get('h',70)\n"
            "    body = ellipsoid(0.62*H,0.55*H,0.8*H).translate(0,0,0.4*H)\n"
            "    eyeL = sphere(d=0.22*H).translate(-0.14*H,0.26*H,0.55*H)\n"
            "    eyeR = sphere(d=0.22*H).translate(0.14*H,0.26*H,0.55*H)\n"
            "    beak = cone(h=0.12*H,d=0.1*H).rotate_x(90).translate(0,0.3*H,0.5*H)\n"
            "    tuftL = cone(h=0.18*H,d=0.12*H).translate(-0.16*H,0,0.78*H)\n"
            "    tuftR = cone(h=0.18*H,d=0.12*H).translate(0.16*H,0,0.78*H)\n"
            "    return (body+eyeL+eyeR+beak+tuftL+tuftR).on_bed()\n"
        ),
        "expects": {"components": 1, "min_bbox": [30, 25, 60], "max_bbox": [70, 60, 95]},
    },
    {
        "name": "phone_stand",
        "prompt": "a phone stand that holds a phone at a viewing angle (one connected piece)",
        "script": (
            "def build():\n"
            "    base = box(80,60,6,center=False)\n"
            "    back = box(80,6,70,center=False).rotate_x(-20,about=[0,0,0]).translate(0,18,6)\n"
            "    lip = box(80,8,12,center=False).translate(0,8,6)\n"
            "    return (base + back + lip).on_bed()\n"
        ),
        "expects": {"components": 1, "min_bbox": [70, 30, 30], "max_bbox": [90, 90, 90]},
    },
    {
        "name": "two_part_box_lid",
        "prompt": "a box and a friction-fit lid as a 2-part assembly (no interference)",
        "assembly": True,
        "script": (
            "def build():\n"
            "    cl=P.get('clearance',0.3); W=50; D=40; H=25; w=2\n"
            "    box_body = box(W,D,H,center=False) - box(W-2*w,D-2*w,H,center=False).translate(w,w,w)\n"
            "    lid = box(W-2*w-2*cl, D-2*w-2*cl, 3, center=False)\n"
            "    parts = arrange_on_bed([box_body, lid], gap=6)\n"
            "    coll = interference(parts[0], parts[1])\n"
            "    assert coll == 0.0, f'lid collides with box: {coll}mm3'\n"
            "    return parts[0] + parts[1]\n"
        ),
        "expects": {"components": 2, "min_bbox": [50, 30, 2], "max_bbox": [130, 50, 30]},
    },
]

_WEIGHTS = {"syntax_exec": 0.15, "geometry_valid": 0.25, "functionality": 0.20,
           "manufacturability": 0.25, "assemblability": 0.15}


def _bbox_ok(bbox, lo, hi) -> bool:
    if not bbox:
        return False
    return all(lo[i] - 0.5 <= bbox[i] <= hi[i] + 0.5 for i in range(3))


def run_case(case: dict, do_slice: bool = False, timeout: float = 60.0) -> dict:
    from .sandbox import run_script_text
    from .validate import validate
    dims = {"syntax_exec": 0.0, "geometry_valid": 0.0, "functionality": 0.0,
            "manufacturability": 0.0, "assemblability": 0.0}
    rec: dict = {"name": case["name"], "prompt": case["prompt"], "dims": dims, "error": None}
    try:
        mesh = run_script_text(case["script"], timeout=timeout, params={})
        dims["syntax_exec"] = 1.0
    except Exception as e:
        rec["error"] = f"{type(e).__name__}: {e}"
        rec["muse"] = 0.0
        return rec
    exp_comp = case.get("expects", {}).get("components", 1)
    rep = validate(mesh, do_slice=do_slice, expected_components=exp_comp)
    d1 = rep.dimensions["D1_mesh_integrity"]["pass"]
    dims["geometry_valid"] = 1.0 if d1 else 0.0
    # functionality proxy: expected component count + bbox in range
    exp = case.get("expects", {})
    km = rep.metrics.get("kernel_metrics", {})
    comp_ok = (km.get("n_components") == exp.get("components")) if "components" in exp else True
    bbox_ok = _bbox_ok(km.get("bbox_mm"), exp.get("min_bbox", [0, 0, 0]),
                       exp.get("max_bbox", [1e9, 1e9, 1e9])) if "min_bbox" in exp else True
    dims["functionality"] = 1.0 if (comp_ok and bbox_ok) else (0.5 if (comp_ok or bbox_ok) else 0.0)
    # manufacturability: D3 + D2
    d3 = rep.dimensions["D3_print_geometry"]["pass"]
    d2 = rep.dimensions["D2_slicer_pass"]["pass"]
    dims["manufacturability"] = (0.6 if d3 else 0.0) + (0.4 if d2 else 0.0)
    # assemblability
    if case.get("assembly"):
        # the script asserts zero interference; reaching here with expected comps == pass
        dims["assemblability"] = 1.0 if comp_ok else 0.5
    else:
        dims["assemblability"] = 1.0  # single part is trivially assemblable
    rec["bbox_mm"] = km.get("bbox_mm")
    rec["n_components"] = km.get("n_components")
    rec["print_ready"] = rep.print_ready
    rec["d2_method"] = rep.dimensions["D2_slicer_pass"].get("method")
    rec["muse"] = round(100 * sum(_WEIGHTS[k] * v for k, v in dims.items()), 1)
    return rec


def run(do_slice: bool = False, timeout: float = 60.0, cases: list | None = None) -> dict:
    cs = cases if cases is not None else CASES
    results = [run_case(c, do_slice=do_slice, timeout=timeout) for c in cs]
    agg = {k: round(100 * sum(r["dims"][k] for r in results) / len(results), 1) for k in _WEIGHTS}
    overall = round(sum(r["muse"] for r in results) / len(results), 1)
    cascade = {  # MUSE-style funnel: fraction passing each stage (>= threshold)
        "syntax_exec": round(100 * sum(1 for r in results if r["dims"]["syntax_exec"] >= 1) / len(results), 1),
        "geometry_valid": round(100 * sum(1 for r in results if r["dims"]["geometry_valid"] >= 1) / len(results), 1),
        "functionality": round(100 * sum(1 for r in results if r["dims"]["functionality"] >= 1) / len(results), 1),
        "manufacturability": round(100 * sum(1 for r in results if r["dims"]["manufacturability"] >= 1) / len(results), 1),
        "assemblability": round(100 * sum(1 for r in results if r["dims"]["assemblability"] >= 1) / len(results), 1),
    }
    return {
        "what_this_is": "INTERNAL fabrication-reliability self-check (self-scored on bundled "
                        "reference scripts) — NOT the MUSE benchmark; not comparable to it. "
                        "Measures pipeline reliability, not text→CAD generation quality.",
        "reliability_score": overall,
        "dimensions_pct": agg, "cascade_pct": cascade,
        "n_cases": len(results), "do_slice": do_slice, "cases": results,
    }


if __name__ == "__main__":  # pragma: no cover
    print(json.dumps(run(), indent=2))
