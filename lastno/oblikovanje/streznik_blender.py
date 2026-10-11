# -*- coding: utf-8 -*-
"""Oblikovanje: Blender kot drugi motor spletnega 3D programa (prosto oblikovanje mrež, render).

Zagon (brez okna; običajno ga zažene strežnik spletnega FreeCAD-a, POST /oblikovanje/zazeni):
    blender.exe -b --factory-startup --python lastno/oblikovanje/streznik_blender.py [-- --vrata 3030]
Stran: http://127.0.0.1:3030/ (v spletnem FreeCAD-u zavihek »Oblikovanje« kot okvir).

Zgradba (enako pravilo kot lastno/splet/streznik.py):
  - HTTP strežnik teče v svoji niti in bpy NIKOLI ne kliče: bere le pripravljen posnetek (bajti JSON), zahteve odloži
    v vrsto. Glavna nit Blenderja (zanka spodaj, Blender je v načinu -b) obdela vrsto in po vsaki spremembi zgradi
    nov posnetek mreže (z modifikatorji, kot jo vidi render).
  - Enote: 1 enota Blenderja = 1 mm (kot FreeCAD), prikaz v mm.
  - AI in skripte: POST /python {koda} (izvedi.py v tej mapi), v imenskem prostoru so bpy, bmesh, np, Vector, Matrix,
    math in pomočniki iz tega modula (dodaj_obliko, gladko, pocisti); spremenljivka `rezultat` gre nazaj.
  - Render: kopija scene (.blend) gre v ločen proces Blenderja (upodabljanje.py, render.py), zato oblikovanje med
    renderjem teče naprej.
  - Igrišče (faza 3, igrisce.py): ideje z različicami (Oblikovanje/Ideje/<ime>/R01.blend …), parametrična oblika z
    drsniki (besedilo »oblika.py« z zgradi(p) + lastnost scene »parametri«), AI oblikovalec (ai_oblikovalec.py: Claude
    gradi, gleda in popravlja; orodja tečejo na glavni niti prek na_glavni), Odpri v Blenderju (okno Blenderja z
    različico; ko jo tam shraniš, se vrne kot nova različica).
  - Varnost: vsak POST potrebuje žeton (glava X-Zeton), ki je vpisan v stran in v povezava.json.
"""

import contextlib
import http.server
import io
import json
import math
import os
import queue
import secrets
import sys
import threading
import time
import traceback
import urllib.parse

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

MAPA = os.path.dirname(os.path.abspath(__file__))
if MAPA not in sys.path:
    sys.path.insert(0, MAPA)
from upodabljanje import UPODABLJANJE, DELOVNA, najdi_blender  # noqa: E402
import igrisce  # noqa: E402
from ai_oblikovalec import AIOblikovalec  # noqa: E402


def _argument(ime, privzeto):
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if ime in argv and argv.index(ime) + 1 < len(argv):
        return argv[argv.index(ime) + 1]
    return privzeto


VRATA = int(_argument("--vrata", os.environ.get("OBLIKOVANJE_VRATA", "3030")))
ZETON = secrets.token_hex(16)
LOKALNO = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "FreeCAD-splet")
POVEZAVA = os.path.join(LOKALNO, "oblikovanje.json")
DNEVNIK = os.path.join(LOKALNO, "oblikovanje.log")
# Mapa z datotekami oblikovanja (.blend), renderji v podmapi Renderji. Prepis: SPLET_OBLIKOVANJE_MAPA.
MAPA_DATOTEK = os.environ.get("SPLET_OBLIKOVANJE_MAPA") or os.path.join(
    os.path.expanduser("~"), "Oblak", "3D modeliranje", "Oblikovanje")
VRSTE_GEOMETRIJE = {"MESH", "CURVE", "SURFACE", "META", "FONT", "CURVES"}


