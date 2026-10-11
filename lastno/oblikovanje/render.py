# Render v Blenderju (Cycles) brez okna: blender.exe -b --factory-startup --python render.py -- naloga.json
#
# Naloga (JSON, pripravi jo upodabljanje.py):
#   vir:        {"posnetek": pot do JSON posnetka spletnega FreeCAD-a} ali {"blend": pot do .blend iz Oblikovanja}
#   kamera:     {polozaj, cilj, gor (mm, svet Z-gor), fov (navpično, °), pravokotna, visina (pol višine okna, mm)}
#               ali null = samodejna izometrija
#   premiki:    {ime objekta: [dx, dy, dz]} (razstavitev v brskalniku), neobvezno
#   osvetlitev: studio | mehka | soncni | mesto | gozd | notranjost | noc
#   ozadje:     svetlo | belo | temno | prozorno | okolje
#   sirina, visina, vzorci, vrtenje (0 ali število sličic za 360°), izhod (mapa)
#
# Scena se normira: središče modela v izhodišče, polmer 1. Luči, tla in kamera so zato neodvisni od velikosti kosa
# (FreeCAD riše v mm, Oblikovanje tudi). Ozadje se doda šele na sliki (numpy): render ima prozorno ozadje in tla, ki
# lovijo le senco, zato senca pade na katerokoli ozadje. Izpis "NAPREDEK a/b" in "SLICICA i/n" bere upodabljanje.py.

import json
import math
import os
import sys
import time

import bpy
import numpy as np
from mathutils import Matrix, Vector

ZACETEK = time.time()


def izpis(*a):
    print(*a, flush=True)


