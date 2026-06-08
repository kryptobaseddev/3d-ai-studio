"""studio3d.profiles — printer database + user printer profiles (XDG, YAML).

Two layers:

1. **Printer DB** (`data/printers.json`, committed in-repo): make/model specs —
   build volume, nozzle, AMS/multicolor capacity, slicer quality presets. The
   maintained ground truth the agent reads to set a user up correctly.

2. **User profiles** (YAML, in the OS config dir): a user's actual printers —
   chosen model + AMS on/off + loaded filament colors. Multiple profiles, one
   active. Cross-platform via XDG:
     - Linux:   $XDG_CONFIG_HOME/studio3d  (default ~/.config/studio3d)
     - macOS:   ~/Library/Application Support/studio3d
     - Windows: %APPDATA%\studio3d

A `profiles.json` manifest tracks the active profile. The active profile drives
bed-fit validation, the process profile (nozzle → wall minimums), and AMS color
mapping for 3MF export — so generated files target the real printer.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field, asdict
from typing import Any

import yaml

from .spec import slugify, PRINTER_PROFILES

_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "printers.json")


# ---------------------------------------------------------------- XDG paths

def config_dir() -> str:
    """Cross-platform per-user config dir for studio3d."""
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    elif os.name == "nt":
        base = os.environ.get("APPDATA", os.path.expanduser("~\\AppData\\Roaming"))
    else:
        base = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    d = os.path.join(base, "studio3d")
    os.makedirs(os.path.join(d, "profiles"), exist_ok=True)
    return d


def _manifest_path() -> str:
    return os.path.join(config_dir(), "profiles.json")


def _profile_path(name: str) -> str:
    return os.path.join(config_dir(), "profiles", f"{slugify(name)}.yaml")


# ---------------------------------------------------------------- printer DB

def load_printer_db() -> dict:
    with open(_DATA, "r", encoding="utf-8") as f:
        return json.load(f)


def find_printers(query: str) -> list[dict]:
    """Fuzzy search the DB by make/model/slug. Empty query returns all."""
    db = load_printer_db()["printers"]
    if not query:
        return db
    q = query.lower().replace("-", " ")
    out = []
    for p in db:
        hay = f"{p['make']} {p['model']} {p['slug']}".lower().replace("-", " ")
        if all(tok in hay for tok in q.split()):
            out.append(p)
    return out


def get_printer(slug_or_query: str) -> dict | None:
    db = load_printer_db()["printers"]
    for p in db:
        if p["slug"] == slug_or_query:
            return p
    hits = find_printers(slug_or_query)
    return hits[0] if hits else None


def derive_process_profile(nozzle_mm: float, process: str) -> str:
    """Map a machine to one of the physics profiles in spec.PRINTER_PROFILES."""
    if process == "resin":
        return "resin"
    return "fdm_0.2" if nozzle_mm and nozzle_mm <= 0.25 else "fdm_0.4"


# ---------------------------------------------------------------- user profile

@dataclass
class Profile:
    name: str
    printer_slug: str
    make: str = ""
    model: str = ""
    process: str = "fdm"
    nozzle_mm: float = 0.4
    build_volume_mm: list = field(default_factory=lambda: [256, 256, 256])
    ams_enabled: bool = False
    max_colors: int = 1
    material: str = "PLA"
    filaments: list = field(default_factory=list)  # [{slot,color,name,material}]
    notes: str = ""

    @property
    def process_profile(self) -> str:
        return derive_process_profile(self.nozzle_mm, self.process)

    @property
    def multicolor_capable(self) -> bool:
        return bool(self.ams_enabled and self.max_colors > 1)

    @property
    def palette(self) -> list[str]:
        return [f.get("color") for f in self.filaments if f.get("color")]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_printer(cls, printer: dict, name: str | None = None,
                     ams_enabled: bool | None = None, colors: list[str] | None = None,
                     material: str | None = None) -> "Profile":
        ams = printer.get("ams", {})
        ams_on = ams.get("supported", False) if ams_enabled is None else ams_enabled
        filaments = []
        for i, c in enumerate(colors or []):
            filaments.append({"slot": i + 1, "color": c, "name": f"Filament {i+1}", "material": material or "PLA"})
        return cls(
            name=name or printer["slug"],
            printer_slug=printer["slug"],
            make=printer["make"],
            model=printer["model"],
            process=printer.get("process", "fdm"),
            nozzle_mm=printer.get("nozzle_mm", 0.4),
            build_volume_mm=printer.get("build_volume_mm", [256, 256, 256]),
            ams_enabled=bool(ams_on),
            max_colors=int(ams.get("max_colors", 1) or 1) if ams_on else 1,
            material=material or (printer.get("default_materials") or ["PLA"])[0],
            filaments=filaments,
            notes=printer.get("notes", "")[:200],
        )


def save_profile(profile: Profile, make_active: bool = True) -> str:
    path = _profile_path(profile.name)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(profile.to_dict(), f, sort_keys=False, allow_unicode=True)
    _register(profile.name, make_active)
    return path


def load_profile(name: str) -> Profile | None:
    path = _profile_path(name)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    allowed = set(Profile.__dataclass_fields__)  # type: ignore[attr-defined]
    return Profile(**{k: v for k, v in data.items() if k in allowed})


def list_profiles() -> list[str]:
    man = _load_manifest()
    return man.get("profiles", [])


def active_profile() -> Profile | None:
    man = _load_manifest()
    name = man.get("active")
    return load_profile(name) if name else None


def set_active(name: str) -> bool:
    if not os.path.exists(_profile_path(name)):
        return False
    man = _load_manifest()
    man["active"] = slugify(name)
    _save_manifest(man)
    return True


def _register(name: str, make_active: bool):
    man = _load_manifest()
    slug = slugify(name)
    if slug not in man.setdefault("profiles", []):
        man["profiles"].append(slug)
    if make_active or not man.get("active"):
        man["active"] = slug
    _save_manifest(man)


def _load_manifest() -> dict:
    p = _manifest_path()
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"active": None, "profiles": []}


def _save_manifest(man: dict):
    with open(_manifest_path(), "w", encoding="utf-8") as f:
        json.dump(man, f, indent=2)
