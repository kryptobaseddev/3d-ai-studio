"""studio3d — the agentic text/image-to-3D-print harness.

A local-first, manifold-by-construction 3D modeling engine that turns a
structured ModelSpec (authored by a Claude Code agent) into print-ready files.

Subpackages / modules:
    dsl       - the CSG geometry DSL the agent writes against
    sandbox   - safe execution of authored geometry scripts
    validate  - print-readiness validation (Meshy 4-dimension benchmark)
    exporters - STL / 3MF / GLB / thumbnail / manifest emission
    spec      - the ModelSpec contract
    generative- optional hosted text/image-to-3D backend (with mock fallback)
    cli       - the `studio3d` command-line entrypoint
"""
__version__ = "0.3.0"
