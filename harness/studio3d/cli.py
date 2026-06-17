"""studio3d.cli — the callable harness command line.

This is the tool the Claude Code plugin (and the user) invokes. Every command
emits a single JSON object on stdout so an agent can parse the result; human logs
go to stderr.

Commands:
    gen          full pipeline from a ModelSpec (file or --json/stdin)
    gen-script   quick pipeline from a raw DSL script + flags
    run-script   sandbox-execute a DSL script to a mesh file (low level)
    validate     validate an existing mesh file -> print-readiness report
    manifest     (re)build output/manifest.json
    examples     list / emit bundled example DSL scripts
    doctor       environment + dependency check
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__


def _eprint(*a):
    print(*a, file=sys.stderr, flush=True)


def _emit(obj: dict, ok: bool = True):
    obj.setdefault("ok", ok)
    print(json.dumps(obj, indent=2))
    return 0 if ok else 1


def _bundle_dir(output_root: str, slug: str, variant: bool = False) -> str:
    """One evolving folder per design (output/<slug>/). Regeneration OVERWRITES
    it in place — git history captures the change, so there is no -001/-002 spam.
    Pass variant=True only when the user explicitly wants a separate copy."""
    os.makedirs(output_root, exist_ok=True)
    if not variant:
        d = os.path.join(output_root, slug)
        os.makedirs(d, exist_ok=True)
        return d
    n = 2
    existing = set(os.listdir(output_root))
    while f"{slug}-v{n}" in existing:
        n += 1
    d = os.path.join(output_root, f"{slug}-v{n}")
    os.makedirs(d, exist_ok=True)
    return d


# ----------------------------------------------------------------------
# core pipeline
# ----------------------------------------------------------------------

def _apply_profile(spec):
    """If a user printer profile is active, target it: bed volume, process profile
    (nozzle → wall minimums), and multicolor capability. Returns bed_mm tuple."""
    try:
        from .profiles import active_profile
        prof = active_profile()
    except Exception:
        prof = None
    if not prof:
        return (256, 256, 256), None
    # the active profile overrides the spec's defaults unless the spec was explicit
    spec.printer_profile = prof.process_profile
    spec.material = spec.material or prof.material
    if prof.multicolor_capable and prof.palette:
        spec.multicolor = spec.multicolor  # keep request intent; palette available
    bed = tuple(prof.build_volume_mm) if prof.build_volume_mm else (256, 256, 256)
    return bed, prof


def _fabricate(spec, output_root: str, timeout: float = 60.0, do_slice: bool = True) -> dict:
    """Run the engine -> validate -> export bundle. Returns a result dict."""
    from .validate import validate
    from . import exporters

    engine = spec.resolved_engine
    provenance = {"engine": engine}

    if engine == "csg":
        if not spec.script:
            raise SystemExit("spec.engine=csg requires a `script` (DSL source)")
        from .sandbox import run_script_text
        _eprint(f"[studio3d] executing CSG script in sandbox (timeout={timeout}s)…")
        mesh = run_script_text(spec.script, timeout=timeout, params=spec.parameters or {})
    else:
        from .generative import generate
        _eprint("[studio3d] routing to generative backend…")
        mesh, gen_info = generate(spec)
        provenance.update(gen_info)
        if gen_info.get("heal"):
            _eprint(f"[studio3d] healed generative mesh: watertight {gen_info['heal'].get('watertight_after')}")

    bed, prof = _apply_profile(spec)
    if prof:
        provenance["printer"] = f"{prof.make} {prof.model}"
        _eprint(f"[studio3d] targeting active profile: {prof.name} ({prof.make} {prof.model}, bed {bed}mm)")
    _eprint("[studio3d] validating print-readiness…")
    report = validate(mesh, printer_profile=spec.printer_profile,
                      material=spec.material, multicolor=spec.multicolor, bed_mm=bed,
                      do_slice=do_slice)
    d2m = report.dimensions.get("D2_slicer_pass", {}).get("method")
    if d2m == "slice":
        _eprint(f"[studio3d] D2 real slice via {report.dimensions['D2_slicer_pass'].get('slicer')}: "
                f"sliced={report.dimensions['D2_slicer_pass'].get('pass')}")

    bundle_dir = _bundle_dir(output_root, spec.slug, variant=getattr(spec, "_variant", False))
    _eprint(f"[studio3d] writing bundle -> {bundle_dir}")
    entry = exporters.write_bundle(mesh, bundle_dir, spec, report, spec.formats)
    # stash provenance
    with open(os.path.join(bundle_dir, "provenance.json"), "w") as f:
        json.dump(provenance, f, indent=2)
    # persist the design plan (the regenerable base design) into the bundle
    plan = getattr(spec, "_plan", None)
    if plan is not None:
        plan.save(os.path.join(bundle_dir, "design.json"))
    # write the auditable Print-Readiness Certificate (prompt -> script hash ->
    # file hashes -> D1-D4 -> slice -> human-approval slot)
    try:
        from .certify import write_certificate
        from datetime import datetime, timezone
        write_certificate(spec, report, bundle_dir, provenance,
                          timestamp=datetime.now(timezone.utc).isoformat())
    except Exception as e:
        _eprint(f"[studio3d] (certificate skipped: {e})")
    manifest_path = exporters.write_manifest(output_root)
    # commit this revision to the design history (single evolving bundle)
    try:
        from .history import commit_bundle
        commit_bundle(bundle_dir, f"{spec.name}: {spec.prompt[:60]}")
    except Exception as e:
        _eprint(f"[studio3d] (history commit skipped: {e})")

    return {
        "bundle_dir": bundle_dir,
        "manifest": manifest_path,
        "print_ready": report.print_ready,
        "score": report.score,
        "files": entry["files"],
        "editable": entry.get("editable"),
        "summary": {
            "bbox_mm": report.metrics.get("bbox_mm"),
            "est_mass_g": report.metrics.get("est_mass_g_solid"),
            "triangles": report.metrics.get("triangles"),
            "kernel_metrics": report.metrics.get("kernel_metrics"),
            "d2": report.dimensions.get("D2_slicer_pass"),
            "issues": report.issues,
            "warnings": report.warnings,
            "suggestions": report.suggestions,
        },
        "engine": engine,
    }


# ----------------------------------------------------------------------
# command handlers
# ----------------------------------------------------------------------

def cmd_gen(args) -> int:
    from .spec import ModelSpec
    if args.json:
        spec = ModelSpec.from_json(args.json)
    elif args.spec and args.spec != "-":
        spec = ModelSpec.load(args.spec)
    else:
        spec = ModelSpec.from_json(sys.stdin.read())
    try:
        res = _fabricate(spec, args.out, timeout=args.timeout,
                         do_slice=not getattr(args, "no_slice", False))
    except Exception as e:
        return _emit({"error": f"{type(e).__name__}: {e}"}, ok=False)
    return _emit(res)


def cmd_gen_script(args) -> int:
    from .spec import ModelSpec
    script = _read_script(args)
    params = {}
    if getattr(args, "params", None):
        try:
            params = json.loads(args.params)
        except Exception as e:
            return _emit({"error": f"--params is not valid JSON: {e}"}, ok=False)
    plan = None
    if getattr(args, "plan", None):
        from .design_plan import DesignPlan
        plan = DesignPlan.load(args.plan)
        spec = plan.to_spec(script=script)
        spec.formats = [f.strip() for f in args.formats.split(",") if f.strip()]
        if params:
            spec.parameters = {**(spec.parameters or {}), **params}
        if args.color:
            spec.color = args.color
    else:
        spec = ModelSpec(
            prompt=args.prompt or args.name or "model",
            name=args.name or "model",
            category=args.category,
            style=getattr(args, "style", "clean"),
            engine="csg",
            script=script,
            parameters=params,
            printer_profile=args.profile,
            material=args.material,
            color=args.color,
            multicolor=args.multicolor,
            formats=[f.strip() for f in args.formats.split(",") if f.strip()],
        )
    spec._variant = getattr(args, "variant", False)
    spec._plan = plan  # stashed so _fabricate can copy design.json into the bundle
    try:
        res = _fabricate(spec, args.out, timeout=args.timeout,
                         do_slice=not getattr(args, "no_slice", False))
    except Exception as e:
        return _emit({"error": f"{type(e).__name__}: {e}"}, ok=False)
    return _emit(res)


def cmd_run_script(args) -> int:
    from .sandbox import run_script_text
    script = _read_script(args)
    try:
        mesh = run_script_text(script, timeout=args.timeout)
        mesh.export(args.out)
    except Exception as e:
        return _emit({"error": f"{type(e).__name__}: {e}"}, ok=False)
    return _emit({
        "out": args.out,
        "triangles": int(len(mesh.faces)),
        "watertight": bool(mesh.is_watertight),
        "is_volume": bool(mesh.is_volume),
        "bbox_mm": [round(float(x), 2) for x in mesh.extents],
    })


def cmd_validate(args) -> int:
    import trimesh
    from .validate import validate
    try:
        mesh = trimesh.load(args.mesh, force="mesh")
        if isinstance(mesh, trimesh.Scene):
            mesh = trimesh.util.concatenate([g for g in mesh.geometry.values()])
        report = validate(mesh, printer_profile=args.profile, material=args.material,
                          multicolor=args.multicolor, do_repair=not args.no_repair,
                          do_slice=getattr(args, "slice", False), model_path=args.mesh)
    except Exception as e:
        return _emit({"error": f"{type(e).__name__}: {e}"}, ok=False)
    return _emit(report.to_dict())


def cmd_slice(args) -> int:
    """Real headless slice-to-G-code (D2 ground truth): print time + filament."""
    from .slicer import slice_model, detect_slicer
    sl = detect_slicer()
    if not sl:
        return _emit({"available": False,
                      "hint": "install OrcaSlicer/PrusaSlicer or set $STUDIO3D_SLICER to the CLI"}, ok=False)
    res = slice_model(args.mesh, material=args.material, timeout=args.timeout)
    return _emit(res, ok=bool(res.get("sliced")))


def cmd_tweak(args) -> int:
    """Edit ONE named parameter on a design plan and regenerate deterministically
    in place — the proof a model is forever-editable, which Meshy's dead mesh isn't."""
    from .design_plan import DesignPlan
    plan = DesignPlan.load(args.plan)
    # parse --set key=value pairs (numbers stay numeric)
    for kv in (args.set or []):
        if "=" not in kv:
            return _emit({"error": f"--set expects key=value, got {kv!r}"}, ok=False)
        k, v = kv.split("=", 1)
        try:
            val = json.loads(v)        # 4.0 -> float, "x" -> needs quotes, true -> bool
        except Exception:
            val = v
        plan.set_param(k.strip(), val)
    plan.bump_revision()
    plan.save(args.plan)
    if not args.script:
        return _emit({"plan": args.plan, "revision": plan.data.get("revision"),
                      "parameters": plan.data.get("parameters", {}),
                      "hint": "pass --script model.py to regenerate now"})
    script = open(args.script).read()
    spec = plan.to_spec(script=script)
    spec._plan = plan
    try:
        res = _fabricate(spec, args.out, timeout=args.timeout,
                         do_slice=not getattr(args, "no_slice", False))
    except Exception as e:
        return _emit({"error": f"{type(e).__name__}: {e}"}, ok=False)
    res["revision"] = plan.data.get("revision")
    res["parameters"] = plan.data.get("parameters", {})
    return _emit(res)


def cmd_kb(args) -> int:
    """Query the local DFAM/CSG domain-RAG (grounds the cad-author in documented
    rules — the report's BlenderRAG capability lever, offline)."""
    from . import kb
    if not args.query:
        return _emit({"stats": kb.stats(),
                      "hint": "studio3d kb 'overhang limit and supports'"})
    hits = kb.search(args.query, k=args.k)
    return _emit({"query": args.query, "hits": hits, "n": len(hits)})


def cmd_muse(args) -> int:
    """Run the internal MUSE-style print-readiness benchmark + report the score."""
    from . import muse
    res = muse.run(do_slice=getattr(args, "slice", False), timeout=args.timeout)
    if not args.full:
        res["cases"] = [{"name": c["name"], "muse": c["muse"], "print_ready": c.get("print_ready"),
                         "error": c.get("error")} for c in res["cases"]]
    return _emit(res)


def cmd_orient(args) -> int:
    """Find the support-minimizing print orientation (SEG) and optionally write the
    reoriented mesh. Slicer-aware placement: fewer supports == less waste/cleanup."""
    import trimesh
    from .validate import orient_for_print
    from trimesh import transformations as tf
    import math
    try:
        mesh = trimesh.load(args.mesh, force="mesh")
        if isinstance(mesh, trimesh.Scene):
            mesh = trimesh.util.concatenate([g for g in mesh.geometry.values()])
        res = orient_for_print(mesh, limit_deg=args.overhang)
        best = res["best"]
        if args.out:
            m = mesh.copy()
            if best["axis"] is not None:
                m.apply_transform(tf.rotation_matrix(math.radians(best["deg"]), best["axis"], m.centroid))
            m.apply_translation([0, 0, -float(m.bounds[0][2])])
            m.export(args.out)
            res["written"] = args.out
    except Exception as e:
        return _emit({"error": f"{type(e).__name__}: {e}"}, ok=False)
    return _emit(res)


def cmd_certify(args) -> int:
    """Sign off a Print-Readiness Certificate (human approval, audit trail)."""
    cert_path = os.path.join(args.bundle, "certificate.json")
    if not os.path.exists(cert_path):
        return _emit({"error": f"no certificate.json in {args.bundle}"}, ok=False)
    with open(cert_path) as f:
        cert = json.load(f)
    cert["human_approved"] = bool(args.approve)
    if args.note:
        cert["human_note"] = args.note
    with open(cert_path, "w") as f:
        json.dump(cert, f, indent=2)
    return _emit({"certificate": cert_path, "human_approved": cert["human_approved"],
                  "print_ready": cert.get("print_ready"), "score": cert.get("score")})


def cmd_manifest(args) -> int:
    from . import exporters
    path = exporters.write_manifest(args.out)
    with open(path) as f:
        data = json.load(f)
    return _emit({"manifest": path, "count": data["count"]})


def cmd_examples(args) -> int:
    examples_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "examples")
    if not os.path.isdir(examples_dir):
        return _emit({"examples_dir": examples_dir, "examples": []})
    items = [f for f in sorted(os.listdir(examples_dir)) if f.endswith(".py")]
    if args.show:
        path = os.path.join(examples_dir, args.show)
        if not os.path.exists(path):
            return _emit({"error": f"no example {args.show!r}"}, ok=False)
        return _emit({"name": args.show, "source": open(path).read()})
    return _emit({"examples_dir": examples_dir, "examples": items})


