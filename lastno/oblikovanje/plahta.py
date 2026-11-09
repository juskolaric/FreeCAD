# -*- coding: utf-8 -*-
"""Plahta (ponjava) kot blago: dvigni, popravi spodaj, spusti in poglej, kako pade.

Plahta je mreža (pokrov brez dna: vrh in štiri stranice v mreži ~70 mm) z lastnostjo objekta »plahta« = "dol" ali "gor".
Osnovna oblika (napeta, kot iz ukroja) je v atributu oglišč »plahta_osnova« (svetovne mm, objekt brez transformacije).

  plahta-ustvari {vir, korak, ime}   iz kvadra (npr. »Prevleka PVC«) naredi plahto iz blaga; vir skrije
  plahta-dvigni  {ime}               plahta v osnovni obliki dvignjena nad tovor (pod njo urejaš)
  plahta-spusti  {ime, okvirjev}     simulacija blaga (Blender Cloth) od dvignjene lege do mirovanja na tovoru;
                                     odgovor nosi okvirje animacije (lega oglišč v 0,1 mm), stran jih predvaja

Simulacija teče v začasni sceni v metrih (gravitacija 9,81 m/s², fizika Blenderja ne upošteva merila enot), trki so
kvadri (okvir vsakega vidnega objekta v njegovih oseh) in tla pod najnižjim objektom. Po simulaciji se začasni podatki
pobrišejo, plahta obdrži končno obliko. Vrstni red oglišč posnetka za stran je enak vrstnemu redu oglišč mreže (gladko
senčenje, brez UV), zato okvirji gredo na geometrijo strani brez preslikave.
"""

import time

import bmesh
import bpy
import numpy as np
from mathutils import Vector

LASTNOST = "plahta"
ATRIBUT = "plahta_osnova"
KORAK = 70.0          # mm, velikost celice blaga
NAD_TOVOROM = 400.0   # mm, dvignjena plahta je toliko nad svojo napeto lego (+ višina plahte)
MERILO = 0.001        # mm -> m za simulacijo
PROSOJNOST_BLAGA = 0.6   # alfa materiala plahte (vir je lahko skoraj prozoren)
_KVADER = ((0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0))


def plahte():
    return [o for o in bpy.context.scene.objects if o.type == "MESH" and o.get(LASTNOST) in ("dol", "gor")]


def _plahta(ime):
    obj = bpy.data.objects.get(ime or "")
    if obj is None:
        vse = plahte()
        obj = vse[0] if len(vse) == 1 else None
    if obj is None or obj.get(LASTNOST) not in ("dol", "gor"):
        raise ValueError("Ni plahte %r." % ime)
    return obj


def _koordinate(me):
    co = np.empty(len(me.vertices) * 3, dtype=np.float64)
    me.vertices.foreach_get("co", co)
    return co.reshape(-1, 3)


def _nastavi(me, co):
    me.vertices.foreach_set("co", np.ascontiguousarray(co, dtype=np.float32).ravel())
    me.update()


def osnova(obj):
    a = obj.data.attributes.get(ATRIBUT)
    v = np.empty(len(obj.data.vertices) * 3, dtype=np.float32)
    a.data.foreach_get("vector", v)
    return v.reshape(-1, 3).astype(np.float64)


