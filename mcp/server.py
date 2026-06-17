#!/usr/bin/env python3
"""3d-studio MCP registry server — on-demand skills/agents + studio3d tools.

Why this exists: native plugin skills/agents inject their name+description into
EVERY session's system prompt (cost scales with count) and add /menu entries. This
server exposes the plugin's NON-entry-point skills and specialist agents as a
*registry* loaded on demand, so the always-on context cost is ~0 (just a few tool
names) while the catalog can grow freely. The user-facing entry points (model3d,
grill-me) stay native so they auto-trigger and appear in the / menu.

Zero dependencies (stdlib only) → runs under system python3. stdout carries ONLY
JSON-RPC; all logging goes to stderr.

Tools:
  list_skills / load_skill(id)   — registry/skills/<id>/SKILL.md  (reference knowledge)
  list_agents / load_agent(id)   — registry/agents/<id>.md        (specialist system prompts)
  studio3d_reference(subject,style?) — packaged subject brief (cues, proportions, recipe)
  studio3d_styles(name?)         — artistic style params
  studio3d_subjects              — list reference subjects
Resources mirror the registry as skill://<id> and agent://<id>.
"""
import json
import os
import re
import subprocess
import sys

ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REG_SKILLS = os.path.join(ROOT, "registry", "skills")
REG_AGENTS = os.path.join(ROOT, "registry", "agents")
STUDIO3D = os.path.join(ROOT, "bin", "studio3d")
PROTOCOL = "2024-11-05"


def log(*a):
    print("[3d-studio-mcp]", *a, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- registry IO

def _frontmatter(text: str) -> dict:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    fm = {}
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                fm[k.strip()] = v.strip()
    return fm


def list_skills() -> list[dict]:
    out = []
    if os.path.isdir(REG_SKILLS):
        for sid in sorted(os.listdir(REG_SKILLS)):
            p = os.path.join(REG_SKILLS, sid, "SKILL.md")
            if os.path.exists(p):
                fm = _frontmatter(open(p, encoding="utf-8").read())
                out.append({"id": sid, "name": fm.get("name", sid), "description": fm.get("description", "")})
    return out


def list_agents() -> list[dict]:
    out = []
    if os.path.isdir(REG_AGENTS):
        for fn in sorted(os.listdir(REG_AGENTS)):
            if fn.endswith(".md"):
                fm = _frontmatter(open(os.path.join(REG_AGENTS, fn), encoding="utf-8").read())
                aid = fn[:-3]
                out.append({"id": aid, "name": fm.get("name", aid), "description": fm.get("description", "")})
    return out


def load_skill(sid: str) -> str:
    p = os.path.join(REG_SKILLS, os.path.basename(sid), "SKILL.md")
    if not os.path.exists(p):
        raise FileNotFoundError(f"no skill {sid!r}; available: {[s['id'] for s in list_skills()]}")
    return open(p, encoding="utf-8").read()


def load_agent(aid: str) -> str:
    p = os.path.join(REG_AGENTS, os.path.basename(aid) + ".md")
    if not os.path.exists(p):
        raise FileNotFoundError(f"no agent {aid!r}; available: {[a['id'] for a in list_agents()]}")
    return open(p, encoding="utf-8").read()


def _studio3d(*args: str) -> str:
    try:
        # invoke via `bash` so it works even if the exec bit is lost on checkout
        proc = subprocess.run(["bash", STUDIO3D, *args], capture_output=True, text=True, timeout=120)
        return proc.stdout or proc.stderr
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"})


# ---------------------------------------------------------------- tool defs

TOOLS = [
    {"name": "list_skills", "description": "List the on-demand reference skills (print-readiness rules, CSG DSL authoring guide, 3D-modeling foundations, printer-setup). Returns id + description; call load_skill to read one.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "load_skill", "description": "Load the full body of a registry skill by id (e.g. 'print-readiness', 'cad-authoring').", "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}},
    {"name": "list_agents", "description": "List the specialist subagents (spec-analyst, cad-author, mesh-validator, design-critic). Returns id + description; call load_agent to get one's system prompt, then dispatch it with the Task/Agent tool.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "load_agent", "description": "Load a specialist agent's full system prompt by id, to spawn it as a subagent.", "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}},
    {"name": "studio3d_reference", "description": "Packaged design reference for a subject (silhouette cues, head-unit-H proportions, CSG recipe) merged with a style — author organic/figurative models by proportion from this.", "inputSchema": {"type": "object", "properties": {"subject": {"type": "string"}, "style": {"type": "string"}}, "required": ["subject"]}},
    {"name": "studio3d_styles", "description": "List artistic styles or show one style's numeric geometry params (head:body ratio, eye-size multiplier, facet level…).", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}}}},
    {"name": "studio3d_subjects", "description": "List the subjects the reference library covers.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "studio3d_kb", "description": "Query the local DFAM/CSG domain knowledge base (design-for-printing numerics, CSG error→fix pairs, proven recipes) before authoring geometry — grounds the model in documented rules.", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "k": {"type": "integer"}}, "required": ["query"]}},
    {"name": "studio3d_build", "description": "Run the full local CSG pipeline from a DSL script: sandbox-execute → validate (D1-D4, real slice if a slicer is installed) → export STL/3MF/GLB + parametric source + Print-Readiness Certificate into output/<slug>/. Returns the bundle path, print_ready, score and kernel metrics.", "inputSchema": {"type": "object", "properties": {"script": {"type": "string", "description": "studio3d DSL source defining build() or result"}, "name": {"type": "string"}, "prompt": {"type": "string"}, "category": {"type": "string"}, "color": {"type": "string"}, "out": {"type": "string"}}, "required": ["script", "name"]}},
    {"name": "studio3d_validate", "description": "Validate an existing mesh file against the 4-dimension print-readiness benchmark (D1 integrity, D2 slicer, D3 geometry, D4 workflow) + kernel metrics. Pass do_slice to run a real headless slice.", "inputSchema": {"type": "object", "properties": {"mesh": {"type": "string"}, "do_slice": {"type": "boolean"}}, "required": ["mesh"]}},
    {"name": "studio3d_muse", "description": "Run the internal MUSE-style print-readiness benchmark and return the score across the 5 cascade dimensions (syntax/geometry/functionality/manufacturability/assemblability).", "inputSchema": {"type": "object", "properties": {}}},
]


