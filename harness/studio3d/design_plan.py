"""studio3d.design_plan — the design plan: a project's regenerable source of truth.

A *design plan* (`design.json`) is the structured output of a "Grill-me" design
session (text + reference images → a complete spec). It captures subject, style,
dimensions, wall thickness, colors, characteristics, unique details, reference
images, and a parts breakdown (schema: ``data/schema/design-plan.schema.json``).

It is the BASE DESIGN: the agent authors a DSL script FROM the plan; the user tweaks
a field (e.g. ``style: cartoonish`` → ``low-poly``, or ``dimensions_mm.height``) and
regenerates. The plan is versioned alongside the model bundle and committed to the
design history, so the whole design — not just the mesh — is recoverable.
"""
from __future__ import annotations

import json
import os
from typing import Any

from .spec import ModelSpec, slugify

_SCHEMA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "schema", "design-plan.schema.json")


def schema() -> dict:
    with open(_SCHEMA, "r", encoding="utf-8") as f:
        return json.load(f)


class DesignPlan:
    """Dict-backed wrapper over a validated design plan."""

    def __init__(self, data: dict):
        self.data = data

    # ---- construction -------------------------------------------------
    @classmethod
    def new(cls, subject: str, *, name: str | None = None, style: str = "clean",
            category: str = "organic", prompt: str = "",
            dimensions_mm: dict | None = None, wall_thickness_mm: float = 2.0,
            printer_profile: str = "fdm_0.4", colors: list | None = None,
            characteristics: list | None = None, unique_details: list | None = None,
            reference_images: list | None = None, parts: list | None = None,
            notes: str = "") -> "DesignPlan":
        nm = name or slugify(subject)
        data = {
            "schema_version": 3,
            "id": nm,
            "name": nm,
            "revision": 1,
            "subject": subject,
            "prompt": prompt or subject,
            "style": style,
            "category": category,
            "dimensions_mm": dimensions_mm or {"height": 60.0},
            "wall_thickness_mm": float(wall_thickness_mm),
            "printer_profile": printer_profile,
            "colors": colors or [],
            "characteristics": characteristics or [],
            "unique_details": unique_details or [],
            "reference_images": reference_images or [],
            "parts": parts or [],
            "notes": notes,
        }
        return cls(data)

    @classmethod
    def load(cls, path: str) -> "DesignPlan":
        with open(path, "r", encoding="utf-8") as f:
            return cls(json.load(f))

    def save(self, path: str) -> str:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)
        return path

    # ---- validation ---------------------------------------------------
    def validate(self) -> list[str]:
        """Return a list of validation errors ([] if valid). Uses jsonschema when
        available; otherwise a minimal required-field check."""
        errors: list[str] = []
        try:
            import jsonschema
            v = jsonschema.Draft202012Validator(schema())
            for e in sorted(v.iter_errors(self.data), key=lambda e: e.path):
                loc = "/".join(str(p) for p in e.path) or "(root)"
                errors.append(f"{loc}: {e.message}")
        except ImportError:
            for req in ("schema_version", "subject", "style", "category", "dimensions_mm"):
                if req not in self.data:
                    errors.append(f"(root): missing required '{req}'")
        return errors

    # ---- accessors ----------------------------------------------------
    @property
    def name(self) -> str:
        return self.data.get("id") or slugify(self.data.get("subject", "model"))

    @property
    def primary_color(self) -> str | None:
        cols = self.data.get("colors") or []
        if cols:
            hx = cols[0].get("hex", "")
            return hx if hx.startswith("#") else f"#{hx}"
        return None

    def target_size(self) -> list:
        d = self.data.get("dimensions_mm", {})
        return [float(d.get("width", 0) or 0), float(d.get("depth", 0) or 0), float(d.get("height", 0) or 0)]

    # ---- bridge to fabrication ---------------------------------------
    def to_spec(self, script: str | None = None) -> ModelSpec:
        cat = self.data.get("category", "organic")
        return ModelSpec(
            prompt=self.data.get("prompt", self.data.get("subject", "model")),
            name=self.name,
            description=self.data.get("notes", ""),
            category=cat if cat in ("mechanical", "functional", "organic", "decorative", "hybrid") else "organic",
            style=self.data.get("style", "clean"),
            engine="csg",
            script=script,
            target_size_mm=self.target_size(),
            printer_profile=self.data.get("printer_profile", "fdm_0.4"),
            material=self.data.get("material", "PLA"),
            color=self.primary_color,
            multicolor=bool(self.data.get("multicolor", False)),
            reference_images=self.data.get("reference_images", []),
            notes=self.data.get("notes", ""),
        )

    def brief(self) -> dict:
        """Reference-grounded brief (subject cues + style params) for the agent."""
        from .library import design_brief
        return design_brief(self.data.get("subject"), self.data.get("style"))

    def bump_revision(self):
        self.data["revision"] = int(self.data.get("revision", 1)) + 1