def ustvari(vir="Prevleka PVC", korak=KORAK, ime="Plahta (blago)"):
    """Plahta iz okvira objekta `vir` (svetovni okvir mreže brez modifikatorjev): pokrov brez dna v mreži `korak` mm."""
    src = bpy.data.objects[vir]
    tocke = np.array([tuple(src.matrix_world @ v.co) for v in src.data.vertices])
    mn, mx = tocke.min(axis=0), tocke.max(axis=0)
    d = mx - mn
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector([mn[i] + (v.co[i] + 0.5) * d[i] for i in range(3)])
    for os_ in range(3):
        n = max(1, int(round(d[os_] / korak)))
        for i in range(1, n):
            co = Vector(mn.tolist())
            co[os_] = mn[os_] + d[os_] * i / n
            no = Vector((0, 0, 0))
            no[os_] = 1.0
            bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=co, plane_no=no)
    bm.normal_update()
    dno = [f for f in bm.faces if f.normal.z < -0.9 and abs(f.calc_center_median().z - mn[2]) < 1e-3]
    bmesh.ops.delete(bm, geom=dno, context="FACES")
    me = bpy.data.meshes.new(ime)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    obj = bpy.data.objects.get(ime)
    if obj is not None:
        stara = obj.data
        obj.data = me
        if stara.users == 0:
            bpy.data.meshes.remove(stara)
    else:
        obj = bpy.data.objects.new(ime, me)
        for c in src.users_collection:
            c.objects.link(obj)
    for m in src.data.materials:   # kopija materiala vira, manj prozorna: gube blaga se vidijo, tovor še skozi
        mb = bpy.data.materials.get(m.name + " (blago)") if m else None
        if m is not None and mb is None:
            mb = m.copy()
            mb.name = m.name + " (blago)"
            barva = list(mb.diffuse_color)
            mb.diffuse_color = barva[:3] + [max(barva[3], PROSOJNOST_BLAGA)]
            bsdf = mb.node_tree.nodes.get("Principled BSDF") if mb.use_nodes else None
            if bsdf is not None and "Alpha" in bsdf.inputs:
                bsdf.inputs["Alpha"].default_value = max(bsdf.inputs["Alpha"].default_value, PROSOJNOST_BLAGA)
        me.materials.append(mb)
    a = me.attributes.new(ATRIBUT, "FLOAT_VECTOR", "POINT")
    a.data.foreach_set("vector", _koordinate(me).astype(np.float32).ravel())
    obj[LASTNOST] = "dol"
    obj["plahta_vir"] = src.name
    src.hide_set(True)
    src.hide_render = True
    return obj


def _visina(obj):
    o = osnova(obj)
    return float(o[:, 2].max() - o[:, 2].min())


def dvigni(obj):
    o = osnova(obj)
    o[:, 2] += _visina(obj) + NAD_TOVOROM
    _nastavi(obj.data, o)
    obj[LASTNOST] = "gor"


def _trki(izkljuci):
    """Kvadri vseh vidnih mrež (okvir v oseh objekta) v metrih in najnižja točka."""
    tocke, ploskve = [], []
    najnizje = None
    for o in bpy.context.scene.objects:
        if o.type != "MESH" or o.name in izkljuci or o.hide_get() or o.hide_viewport:
            continue
        kot = [o.matrix_world @ Vector(c) for c in o.bound_box]
        if (kot[6] - kot[0]).length < 15.0:   # vijaki, ringle
            continue
        z = len(tocke)
        tocke += [tuple(v * MERILO) for v in kot]
        ploskve += [tuple(z + i for i in f) for f in _KVADER]
        nz = min(v.z for v in kot)
        najnizje = nz if najnizje is None else min(najnizje, nz)
    return tocke, ploskve, (najnizje or 0.0) * MERILO