def _log(besedilo):
    vrstica = time.strftime("%H:%M:%S ") + besedilo
    print(vrstica, flush=True)
    try:
        with open(DNEVNIK, "a", encoding="utf-8") as f:
            f.write(vrstica + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------------------------------------------------------
# Scena

def nastavi_enote(scena=None):
    scena = scena or bpy.context.scene
    us = scena.unit_settings
    us.system = "METRIC"
    us.scale_length = 0.001
    us.length_unit = "MILLIMETERS"


def nova_scena():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    nastavi_enote()
    STANJE.datoteka = ""
    STANJE.spremenjeno = False


def srgb(c):
    c = max(0.0, min(1.0, c))
    return c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def videz_materiala(mat):
    """Barva (sRGB), kovinskost, hrapavost in prosojnost iz Principled BSDF (ali barve materiala)."""
    barva, kov, hrap, alfa = list(mat.diffuse_color[:3]) if mat else [0.8, 0.8, 0.8], 0.0, 0.45, 1.0
    if mat is not None and mat.node_tree is not None:
        for n in mat.node_tree.nodes:
            if n.type == "BSDF_PRINCIPLED":
                # barva iz vozlišč (tekstura, preliv): privzeta vrednost vhoda ni barva; vzemi barvo materiala v pogledu
                vir = n.inputs["Base Color"]
                barva = list(mat.diffuse_color[:3]) if vir.is_linked else list(vir.default_value[:3])
                kov = float(n.inputs["Metallic"].default_value)
                hrap = float(n.inputs["Roughness"].default_value)
                alfa = float(n.inputs["Alpha"].default_value)
                vir_t = n.inputs.get("Transmission Weight") or n.inputs.get("Transmission")
                if vir_t is not None and float(vir_t.default_value) > 0.5:
                    alfa = min(alfa, 0.18)    # steklo, pleksi: v pogledu prosojno (render ga riše s prepustnostjo)
                break
    return {"barva": [round(srgb(c), 4) for c in barva], "kovinskost": round(kov, 3),
            "hrapavost": round(hrap, 3), "prosojnost": round(1 - alfa, 3)}


def preliv_po_visini(mat):
    """(rampa, od, do), če je osnovna barva preliv (ColorRamp) po višini Z koordinat objekta (Map Range iz Separate XYZ.Z),
    sicer None. Pogled tak material pokaže z barvami po ogliščih (oblaki, valovi in ostale teksture se ne vidijo)."""
    if mat is None or mat.node_tree is None:
        return None
    for n in mat.node_tree.nodes:
        if n.type != "VALTORGB" or not n.inputs["Fac"].is_linked:
            continue
        mr = n.inputs["Fac"].links[0].from_node
        if mr.type != "MAP_RANGE" or not mr.inputs["Value"].is_linked:
            continue
        sep = mr.inputs["Value"].links[0]
        if sep.from_node.type == "SEPXYZ" and sep.from_socket.name == "Z":
            return n.color_ramp, float(mr.inputs["From Min"].default_value), float(mr.inputs["From Max"].default_value)
    return None


def posnetek_objekta(obj, dg):
    """Mreža objekta (z modifikatorji) v svetovnih koordinatah: točke, normale (gladko/ostro po robovih), trikotniki
    po materialih. Točke so podvojene le, kjer se normale ločijo (ostri robovi)."""
    ev = obj.evaluated_get(dg)
    try:
        mreza = ev.to_mesh()
    except RuntimeError:
        return None
    try:
        if mreza is None or not len(mreza.polygons):
            return None
        mreza.calc_loop_triangles()
        nt = len(mreza.loop_triangles)
        zanke = np.empty(nt * 3, dtype=np.int32)
        mreza.loop_triangles.foreach_get("loops", zanke)
        mat_idx = np.empty(nt, dtype=np.int32)
        mreza.loop_triangles.foreach_get("material_index", mat_idx)
        nl = len(mreza.loops)
        oglisce = np.empty(nl, dtype=np.int32)
        mreza.loops.foreach_get("vertex_index", oglisce)
        normale = np.empty(nl * 3, dtype=np.float32)
        try:
            mreza.corner_normals.foreach_get("vector", normale)
        except (AttributeError, RuntimeError):   # Blender pred 4.1
            mreza.calc_normals_split()
            mreza.loops.foreach_get("normal", normale)
        normale = normale.reshape(-1, 3)
        co = np.empty(len(mreza.vertices) * 3, dtype=np.float32)
        mreza.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        co_lok = co.copy()
        m = np.array(ev.matrix_world, dtype=np.float32)
        co = co @ m[:3, :3].T + m[:3, 3]
        nm = np.linalg.inv(m[:3, :3]).T
        normale = normale @ nm.T
        normale /= np.maximum(np.linalg.norm(normale, axis=1, keepdims=True), 1e-12)
        # trikotniki po materialih, oglišča zank združena po (oglišče, normala)
        red = np.argsort(mat_idx, kind="stable")
        mat_idx = mat_idx[red]
        zanke = zanke.reshape(-1, 3)[red].ravel()
        kljuc = np.concatenate([oglisce[zanke, None], np.round(normale[zanke] * 1000).astype(np.int32)], axis=1)
        _, prvi, inverz = np.unique(kljuc, axis=0, return_index=True, return_inverse=True)
        izbrane = zanke[prvi]
        tocke = co[oglisce[izbrane]]
        norm = normale[izbrane]
        skupine = []
        if nt:
            meje = np.flatnonzero(np.diff(mat_idx)) + 1
            zacetki = np.concatenate([[0], meje])
            konci = np.concatenate([meje, [nt]])
            for z, k in zip(zacetki, konci):
                skupine.append([int(z), int(k - z), int(mat_idx[z])])
        materiali = []
        barve = None
        for i in range(max(len(obj.material_slots), 1)):
            mat = obj.material_slots[i].material if i < len(obj.material_slots) else None
            materiali.append(videz_materiala(mat))
            preliv = preliv_po_visini(mat)
            if preliv is None:
                continue
            rampa, od, do = preliv
            if barve is None:
                barve = np.ones((len(tocke), 3), dtype=np.float32)
            materiali[-1]["barva"] = [1.0, 1.0, 1.0]
            materiali[-1]["poOgliscih"] = True
            # oglišča trikotnikov tega materiala: barva iz preliva (16 korakov tabele, nato interpolacija)
            tri = inverz.reshape(-1, 3)
            ogl = np.unique(tri[mat_idx == i].ravel())
            tabela_t = np.linspace(0.0, 1.0, 65)
            tabela = np.array([[srgb(c) for c in rampa.evaluate(float(t))[:3]] for t in tabela_t], dtype=np.float32)
            t = np.clip((co_lok[oglisce[izbrane[ogl]], 2] - od) / max(do - od, 1e-6), 0.0, 1.0)
            barve[ogl] = np.stack([np.interp(t, tabela_t, tabela[:, k]) for k in range(3)], axis=1)
        mn, mx = tocke.min(axis=0), tocke.max(axis=0)
        dodatno = {"barve": np.round(barve.astype(np.float64), 3).ravel().tolist()} if barve is not None else {}
        return {
            **dodatno,
            "ime": obj.name,
            "tocke": np.round(tocke.astype(np.float64), 3).ravel().tolist(),
            "normale": np.round(norm.astype(np.float64), 3).ravel().tolist(),
            "trikotniki": inverz.ravel().astype(np.int64).tolist(),
            "skupine": skupine,
            "materiali": materiali,
            "okvir": [np.round(mn.astype(np.float64), 3).tolist(), np.round(mx.astype(np.float64), 3).tolist()],
        }
    finally:
        ev.to_mesh_clear()


# Predpomnilnik posnetkov objektov: ključ -> JSON objekta. Ključ zajame ime, podatke, lego, materiale in modifikatorje;
# poljubna koda (POST /python, izvedi_kodo, uvoz) ga izprazni, ker lahko spremeni mrežo na mestu. Drsnik zgradi znova le
# zbirko Oblika (nova imena podatkov), uvoženi kosi (Slim A: 360 tisoč trikotnikov) ostanejo iz predpomnilnika.
_PREDPOMNILNIK = {}


def _kljuc_objekta(obj):
    try:
        st = len(obj.data.vertices) if obj.type == "MESH" else 0
    except AttributeError:
        st = 0
    return (obj.name, obj.data.name if obj.data else "", st, tuple(round(x, 4) for vr in obj.matrix_world for x in vr),
            tuple((sl.material.name if sl.material else "") for sl in obj.material_slots),
            tuple((m.type, m.show_viewport) for m in obj.modifiers), obj.data.is_editmode if hasattr(obj.data, "is_editmode") else False)


def zgradi_posnetek():
    zacetek = time.time()
    dg = bpy.context.evaluated_depsgraph_get()
    objekti, seznam = [], []
    zadetkov = 0
    for obj in bpy.context.scene.objects:
        if obj.type not in VRSTE_GEOMETRIJE:
            continue
        vidno = not obj.hide_get() and not obj.hide_viewport
        seznam.append({"ime": obj.name, "vrsta": obj.type, "vidno": vidno,
                       "modifikatorji": [mod.type for mod in obj.modifiers],
                       "izbran": obj.select_get()})
        if not vidno:
            continue
        # objekti parametrične oblike se ob drsniku zgradijo znova z istim imenom in istim številom točk: brez predpomnilnika
        kljuc = None if any(z.name == igrisce.ZBIRKA for z in obj.users_collection) else _kljuc_objekta(obj)
        if kljuc is not None and kljuc in _PREDPOMNILNIK:
            objekti.append(_PREDPOMNILNIK[kljuc])
            zadetkov += 1
            continue
        try:
            p = posnetek_objekta(obj, dg)
        except Exception:  # noqa: BLE001
            _log("objekt %s: %s" % (obj.name, traceback.format_exc()))
            p = None
        if p:
            p = json.dumps(p, separators=(",", ":"))
            if kljuc is not None:
                _PREDPOMNILNIK[kljuc] = p
            objekti.append(p)
    STANJE.verzija += 1
    STANJE.parametri = igrisce.parametri()
    STANJE.ima_obliko = bool(igrisce.koda_oblike())
    if len(_PREDPOMNILNIK) > 400:
        _PREDPOMNILNIK.clear()
    glava = json.dumps({"verzija": STANJE.verzija, "seznam": seznam, "datoteka": STANJE.datoteka,
                        "parametri": STANJE.parametri, "imaObliko": STANJE.ima_obliko}, separators=(",", ":"))
    STANJE.posnetek = (glava[:-1] + ',"objekti":[' + ",".join(objekti) + "]}").encode("utf-8")
    STANJE.seznam = seznam
    _log("posnetek %d: %d objektov (%d iz predpomnilnika), %.0f kB, %.2f s" % (
        STANJE.verzija, len(objekti), zadetkov, len(STANJE.posnetek) / 1024, time.time() - zacetek))


# ---------------------------------------------------------------------------------------------------------------
# Pomočniki za skripte (AI) in gumbe na strani

def gladko(obj, nivo=2, nivo_render=3):
    """Gladka kletka: Subdivision Surface in gladko senčenje (Catmull-Clark)."""
    mod = obj.modifiers.get("Gladko") or obj.modifiers.new("Gladko", "SUBSURF")
    mod.levels, mod.render_levels = nivo, nivo_render
    if obj.type == "MESH":
        try:
            obj.data.shade_smooth()
        except AttributeError:
            obj.data.polygons.foreach_set("use_smooth", [True] * len(obj.data.polygons))
    return obj


def _nov_objekt(ime, mreza):
    obj = bpy.data.objects.new(ime, mreza)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def material(ime, barva=(0.8, 0.8, 0.8), kovinskost=0.0, hrapavost=0.4):
    """Material Principled BSDF; barva v sRGB (0..1) kot v FreeCAD-u."""
    mat = bpy.data.materials.get(ime) or bpy.data.materials.new(ime)
    try:
        mat.use_nodes = True
    except Exception:  # noqa: BLE001
        pass
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in barva]
    bsdf.inputs["Base Color"].default_value = (*lin, 1.0)
    bsdf.inputs["Metallic"].default_value = kovinskost
    bsdf.inputs["Roughness"].default_value = hrapavost
    mat.diffuse_color = (*lin, 1.0)
    return mat


