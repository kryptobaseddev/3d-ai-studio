"""Parametric enclosure with a friction-fit lid — a classic functional print.

Demonstrates: hollow box with controlled wall thickness, a recessed lip for the
lid, a base chamfer to fight elephant's foot, and mating clearance. Two solids are
unioned side-by-side onto one build plate (box + lid) so they print together.
Units: mm.

    studio3d gen-script --script examples/parametric_box.py --name parametric-box \
      --prompt "a small parts box with a press-fit lid" --out output
"""

INNER_W, INNER_D, INNER_H = 60.0, 40.0, 25.0
WALL = 2.0          # >= 0.8mm; 2.0 is sturdy
FLOOR = 2.0
CLEAR = 0.2         # press-fit clearance for the lid lip
LID_T = 2.0
LIP_H = 4.0


def _enclosure():
    ow, od = INNER_W + 2 * WALL, INNER_D + 2 * WALL
    oh = INNER_H + FLOOR
    outer = box(ow, od, oh, center=False)
    cavity = box(INNER_W, INNER_D, INNER_H, center=False).translate(WALL, WALL, FLOOR)
    body = outer - cavity
    # recess a lip seat at the top inner rim for the lid to drop into
    seat = box(INNER_W + CLEAR * 2, INNER_D + CLEAR * 2, LIP_H + 0.5, center=False) \
        .translate(WALL - CLEAR, WALL - CLEAR, oh - LIP_H)
    seat_keep = box(INNER_W, INNER_D, LIP_H + 1.0, center=False).translate(WALL, WALL, oh - LIP_H)
    body = body - (seat - seat_keep)
    # 45-degree base chamfer: subtract a square ring frustum from the bottom edge
    chamfer = _base_chamfer(ow, od, 0.8)
    return (body - chamfer).on_bed()


def _base_chamfer(ow, od, c):
    """A 45-degree relief around the bottom outer edge (elephant's-foot guard)."""
    big = box(ow + 4, od + 4, c, center=False).translate(-2, -2, 0)
    small = box(ow - 2 * c, od - 2 * c, c + 0.2, center=False).translate(c, c, -0.1)
    # ring = big minus small footprint, but tapered: approximate with a thin ring
    return (big - small)


def _lid():
    ow, od = INNER_W + 2 * WALL, INNER_D + 2 * WALL
    top = box(ow, od, LID_T, center=False)
    # downward lip that fits the seat with clearance
    lip = box(INNER_W - CLEAR * 2, INNER_D - CLEAR * 2, LIP_H, center=False) \
        .translate(WALL + CLEAR, WALL + CLEAR, -LIP_H)
    lid = top + lip
    return lid.on_bed().translate(ow + 6, 0, 0)   # park beside the box


def build():
    return _enclosure() + _lid()