def simuliraj(obj, okvirjev=96, fps=24, vsak=2):
    """Pade iz dvignjene lege na tovor. Vrne (okvirji [N*3 int, 0,1 mm], končne koordinate mm, čas)."""
    zacetek = time.time()
    o = osnova(obj)
    start = o.copy()
    start[:, 2] += _visina(obj) + NAD_TOVOROM
    izkljuci = {obj.name, obj.get("plahta_vir", "")} | {x.name for c in obj.users_collection for x in c.objects}
    t, f, tla = _trki(izkljuci)

    # Začasni objekti v zbirki trenutne scene (depsgraph druge scene v načinu -b ni na voljo), v metrih: gravitacija
    # scene je -9,81 enot/s², fizika merila enot ne upošteva. Blago trči le z zbirko simulacije.
    sc = bpy.context.scene
    stari = (sc.frame_current, tuple(sc.gravity), sc.use_gravity, sc.render.fps, sc.render.fps_base)
    sc.gravity = (0.0, 0.0, -9.81)
    sc.use_gravity = True
    sc.render.fps, sc.render.fps_base = fps, 1.0
    zb = bpy.data.collections.new("PlahtaSimulacija")
    sc.collection.children.link(zb)
    novi = []
    try:
        me = bpy.data.meshes.new("PlahtaSim")
        me.from_pydata((start * MERILO).tolist(), [], [tuple(p.vertices) for p in obj.data.polygons])
        blago = bpy.data.objects.new("PlahtaSim", me)
        zb.objects.link(blago)
        novi.append(blago)
        m = blago.modifiers.new("Blago", "CLOTH")
        s = m.settings
        s.quality = 10
        s.mass = 0.3
        s.air_damping = 1.0
        s.tension_stiffness = s.compression_stiffness = 40.0
        s.shear_stiffness = 5.0
        s.bending_stiffness = 10.0   # PVC ponjava je toga: velike gube, ne drobnih
        m.collision_settings.use_collision = True
        m.collision_settings.collision_quality = 5
        m.collision_settings.distance_min = 0.008
        m.collision_settings.use_self_collision = False
        m.point_cache.frame_start, m.point_cache.frame_end = 1, okvirjev
        m.collision_settings.collection = zb

        mt = bpy.data.meshes.new("PlahtaTrki")
        r = 20.0
        n0 = len(t)
        t = t + [(-r, -r, tla), (r, -r, tla), (r, r, tla), (-r, r, tla)]
        mt.from_pydata(t, [], f + [(n0, n0 + 1, n0 + 2, n0 + 3)])
        trk = bpy.data.objects.new("PlahtaTrki", mt)
        zb.objects.link(trk)
        novi.append(trk)
        trk.modifiers.new("Trk", "COLLISION")
        trk.collision.thickness_outer = 0.015
        trk.collision.cloth_friction = 5.0
        trk.collision.damping = 0.5

        okvirji = []
        konec = None
        for fr in range(1, okvirjev + 1):
            sc.frame_set(fr)
            dg = bpy.context.evaluated_depsgraph_get()
            ev = blago.evaluated_get(dg)
            em = ev.to_mesh()
            try:
                co = _koordinate(em) / MERILO
            finally:
                ev.to_mesh_clear()
            konec = co
            if fr == 1 or fr % vsak == 0 or fr == okvirjev:
                okvirji.append(np.round(co * 10).astype(np.int32).ravel().tolist())
        return okvirji, konec, time.time() - zacetek, fps / vsak
    finally:
        for x in novi:
            data = x.data
            bpy.data.objects.remove(x, do_unlink=True)
            if data is not None and data.users == 0:
                bpy.data.meshes.remove(data)
        bpy.data.collections.remove(zb)
        sc.gravity, sc.use_gravity, sc.render.fps, sc.render.fps_base = stari[1], stari[2], stari[3], stari[4]
        sc.frame_set(stari[0])


def spusti(obj, okvirjev=96):
    okvirji, konec, cas, fps = simuliraj(obj, okvirjev)
    _nastavi(obj.data, konec)
    obj[LASTNOST] = "dol"
    return okvirji, cas, fps


def ukaz(u):
    d = u.get("dejanje") or ""
    if not d.startswith("plahta-"):
        return None
    if d == "plahta-ustvari":
        obj = ustvari(u.get("vir") or "Prevleka PVC", float(u.get("korak") or KORAK), u.get("ime") or "Plahta (blago)")
        return {"ok": True, "ime": obj.name, "oglisc": len(obj.data.vertices)}
    obj = _plahta(u.get("ime"))
    if d == "plahta-dvigni":
        dvigni(obj)
        return {"ok": True, "ime": obj.name, "stanje": "gor", "sporocilo": "Plahta je dvignjena; spodaj lahko urejaš."}
    if d == "plahta-spusti":
        okvirji, cas, fps = spusti(obj, int(u.get("okvirjev") or 96))
        return {"ok": True, "ime": obj.name, "stanje": "dol", "okvirji": okvirji, "fps": fps,
                "sporocilo": "Plahta je padla (simulacija %.1f s)." % cas}
    return {"ok": False, "sporocilo": "neznano dejanje: %s" % d}