def cmd_doctor(args) -> int:
    checks = {}
    for mod in ["numpy", "trimesh", "manifold3d", "shapely", "PIL", "matplotlib",
                "rtree", "stl", "lxml", "scipy"]:
        try:
            m = __import__(mod)
            checks[mod] = getattr(m, "__version__", "ok")
        except Exception as e:
            checks[mod] = f"MISSING ({type(e).__name__})"
    # boolean engine sanity
    boolean_ok = False
    try:
        import trimesh
        a = trimesh.creation.box([10, 10, 10])
        b = trimesh.creation.box([10, 10, 10]); b.apply_translation([5, 5, 5])
        r = trimesh.boolean.difference([a, b])
        boolean_ok = bool(r.is_watertight)
    except Exception as e:
        checks["boolean_engine_error"] = str(e)
    checks["manifold_boolean_watertight"] = boolean_ok
    # optional / capability checks
    try:
        import yaml  # noqa: F401
        checks["pyyaml"] = "ok"
    except Exception:
        checks["pyyaml"] = "MISSING"
    import shutil as _sh
    checks["blender_render"] = "ok" if _sh.which("blender") else "matplotlib-fallback"
    try:
        from .profiles import active_profile, load_printer_db
        checks["printer_db"] = f"{load_printer_db()['count']} printers"
        prof = active_profile()
        checks["active_profile"] = f"{prof.name} ({prof.make} {prof.model})" if prof else "none"
    except Exception as e:
        checks["profiles_error"] = str(e)
    try:
        from .library import list_subjects, list_styles
        checks["reference_library"] = f"{len(list_subjects())} subjects"
        checks["style_system"] = f"{len(list_styles())} styles"
        from .design_plan import schema
        checks["design_plan_schema"] = "ok" if schema().get("$id") else "MISSING"
    except Exception as e:
        checks["library_error"] = str(e)
    checks["python"] = sys.version.split()[0]
    checks["studio3d"] = __version__
    ok = all(not str(v).startswith("MISSING") for v in checks.values()) and boolean_ok
    return _emit({"checks": checks}, ok=ok)


