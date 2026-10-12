# -*- coding: utf-8 -*-
"""Sličice različic idej v ločenem Blenderju brez okna (ne moti žive scene strežnika Oblikovanja).

    blender -b --factory-startup --python slicica_izris.py -- naloga.json

naloga.json: [{"blend": pot, "png": pot}, ...]. Vsako datoteko odpre, izriše Workbench (studio luč, barve materialov,
obris, prozorno ozadje) iz iste smeri kot stran (izometrija 1, -1,25, 0,9; perspektiva 30° navpično), 320 × 240,
enako kot sličice, ki jih izriše stran iz svojega pogleda. Skriti objekti se ne izrišejo. Izpis: SLICICA OK|NAPAKA pot.
"""
import json
import math
import os
import sys
import traceback

import bpy
from mathutils import Vector

VRSTE_GEOMETRIJE = {"MESH", "CURVE", "SURFACE", "META", "FONT", "CURVES"}
SMER = Vector((1.0, -1.25, 0.9)).normalized()
VELIKOST = (320, 240)
KOT = math.radians(30)        # navpični zorni kot kot na strani (three.js PerspectiveCamera fov 30)


def okvir_vidnih():
    dg = bpy.context.evaluated_depsgraph_get()
    mn, mx = Vector((1e30,) * 3), Vector((-1e30,) * 3)
    for obj in bpy.context.scene.objects:
        if obj.type not in VRSTE_GEOMETRIJE:
            continue
        try:
            skrit = obj.hide_get() or obj.hide_viewport or obj.hide_render
        except RuntimeError:
            skrit = obj.hide_render
        if skrit:
            obj.hide_render = True        # kar stran ne kaže, ne sme na sličico
            continue
        ev = obj.evaluated_get(dg)
        for v in ev.bound_box:
            w = ev.matrix_world @ Vector(v)
            mn, mx = Vector(map(min, mn, w)), Vector(map(max, mx, w))
    return (mn, mx) if mn.x <= mx.x else (None, None)


def barve_kot_na_strani():
    """Workbench riše barvo materiala v pogledu (diffuse_color); stran bere Principled BSDF. Uskladi (datoteka se ne shrani)."""
    for mat in bpy.data.materials:
        if mat.node_tree is None:
            continue
        for n in mat.node_tree.nodes:
            if n.type == "BSDF_PRINCIPLED":
                vir = n.inputs["Base Color"]
                barva = list(mat.diffuse_color[:3]) if vir.is_linked else list(vir.default_value[:3])
                alfa = float(n.inputs["Alpha"].default_value)
                vir_t = n.inputs.get("Transmission Weight") or n.inputs.get("Transmission")
                if vir_t is not None and float(vir_t.default_value) > 0.5:
                    alfa = min(alfa, 0.18)      # steklo, pleksi: prosojno kot na strani
                mat.diffuse_color = (*barva, alfa)
                mat.metallic = float(n.inputs["Metallic"].default_value)
                mat.roughness = float(n.inputs["Roughness"].default_value)
                break


def izrisi(pot_png):
    scena = bpy.context.scene
    barve_kot_na_strani()
    mn, mx = okvir_vidnih()
    if mn is None:
        raise ValueError("scena nima vidne geometrije")
    sredisce = (mn + mx) / 2
    polmer = max((mx - mn).length / 2, 1e-3)
    r = scena.render
    r.engine = "BLENDER_WORKBENCH"
    sh = scena.display.shading
    sh.light, sh.color_type, sh.show_cavity, sh.show_object_outline = "STUDIO", "MATERIAL", False, True
    try:
        sh.show_shadows = False
    except AttributeError:
        pass
    # AgX (privzeto) barve potemni in razbarva; stran riše sRGB brez preslikave tonov
    scena.view_settings.view_transform = "Standard"
    scena.view_settings.look = "None"
    scena.view_settings.exposure = 1.6        # studijska luč Workbencha je temnejša od osvetlitve strani (umerjeno 2026-10-12)
    try:
        sh.studio_light = "Default"
    except TypeError:
        pass
    r.resolution_x, r.resolution_y, r.resolution_percentage = VELIKOST[0], VELIKOST[1], 100
    r.film_transparent = True
    r.image_settings.file_format = "PNG"
    r.image_settings.color_mode = "RGBA"
    cam = bpy.data.objects.new("_SlicicaAI", bpy.data.cameras.new("_SlicicaAI"))
    scena.collection.objects.link(cam)
    scena.camera = cam
    cam.data.type = "PERSP"
    cam.data.sensor_fit = "VERTICAL"
    cam.data.lens_unit = "FOV"
    cam.data.angle_y = KOT
    razdalja = polmer / math.sin(KOT / 2) * 1.05
    cam.data.clip_start, cam.data.clip_end = max(razdalja - polmer * 2, 0.01), razdalja + polmer * 4
    cam.location = sredisce + SMER * razdalja
    cam.rotation_euler = (-SMER).to_track_quat("-Z", "Y").to_euler()
    r.filepath = pot_png
    bpy.ops.render.render(write_still=True)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if not argv:
        print("uporaba: blender -b --python slicica_izris.py -- naloga.json")
        return 2
    with open(argv[0], encoding="utf-8") as f:
        naloge = json.load(f)
    napak = 0
    for n in naloge:
        try:
            bpy.ops.wm.open_mainfile(filepath=n["blend"], load_ui=False)
            os.makedirs(os.path.dirname(n["png"]), exist_ok=True)
            zacasna = n["png"] + ".delno.png"
            izrisi(zacasna)
            os.replace(zacasna, n["png"])
            print("SLICICA OK %s" % n["png"], flush=True)
        except Exception:
            napak += 1
            print("SLICICA NAPAKA %s" % n["png"], flush=True)
            traceback.print_exc()
    return 1 if napak and napak == len(naloge) else 0


if __name__ == "__main__":
    sys.exit(main())
