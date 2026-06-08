"""Cute cartoon owl figurine — proportional CSG, reference-grounded.

Authored against a single head-unit H so proportions stay locked. H≈40mm gives
a total height ≈ 88mm with the head ≈ 45% of the total. Units: mm, Z up, and the
FACE points toward -Y (front).

Design cues (what makes it read as a cute owl):
  * big forward eyes on a nearly-flush facial disc (NOT on a stalk)
  * soft wide ear tufts angled outward (NOT sharp central horns)
  * wings folded/merged into the body (NOT flat slabs)
  * a low, wide teardrop body so it sits like a plump owl

    studio3d gen-script --script examples/owl.py --name owl \
      --prompt "a cute cartoon owl figurine" --color "#8d6e63" --out output
"""


def build():
    H = 40.0  # head unit

    # ---- body: a plump teardrop, wider at the base, sitting low ----------
    # ellipsoid(1.1H wide, 0.96H deep, 1.7H tall)
    body_cz = 0.85 * H
    body = ellipsoid(1.1 * H, 0.96 * H, 1.7 * H).at(0, 0, body_cz)

    # ---- head: a sphere merged onto the body with NO neck ----------------
    # head center only ~0.7H above body center so the two blend together
    head_cz = body_cz + 0.7 * H
    head = sphere(d=1.0 * H).at(0, 0, head_cz)
    owl = body + head

    # ---- facial disc: a heart-shaped face that frames the eyes ----------
    # Slightly more proud + wider so it actually reads from the front, but
    # still nearly flush (a raised face, not a stalk).
    face_y = -0.40 * H  # front surface of the d=1.0H head is at y=-0.5H
    disc_cz = head_cz - 0.05 * H
    disc = ellipsoid(0.66 * H, 0.16 * H, 0.52 * H).at(0, face_y, disc_cz)
    owl = owl + disc

    # ---- eyes: two BIG forward spheres, barely raised --------------------
    # combined span ≈ 0.62 of the face width -> centers at ±0.165H
    eye_d = 0.30 * H
    eye_dx = 0.165 * H
    eye_y = face_y - 0.05 * H  # proud of the disc
    eye_z = disc_cz - 0.01 * H  # slightly low for cuteness
    for sx in (-1, 1):
        eye = sphere(d=eye_d).at(sx * eye_dx, eye_y, eye_z)
        owl = owl + eye
        # carve a pupil into each eye
        pupil = sphere(d=0.13 * H).at(sx * eye_dx, eye_y - 0.14 * H, eye_z)
        owl = owl - pupil

    # ---- beak: a SMALL short cone, tip DOWN, poking out between the eyes -
    # Sits just below the eye centerline, clearly proud of the face so it
    # reads from the front as a little nose/beak.
    beak = (
        cone(h=0.22 * H, d=0.18 * H)
        .rotate_x(180)  # tip points straight down
        .at(0, face_y - 0.11 * H, eye_z - 0.13 * H)
    )
    owl = owl + beak

    # ---- ear tufts: SOFT feather tufts (NOT horns) ----------------------
    # Built as a hull of a wide low base-sphere and a fairly LARGE, only
    # slightly offset top-sphere. Keeping the tip sphere big and the lean
    # short makes a stubby, rounded, plush tuft — never a sharp point.
    for sx in (-1, 1):
        base_z = head_cz + 0.30 * H
        tuft_base = sphere(d=0.34 * H).at(sx * 0.28 * H, 0.05 * H, base_z)
        tuft_tip = sphere(d=0.20 * H).at(
            sx * 0.40 * H, 0.04 * H, base_z + 0.22 * H  # short up-and-out lean
        )
        tuft = hull(tuft_base, tuft_tip)
        owl = owl + tuft

    # ---- wings: flattened ellipsoids folded into the sides ---------------
    # ellipsoid(0.18H, 0.34H, 0.9H) overlapped heavily into the body
    for sx in (-1, 1):
        wing = ellipsoid(0.18 * H, 0.34 * H, 0.9 * H).at(
            sx * 0.52 * H, 0.05 * H, body_cz
        )
        owl = owl + wing

    # ---- feet: little ellipsoids poking forward so it stands flat --------
    for sx in (-1, 1):
        foot = ellipsoid(0.30 * H, 0.40 * H, 0.18 * H).at(
            sx * 0.28 * H, -0.18 * H, 0.07 * H
        )
        owl = owl + foot

    return owl.on_bed()