def cmd_render(args) -> int:
    """Multi-view render of a mesh (for the agent's visual-critique loop)."""
    from .render import render_views
    out_dir = args.out or os.path.join(os.path.dirname(os.path.abspath(args.mesh)), "views")
    views = [v.strip() for v in args.views.split(",") if v.strip()]
    try:
        res = render_views(args.mesh, out_dir, color=args.color, size=args.size, views=views)
    except Exception as e:
        return _emit({"error": f"{type(e).__name__}: {e}"}, ok=False)
    return _emit({"engine": res.get("engine"), "views": res.get("views"),
                  "hint": "Read each PNG and compare against the design intent; revise the script if it doesn't match."})


def cmd_printers(args) -> int:
    from .profiles import find_printers
    hits = find_printers(args.search or "")
    if args.full:
        return _emit({"count": len(hits), "printers": hits})
    rows = [{"slug": p["slug"], "make": p["make"], "model": p["model"],
             "build_volume_mm": p["build_volume_mm"], "nozzle_mm": p["nozzle_mm"],
             "ams": p["ams"]["name"], "max_colors": p["ams"]["max_colors"],
             "presets": len(p.get("presets", []))} for p in hits]
    return _emit({"count": len(rows), "printers": rows})


def cmd_profile(args) -> int:
    from . import profiles as P
    action = args.action
    if action == "list":
        active = P._load_manifest().get("active")
        return _emit({"active": active, "profiles": P.list_profiles(),
                      "config_dir": P.config_dir()})
    if action == "show":
        prof = P.load_profile(args.name) if args.name else P.active_profile()
        if not prof:
            return _emit({"error": "no such profile (or no active profile)"}, ok=False)
        d = prof.to_dict()
        d["process_profile"] = prof.process_profile
        d["multicolor_capable"] = prof.multicolor_capable
        return _emit({"profile": d})
    if action == "use":
        ok = P.set_active(args.name)
        return _emit({"active": args.name} if ok else {"error": f"no profile {args.name!r}"}, ok=ok)
    if action == "add":
        printer = P.get_printer(args.printer)
        if not printer:
            return _emit({"error": f"no printer matching {args.printer!r}; try 'studio3d printers --search ...'"}, ok=False)
        colors = [c.strip() for c in (args.colors or "").split(",") if c.strip()]
        ams = None if args.ams is None else args.ams
        prof = P.Profile.from_printer(printer, name=args.name, ams_enabled=ams,
                                      colors=colors, material=args.material)
        path = P.save_profile(prof, make_active=not args.no_activate)
        d = prof.to_dict(); d["process_profile"] = prof.process_profile
        return _emit({"saved": path, "active": not args.no_activate, "profile": d})
    return _emit({"error": f"unknown profile action {action!r}"}, ok=False)


