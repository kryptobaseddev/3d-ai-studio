"""studio3d.spec — the ModelSpec contract.

A ModelSpec is the structured intermediate representation an agent produces from
a natural-language request (+ optional reference images). It is the single
hand-off between *understanding* (done by the agent) and *fabrication* (done by
the harness). It is serialized to ``spec.json`` in every output bundle so a run
is fully reproducible and auditable.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from typing import Any


# ---- printer / process profiles -------------------------------------------
# Each profile carries the Dimension-3 (print-geometry) thresholds in mm.
PRINTER_PROFILES: dict[str, dict[str, float | str]] = {
    "fdm_0.4": {
        "label": "FDM, 0.4mm nozzle (Bambu X1C / P1S default)",
        "nozzle": 0.4,
        "min_wall": 0.8,          # 2x nozzle — reliable vertical wall
        "min_feature": 0.4,
        "overhang_deg": 50.0,     # steeper than this needs support
        "min_hole": 2.0,
        "clearance": 0.2,         # mating-part gap
        "process": "fdm",
    },
    "fdm_0.2": {
        "label": "FDM, 0.2mm nozzle (fine detail)",
        "nozzle": 0.2,
        "min_wall": 0.4,
        "min_feature": 0.2,
        "overhang_deg": 50.0,
        "min_hole": 1.0,
        "clearance": 0.15,
        "process": "fdm",
    },
    "resin": {
        "label": "MSLA/DLP resin (Elegoo Saturn / Mars)",
        "nozzle": 0.05,
        "min_wall": 0.3,
        "min_feature": 0.1,
        "overhang_deg": 45.0,
        "min_hole": 0.5,
        "clearance": 0.1,
        "process": "resin",
    },
}

DEFAULT_PROFILE = "fdm_0.4"

# routing categories
CATEGORIES = ("mechanical", "functional", "organic", "decorative", "hybrid")
# generation engines
ENGINES = ("csg", "generative", "auto")


def slugify(text: str, maxlen: int = 48) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (text or "model").strip().lower()).strip("-")
    return (s or "model")[:maxlen]


@dataclass
class ModelSpec:
    """Structured description of a model to fabricate.

    The agent fills this in from the user's prompt + images. ``engine`` selects
    the fabrication path; ``csg`` is the default local, manifold-by-construction
    path and ``generative`` routes to a hosted text/image-to-3D backend.
    """

    prompt: str
    name: str = ""
    description: str = ""
    category: str = "mechanical"
    style: str = "clean"      # artistic style: clean|realistic|cartoonish|chibi|anime|low-poly|geometric
    engine: str = "auto"

    # geometry intent (agent-authored CSG script lives here when engine==csg)
    script: str | None = None
    # parameters surfaced for the UI / future re-parameterization
    parameters: dict[str, Any] = field(default_factory=dict)

    # target physical envelope (mm); 0 means "let the model decide"
    target_size_mm: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])

    # print target
    printer_profile: str = DEFAULT_PROFILE
    material: str = "PLA"
    multicolor: bool = False
    color: str | None = None          # hex like "#3a86ff"

    # inputs
    reference_images: list[str] = field(default_factory=list)

    # output preferences
    formats: list[str] = field(default_factory=lambda: ["stl", "3mf", "glb"])

    # provenance
    notes: str = ""

    def __post_init__(self):
        if not self.name:
            self.name = slugify(self.prompt)
        if self.category not in CATEGORIES:
            raise ValueError(f"category must be one of {CATEGORIES}, got {self.category!r}")
        if self.engine not in ENGINES:
            raise ValueError(f"engine must be one of {ENGINES}, got {self.engine!r}")
        if self.printer_profile not in PRINTER_PROFILES:
            raise ValueError(
                f"printer_profile must be one of {list(PRINTER_PROFILES)}, got {self.printer_profile!r}"
            )

    @property
    def profile(self) -> dict[str, float | str]:
        return PRINTER_PROFILES[self.printer_profile]

    @property
    def resolved_engine(self) -> str:
        """Resolve ``auto`` to a concrete engine from the category."""
        if self.engine != "auto":
            return self.engine
        if self.category in ("organic",):
            return "generative"
        return "csg"

    @property
    def slug(self) -> str:
        return slugify(self.name)

    # ---- serialization -------------------------------------------------
    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, d: dict) -> "ModelSpec":
        allowed = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in allowed})

    @classmethod
    def from_json(cls, s: str) -> "ModelSpec":
        return cls.from_dict(json.loads(s))

    @classmethod
    def load(cls, path: str) -> "ModelSpec":
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_json(f.read())
