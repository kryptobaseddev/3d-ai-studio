"""studio3d.certify — the Print-Readiness Certificate.

A bundle artifact that records the full, auditable provenance chain from prompt to
buildable part: prompt → deterministic CSG script (hashed) → render hashes →
D1-D4 verdicts → real slice result → human approval slot. This is the moat over a
non-deterministic cloud generator: an engineering/maker buyer can reproduce and
audit exactly how a part was produced (relevant under the EU Product Liability
Directive, where the approving professional bears responsibility).
"""
from __future__ import annotations

import hashlib
import json
import os


def _sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _sha256_file(path: str) -> str | None:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def build_certificate(spec, report, bundle_dir: str, provenance: dict | None = None,
                      timestamp: str | None = None) -> dict:
    """Assemble the certificate dict for one bundle. ``timestamp`` is passed in
    (callers stamp wall-clock time) so this stays deterministic/testable."""
    dims = report.dimensions if hasattr(report, "dimensions") else report.get("dimensions", {})
    metrics = report.metrics if hasattr(report, "metrics") else report.get("metrics", {})
    d2 = dims.get("D2_slicer_pass", {})

    file_hashes = {}
    for fn in ("model.stl", "model.3mf", "model.glb", "model.py"):
        p = os.path.join(bundle_dir, fn)
        if os.path.exists(p):
            file_hashes[fn] = _sha256_file(p)

    return {
        "certificate_version": 1,
        "generator": "studio3d",
        "timestamp": timestamp,
        "prompt": getattr(spec, "prompt", None),
        "engine": getattr(spec, "resolved_engine", None),
        "deterministic": getattr(spec, "resolved_engine", None) == "csg",
        "script_sha256": _sha256_text(getattr(spec, "script", "") or ""),
        "parameters": getattr(spec, "parameters", {}) or {},
        "printer_profile": getattr(spec, "printer_profile", None),
        "material": getattr(spec, "material", None),
        "file_sha256": file_hashes,
        "print_ready": bool(getattr(report, "print_ready", False)),
        "score": int(getattr(report, "score", 0)),
        "dimensions": {
            "D1_mesh_integrity": dims.get("D1_mesh_integrity", {}).get("pass"),
            "D2_slicer_pass": {"pass": d2.get("pass"), "method": d2.get("method"),
                               "slicer": d2.get("slicer"), "print_time": d2.get("print_time"),
                               "filament_g": d2.get("filament_g")},
            "D3_print_geometry": dims.get("D3_print_geometry", {}).get("pass"),
            "D4_workflow": dims.get("D4_workflow", {}).get("pass"),
        },
        "kernel_metrics": metrics.get("kernel_metrics"),
        "provenance": provenance or {},
        "human_approved": None,   # set true/false when a human signs off
        "human_note": None,
    }


def write_certificate(spec, report, bundle_dir: str, provenance: dict | None = None,
                      timestamp: str | None = None) -> str:
    cert = build_certificate(spec, report, bundle_dir, provenance, timestamp)
    path = os.path.join(bundle_dir, "certificate.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cert, f, indent=2)
    return path