def call_tool(name: str, args: dict) -> str:
    if name == "list_skills":
        return json.dumps(list_skills(), indent=2)
    if name == "load_skill":
        return load_skill(args["id"])
    if name == "list_agents":
        return json.dumps(list_agents(), indent=2)
    if name == "load_agent":
        return load_agent(args["id"])
    if name == "studio3d_reference":
        a = ["reference", args["subject"]]
        if args.get("style"):
            a += ["--style", args["style"]]
        return _studio3d(*a)
    if name == "studio3d_styles":
        return _studio3d("styles", *( [args["name"]] if args.get("name") else [] ))
    if name == "studio3d_subjects":
        return _studio3d("reference")
    if name == "studio3d_kb":
        return _studio3d("kb", args["query"], "-k", str(args.get("k", 4)))
    if name == "studio3d_build":
        a = ["gen-script", "--code", args["script"], "--name", args["name"]]
        if args.get("prompt"):
            a += ["--prompt", args["prompt"]]
        if args.get("category"):
            a += ["--category", args["category"]]
        if args.get("color"):
            a += ["--color", args["color"]]
        a += ["--out", args.get("out", "output")]
        return _studio3d(*a)
    if name == "studio3d_validate":
        a = ["validate", args["mesh"]]
        if args.get("do_slice"):
            a += ["--slice"]
        return _studio3d(*a)
    if name == "studio3d_muse":
        return _studio3d("muse")
    raise ValueError(f"unknown tool {name!r}")


# ---------------------------------------------------------------- resources

def list_resources() -> list[dict]:
    res = []
    for s in list_skills():
        res.append({"uri": f"skill://{s['id']}", "name": s["name"], "description": s["description"], "mimeType": "text/markdown"})
    for a in list_agents():
        res.append({"uri": f"agent://{a['id']}", "name": a["name"], "description": a["description"], "mimeType": "text/markdown"})
    return res


def read_resource(uri: str) -> str:
    if uri.startswith("skill://"):
        return load_skill(uri[len("skill://"):])
    if uri.startswith("agent://"):
        return load_agent(uri[len("agent://"):])
    raise FileNotFoundError(uri)


# ---------------------------------------------------------------- JSON-RPC loop

def respond(rid, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": rid}
    if error is not None:
        msg["error"] = error
    else:
        msg["result"] = result
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def main():
    log(f"starting; registry root={ROOT}")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception as e:
            log("bad json:", e)
            continue
        method = req.get("method")
        rid = req.get("id")
        try:
            if method == "initialize":
                respond(rid, {
                    "protocolVersion": PROTOCOL,
                    "capabilities": {"tools": {}, "resources": {}},
                    "serverInfo": {"name": "3d-studio-registry", "version": "0.4.0"},
                    "instructions": (
                        "3d-studio on-demand registry + pipeline. The /model3d and /grill-me skills are native; "
                        "everything else loads here to keep always-on cost ~0. Pull capabilities just-in-time: "
                        "list_skills/load_skill for reference knowledge (print-readiness rules, cad-authoring DSL "
                        "guide, 3d-modeling foundations, printer-setup); list_agents/load_agent to get a specialist's "
                        "system prompt, then spawn it with your Task/Agent tool. studio3d_reference/styles/subjects "
                        "give the packaged design grounding for authoring by proportion. studio3d_kb grounds the "
                        "author in DFAM/CSG rules; studio3d_build runs the full local CSG pipeline (build→validate→"
                        "real-slice→export+certificate); studio3d_validate checks any mesh; studio3d_muse benchmarks."
                    ),
                })
            elif method in ("notifications/initialized", "initialized"):
                continue  # notification, no response
            elif method == "tools/list":
                respond(rid, {"tools": TOOLS})
            elif method == "tools/call":
                params = req.get("params", {})
                text = call_tool(params.get("name"), params.get("arguments", {}) or {})
                respond(rid, {"content": [{"type": "text", "text": text}]})
            elif method == "resources/list":
                respond(rid, {"resources": list_resources()})
            elif method == "resources/read":
                uri = req.get("params", {}).get("uri", "")
                respond(rid, {"contents": [{"uri": uri, "mimeType": "text/markdown", "text": read_resource(uri)}]})
            elif method == "ping":
                respond(rid, {})
            else:
                if rid is not None:
                    respond(rid, error={"code": -32601, "message": f"method not found: {method}"})
        except Exception as e:
            log("error handling", method, ":", e)
            if rid is not None:
                respond(rid, error={"code": -32000, "message": f"{type(e).__name__}: {e}"})


if __name__ == "__main__":
    main()