def cmd_import(args) -> int:
    """Import an existing STL/3MF/GLB/OBJ into the output as an editable bundle."""
    import trimesh
    from .dsl import load_mesh
    from .spec import ModelSpec
    from .validate import validate
    from . import exporters
    try:
        solid = load_mesh(args.file, repair=not args.no_repair)
        mesh = solid.on_bed().center_xy().mesh if args.reorient else solid.mesh
        name = args.name or os.path.splitext(os.path.basename(args.file))[0]
        spec = ModelSpec(prompt=f"imported from {os.path.basename(args.file)}", name=name,
                         category="mechanical", engine="csg", color=args.color,
                         formats=["stl", "3mf", "glb"])
        bed, prof = _apply_profile(spec)
        report = validate(mesh, printer_profile=spec.printer_profile, material=spec.material, bed_mm=bed)
        bundle = _bundle_dir(args.out, spec.slug)
        entry = exporters.write_bundle(mesh, bundle, spec, report, spec.formats)
        exporters.write_manifest(args.out)
        try:
            from .history import commit_bundle
            commit_bundle(bundle, f"import {name}")
        except Exception:
            pass
    except Exception as e:
        return _emit({"error": f"{type(e).__name__}: {e}"}, ok=False)
    return _emit({"bundle_dir": bundle, "print_ready": report.print_ready, "score": report.score,
                  "files": entry["files"], "bbox_mm": report.metrics.get("bbox_mm"),
                  "hint": "Modify it by writing a DSL script that calls load_mesh('<bundle>/model.stl') then booleans/transforms, and run `studio3d gen-script`."})


