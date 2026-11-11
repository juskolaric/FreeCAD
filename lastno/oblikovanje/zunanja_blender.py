# -*- coding: utf-8 -*-
"""Zunanja oblika, 2. korak (teče v Blenderju brez okna): iz mreže strojnega sestava (zunanja_izvoz.py) obdrži samo
ploskve, ki se vidijo od zunaj, jih poenostavi in shrani kot novo različico ideje v Oblikovanju.
Kliče ga zunanja_oblika.py; parametri: ZO_RECEPT (recept JSON), ZO_VHOD (mreza.npz + mreza.json).

Vidnost: iz vzorčnih točk vsake izvorne ploskve gredo žarki v 64 smeri; ploskev ostane, če jih dovolj pride ven
(prag `prag_vidnosti`, privzeto 1 %). Notranja stran pločevine, notranjost in vse za steklom tako odpade.
"""
import json
import math
import os
import sys
import time

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

MAPA = os.path.dirname(os.path.abspath(__file__))
if MAPA not in sys.path:
    sys.path.insert(0, MAPA)
import igrisce  # noqa: E402


def smeri(n=64):
    i = np.arange(n) + 0.5
    fi = np.arccos(1 - 2 * i / n)
    th = math.pi * (1 + 5 ** 0.5) * i
    return np.stack([np.cos(th) * np.sin(fi), np.sin(th) * np.sin(fi), np.cos(fi)], axis=1)


def vidne_ploskve(V, T, P, N, prag, korak=50.0, najvec=300, Z=None):
    """Vrne (vidna[ploskev] bool, smer[ploskev] vsota smeri, v katere žarki uidejo). N[trikotnik] = nalepka: nalepke
    ne zakrivajo ničesar (pločevina pod njimi ostane), same pa so preverjene proti vsemu."""
    tocke = [tuple(v) for v in V.tolist()]
    drevo_vse = BVHTree.FromPolygons(tocke, [tuple(t) for t in T.tolist()], epsilon=0.0)
    nezakriva = N | Z if Z is not None else N      # nalepke in prozorni kosi (pleksi) ne zakrivajo
    drevo_osnova = BVHTree.FromPolygons(tocke, [tuple(t) for t in T[~nezakriva].tolist()], epsilon=0.0) if nezakriva.any() else drevo_vse
    a, b, c = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
    plosc = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    st = int(P.max()) + 1
    red = np.argsort(P, kind="stable")
    meje = np.searchsorted(P[red], np.arange(st + 1))
    S = smeri()
    Sv = [Vector(s) for s in S.tolist()]
    rng = np.random.default_rng(1)
    vidna = np.zeros(st, dtype=bool)
    smer = np.zeros((st, 3))
    for f in range(st):
        tri = red[meje[f]:meje[f + 1]]
        if not len(tri):
            continue
        drevo = drevo_vse if N[tri[0]] else drevo_osnova
        pl = plosc[tri]
        skupaj = float(pl.sum())
        if skupaj <= 1e-9:
            continue
        n = int(min(najvec, max(8, skupaj / (korak * korak))))
        izbrani = tri[rng.choice(len(tri), size=n, p=pl / skupaj)]
        r1, r2 = np.sqrt(rng.random(n)), rng.random(n)
        tocke = (a[izbrani] * (1 - r1)[:, None] + b[izbrani] * (r1 * (1 - r2))[:, None] + c[izbrani] * (r1 * r2)[:, None])
        usli = np.zeros(len(S), dtype=np.int32)
        for t in tocke.tolist():
            o = Vector(t)
            for k, d in enumerate(Sv):
                if drevo.ray_cast(o + d * 0.02, d)[0] is None:
                    usli[k] += 1
        delez = usli.sum() / float(n * len(S))
        if delez >= prag:
            vidna[f] = True
            smer[f] = (S * usli[:, None]).sum(axis=0)
    return vidna, smer


