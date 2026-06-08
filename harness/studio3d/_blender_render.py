"""Blender headless multi-view renderer (invoked by studio3d.render).

Run as:  blender --background --factory-startup --python _blender_render.py -- \
            <stl_path> <out_dir> <hex_color> <size> <views_csv>

Uses the WORKBENCH engine (solid shading) — fast, GPU-optional, and unaffected by
the OCIO color-config version skew on some Blender builds. Produces one PNG per
requested view (front/right/top/iso/back/left) framing the part on a ground plane,
for an agent to visually critique against the design intent.
"""
import sys
import math
import bpy  # type: ignore
import mathutils  # type: ignore


def _argv():
    argv = sys.argv
    return argv[argv.index("--") + 1:] if "--" in argv else []


def _hex_rgb(h):
    h = (h or "#9aa7b2").lstrip("#")
    if len(h) < 6:
        h = "9aa7b2"
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_stl(path):
    bpy.ops.wm.stl_import(filepath=path)
    objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    # join if multiple
    if len(objs) > 1:
        bpy.context.view_layer.objects.active = objs[0]
        for o in objs:
            o.select_set(True)
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active or objs[0]
    return obj


def setup(obj, color, size):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x = size
    scene.render.resolution_y = size
    scene.render.film_transparent = True
    shading = scene.display.shading
    shading.light = "STUDIO"
    shading.color_type = "SINGLE"
    shading.single_color = _hex_rgb(color)
    shading.show_shadows = True
    shading.show_cavity = True
    shading.cavity_type = "BOTH"

    # material color too (in case)
    mat = bpy.data.materials.new("part")
    mat.diffuse_color = (*_hex_rgb(color), 1.0)
    obj.data.materials.append(mat)

    # ground the object: min-z to 0, centered in XY
    bbox = [obj.matrix_world @ mathutils.Vector(c) for c in obj.bound_box]
    minz = min(v.z for v in bbox)
    cx = sum(v.x for v in bbox) / 8.0
    cy = sum(v.y for v in bbox) / 8.0
    obj.location.x -= cx
    obj.location.y -= cy
    obj.location.z -= minz

    # recompute bounds after move
    bbox = [obj.matrix_world @ mathutils.Vector(c) for c in obj.bound_box]
    center = mathutils.Vector((
        sum(v.x for v in bbox) / 8.0,
        sum(v.y for v in bbox) / 8.0,
        sum(v.z for v in bbox) / 8.0,
    ))
    dims = obj.dimensions
    radius = max(dims.x, dims.y, dims.z)
    return center, max(radius, 1.0)


def add_camera(center, radius, view):
    cam_data = bpy.data.cameras.new("cam")
    cam = bpy.data.objects.new("cam", cam_data)
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam

    d = radius * 2.4
    dirs = {
        "front": (0, -d, radius * 0.35),
        "back": (0, d, radius * 0.35),
        "right": (d, 0, radius * 0.35),
        "left": (-d, 0, radius * 0.35),
        "top": (0.001, 0, d),
        "iso": (d * 0.75, -d * 0.75, d * 0.7),
    }
    off = mathutils.Vector(dirs.get(view, dirs["iso"]))
    cam.location = center + off
    # point at center
    direction = center - cam.location
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    cam_data.lens = 50
    return cam


def render(out_path):
    bpy.context.scene.render.filepath = out_path
    bpy.context.scene.render.image_settings.file_format = "PNG"
    bpy.ops.render.render(write_still=True)


def main():
    args = _argv()
    stl_path, out_dir, color, size_s, views_s = (args + ["", "", "#9aa7b2", "720", "front,right,top,iso"])[:5]
    size = int(size_s)
    views = [v.strip() for v in views_s.split(",") if v.strip()]

    clear_scene()
    obj = import_stl(stl_path)
    center, radius = setup(obj, color, size)

    import os
    os.makedirs(out_dir, exist_ok=True)
    for v in views:
        # remove old cameras
        for o in list(bpy.context.scene.objects):
            if o.type == "CAMERA":
                bpy.data.objects.remove(o, do_unlink=True)
        add_camera(center, radius, v)
        render(os.path.join(out_dir, f"view_{v}.png"))
        print(f"STUDIO3D_RENDERED {v}")


if __name__ == "__main__":
    main()
