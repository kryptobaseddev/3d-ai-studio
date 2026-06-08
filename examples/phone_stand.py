"""Minimalist phone/tablet stand — one connected wedge with a leaning cradle.

Authored as a SINGLE extruded side-silhouette (so it is inherently one connected,
manifold solid — no floating plates): a base, a back support leaning back ~17deg
from vertical, and a front ledge the phone's bottom edge rests in, with a cable
pass-through. Units: mm.

    studio3d gen-script --script examples/phone_stand.py --name phone-stand \
      --prompt "an angled phone stand with a cable slot" --color "#4a90d9" --out output
"""


def build():
    width = 78.0          # how wide (across the phone)

    # side silhouette in (depth, height) mm, traced as a closed loop. depth runs
    # front(0) -> back; height is up. The phone's bottom edge sits in the GROOVE
    # (between the front lip and the support) and leans on the SUPPORT FRONT FACE,
    # which tilts back ~14deg from vertical for a comfortable viewing angle.
    profile = [
        [0, 0],       # front bottom of base
        [0, 10],      # front face of base (10mm thick)
        [16, 10],     # base top, back to the lip
        [16, 24],     # front lip rises (stops the phone sliding off)
        [24, 24],     # lip top
        [24, 10],     # lip back wall down into the groove
        [30, 10],     # groove floor -> foot of the support
        [52, 95],     # SUPPORT FRONT FACE: leans back 22mm over 85mm (~14.5deg)
        [66, 95],     # support top (14mm thick)
        [82, 10],     # support back face slopes down to the base
        [82, 0],      # back bottom of base
    ]

    # extrude along Z by `width`, then stand it up: height->Z, width->X, depth->Y
    stand = extrude(profile, width, center=False).rotate_x(90).rotate_z(90)

    # cable pass-through behind the cradle groove (so a charging cable can exit)
    cable = slot(20, 11, 60).rotate_x(90)
    stand = stand - cable.at(0, 22, 16)

    return stand.center_xy().on_bed()