def dodaj_obliko(vrsta, velikost=40.0, lega=(0, 0, 0), ime=None):
    """Osnovno telo (mm): kocka (gladka kletka), krogla, valj, torus, stozec, kaplja (metaball)."""
    r = velikost / 2.0
    bm = bmesh.new()
    if vrsta == "kaplja":
        mb = bpy.data.metaballs.new(ime or "Kaplja")
        mb.resolution = velikost / 20.0
        mb.render_resolution = velikost / 40.0
        for i, (x, z, rr) in enumerate([(0, 0, r), (r * 0.9, r * 0.2, r * 0.7), (-r * 0.6, r * 0.5, r * 0.6)]):
            el = mb.elements.new()
            el.co = (x, 0, z)
            el.radius = rr
        obj = _nov_objekt(ime or "Kaplja", mb)
    else:
        if vrsta == "kocka":
            bmesh.ops.create_cube(bm, size=velikost)
        elif vrsta == "krogla":
            bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=24, radius=r)
        elif vrsta == "valj":
            bmesh.ops.create_cone(bm, cap_ends=True, segments=48, radius1=r, radius2=r, depth=velikost)
        elif vrsta == "stozec":
            bmesh.ops.create_cone(bm, cap_ends=True, segments=48, radius1=r, radius2=0, depth=velikost)
        elif vrsta == "torus":
            R, rr, nu, nv = r * 0.75, r * 0.25, 48, 24
            krogi = []
            for i in range(nu):
                a = 2 * math.pi * i / nu
                krog = []
                for j in range(nv):
                    b = 2 * math.pi * j / nv
                    krog.append(bm.verts.new(((R + rr * math.cos(b)) * math.cos(a), (R + rr * math.cos(b)) * math.sin(a),
                                              rr * math.sin(b))))
                krogi.append(krog)
            for i in range(nu):
                for j in range(nv):
                    a, b = krogi[i], krogi[(i + 1) % nu]
                    bm.faces.new((a[j], b[j], b[(j + 1) % nv], a[(j + 1) % nv]))
        else:
            bm.free()
            raise ValueError("neznana oblika: %s" % vrsta)
        mreza = bpy.data.meshes.new(ime or vrsta.capitalize())
        bm.to_mesh(mreza)
        bm.free()
        obj = _nov_objekt(ime or vrsta.capitalize(), mreza)
        if vrsta == "kocka":
            gladko(obj)
        else:
            try:
                mreza.shade_smooth()
            except AttributeError:
                pass
    obj.location = lega
    return obj