def cmd_history(args) -> int:
    from . import history as H
    if args.revert:
        ok = H.revert_bundle(args.out, args.bundle, args.revert)
        return _emit({"reverted": args.bundle, "to": args.revert} if ok else {"error": "revert failed"}, ok=ok)
    log = H.history(args.out, bundle=args.bundle, limit=args.limit)
    return _emit({"count": len(log), "history": log})


def cmd_reference(args) -> int:
    """Look up the packaged design reference for a subject (silhouette cues +
    proportions + CSG recipe) so authoring is grounded, not improvised."""
    from .library import get_reference, list_subjects, design_brief
    if args.subject:
        brief = design_brief(args.subject, args.style)
        if not brief["have_reference"]:
            return _emit({"error": f"no reference for {args.subject!r}",
                          "available": list_subjects()}, ok=False)
        return _emit({"brief": brief})
    return _emit({"subjects": list_subjects()})


def cmd_styles(args) -> int:
    from .library import list_styles, get_style
    if args.name:
        st = get_style(args.name)
        return _emit({"style": st} if st else {"error": f"no style {args.name!r}", "available": list_styles()}, ok=st is not None)
    return _emit({"styles": list_styles()})


def cmd_plan(args) -> int:
    from .design_plan import DesignPlan
    if args.action == "new":
        plan = DesignPlan.new(
            subject=args.subject, name=args.name, style=args.style,
            category=args.category, prompt=args.prompt or args.subject,
            dimensions_mm={"height": args.height} if args.height else None,
            wall_thickness_mm=args.wall, printer_profile=args.profile,
            colors=[{"hex": args.color, "name": "primary", "part": "body"}] if args.color else None,
        )
        errs = plan.validate()
        path = args.out or f"{plan.name}.design.json"
        plan.save(path)
        return _emit({"saved": path, "valid": not errs, "errors": errs,
                      "brief": plan.brief()})
    if args.action in ("show", "validate", "brief"):
        plan = DesignPlan.load(args.file)
        if args.action == "validate":
            errs = plan.validate()
            return _emit({"valid": not errs, "errors": errs}, ok=not errs)
        if args.action == "brief":
            return _emit({"brief": plan.brief()})
        return _emit({"plan": plan.data, "errors": plan.validate()})
    return _emit({"error": f"unknown plan action {args.action!r}"}, ok=False)


