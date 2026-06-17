"""studio3d.generative — optional hosted text/image-to-3D backend.

The local CSG engine is the default. For *organic* shapes (characters, animals,
busts) the agent can route to a generative backend. This module abstracts that
behind a single ``generate(spec)`` call with graceful degradation:

    backend = $STUDIO3D_GEN_BACKEND       (meshy | mock; default: auto)
    auto -> meshy if MESHY_API_KEY is set, else mock

The ``mock`` backend produces a deterministic placeholder solid so the entire
pipeline (validate -> export -> UI) runs end-to-end with NO credentials — useful
for the POC, CI, and offline development. The ``meshy`` backend implements the
documented async task model (create -> poll -> download GLB).
"""
from __future__ import annotations

import os
import time
import urllib.request
import urllib.error
import json
import tempfile

import numpy as np
import trimesh

MESHY_BASE = "https://api.meshy.ai"
# documented public test key — returns mock responses, consumes no credits
MESHY_TEST_KEY = "msy_dummy_api_key_for_test_mode_12345678"


def select_backend() -> str:
    explicit = os.environ.get("STUDIO3D_GEN_BACKEND", "auto").lower()
    if explicit in ("meshy", "mock"):
        return explicit
    return "meshy" if os.environ.get("MESHY_API_KEY") else "mock"


def generate(spec, timeout: float = 300.0) -> tuple[trimesh.Trimesh, dict]:
    """Generate a mesh for ``spec`` via the selected backend.

    Returns (mesh, info). ``info`` records the backend and any provenance.
    """
    backend = select_backend()
    if backend == "meshy":
        try:
            mesh, info = _generate_meshy(spec, timeout=timeout)
        except Exception as e:
            # never hard-fail the pipeline — fall back to mock with a note
            mesh, info = _generate_mock(spec)
            info["meshy_error"] = f"{type(e).__name__}: {e}"
            info["fell_back"] = True
    else:
        mesh, info = _generate_mock(spec)
    # ALWAYS heal generative output toward a watertight 2-manifold solid. No
    # generative model is print-ready by default (it ships triangle soup); this
    # is the mandatory gate that makes the hybrid path deliver a buildable part.
    try:
        from .validate import heal
        info["heal"] = heal(mesh)
    except Exception as e:
        info["heal_error"] = f"{type(e).__name__}: {e}"
    return mesh, info


# ----------------------------------------------------------------------
# Mock backend — deterministic placeholder organic-ish solid
# ----------------------------------------------------------------------

def _generate_mock(spec) -> tuple[trimesh.Trimesh, dict]:
    """A deterministic stand-in: a smoothed, lumpy capsule sized to the spec.
    Always watertight/manifold so downstream validation behaves realistically."""
    target = getattr(spec, "target_size_mm", None) or [0, 0, 0]
    h = max([float(t) for t in target] + [40.0])
    body = trimesh.creation.capsule(height=h * 0.6, radius=h * 0.22, count=[32, 32])
    head = trimesh.creation.icosphere(subdivisions=3, radius=h * 0.18)
    head.apply_translation([0, 0, h * 0.6 + h * 0.05])
    mesh = trimesh.boolean.union([body, head])
    mesh.merge_vertices()
    info = {
        "backend": "mock",
        "note": "placeholder geometry — set MESHY_API_KEY or STUDIO3D_GEN_BACKEND=meshy "
                "for real generative output",
    }
    return mesh, info


# ----------------------------------------------------------------------
# Meshy backend — async task model (create -> poll -> download)
# ----------------------------------------------------------------------

def _meshy_key() -> str:
    return os.environ.get("MESHY_API_KEY", MESHY_TEST_KEY)


def _http(method: str, url: str, key: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def _generate_meshy(spec, timeout: float = 300.0) -> tuple[trimesh.Trimesh, dict]:
    """Text-to-3D via Meshy v2 async tasks. Falls through to image-to-3D when
    reference images are present (first image only, as a data URL is not used here
    — Meshy expects a public/base64 image URI; left for production extension)."""
    key = _meshy_key()
    # create task
    create = _http("POST", f"{MESHY_BASE}/openapi/v2/text-to-3d", key, {
        "mode": "preview",
        "prompt": spec.prompt,
        "art_style": "realistic",
        "should_remesh": True,
    })
    task_id = create.get("result") or create.get("id")
    if not task_id:
        raise RuntimeError(f"meshy: no task id in response: {create}")

    # poll
    deadline = time.monotonic() + timeout
    status = {}
    while time.monotonic() < deadline:
        status = _http("GET", f"{MESHY_BASE}/openapi/v2/text-to-3d/{task_id}", key)
        st = status.get("status")
        if st == "SUCCEEDED":
            break
        if st in ("FAILED", "CANCELED", "EXPIRED"):
            raise RuntimeError(f"meshy task {st}: {status.get('task_error')}")
        time.sleep(5)
    else:
        raise RuntimeError("meshy: polling timed out")

    urls = status.get("model_urls", {}) or {}
    glb_url = urls.get("glb") or urls.get("obj") or urls.get("stl")
    if not glb_url:
        raise RuntimeError(f"meshy: no model url in {status}")

    # download + load
    with tempfile.NamedTemporaryFile(suffix=".glb", delete=False) as tf:
        with urllib.request.urlopen(glb_url, timeout=120) as r:
            tf.write(r.read())
        path = tf.name
    loaded = trimesh.load(path, force="mesh")
    if isinstance(loaded, trimesh.Scene):
        loaded = trimesh.util.concatenate([g for g in loaded.geometry.values()])
    loaded.merge_vertices()
    info = {"backend": "meshy", "task_id": task_id, "model_url": glb_url,
            "test_mode": key == MESHY_TEST_KEY}
    return loaded, info