def pocisti():
    """Odstrani vse objekte iz scene (nova prazna scena z enotami mm)."""
    nova_scena()


# ---------------------------------------------------------------------------------------------------------------
# Stanje in vrsta

class Stanje:
    def __init__(self):
        self.vrsta = queue.Queue()
        self.posnetek = b'{"verzija":0,"objekti":[],"seznam":[]}'
        self.seznam = []
        self.verzija = 0
        self.datoteka = ""
        self.spremenjeno = False
        self.umazano = True
        self.konec = False
        self.napaka = ""
        self.parametri = []
        self.ima_obliko = False
        self.verzija_ideje = 0
        self.zunanje = None          # {"pot", "mtime", "izhaja"}: različica, odprta v oknu Blenderja

    def stanje(self):
        return {"verzija": self.verzija, "datoteka": self.datoteka,
                "ime": os.path.splitext(os.path.basename(self.datoteka))[0] if self.datoteka else "",
                "spremenjeno": self.spremenjeno, "mapa": MAPA_DATOTEK, "blender": bpy.app.version_string,
                "napaka": self.napaka, "verzijaIdeje": self.verzija_ideje,
                "ideja": os.path.basename(IDEJE.mapa) if IDEJE.mapa else "", "razlicica": IDEJE.razlicica,
                "vBlenderju": bool(self.zunanje), "ai": AI.stanje}


STANJE = Stanje()


def _imenski_prostor():
    return {"bpy": bpy, "bmesh": bmesh, "np": np, "Vector": Vector, "Matrix": Matrix, "math": math,
            "dodaj_obliko": dodaj_obliko, "gladko": gladko, "material": material, "pocisti": pocisti,
            "nov_objekt": _nov_objekt, "nastavi_enote": nastavi_enote, "C": bpy.context, "D": bpy.data, "rezultat": None}


def _pot_datoteke(ime):
    ime = "".join("_" if (c in '<>:"/\\|?*' or ord(c) < 32) else c for c in str(ime)).strip(" .") or "Oblika"
    return os.path.join(MAPA_DATOTEK, ime if ime.lower().endswith(".blend") else ime + ".blend")


def obdelaj(vrsta, podatki, odgovor):
    izpis = io.StringIO()
    try:
        with contextlib.redirect_stdout(izpis):
            if vrsta == "klic":
                odgovor["rezultat"] = podatki()
            elif vrsta == "python":
                _PREDPOMNILNIK.clear()
                ns = _imenski_prostor()
                exec(compile(podatki.get("koda", ""), "<oblikovanje>", "exec"), ns)
                odgovor["rezultat"] = ns.get("rezultat")
            elif vrsta == "ukaz":
                odgovor["rezultat"] = ukaz(podatki)
            elif vrsta == "render":
                odgovor["rezultat"] = zacni_render(podatki)
        if vrsta in ("python", "ukaz"):
            STANJE.spremenjeno = STANJE.spremenjeno or podatki.get("dejanje") not in BREZ_SPREMEMBE
            STANJE.umazano = True
        elif vrsta == "klic":
            STANJE.umazano = True
    except Exception:  # noqa: BLE001
        odgovor["napaka"] = traceback.format_exc()
        STANJE.umazano = True
    odgovor["izpis"] = izpis.getvalue()


BREZ_SPREMEMBE = ("shrani", "odpri", "nova", "izvozi", "izvozi-za-tisk", "izberi", "nova-ideja", "odpri-idejo", "shrani-razlicico",
                  "odpri-razlicico", "uredi-razlicico", "odpri-v-blenderju")


ZADNJA_IDEJA = os.path.join(LOKALNO, "oblikovanje-zadnja.json")


def _po_ideji():
    _PREDPOMNILNIK.clear()      # odprta druga različica ima lahko ista imena objektov z drugo geometrijo
    STANJE.verzija_ideje += 1
    try:   # ob naslednjem zagonu se odpre ista ideja
        with open(ZADNJA_IDEJA, "w", encoding="utf-8") as f:
            json.dump({"ideja": os.path.basename(IDEJE.mapa) if IDEJE.mapa else ""}, f, ensure_ascii=False)
    except OSError:
        pass
    AI.nalozi(IDEJE.mapa)
    STANJE.datoteka = os.path.join(IDEJE.mapa, IDEJE.razlicica + ".blend") if IDEJE.razlicica else ""