def _read_script(args) -> str:
    if getattr(args, "script", None) and args.script != "-":
        with open(args.script) as f:
            return f.read()
    if getattr(args, "code", None):
        return args.code
    return sys.stdin.read()


# ----------------------------------------------------------------------
# argparse
# ----------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="studio3d", description="agentic text/image-to-3D-print harness")
    p.add_argument("--version", action="version", version=f"studio3d {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("gen", help="full pipeline from a ModelSpec")
    g.add_argument("--spec", help="path to spec.json ('-' or omit for stdin)")
    g.add_argument("--json", help="inline ModelSpec JSON string")
    g.add_argument("--out", default="output", help="output root (default: output)")
    g.add_argument("--timeout", type=float, default=60.0)
    g.add_argument("--no-slice", action="store_true", help="skip the real D2 slice (use the labeled proxy)")
    g.set_defaults(func=cmd_gen)

    gs = sub.add_parser("gen-script", help="full pipeline from a raw DSL script")
    gs.add_argument("--script", help="path to a .py DSL script ('-' for stdin)")
    gs.add_argument("--code", help="inline DSL source")
    gs.add_argument("--name", default="model")
    gs.add_argument("--prompt", default="")
    gs.add_argument("--category", default="mechanical")
    gs.add_argument("--style", default="clean")
    gs.add_argument("--profile", default="fdm_0.4")
    gs.add_argument("--material", default="PLA")
    gs.add_argument("--color", default=None)
    gs.add_argument("--multicolor", action="store_true")
    gs.add_argument("--formats", default="stl,3mf,glb")
    gs.add_argument("--out", default="output")
    gs.add_argument("--timeout", type=float, default=60.0)
    gs.add_argument("--variant", action="store_true", help="write a separate copy instead of overwriting the design in place")
    gs.add_argument("--plan", help="design.json plan to fabricate from (sets style/size/color/category)")
    gs.add_argument("--params", help="JSON dict of named parameters injected as P (e.g. '{\"hole_d\":4.5}')")
    gs.add_argument("--no-slice", action="store_true", help="skip the real D2 slice (use the labeled proxy)")
    gs.set_defaults(func=cmd_gen_script)

    rs = sub.add_parser("run-script", help="sandbox-execute a DSL script to a mesh file")
    rs.add_argument("--script", help="path to .py DSL script ('-' for stdin)")
    rs.add_argument("--code", help="inline DSL source")
    rs.add_argument("--out", default="model.stl")
    rs.add_argument("--timeout", type=float, default=60.0)
    rs.set_defaults(func=cmd_run_script)

    v = sub.add_parser("validate", help="validate an existing mesh file")
    v.add_argument("mesh", help="path to STL/3MF/GLB/OBJ/PLY")
    v.add_argument("--profile", default="fdm_0.4")
    v.add_argument("--material", default="PLA")
    v.add_argument("--multicolor", action="store_true")
    v.add_argument("--no-repair", action="store_true")
    v.add_argument("--slice", action="store_true", help="run a REAL headless slice for D2 (needs a slicer installed)")
    v.set_defaults(func=cmd_validate)

    sl = sub.add_parser("slice", help="real headless slice-to-G-code (D2 ground truth)")
    sl.add_argument("mesh", help="path to STL/3MF to slice")
    sl.add_argument("--material", default="PLA")
    sl.add_argument("--timeout", type=float, default=120.0)
    sl.set_defaults(func=cmd_slice)

    tw = sub.add_parser("tweak", help="edit one design-plan parameter and regenerate in place")
    tw.add_argument("--plan", required=True, help="design.json to tweak")
    tw.add_argument("--set", action="append", help="key=value (repeatable), value is JSON (4.0, true, \"text\")")
    tw.add_argument("--script", help="model.py to regenerate from (omit to only edit the plan)")
    tw.add_argument("--out", default="output")
    tw.add_argument("--timeout", type=float, default=60.0)
    tw.add_argument("--no-slice", action="store_true")
    tw.set_defaults(func=cmd_tweak)

    kbp = sub.add_parser("kb", help="query the local DFAM/CSG domain knowledge base")
    kbp.add_argument("query", nargs="?", help="what to look up (e.g. 'overhang limit')")
    kbp.add_argument("-k", type=int, default=4, help="number of chunks to return")
    kbp.set_defaults(func=cmd_kb)

    mu = sub.add_parser("muse", help="run the internal MUSE print-readiness benchmark")
    mu.add_argument("--slice", action="store_true", help="use real slicing for D2 (needs a slicer)")
    mu.add_argument("--full", action="store_true", help="include per-case dimension detail")
    mu.add_argument("--timeout", type=float, default=60.0)
    mu.set_defaults(func=cmd_muse)

    orp = sub.add_parser("orient", help="find the support-minimizing print orientation (SEG)")
    orp.add_argument("mesh", help="path to STL/3MF/GLB/OBJ/PLY")
    orp.add_argument("--out", help="write the reoriented mesh here")
    orp.add_argument("--overhang", type=float, default=50.0, help="overhang limit deg from vertical")
    orp.set_defaults(func=cmd_orient)

    cf = sub.add_parser("certify", help="human sign-off on a bundle's Print-Readiness Certificate")
    cf.add_argument("bundle", help="bundle dir containing certificate.json")
    cf.add_argument("--approve", action="store_true", help="mark human_approved=true")
    cf.add_argument("--note", help="reviewer note")
    cf.set_defaults(func=cmd_certify)

    m = sub.add_parser("manifest", help="(re)build output/manifest.json")
    m.add_argument("--out", default="output")
    m.set_defaults(func=cmd_manifest)

    e = sub.add_parser("examples", help="list / show bundled example scripts")
    e.add_argument("--show", help="print the source of an example by filename")
    e.set_defaults(func=cmd_examples)

    d = sub.add_parser("doctor", help="environment + dependency check")
    d.set_defaults(func=cmd_doctor)

    r = sub.add_parser("render", help="multi-view render of a mesh (visual-critique loop)")
    r.add_argument("mesh", help="path to STL/3MF/GLB/OBJ/PLY")
    r.add_argument("--out", help="output dir for view PNGs (default: <mesh dir>/views)")
    r.add_argument("--views", default="front,right,top,iso")
    r.add_argument("--color", default="#9aa7b2")
    r.add_argument("--size", type=int, default=720)
    r.set_defaults(func=cmd_render)

    pr = sub.add_parser("printers", help="search the in-repo printer database")
    pr.add_argument("--search", default="", help="filter by make/model/slug")
    pr.add_argument("--full", action="store_true", help="full records incl. presets")
    pr.set_defaults(func=cmd_printers)

    pf = sub.add_parser("profile", help="manage user printer profiles (XDG config)")
    pf.add_argument("action", choices=["list", "show", "use", "add"])
    pf.add_argument("--name", help="profile name")
    pf.add_argument("--printer", help="printer make/model/slug from the DB (for add)")
    pf.add_argument("--colors", help="comma-separated filament hex colors, e.g. '#000000,#ffffff'")
    pf.add_argument("--material", default="PLA")
    pf.add_argument("--ams", type=lambda s: s.lower() in ("1", "true", "yes", "on"),
                    default=None, help="override AMS on/off (true/false)")
    pf.add_argument("--no-activate", action="store_true", help="don't make the new profile active")
    pf.set_defaults(func=cmd_profile)

    im = sub.add_parser("import", help="import an existing mesh as an editable bundle")
    im.add_argument("file", help="path to STL/3MF/GLB/OBJ/PLY")
    im.add_argument("--name")
    im.add_argument("--color", default="#9aa7b2")
    im.add_argument("--reorient", action="store_true", help="re-center on the bed")
    im.add_argument("--no-repair", action="store_true")
    im.add_argument("--out", default="output")
    im.set_defaults(func=cmd_import)

    h = sub.add_parser("history", help="show / revert design change history (git-tracked)")
    h.add_argument("--bundle", help="scope to one bundle id (folder name)")
    h.add_argument("--revert", help="commit SHA to restore the bundle to (point-in-time recovery)")
    h.add_argument("--limit", type=int, default=20)
    h.add_argument("--out", default="output")
    h.set_defaults(func=cmd_history)

    ref = sub.add_parser("reference", help="packaged subject reference (cues + proportions + recipe)")
    ref.add_argument("subject", nargs="?", help="subject to look up (owl, cat, vase…); omit to list all")
    ref.add_argument("--style", default="clean")
    ref.set_defaults(func=cmd_reference)

    st = sub.add_parser("styles", help="list artistic styles or show one's parameters")
    st.add_argument("name", nargs="?", help="style to show; omit to list all")
    st.set_defaults(func=cmd_styles)

    pl = sub.add_parser("plan", help="create / show / validate a design plan (the base design)")
    pl.add_argument("action", choices=["new", "show", "validate", "brief"])
    pl.add_argument("file", nargs="?", help="design.json path (for show/validate/brief)")
    pl.add_argument("--subject", help="subject for 'new'")
    pl.add_argument("--name")
    pl.add_argument("--style", default="clean")
    pl.add_argument("--category", default="organic")
    pl.add_argument("--prompt", default="")
    pl.add_argument("--height", type=float)
    pl.add_argument("--wall", type=float, default=2.0)
    pl.add_argument("--profile", default="fdm_0.4")
    pl.add_argument("--color")
    pl.add_argument("--out", help="output path for 'new'")
    pl.set_defaults(func=cmd_plan)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
