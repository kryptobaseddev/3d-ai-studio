"""studio3d.library — packaged design knowledge: styles + subject references.

Two shipped JSON knowledge bases ground the agent so generated models are
recognizable and on-style instead of lumpy guesses:

- ``data/styles.json``           — artistic styles (realistic / cartoonish / anime /
  chibi / low-poly / geometric / stylized) as concrete geometry parameters
  (head:body ratio, eye-size multiplier, facet level, fillet treatment…).
- ``data/reference_library.json`` — 20 common subjects (owl, cat, dog, dragon, vase…)
  with the essential silhouette cues, numeric proportions (by head-unit H / total T),
  and a CSG construction recipe. This is what makes the owl look like an owl.

These are the "known references packaged with the plugin" — the agent looks up the
subject + style before authoring, and the design-critic scores the render against
the subject's silhouette cues.
"""
from __future__ import annotations

import json
import os

_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def _load(name: str) -> dict:
    with open(os.path.join(_DATA, name), "r", encoding="utf-8") as f:
        return json.load(f)


def load_styles() -> dict:
    return _load("styles.json")


def load_reference_library() -> dict:
    return _load("reference_library.json")


def get_style(name: str) -> dict | None:
    """Return a style's parameter dict (tolerant of name variants)."""
    styles = load_styles().get("styles", {})
    key = (name or "").strip().lower().replace("-", "_")
    if key in styles:
        return {"name": key, **styles[key]}
    # aliases
    alias = {"clean": "stylized_clean", "stylized": "stylized_clean", "lowpoly": "low_poly",
             "cartoon": "cartoonish", "realism": "realistic"}
    if key in alias and alias[key] in styles:
        return {"name": alias[key], **styles[alias[key]]}
    return None


def list_styles() -> list[str]:
    return list(load_styles().get("styles", {}).keys())


def get_reference(subject: str) -> dict | None:
    """Look up a subject's reference guide (silhouette cues, proportions, recipe).
    Matches on the subject token (e.g. 'a cute owl' -> 'owl')."""
    lib = load_reference_library()
    subjects = {k: v for k, v in lib.items() if not k.startswith("_")}
    s = (subject or "").lower()
    # direct + token containment
    for key in subjects:
        norm = key.replace("_", " ")
        if key == s or norm in s or s in norm or any(tok == key for tok in s.split()):
            return {"subject": key, **subjects[key]}
    # singular/plural-ish fallback
    for key in subjects:
        if key.rstrip("s") in s or s.rstrip("s") == key:
            return {"subject": key, **subjects[key]}
    return None


def list_subjects() -> list[str]:
    return [k for k in load_reference_library().keys() if not k.startswith("_")]


def design_brief(subject: str | None, style: str | None) -> dict:
    """Assemble the grounded brief the agent should follow: the subject's silhouette
    cues + proportions + recipe, merged with the chosen style's parameters. Returned
    to the agent so authoring is reference-grounded, not improvised."""
    ref = get_reference(subject) if subject else None
    sty = get_style(style or "clean")
    meta = load_reference_library().get("_meta", {})
    return {
        "subject": subject,
        "style": (sty or {}).get("name", style),
        "reference": ref,        # cues, proportions, csg_recipe, pitfalls
        "style_params": sty,     # head ratio, eye multiplier, facet level, fillets…
        "method": meta.get("universal_method"),
        "eye_rule": meta.get("eye_rule"),
        "print_constraints": meta.get("print_constraints"),
        "have_reference": ref is not None,
    }