def ukaz_ideje(p):
    d = p.get("dejanje")
    if d in ("nova-ideja", "odpri-idejo", "odpri-razlicico") and AI.stanje == "dela":
        return {"ok": False, "sporocilo": "Claude še dela; počakaj ali ga ustavi."}
    if d == "nova-ideja":
        ime = IDEJE.nova(p.get("ime") or "Ideja", p.get("opis", ""))
        if not p.get("obdrzi"):
            nova_scena()
        _po_ideji()
        STANJE.spremenjeno = False
        return {"ok": True, "ime": ime}
    if d == "odpri-idejo":
        IDEJE.odpri(p.get("ime", ""))
        _po_ideji()
        STANJE.spremenjeno = False
        return {"ok": True}
    if d == "shrani-razlicico":
        rid = IDEJE.shrani_razlicico(p.get("opomba", ""), p.get("vir", "roka"))
        _po_ideji()
        STANJE.spremenjeno = False
        return {"ok": True, "id": rid}
    if d == "odpri-razlicico":
        IDEJE.odpri_razlicico(p.get("id", ""))
        _po_ideji()
        STANJE.spremenjeno = False
        return {"ok": True}
    if d == "uredi-razlicico":
        polja = {k: p[k] for k in ("zvezdica", "opomba") if k in p}
        IDEJE.uredi_razlicico(p.get("id", ""), **polja)
        STANJE.verzija_ideje += 1
        return {"ok": True}
    if d == "parameter":
        igrisce.zgradi_obliko(_imenski_prostor(), p.get("vrednosti") or {})
        return {"ok": True}
    if d == "odpri-v-blenderju":
        return odpri_v_blenderju()
    return None