def poenostavi(V, tri, gosto):
    """Mreža enega telesa: zlepi točke, združi soravne trikotnike; če jih ostane več kot `gosto`, razredči (Decimate)
    na približno en trikotnik na cm2 površine. Vrne (točke, trikotniki)."""
    uporabljene, nazaj = np.unique(tri, return_inverse=True)
    me = bpy.data.meshes.new("_kos")
    me.from_pydata(V[uporabljene].tolist(), [], nazaj.reshape(-1, 3).tolist())
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.02)
    bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(0.5), verts=bm.verts, edges=bm.edges)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    povrsina = sum(f.calc_area() for f in bm.faces)
    bm.to_mesh(me)
    bm.free()
    n = len(me.polygons)
    if n > gosto:
        cilj = max(gosto / 3.0, min(n, povrsina / 100.0))
        if cilj < n:
            obj = bpy.data.objects.new("_kos", me)
            bpy.context.scene.collection.objects.link(obj)
            mod = obj.modifiers.new("redcenje", "DECIMATE")
            mod.ratio = cilj / n
            nova = bpy.data.meshes.new_from_object(obj.evaluated_get(bpy.context.evaluated_depsgraph_get()))
            bpy.data.objects.remove(obj)
            bpy.data.meshes.remove(me)
            me = nova
    v = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", v)
    me.calc_loop_triangles()
    t = np.empty(len(me.loop_triangles) * 3, dtype=np.int32)
    me.loop_triangles.foreach_get("vertices", t)
    bpy.data.meshes.remove(me)
    return v.reshape(-1, 3), t.reshape(-1, 3)


def material(ime, m):
    mat = bpy.data.materials.new(ime)
    mat.use_nodes = True
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    barva = list(m.get("barva", (0.8, 0.8, 0.8)))[:3] + [1.0]
    bsdf.inputs["Base Color"].default_value = barva
    bsdf.inputs["Metallic"].default_value = float(m.get("kovinskost", 0.0))
    bsdf.inputs["Roughness"].default_value = float(m.get("hrapavost", 0.45))
    alfa = float(m.get("alfa", 1.0))
    if "prepustnost" in m:          # pleksi, steklo (od 2026-11-11)
        for vhod in ("Transmission Weight", "Transmission"):
            if vhod in bsdf.inputs:
                bsdf.inputs[vhod].default_value = float(m["prepustnost"])
                break
        if "IOR" in bsdf.inputs:
            bsdf.inputs["IOR"].default_value = float(m.get("ior", 1.49))
    if alfa < 1.0:
        bsdf.inputs["Alpha"].default_value = alfa
        for atr, vr in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
            if hasattr(mat, atr):
                try:
                    setattr(mat, atr, vr)
                except Exception:  # noqa: BLE001
                    pass
    mat.diffuse_color = barva[:3] + [alfa]
    return mat


def nalepka_iz_ploskev(scena, spec, materiali, kosi=()):
    """Nalepka iz zunanjih ploskev (recept "nalepke_ploskve", od 2026-11-11): ploskve objektov, katerih ime se začne z enim
    od `skupine`, z normalo v smeri `smer` (kosinus > `prag`), brez prozornih (pleksi), premaknjene `odmik` mm ven.
    Svoj objekt `ime` z materialom `material` in UV kot ravninska projekcija (u vodoravno, v navpično, 0..1 po okvirju), da
    se pozneje nanj položi grafika lokacije."""
    smer = Vector(spec["smer"]).normalized()
    prag = float(spec.get("prag", 0.5))
    odmik = float(spec.get("odmik", 0.5))
    predpone = [x.lower() for x in spec["skupine"]]
    bm = bmesh.new()
    for o in list(scena.objects):
        if o.type != "MESH" or not o.name.lower().startswith(tuple(predpone)):
            continue
        prozorni = {i for i, m in enumerate(o.data.materials) if m and m.name == materiali.get("_prozorno", {}).get("ime")}
        src = bmesh.new()
        src.from_mesh(o.data)
        src.transform(o.matrix_world)
        src.normal_update()
        sloj = src.faces.layers.int.get("kos")
        brez = [x.lower() for x in spec.get("brez", [])]      # deli imen kosov brez nalepke (ključavnica, zaklep)
        izbrane = [f for f in src.faces if f.material_index not in prozorni and f.normal.dot(smer) > prag
                   and not (brez and sloj is not None and any(x in kosi[f[sloj]].lower() for x in brez))]
        preslikava = {}
        for f in izbrane:
            vs = []
            for v in f.verts:
                if v.index not in preslikava:
                    preslikava[v.index] = bm.verts.new(v.co + smer * odmik)
                vs.append(preslikava[v.index])
            try:
                bm.faces.new(vs)
            except ValueError:
                pass
        src.free()
    if not bm.faces:
        bm.free()
        return None
    gor = Vector((0, 0, 1))
    u_os = gor.cross(smer).normalized() if abs(smer.dot(gor)) < 0.99 else Vector((1, 0, 0))
    us = [v.co.dot(u_os) for v in bm.verts]
    vs_ = [v.co.z for v in bm.verts]
    u0, u1, v0, v1 = min(us), max(us), min(vs_), max(vs_)
    uv = bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        for lp in f.loops:
            lp[uv].uv = ((lp.vert.co.dot(u_os) - u0) / max(u1 - u0, 1e-6), (lp.vert.co.z - v0) / max(v1 - v0, 1e-6))
    me = bpy.data.meshes.new(spec["ime"])
    bm.to_mesh(me)
    bm.free()
    m = spec.get("material", {"ime": "Nalepka", "barva": [0.9, 0.9, 0.9]})
    me.materials.append(bpy.data.materials.get(m.get("ime", "Nalepka")) or material(m.get("ime", "Nalepka"), m))
    obj = bpy.data.objects.new(spec["ime"], me)
    obj["nalepka"] = json.dumps({"smer": list(smer), "okvir_u": [u0, u1], "okvir_v": [v0, v1], "u_os": list(u_os)})
    scena.collection.objects.link(obj)
    return obj


