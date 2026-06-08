"""Twisted vase — a watertight, water-holding vessel with spiral flute decoration.

KEY FIX: the twist/flutes are applied ONLY to the OUTER surface; the inner bore is a
SMOOTH cylinder. That guarantees a >=4mm wall everywhere (no thin spots) and a closed,
watertight vessel that actually holds water — unlike an in-phase fluted inner+outer,
which produces near-zero perpendicular walls at the flute flanks. Units: mm.

    studio3d gen-script --script examples/twist_vase.py --name twist-vase \
      --prompt "a tall twisted vase that holds water" --color "#8e7cc3" --out output
"""

import math


def _fluted(base_r, lobe, lobes, n=160):
    """A fluted (lobed) closed profile: radius = base_r + lobe*cos(lobes*theta)."""
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        r = base_r + lobe * math.cos(lobes * a)
        pts.append([r * math.cos(a), r * math.sin(a)])
    return pts


def build():
    H = 130.0
    turns = 0.65          # a clear, elegant spiral
    lobes = 9
    lobe = 2.6            # flute depth — purely external decoration now
    base_r = 30.0
    floor = 6.0           # solid base so it holds water
    bore_r = base_r - lobe - 4.0   # smooth bore -> wall >= 4mm at every flute valley

    outer = twist_extrude(_fluted(base_r, lobe, lobes), height=H, turns=turns)
    bore = cylinder(h=H, d=2 * bore_r, center=False).translate(0, 0, floor)
    return (outer - bore).on_bed()
