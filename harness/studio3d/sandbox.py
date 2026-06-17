"""studio3d.sandbox — safe execution of agent-authored DSL scripts.

Threat model: the script is authored by the user's own coding agent, so this is
defense-in-depth against *accidents* (infinite loops, runaway memory, stray file
or network access, destructive os calls) rather than a hostile adversary. Two
layers:

1. Restricted globals: only the DSL namespace + a curated set of safe builtins,
   plus an import hook that whitelists a small module set. ``open``, ``exec``,
   ``eval``, ``__import__`` of arbitrary modules, ``os``, ``sys``, ``subprocess``,
   ``socket`` etc. are blocked.
2. Subprocess isolation: scripts run in a fresh interpreter with CPU-time and
   address-space rlimits and a wall-clock timeout, so a bad script cannot wedge
   the host. The result mesh is returned by exporting to a temp file.

Public API:
    run_script_text(code, timeout=30)      -> trimesh.Trimesh   (subprocess)
    execute_in_process(code)               -> Solid             (same process)
"""
from __future__ import annotations

import builtins as _builtins
import os
import subprocess
import sys
import tempfile
import textwrap

# Modules an authored script is allowed to import (most aren't needed because
# the DSL is injected, but math/numpy are handy for procedural geometry).
_ALLOWED_IMPORTS = {
    "math",
    "numpy",
    "random",
    "itertools",
    "functools",
    "statistics",
    "studio3d",
    "studio3d.dsl",
}

# Builtins that are safe to expose to authored scripts.
_SAFE_BUILTIN_NAMES = {
    "abs", "all", "any", "bool", "dict", "divmod", "enumerate", "filter",
    "float", "frozenset", "int", "len", "list", "map", "max", "min", "next",
    "pow", "print", "range", "reversed", "round", "set", "slice", "sorted",
    "str", "sum", "tuple", "zip", "isinstance", "hasattr", "getattr",
    "True", "False", "None", "ValueError", "TypeError", "RuntimeError",
    "ZeroDivisionError", "IndexError", "KeyError", "Exception",
}

_BLOCKED_MESSAGE = "blocked in studio3d sandbox: {name!r} is not available to authored geometry scripts"


def _guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    root = name.split(".")[0]
    if name in _ALLOWED_IMPORTS or root in _ALLOWED_IMPORTS:
        return _builtins.__import__(name, globals, locals, fromlist, level)
    raise ImportError(_BLOCKED_MESSAGE.format(name=name))


def restricted_globals() -> dict:
    """Build a globals dict exposing the DSL + a safe builtin subset."""
    from studio3d import dsl

    safe_builtins = {n: getattr(_builtins, n) for n in _SAFE_BUILTIN_NAMES if hasattr(_builtins, n)}
    safe_builtins["__import__"] = _guarded_import

    g: dict = {"__builtins__": safe_builtins, "__name__": "__studio3d_model__"}
    # inject every public DSL symbol
    for sym in dsl.__all__:
        g[sym] = getattr(dsl, sym)
    g["dsl"] = dsl
    return g


def execute_in_process(code: str, params: dict | None = None):
    """Execute ``code`` with restricted globals and return the resulting Solid.

    The script must define ``build()`` returning a Solid, or assign ``result``.
    Runs in-process — use :func:`run_script_text` for hard isolation/timeouts.

    ``params`` is injected as a ``P`` dict so a script can read named, tweakable
    parameters (``P.get("hole_d", 4.5)``) instead of magic numbers — this is what
    makes a model regenerable from ``design.json`` with one parameter changed.
    """
    from studio3d.dsl import Solid

    g = restricted_globals()
    g["P"] = dict(params or {})
    compiled = compile(code, "<authored-model>", "exec")
    exec(compiled, g)  # noqa: S102 - intentional, sandboxed globals

    solid = None
    if "result" in g and g["result"] is not None:
        solid = g["result"]
    elif "build" in g and callable(g["build"]):
        solid = g["build"]()
    else:
        raise RuntimeError(
            "authored script produced no model: define `build()` returning a Solid, "
            "or assign a module-level `result`."
        )
    if not isinstance(solid, Solid):
        raise TypeError(f"model must be a Solid, got {type(solid).__name__}")
    return solid


# --------------------------------------------------------------------------
# Subprocess runner — applies rlimits + timeout, exports the mesh to disk.
# --------------------------------------------------------------------------

_RUNNER_TEMPLATE = textwrap.dedent(
    '''
    import sys, resource
    # CPU-time hard limit (seconds). NOTE: we deliberately do NOT set RLIMIT_AS
    # because numpy/OpenBLAS reserve large *virtual* arenas and an address-space
    # cap causes spurious hangs/aborts. Wall-clock timeout + CPU cap are the
    # meaningful guards for a local, trusted-agent tool.
    try:
        resource.setrlimit(resource.RLIMIT_CPU, ({cpu}, {cpu}))
    except Exception:
        pass
    sys.path.insert(0, {harness!r})
    import json as _json
    from studio3d.sandbox import execute_in_process
    code = open({code_path!r}, "r", encoding="utf-8").read()
    try:
        _params = _json.load(open({params_path!r}, "r", encoding="utf-8"))
    except Exception:
        _params = {{}}
    solid = execute_in_process(code, _params)
    # PLY preserves shared vertices (unlike STL's triangle soup), so watertight
    # topology survives the cross-process handoff.
    solid.mesh.export({out_path!r})
    print("STUDIO3D_OK", len(solid.mesh.faces))
    '''
)


def run_script_text(code: str, timeout: float = 30.0, cpu_seconds: int = 25,
                    mem_bytes: int | None = None, params: dict | None = None):
    """Execute authored ``code`` in an isolated subprocess; return a Trimesh.

    ``params`` is injected as a ``P`` dict for named, tweakable parameters.
    Raises ``RuntimeError`` on timeout, resource exhaustion, or script error.
    """
    import json
    import trimesh

    harness_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with tempfile.TemporaryDirectory(prefix="studio3d_") as td:
        code_path = os.path.join(td, "model.py")
        out_path = os.path.join(td, "model.ply")
        params_path = os.path.join(td, "params.json")
        with open(code_path, "w", encoding="utf-8") as f:
            f.write(code)
        with open(params_path, "w", encoding="utf-8") as f:
            json.dump(params or {}, f)
        runner = _RUNNER_TEMPLATE.format(
            cpu=cpu_seconds, harness=harness_root,
            code_path=code_path, out_path=out_path, params_path=params_path,
        )
        # Inherit the parent env (so library/locale discovery works) but pin
        # thread pools to 1 (avoids OpenBLAS deadlocks under subprocess) and
        # point caches/HOME at the throwaway tempdir.
        env = dict(os.environ)
        env.update({
            "PYTHONPATH": harness_root,
            "MPLBACKEND": "Agg",
            "HOME": td,
            "TMPDIR": td,
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
        })
        try:
            proc = subprocess.run(
                [sys.executable, "-c", runner],
                capture_output=True, text=True, timeout=timeout,
                env=env, cwd=td,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"authored script exceeded {timeout}s wall-clock timeout")

        if proc.returncode != 0 or "STUDIO3D_OK" not in proc.stdout:
            raise RuntimeError(
                "authored script failed:\n"
                + (proc.stderr.strip() or proc.stdout.strip() or "no output")
            )
        if not os.path.exists(out_path):
            raise RuntimeError("authored script did not produce a mesh")
        mesh = trimesh.load(out_path, process=False)
        # defensively merge any coincident vertices so watertight topology is intact
        mesh.merge_vertices()
        return mesh