def main():
    with open(os.environ["ZO_RECEPT"], encoding="utf-8") as f:
        recept = json.load(f)
    vhod = os.environ["ZO_VHOD"]
    with open(os.path.splitext(vhod)[0] + ".json", encoding="utf-8") as f:
        meta = json.load(f)
    d = np.load(vhod)
    V, T, P, G, K = d["tocke"].astype(np.float64), d["trikotniki"], d["ploskev"], d["skupina"], d["telo"]
    M = d["kos"]
    N = d["nalepka"] if "nalepka" in d else np.zeros(len(T), dtype=bool)
    Z = d["prozoren"] if "prozoren" in d else np.zeros(len(T), dtype=bool)

    t0 = time.time()
    vidna, smer = vidne_ploskve(V, T, P, N, float(recept.get("prag_vidnosti", 0.01)), Z=Z)
    print("vidnost: %d od %d ploskev, %.1f s" % (int(vidna.sum()), len(vidna), time.time() - t0), flush=True)

    ostane = vidna[P]
    T, P, G, K, M, Z = T[ostane], P[ostane], G[ostane], K[ostane], M[ostane], Z[ostane]
    nrm = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
    obrni = (nrm * smer[P]).sum(axis=1) < 0          # normala naj kaže ven (v smer, kamor žarki uidejo)
    T[obrni] = T[obrni][:, ::-1]

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scena = bpy.context.scene
    us = scena.unit_settings
    us.system, us.scale_length, us.length_unit = "METRIC", 0.001, "MILLIMETERS"
    materiali = recept.get("materiali", {})
    povzetek = []
    gosto = int(recept.get("najvec_trikotnikov_kosa", 1500))
    for sid, ime in enumerate(meta["skupine"]):
        if not (G == sid).any():
            continue
        tocke, lica, st, reze, snovi, kos_lic = [], [], 0, [], [], []
        for kos in np.unique(K[G == sid]):         # vsako telo posebej: gosto mrežo (ključavnica, gumb) razredči
            izbor = (G == sid) & (K == kos)
            v, t = poenostavi(V, T[izbor], gosto)
            if len(t):
                ime_kosa = meta["kosi"][int(M[izbor][0])]
                snov = next(k for k in (ime_kosa, ime, "*") if k in materiali or k == "*")
                for i_v, (vzorec, m_v) in enumerate(recept.get("materiali_vzorci", [])):   # del imena kosa -> material
                    if vzorec.lower() in ime_kosa.lower():
                        snov = "_vzorec%d" % i_v
                        materiali.setdefault(snov, m_v)
                        break
                if Z[izbor].any() and "prozorno" in recept:      # pleksi (recept "prozorni")
                    snov = "_prozorno"
                    materiali.setdefault("_prozorno", recept["prozorno"])
                if snov not in snovi:
                    snovi.append(snov)
                reze.extend([snovi.index(snov)] * len(t))
                kos_lic.extend([int(M[izbor][0])] * len(t))
                tocke.append(v)
                lica.append(t + st)
                st += len(v)
        if not lica:
            continue
        me = bpy.data.meshes.new(ime)
        me.from_pydata(np.concatenate(tocke).tolist(), [], np.concatenate(lica).tolist())
        me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
        me.set_sharp_from_angle(angle=math.radians(30))
        for snov in snovi:          # ista snov (ključ recepta) = en material v datoteki
            ime_mat = materiali.get(snov, {}).get("ime") or ("Osnova" if snov == "*" else snov)
            me.materials.append(bpy.data.materials.get(ime_mat) or material(ime_mat, materiali.get(snov) or {}))
        me.polygons.foreach_set("material_index", reze)
        me.attributes.new("kos", "INT", "FACE").data.foreach_set("value", kos_lic)   # indeks v meta["kosi"] (nalepke: brez)
        me.update()
        obj = bpy.data.objects.new(ime, me)
        scena.collection.objects.link(obj)
        if ime == "Nalepke":            # nalepke se modelirajo posebej; osnovna oblika je brez njih
            obj.hide_viewport = obj.hide_render = True
        povzetek.append("%s %d" % (ime, len(me.polygons)))
    for spec in recept.get("nalepke_ploskve", []):
        obj = nalepka_iz_ploskev(scena, spec, materiali, meta["kosi"])
        if obj is not None:
            povzetek.append("%s %d" % (obj.name, len(obj.data.polygons)))
    ploskev = sum(len(o.data.polygons) for o in scena.objects)
    scena["zunanja_oblika"] = json.dumps({"sestav": meta["sestav"], "odtis": meta["odtis"]}, ensure_ascii=False)

    koren = os.path.join(os.path.expanduser("~"), "Oblak", "3D modeliranje", "Oblikovanje")
    koren = os.environ.get("SPLET_OBLIKOVANJE_MAPA") or koren
    projekt = os.path.join(koren, "Projekti", igrisce.varno_ime(recept["projekt_oblikovanja"], "Projekt"))
    ideje = igrisce.Ideje(koren)
    ideje.nastavi_koren(projekt)
    mapa = os.path.join(ideje.koren, igrisce.varno_ime(recept["ideja"]))
    if os.path.isfile(os.path.join(mapa, "ideja.json")):
        ideje.mapa = mapa
        ideje.razlicica = ideje.podatki().get("aktivna", "")
    else:
        ideje.nova(recept["ideja"], recept.get("opis", ""))
    okvir = meta.get("okvir") or [[0, 0, 0], [0, 0, 0]]
    mere = " × ".join("%.0f" % (okvir[1][i] - okvir[0][i]) for i in range(3))
    cas = time.strftime("%d. %m. %Y %H:%M", time.localtime(meta["sestav_mtime"]))
    rid = ideje.shrani_razlicico("Iz strojnega sestava %s (shranjen %s): %d objektov, %d ploskev, okvir %s mm; odtis %s"
                                 % (os.path.basename(meta["sestav"]), cas, len(scena.objects), ploskev, mere, meta["odtis"]),
                                 "strojni model")
    with open(os.path.join(ideje.mapa, "vir.json"), "w", encoding="utf-8") as f:
        json.dump({"sestav": meta["sestav"], "sestav_mtime": meta["sestav_mtime"], "odtis": meta["odtis"],
                   "razlicica": rid, "recept_odtis": os.environ.get("ZO_RECEPT_ODTIS", ""), "cas": time.strftime("%Y-%m-%dT%H:%M:%S"), "ploskev": ploskev,
                   "recept": os.environ["ZO_RECEPT"]}, f, ensure_ascii=False, indent=1)
    print("KONEC: %s %s, %d ploskev (%s), %.1f s" % (recept["ideja"], rid, ploskev, ", ".join(povzetek), time.time() - t0), flush=True)


try:
    main()
except Exception:  # noqa: BLE001
    import traceback
    traceback.print_exc()
    sys.stdout.flush()
    os._exit(1)
