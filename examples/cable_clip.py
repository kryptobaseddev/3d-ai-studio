"""Adhesive cable clip (2 cables) — snap-fit C-hooks on a stick-on base.

A functional clip: a flat adhesive base with two upward-opening C-rings. Each ring
bore is sized for the cable; the mouth is deliberately NARROWER than the bore so a
cable snaps in and is retained. Cables run along X through the rings. Units: mm.

    studio3d gen-script --script examples/cable_clip.py --name cable-clip \
      --prompt "an adhesive snap-in clip that holds two cables" --color "#ff6b35" --out output
"""


def _hook(bore_d, wall, width, mouth):
    """One upward-opening C-hook (ring with a slot cut out of the top).
    Ring axis runs along X so a cable passes through; opening faces +Z."""
    outer_d = bore_d + 2 * wall
    ring = tube(h=width, d_outer=outer_d, d_inner=bore_d).rotate_y(90)  # axis -> X
    # mouth: a slot through the top, narrower than the bore so the cable is retained
    slot_cut = box(width + 2, mouth, outer_d).translate(0, 0, outer_d / 2)
    return ring - slot_cut


def build():
    base_w, base_d, base_t = 46.0, 16.0, 3.0
    bore_d, wall, width, mouth = 7.0, 2.4, 12.0, 4.6   # mouth < bore -> grips

    base = rounded_box(base_w, base_d, base_t, radius=2)

    clip = base
    # two hooks, sitting on top of the base, spaced along X
    hook = _hook(bore_d, wall, width, mouth)
    hz = base_t / 2 + (bore_d + 2 * wall) / 2 - 0.5   # seat the ring on the base
    for sx in (-1, 1):
        clip = clip + hook.at(sx * 11, 0, hz)

    return clip.on_bed()