def naloga_iz_argumentov():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    with open(argv[0], encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------------------------------------------
# Naprava: OptiX na grafični kartici, sicer CUDA, sicer procesor

def nastavi_napravo(scena, vrste=("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL")):
    """Prva naprava s seznama, ki jo Cycles najde. OptiX potrebuje dovolj nov gonilnik NVIDIA (Blender 5.2: jedro se
    sicer ne prevede, OPTIX_ERROR_INTERNAL_COMPILER_ERROR); upodabljanje.py takrat ponovi render s CUDA."""
    scena.render.engine = "CYCLES"
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        for vrsta in vrste:
            try:
                prefs.compute_device_type = vrsta
            except TypeError:
                continue
            prefs.get_devices()
            gpu = [d for d in prefs.devices if d.type == vrsta]
            if gpu:
                for d in prefs.devices:
                    d.use = d.type == vrsta
                scena.cycles.device = "GPU"
                izpis("NAPRAVA", vrsta, ", ".join(d.name for d in gpu))
                return
    except Exception as e:  # noqa: BLE001
        izpis("NAPRAVA napaka", e)
    scena.cycles.device = "CPU"
    izpis("NAPRAVA CPU")


# ---------------------------------------------------------------------------------------------------------------
# Materiali

def srgb_v_linearno(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def principled(mat):
    try:
        mat.use_nodes = True   # v Blenderju 5 je vedno vklopljeno (lastnost je opuščena)
    except Exception:  # noqa: BLE001
        pass
    for n in mat.node_tree.nodes:
        if n.type == "BSDF_PRINCIPLED":
            return n
    return mat.node_tree.nodes.new("ShaderNodeBsdfPrincipled")


def vhod(node, *imena):
    for ime in imena:
        if ime in node.inputs:
            return node.inputs[ime]
    return None


def material_videza(r, g, b, kov, hrap, zrn, vzorec):
    """Material iz videza ploskve posnetka (barva sRGB, kovinskost, hrapavost, zrnatost, vzorec 1 = les)."""
    mat = bpy.data.materials.new("Videz")
    bsdf = principled(mat)
    barva = (srgb_v_linearno(r), srgb_v_linearno(g), srgb_v_linearno(b), 1.0)
    vhod(bsdf, "Base Color").default_value = barva
    vhod(bsdf, "Metallic").default_value = kov
    vhod(bsdf, "Roughness").default_value = hrap
    drevo, povezi = mat.node_tree.nodes, mat.node_tree.links
    if zrn > 0.01:
        # zrnatost (peskano, barvano z zrnom): drobna izboklina iz šuma
        sum_ = drevo.new("ShaderNodeTexNoise")
        sum_.inputs["Scale"].default_value = 900.0
        izb = drevo.new("ShaderNodeBump")
        izb.inputs["Strength"].default_value = min(0.35, 0.6 * zrn)
        izb.inputs["Distance"].default_value = 0.002
        povezi.new(sum_.outputs["Fac"], izb.inputs["Height"])
        povezi.new(izb.outputs["Normal"], vhod(bsdf, "Normal"))
    if int(vzorec) == 1:
        # les: letnice vzdolž X (valovi s šumom), barva med svetlejšo in temnejšo
        val = drevo.new("ShaderNodeTexWave")
        val.wave_type = "RINGS"
        try:
            val.rings_direction = "X"
        except Exception:  # noqa: BLE001
            pass
        val.inputs["Scale"].default_value = 18.0
        val.inputs["Distortion"].default_value = 6.0
        rampa = drevo.new("ShaderNodeValToRGB")
        rampa.color_ramp.elements[0].color = tuple(c * 0.62 for c in barva[:3]) + (1.0,)
        rampa.color_ramp.elements[1].color = barva
        povezi.new(val.outputs["Fac"], rampa.inputs["Fac"])
        povezi.new(rampa.outputs["Color"], vhod(bsdf, "Base Color"))
    return mat


# ---------------------------------------------------------------------------------------------------------------
# Scena iz posnetka spletnega FreeCAD-a

def scena_iz_posnetka(pot, premiki):
    with open(pot, "rb") as f:
        posnetek = json.loads(f.read().decode("utf-8"))
    materiali = {}
    objekti = []
    for o in posnetek.get("objekti", []):
        tocke = np.asarray(o.get("tocke") or [], dtype=np.float32).reshape(-1, 3)
        trik = np.asarray(o.get("trikotniki") or [], dtype=np.int32).reshape(-1, 3)
        if not len(tocke) or not len(trik):
            continue
        premik = premiki.get(o.get("ime")) if premiki else None
        if premik:
            tocke = tocke + np.asarray(premik, dtype=np.float32)
        # indeks materiala po trikotnikih iz ploskev posnetka
        indeksi = np.zeros(len(trik), dtype=np.int32)
        sloti = []
        for p in o.get("ploskve", []):
            t0, nt = int(p[2]), int(p[3])
            videz = list(p[4:11])
            videz = tuple(round(float(x), 3) for x in videz + [0.8, 0.8, 0.8, 0.15, 0.42, 0, 0][len(videz):])
            if videz not in materiali:
                materiali[videz] = material_videza(*videz)
            mat = materiali[videz]
            if mat not in sloti:
                sloti.append(mat)
            indeksi[t0:t0 + nt] = sloti.index(mat)
        mreza = bpy.data.meshes.new(o.get("oznaka") or o.get("ime") or "Kos")
        mreza.vertices.add(len(tocke))
        mreza.vertices.foreach_set("co", tocke.ravel())
        mreza.loops.add(trik.size)
        mreza.loops.foreach_set("vertex_index", trik.ravel())
        mreza.polygons.add(len(trik))
        mreza.polygons.foreach_set("loop_start", np.arange(0, trik.size, 3, dtype=np.int32))
        mreza.update()
        mreza.validate()
        for m in sloti:
            mreza.materials.append(m)
        if sloti:
            mreza.polygons.foreach_set("material_index", indeksi[:len(mreza.polygons)])
        # gladko znotraj ploskve, ostro na robovih: posnetek ima ločene točke za vsako ploskev FreeCAD-a
        try:
            mreza.shade_smooth()
        except AttributeError:
            mreza.polygons.foreach_set("use_smooth", [True] * len(mreza.polygons))
        obj = bpy.data.objects.new(mreza.name, mreza)
        bpy.context.scene.collection.objects.link(obj)
        objekti.append(obj)
    izpis("SCENA posnetek: %d objektov, %d materialov" % (len(objekti), len(materiali)))
    return objekti


def scena_iz_blend(pot):
    bpy.ops.wm.open_mainfile(filepath=pot)
    scena = bpy.context.scene
    # kamere in luči iz Oblikovanja ne uporabimo: render ima svoj studio
    for obj in list(scena.objects):
        if obj.type in ("CAMERA", "LIGHT"):
            bpy.data.objects.remove(obj, do_unlink=True)
    objekti = [o for o in scena.objects if o.type in ("MESH", "CURVE", "SURFACE", "META", "FONT", "CURVES", "VOLUME")
               and not o.hide_render]
    izpis("SCENA blend: %d objektov" % len(objekti))
    return objekti


def okvir(objekti):
    dg = bpy.context.evaluated_depsgraph_get()
    mn = Vector((1e30, 1e30, 1e30))
    mx = Vector((-1e30, -1e30, -1e30))
    for obj in objekti:
        ev = obj.evaluated_get(dg)
        for v in ev.bound_box:
            w = ev.matrix_world @ Vector(v)
            mn = Vector(map(min, mn, w))
            mx = Vector(map(max, mx, w))
    if mn.x > mx.x:
        return Vector((0, 0, 0)), Vector((0, 0, 0))
    return mn, mx


def normiraj(objekti):
    """Vse objekte brez starša obesi na koren, ki model premakne v izhodišče in ga poveča na polmer 1."""
    mn, mx = okvir(objekti)
    sredisce = (mn + mx) / 2
    polmer = max((mx - mn).length / 2, 1e-6)
    s = 1.0 / polmer
    koren = bpy.data.objects.new("Koren", None)
    bpy.context.scene.collection.objects.link(koren)
    koren.matrix_world = Matrix.Diagonal((s, s, s, 1.0)) @ Matrix.Translation(-sredisce)
    for obj in bpy.context.scene.objects:
        if obj is not koren and obj.parent is None and obj.type not in ("CAMERA", "LIGHT"):
            obj.parent = koren
            obj.matrix_parent_inverse = Matrix.Identity(4)
    bpy.context.view_layer.update()
    preslikaj = lambda p: (Vector(p) - sredisce) * s  # noqa: E731
    dno = (mn.z - sredisce.z) * s
    izpis("NORMIRANO polmer %.3f, dno %.3f" % (polmer, dno))
    return preslikaj, s, dno


# ---------------------------------------------------------------------------------------------------------------
# Osvetlitev in tla

OKOLJA = {   # Blenderjeva vgrajena okolja (datafiles/studiolights/world)
    "studio": "studio.exr", "mehka": "interior.exr", "soncni": "sunset.exr", "mesto": "city.exr",
    "gozd": "forest.exr", "notranjost": "interior.exr", "noc": "night.exr",
}
# (jakost okolja, luči: (ime, smer od središča, razdalja, velikost, moč, barva))
LUCI = {
    "studio": (0.35, [("Glavna", (-1.0, -1.3, 1.5), 4.5, 3.0, 320, (1.0, 0.98, 0.95)),
                      ("Polnilna", (1.6, -0.8, 0.6), 5.0, 4.0, 70, (0.92, 0.96, 1.0)),
                      ("Obrisna", (0.6, 1.6, 1.2), 4.5, 2.0, 220, (1.0, 1.0, 1.0))]),
    "mehka": (0.7, [("Zgoraj", (0.0, 0.0, 1.0), 4.0, 6.0, 260, (1.0, 1.0, 1.0))]),
    "soncni": (0.8, [("Sonce", (-1.5, 1.0, 0.45), 6.0, 0.6, 600, (1.0, 0.72, 0.45))]),
    "mesto": (1.0, []), "gozd": (1.0, []), "notranjost": (1.1, []), "noc": (2.0, []),
}


def okolje(scena, ime, jakost):
    svet = bpy.data.worlds.new("Okolje")
    scena.world = svet
    try:
        svet.use_nodes = True
    except Exception:  # noqa: BLE001
        pass
    drevo, povezi = svet.node_tree.nodes, svet.node_tree.links
    ozadje = next((n for n in drevo if n.type == "BACKGROUND"), None) or drevo.new("ShaderNodeBackground")
    izhod = next((n for n in drevo if n.type == "OUTPUT_WORLD"), None) or drevo.new("ShaderNodeOutputWorld")
    pot = os.path.join(bpy.utils.system_resource("DATAFILES"), "studiolights", "world", OKOLJA.get(ime, "studio.exr"))
    if os.path.isfile(pot):
        slika = drevo.new("ShaderNodeTexEnvironment")
        slika.image = bpy.data.images.load(pot)
        # svet je Z-gor (FreeCAD), okolja Blenderja tudi; zasuk po Z, da glavna svetloba pride spredaj levo
        koord = drevo.new("ShaderNodeTexCoord")
        preslik = drevo.new("ShaderNodeMapping")
        preslik.inputs["Rotation"].default_value = (0.0, 0.0, math.radians(-60))
        povezi.new(koord.outputs["Generated"], preslik.inputs["Vector"])
        povezi.new(preslik.outputs["Vector"], slika.inputs["Vector"])
        povezi.new(slika.outputs["Color"], ozadje.inputs["Color"])
    else:
        ozadje.inputs["Color"].default_value = (0.8, 0.8, 0.8, 1.0)
        izpis("OKOLJE ni datoteke", pot)
    ozadje.inputs["Strength"].default_value = jakost
    povezi.new(ozadje.outputs["Background"], izhod.inputs["Surface"])


def luci(scena, ime):
    for lime, smer, razdalja, velikost, moc, barva in LUCI.get(ime, LUCI["studio"])[1]:
        podatki = bpy.data.lights.new(lime, "AREA")
        podatki.shape = "DISK"
        podatki.size = velikost
        podatki.energy = moc
        podatki.color = barva
        obj = bpy.data.objects.new(lime, podatki)
        scena.collection.objects.link(obj)
        obj.location = Vector(smer).normalized() * razdalja
        obj.rotation_euler = (-obj.location).to_track_quat("-Z", "Y").to_euler()


def tla(scena, dno):
    mreza = bpy.data.meshes.new("Tla")
    r = 60.0
    mreza.from_pydata([(-r, -r, dno), (r, -r, dno), (r, r, dno), (-r, r, dno)], [], [(0, 1, 2, 3)])
    obj = bpy.data.objects.new("Tla", mreza)
    scena.collection.objects.link(obj)
    obj.is_shadow_catcher = True
    return obj


# ---------------------------------------------------------------------------------------------------------------
# Kamera

def kamera(scena, podatki, preslikaj, s, sirina, visina):
    cam = bpy.data.cameras.new("Kamera")
    obj = bpy.data.objects.new("Kamera", cam)
    scena.collection.objects.link(obj)
    scena.camera = obj
    cam.clip_start = 0.001
    cam.clip_end = 1000.0
    cam.sensor_fit = "VERTICAL"
    if podatki:
        polozaj = preslikaj(podatki["polozaj"])
        cilj = preslikaj(podatki["cilj"])
        gor = Vector(podatki.get("gor") or (0, 0, 1)).normalized()
        if podatki.get("pravokotna"):
            cam.type = "ORTHO"
            cam.ortho_scale = 2.0 * float(podatki["visina"]) * s
            # pravokotna kamera brskalnika sme biti v modelu: odmakni jo nazaj, smer ostane
            polozaj = cilj + (polozaj - cilj).normalized() * 20.0
        else:
            cam.angle_y = math.radians(float(podatki.get("fov") or 40))
    else:
        cilj = Vector((0, 0, 0))
        polozaj = Vector((1.0, -1.15, 0.85)).normalized() * 4.2
        gor = Vector((0, 0, 1))
        cam.angle_y = math.radians(30)
    z = (polozaj - cilj).normalized()          # kamera gleda v -Z
    x = gor.cross(z)
    if x.length < 1e-6:
        x = Vector((1, 0, 0))
    x.normalize()
    y = z.cross(x)
    m = Matrix((x, y, z)).transposed().to_4x4()
    m.translation = polozaj
    obj.matrix_world = m
    return obj, cilj


# ---------------------------------------------------------------------------------------------------------------
# Ozadje na sliki (numpy): render je prozoren, senca na tleh je delno prozorna črna

OZADJA = {   # (zgoraj, spodaj) v prikaznem sRGB
    "svetlo": ((0.97, 0.975, 0.98), (0.84, 0.855, 0.875)),
    "belo": ((1.0, 1.0, 1.0), (1.0, 1.0, 1.0)),
    "temno": ((0.20, 0.215, 0.235), (0.07, 0.075, 0.085)),
}


def sestavi_ozadje(pot, vrsta):
    if vrsta not in OZADJA:
        return
    slika = bpy.data.images.load(pot, check_existing=False)
    w, h = slika.size
    px = np.empty(w * h * 4, dtype=np.float32)
    slika.pixels.foreach_get(px)
    px = px.reshape(h, w, 4)              # vrstice od spodaj navzgor
    zg, sp = (np.asarray(c, dtype=np.float32) for c in OZADJA[vrsta])
    t = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None, None]
    ozadje = sp * (1 - t) + zg * t
    a = px[:, :, 3:4]
    px[:, :, :3] = px[:, :, :3] * a + ozadje * (1 - a)
    px[:, :, 3] = 1.0
    slika.pixels.foreach_set(px.ravel())
    slika.filepath_raw = pot
    slika.file_format = "PNG"
    slika.save()
    bpy.data.images.remove(slika)


# ---------------------------------------------------------------------------------------------------------------

def main():
    n = naloga_iz_argumentov()
    vir = n["vir"]
    if vir.get("blend"):
        objekti = scena_iz_blend(vir["blend"])
    else:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        objekti = scena_iz_posnetka(vir["posnetek"], n.get("premiki") or {})
    scena = bpy.context.scene
    if not objekti:
        izpis("NAPAKA: v sceni ni nobenega kosa")
        sys.exit(2)
    preslikaj, s, dno = normiraj(objekti)

    nastavi_napravo(scena, n.get("naprave") or ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL"))
    sirina, visina = int(n.get("sirina") or 1600), int(n.get("visina") or 1000)
    scena.render.resolution_x, scena.render.resolution_y = sirina, visina
    scena.render.resolution_percentage = 100
    scena.cycles.samples = int(n.get("vzorci") or 128)
    scena.cycles.use_adaptive_sampling = True
    scena.cycles.use_denoising = True
    try:
        scena.cycles.denoiser = "OPENIMAGEDENOISE"
        scena.cycles.denoising_use_gpu = True
    except Exception:  # noqa: BLE001
        pass
    scena.cycles.max_bounces = 8
    for prikaz in ("Khronos PBR Neutral", "AgX", "Filmic"):   # Khronos: barve kot v FreeCAD-u, brez razbarvanja AgX
        try:
            scena.view_settings.view_transform = prikaz
            break
        except TypeError:
            continue

    osv = n.get("osvetlitev") or "studio"
    vrsta_ozadja = n.get("ozadje") or "svetlo"
    okolje(scena, osv, LUCI.get(osv, LUCI["studio"])[0])
    luci(scena, osv)
    cam, cilj = kamera(scena, n.get("kamera"), preslikaj, s, sirina, visina)
    pod_tlemi = cam.matrix_world.translation.z < dno + 0.02 and cam.data.type != "ORTHO"
    if vrsta_ozadja != "okolje" and not pod_tlemi:
        tla(scena, dno)
    scena.render.film_transparent = vrsta_ozadja != "okolje"
    try:   # steklo, pleksi: skozi steklo se vidi sestavljeno ozadje (sicer so robovi in ploskve stekla temni)
        scena.cycles.film_transparent_glass = scena.render.film_transparent
        scena.cycles.film_transparent_roughness = 0.1
    except AttributeError:
        pass
    scena.cycles.transmission_bounces = max(scena.cycles.transmission_bounces, 12)
    scena.render.image_settings.file_format = "PNG"
    scena.render.image_settings.color_mode = "RGBA"

    izhod = n["izhod"]
    os.makedirs(izhod, exist_ok=True)
    slicic = int(n.get("vrtenje") or 0)
    if slicic > 1:
        # vrtenje 360° okoli navpične osi skozi cilj kamere
        nosilec = bpy.data.objects.new("Vrtenje", None)
        scena.collection.objects.link(nosilec)
        nosilec.location = Vector((cilj.x, cilj.y, 0))
        svet_kamere = cam.matrix_world.copy()
        cam.parent = nosilec
        cam.matrix_parent_inverse = nosilec.matrix_world.inverted()
        cam.matrix_world = svet_kamere
        for i in range(slicic):
            nosilec.rotation_euler = (0, 0, 2 * math.pi * i / slicic)
            bpy.context.view_layer.update()
            pot = os.path.join(izhod, "slicica_%04d.png" % i)
            scena.render.filepath = pot
            bpy.ops.render.render(write_still=True)
            sestavi_ozadje(pot, vrsta_ozadja)
            izpis("SLICICA %d/%d" % (i + 1, slicic))
    else:
        pot = os.path.join(izhod, "render.png")
        scena.render.filepath = pot
        bpy.ops.render.render(write_still=True)
        sestavi_ozadje(pot, vrsta_ozadja)
    izpis("KONEC %.1f s" % (time.time() - ZACETEK))


try:
    main()
except SystemExit:
    raise
except Exception:  # noqa: BLE001
    import traceback
    izpis("NAPAKA:", traceback.format_exc())
    sys.exit(1)