def odpri_v_blenderju():
    """Trenutno sceno odpre v oknu Blenderja (dovoljeno, 2026-10-10). Ko jo tam shraniš, se vrne kot nova različica."""
    import subprocess
    if not IDEJE.mapa:
        return {"ok": False, "sporocilo": "Najprej odpri ali ustvari idejo."}
    pot = os.path.join(IDEJE.mapa, "_v_blenderju.blend")
    bpy.ops.wm.save_as_mainfile(filepath=pot, copy=True, compress=False)
    blender = najdi_blender() or bpy.app.binary_path
    okolje = {k: v for k, v in os.environ.items() if k not in ("PYTHONHOME", "PYTHONPATH")}
    proces = subprocess.Popen([blender, pot], cwd=IDEJE.mapa, env=okolje, close_fds=True,
                              creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    STANJE.zunanje = {"pot": pot, "mtime": os.path.getmtime(pot), "izhaja": IDEJE.razlicica, "proces": proces}
    STANJE.verzija_ideje += 1
    return {"ok": True, "sporocilo": "Blender se odpira. Ko obliko tam shraniš (Ctrl+S), se vrne sem kot nova različica."}


def preveri_zunanje():
    z = STANJE.zunanje
    if not z:
        return
    zaprto = z["proces"].poll() is not None
    try:
        mtime = os.path.getmtime(z["pot"])
    except OSError:
        mtime = 0.0
    if mtime <= z["mtime"] + 0.01:
        if zaprto:   # okno Blenderja je zaprto brez shranjevanja
            STANJE.zunanje = None
            STANJE.verzija_ideje += 1
        return
    time.sleep(0.5)   # Blender še piše
    z["mtime"] = os.path.getmtime(z["pot"])
    igrisce.nalozi_blend(z["pot"])
    IDEJE.razlicica = z.get("izhaja", "")
    rid = IDEJE.shrani_razlicico("Ročno urejeno v Blenderju", "Blender")
    _po_ideji()
    STANJE.umazano = True
    _log("različica %s iz okna Blenderja" % rid)
    if zaprto:
        STANJE.zunanje = None


def ukaz(p):
    d = p.get("dejanje")
    izid = ukaz_ideje(p)
    if izid is not None:
        return izid
    if d == "nova":
        nova_scena()
        return {"ok": True}
    if d == "dodaj":
        obj = dodaj_obliko(p.get("vrsta", "kocka"), float(p.get("velikost") or 40))
        izberi(obj.name)
        return {"ok": True, "ime": obj.name}
    if d == "izberi":
        izberi(p.get("ime"), bool(p.get("dodaj")))
        return {"ok": True}
    if d == "vidnost":
        obj = bpy.data.objects.get(p.get("ime") or "")
        if obj:
            obj.hide_set(not p.get("vidno", True))
            obj.hide_render = not p.get("vidno", True)
        return {"ok": bool(obj)}
    if d == "odstrani":
        obj = bpy.data.objects.get(p.get("ime") or "")
        if obj:
            bpy.data.objects.remove(obj, do_unlink=True)
        return {"ok": bool(obj)}
    if d == "shrani":
        pot = _pot_datoteke(p["ime"]) if p.get("ime") else STANJE.datoteka
        if not pot:
            return {"ok": False, "sporocilo": "Datoteka še nima imena."}
        os.makedirs(os.path.dirname(pot), exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=pot, compress=True)
        STANJE.datoteka, STANJE.spremenjeno = pot, False
        return {"ok": True, "pot": pot}
    if d == "odpri":
        pot = p.get("pot") or ""
        if not (os.path.isfile(pot) and pot.lower().endswith(".blend")):
            return {"ok": False, "sporocilo": "Ni datoteke .blend."}
        bpy.ops.wm.open_mainfile(filepath=pot)
        nastavi_enote()
        STANJE.datoteka, STANJE.spremenjeno = pot, False
        return {"ok": True}
    if d == "izvozi-za-tisk":
        # 3D natisni: STL vidnih objektov v FreeCAD-splet/tisk; v vhod plošče Tiskaj ga prestavi strežnik FreeCAD-a
        ime = os.path.basename(IDEJE.mapa) if IDEJE.mapa else (os.path.splitext(os.path.basename(STANJE.datoteka))[0] or "Oblika")
        ime = "".join("_" if (c in '<>:"/\\|?*' or ord(c) < 32) else c for c in ime).strip(" .") or "Oblika"
        mapa = os.path.join(LOKALNO, "tisk")
        os.makedirs(mapa, exist_ok=True)
        pot = os.path.join(mapa, ime + ".stl")
        izvozi_stl(pot)
        return {"ok": True, "pot": pot}
    if d == "izvozi":
        # STL za tisk: vidni objekti z modifikatorji, v mm
        ime = p.get("ime") or (os.path.splitext(os.path.basename(STANJE.datoteka))[0] if STANJE.datoteka else "Oblika")
        pot = os.path.join(MAPA_DATOTEK, "Izvoz", _pot_datoteke(ime).rsplit(os.sep, 1)[1][:-6] + ".stl")
        os.makedirs(os.path.dirname(pot), exist_ok=True)
        izvozi_stl(pot)
        return {"ok": True, "pot": pot}
    return {"ok": False, "sporocilo": "neznano dejanje: %s" % d}


def izberi(ime, dodaj=False):
    if not dodaj:
        for o in bpy.context.scene.objects:
            o.select_set(False)
    obj = bpy.data.objects.get(ime or "")
    if obj is not None:
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj


def izvozi_stl(pot):
    dg = bpy.context.evaluated_depsgraph_get()
    tocke, trik = [], []
    for obj in bpy.context.scene.objects:
        if obj.type not in VRSTE_GEOMETRIJE or obj.hide_get():
            continue
        ev = obj.evaluated_get(dg)
        mreza = ev.to_mesh()
        try:
            mreza.calc_loop_triangles()
            m = ev.matrix_world
            zamik = len(tocke)
            tocke += [tuple(m @ v.co) for v in mreza.vertices]
            trik += [tuple(zamik + i for i in t.vertices) for t in mreza.loop_triangles]
        finally:
            ev.to_mesh_clear()
    t = np.asarray(tocke, dtype=np.float32)
    f = np.asarray(trik, dtype=np.int64).reshape(-1, 3)
    a, b, c = t[f[:, 0]], t[f[:, 1]], t[f[:, 2]]
    n = np.cross(b - a, c - a)
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    zapis = np.zeros(len(f), dtype=[("n", "<f4", 3), ("a", "<f4", 3), ("b", "<f4", 3), ("c", "<f4", 3), ("x", "<u2")])
    zapis["n"], zapis["a"], zapis["b"], zapis["c"] = n, a, b, c
    with open(pot, "wb") as fh:
        fh.write(b"Oblikovanje (Blender)".ljust(80, b" "))
        fh.write(np.uint32(len(f)).tobytes())
        fh.write(zapis.tobytes())


def zacni_render(p):
    """Kopija scene v .blend (render bere to, oblikovanje teče naprej) in naloga v vrsto upodabljanja."""
    os.makedirs(DELOVNA, exist_ok=True)
    kopija = os.path.join(DELOVNA, "oblikovanje-%s.blend" % time.strftime("%Y%m%d-%H%M%S"))
    bpy.ops.wm.save_as_mainfile(filepath=kopija, copy=True, compress=False)
    if IDEJE.mapa:   # render ideje gre v njeno mapo Renderji, ime = ideja in različica
        ime = os.path.basename(IDEJE.mapa) + (" " + IDEJE.razlicica if IDEJE.razlicica else "")
        mapa = os.path.join(IDEJE.mapa, "Renderji")
    else:
        ime = os.path.splitext(os.path.basename(STANJE.datoteka))[0] if STANJE.datoteka else "Oblikovanje"
        mapa = os.path.join(MAPA_DATOTEK, "Renderji")
    nid = UPODABLJANJE.zacni({"blend": kopija}, p, ime=ime, kopija=mapa)
    return {"ok": True, "id": nid}


# ---------------------------------------------------------------------------------------------------------------
# AI oblikovalec: orodja (glavna nit) in pošiljanje

def na_glavni(fn, cas=120.0):
    """Izvede fn na glavni niti Blenderja (iz niti AI) in vrne rezultat; napako sproži znova kot RuntimeError."""
    koncano, o = _cakaj("klic", fn, cas)
    if not koncano:
        raise RuntimeError("Blender ni odgovoril v %d s" % cas)
    if o["napaka"]:
        raise RuntimeError(o["napaka"])
    return o["rezultat"]


def _orodje_nastavi_obliko(vhod):
    igrisce.nastavi_obliko(_imenski_prostor(), vhod["koda"], vhod["parametri"])
    STANJE.spremenjeno = True
    return igrisce.povzetek(), None


def _orodje_izvedi_kodo(vhod):
    _PREDPOMNILNIK.clear()
    izpis = io.StringIO()
    ns = _imenski_prostor()
    with contextlib.redirect_stdout(izpis):
        exec(compile(vhod["koda"], "<izvedi_kodo>", "exec"), ns)
    STANJE.spremenjeno = True
    besedilo = izpis.getvalue()[-6000:]
    if ns.get("rezultat") is not None:
        besedilo += "\nrezultat: " + json.dumps(ns["rezultat"], ensure_ascii=False, default=str)[:4000]
    return (besedilo + "\n\n" + igrisce.povzetek()).strip(), None


def _orodje_poglej(vhod):
    pot = igrisce.nov_pogled_pot(IDEJE.mapa)
    imena = igrisce.pogledi(pot)
    return "Pogledi v sliki (levo zgoraj, desno zgoraj, levo spodaj, desno spodaj): %s.\n%s" % (
        ", ".join(imena), igrisce.povzetek()), pot


def _orodje_preberi_obliko(vhod):
    koda = igrisce.koda_oblike()
    if not koda:
        return "Scena nima parametrične oblike.\n" + igrisce.povzetek(), None
    return "Parametri: %s\n\nKoda oblika.py:\n%s" % (json.dumps(igrisce.parametri(), ensure_ascii=False), koda), None


def _konec_odgovora(opomba):
    STANJE.umazano = True
    rid = IDEJE.shrani_razlicico(opomba.strip().splitlines()[0][:120] if opomba.strip() else "AI", "AI")
    _po_ideji()
    STANJE.spremenjeno = False
    return rid


def zacni_ai(p):
    """Glavna nit: po potrebi ustvari idejo iz sporočila (trenutna scena postane izhodišče), nato zažene AI v njeni niti."""
    besedilo = (p.get("sporocilo") or "").strip()
    if not besedilo:
        return {"ok": False, "sporocilo": "Prazno sporočilo."}
    if not IDEJE.mapa:
        ime = " ".join(besedilo.split()[:5]).strip(" .,!?") or "Ideja"
        IDEJE.nova(ime, besedilo)
        if len(bpy.context.scene.objects):
            IDEJE.shrani_razlicico("Izhodišče", "roka")
        _po_ideji()
    AI.poslji(besedilo, p.get("slike") or [], {
        "mapa": IDEJE.mapa, "povzetek": igrisce.povzetek, "konec": _konec_odgovora,
        "orodja": {"nastavi_obliko": _orodje_nastavi_obliko, "izvedi_kodo": _orodje_izvedi_kodo,
                   "poglej": _orodje_poglej, "preberi_obliko": _orodje_preberi_obliko}})
    STANJE.verzija_ideje += 1
    return {"ok": True}


AI = AIOblikovalec(na_glavni)
IDEJE = igrisce.Ideje(MAPA_DATOTEK)


# ---------------------------------------------------------------------------------------------------------------
# HTTP

class Streznik(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def handle_error(self, request, client_address):
        if issubclass(sys.exc_info()[0] or Exception, (ConnectionAbortedError, ConnectionResetError, BrokenPipeError)):
            return
        super().handle_error(request, client_address)


def _cakaj(vrsta, podatki, cas=120.0):
    odgovor = {"konec": threading.Event(), "izpis": "", "napaka": "", "rezultat": None}
    STANJE.vrsta.put((vrsta, podatki, odgovor))
    koncano = odgovor["konec"].wait(cas)
    return koncano, odgovor


class Zahteva(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _odgovor(self, telo, vrsta="application/json; charset=utf-8", koda=200):
        if isinstance(telo, (dict, list)):
            telo = json.dumps(telo, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(koda)
        self.send_header("Content-Type", vrsta)
        self.send_header("Content-Length", str(len(telo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(telo)

    def do_GET(self):
        pot, _, poizvedba = self.path.partition("?")
        q = {k: v[0] for k, v in urllib.parse.parse_qs(poizvedba).items()}
        if pot == "/":
            with open(os.path.join(MAPA, "oblikovanje.html"), "rb") as f:
                self._odgovor(f.read().replace(b"__ZETON__", ZETON.encode("ascii")), "text/html; charset=utf-8")
        elif pot == "/render-plosca.js":
            with open(os.path.join(MAPA, "render-plosca.js"), "rb") as f:
                self._odgovor(f.read(), "text/javascript; charset=utf-8")
        elif pot == "/stanje":
            self._odgovor(STANJE.stanje())
        elif pot == "/model":
            self._odgovor(STANJE.posnetek)
        elif pot == "/datoteke":
            datoteke = []
            for koren, _, imena in os.walk(MAPA_DATOTEK):
                for ime in imena:
                    if ime.lower().endswith(".blend"):
                        p = os.path.join(koren, ime)
                        datoteke.append({"pot": p, "ime": os.path.relpath(p, MAPA_DATOTEK)[:-6],
                                         "spremenjeno": os.path.getmtime(p)})
            datoteke.sort(key=lambda d: -d["spremenjeno"])
            self._odgovor({"mapa": MAPA_DATOTEK, "datoteke": datoteke})
        elif pot == "/ideje":
            self._odgovor({"ideje": IDEJE.seznam(), "mapa": IDEJE.koren})
        elif pot == "/ideja":
            self._odgovor(IDEJE.opis() or {})
        elif pot == "/ideja/slicica":
            pot_slike = IDEJE.pot_slicice(q.get("ideja", ""), q.get("r", ""))
            if not pot_slike:
                self._odgovor(b"", "text/plain", 404)
                return
            with open(pot_slike, "rb") as f:
                self._odgovor(f.read(), "image/png")
        elif pot == "/ai/stanje":
            self._odgovor(AI.stanje_od(int(q.get("od", "0") or 0)))
        elif pot == "/ai/slika":
            ime = os.path.basename(q.get("ime", ""))
            pot_slike = os.path.join(IDEJE.mapa, "pogledi", ime) if IDEJE.mapa and ime.endswith(".png") else ""
            if not pot_slike or not os.path.isfile(pot_slike):
                self._odgovor(b"", "text/plain", 404)
                return
            with open(pot_slike, "rb") as f:
                self._odgovor(f.read(), "image/png")
        elif pot == "/render/stanje":
            s = UPODABLJANJE.stanje(q.get("id", ""))
            self._odgovor(s if s else {"napaka": "ni naloge"}, koda=200 if s else 404)
        elif pot == "/render/seznam":
            self._odgovor(UPODABLJANJE.seznam())
        elif pot == "/render/slika":
            pot_slike = UPODABLJANJE.datoteka(q.get("id", ""))
            if not pot_slike or not os.path.isfile(pot_slike):
                self._odgovor(b"", "text/plain", 404)
                return
            with open(pot_slike, "rb") as f:
                self._odgovor(f.read(), "video/mp4" if pot_slike.endswith(".mp4") else "image/png")
        else:
            self._odgovor(b"ni", "text/plain", 404)

    def do_POST(self):
        dolzina = int(self.headers.get("Content-Length") or 0)
        telo = self.rfile.read(dolzina) if dolzina else b""
        if self.headers.get("X-Zeton") != ZETON:
            self._odgovor({"napaka": "zeton"}, koda=403)
            return
        try:
            podatki = json.loads(telo.decode("utf-8") or "{}")
        except ValueError:
            self._odgovor({"napaka": "json"}, koda=400)
            return
        pot = self.path.split("?")[0]
        if pot == "/python":
            koncano, o = _cakaj("python", podatki, float(podatki.get("cakaj", 120) or 120))
            self._odgovor({"ok": koncano and not o["napaka"], "koncano": koncano, "izpis": o["izpis"],
                           "napaka": o["napaka"], "rezultat": o["rezultat"]})
        elif pot in ("/ukaz", "/render"):
            koncano, o = _cakaj("ukaz" if pot == "/ukaz" else "render", podatki)
            if not koncano:
                self._odgovor({"ok": False, "sporocilo": "Blender še dela; poglej čez nekaj časa."})
            elif o["napaka"]:
                self._odgovor({"ok": False, "sporocilo": o["napaka"].strip().splitlines()[-1], "napaka": o["napaka"]})
            else:
                self._odgovor(o["rezultat"] or {"ok": True})
        elif pot == "/ai":
            koncano, o = _cakaj("klic", lambda: zacni_ai(podatki), 60)
            if not koncano or o["napaka"]:
                self._odgovor({"ok": False, "sporocilo": (o["napaka"] or "Blender ne odgovarja").strip().splitlines()[-1]})
            else:
                self._odgovor(o["rezultat"])
        elif pot == "/ai/ustavi":
            AI.prekini()
            self._odgovor({"ok": True})
        elif pot == "/slicica":
            import base64
            png = podatki.get("png", "")
            try:
                bajti = base64.b64decode(png.partition(",")[2] if png.startswith("data:") else png)
            except (ValueError, TypeError):
                bajti = b""
            if not bajti.startswith(b"\x89PNG") or len(bajti) > 3_000_000:
                self._odgovor({"ok": False}, koda=400)
                return
            IDEJE.shrani_slicico(podatki.get("razlicica", ""), bajti)
            STANJE.verzija_ideje += 1
            self._odgovor({"ok": True})
        elif pot == "/render/ustavi":
            self._odgovor({"ok": UPODABLJANJE.ustavi(podatki.get("id", ""))})
        elif pot == "/izhod":
            STANJE.konec = True
            self._odgovor({"ok": True})
        else:
            self._odgovor(b"ni", "text/plain", 404)


def zapisi_povezavo():
    os.makedirs(LOKALNO, exist_ok=True)
    with open(POVEZAVA, "w", encoding="utf-8") as f:
        json.dump({"vrata": VRATA, "zeton": ZETON, "pid": os.getpid(), "blender": bpy.app.version_string}, f)


def main():
    os.makedirs(LOKALNO, exist_ok=True)
    try:
        streznik = Streznik(("127.0.0.1", VRATA), Zahteva)
    except OSError as e:
        _log("vrata %d so zasedena (%s); ali Oblikovanje že teče?" % (VRATA, e))
        return
    nova_scena()
    try:
        with open(ZADNJA_IDEJA, encoding="utf-8") as f:
            zadnja = json.load(f).get("ideja", "")
        if zadnja:
            IDEJE.odpri(zadnja)
            _po_ideji()
    except (OSError, ValueError):
        pass
    except Exception:  # noqa: BLE001
        _log("zadnja ideja: " + traceback.format_exc())
    zapisi_povezavo()
    threading.Thread(target=streznik.serve_forever, daemon=True, name="http").start()
    _log("Oblikovanje (Blender %s) na http://127.0.0.1:%d/" % (bpy.app.version_string, VRATA))
    zadnje_zunanje = 0.0
    while not STANJE.konec:
        if STANJE.zunanje and time.time() - zadnje_zunanje > 1.0:
            zadnje_zunanje = time.time()
            try:
                preveri_zunanje()
            except Exception:  # noqa: BLE001
                _log("okno Blenderja: " + traceback.format_exc())
        try:
            vrsta, podatki, odgovor = STANJE.vrsta.get(timeout=0.05)
        except queue.Empty:
            vrsta = None
        if vrsta is not None:
            obdelaj(vrsta, podatki, odgovor)
            if odgovor is not None:
                odgovor["konec"].set()
            continue   # najprej izprazni vrsto, posnetek enkrat na koncu
        if STANJE.umazano:
            STANJE.umazano = False
            try:
                zgradi_posnetek()
                STANJE.napaka = ""
            except Exception:  # noqa: BLE001
                STANJE.napaka = traceback.format_exc()
                _log("posnetek: " + STANJE.napaka)
    streznik.shutdown()
    _log("Oblikovanje: izhod")
    try:
        os.remove(POVEZAVA)
    except OSError:
        pass


main()
