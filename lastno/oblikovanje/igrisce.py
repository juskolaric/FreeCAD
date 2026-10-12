# -*- coding: utf-8 -*-
"""Igrišče Oblikovanja (faza 3): ideje in različice, parametrična oblika z drsniki, hitri pogledi za AI.

Teče v Blenderju (strežnik streznik_blender.py), vse funkcije kliče samo glavna nit.

Ideja = mapa <MAPA_DATOTEK>/Ideje/<ime>/ z:
    ideja.json      ime, opis, ustvarjeno, aktivna, razlicice [{id, opomba, vir, cas, zvezdica}]
    R01.blend …     različice (vsaka je cela scena; parametrična oblika je v njej kot besedilo »oblika.py«)
    R01.png …       sličice (izriše jih stran iz svojega pogleda)
    pogovor.json    pogovor s Claudom (sporočila API, samo dodajanje), prikaz.json (koraki za stran)
    pogledi/        slike, ki jih je AI pogledal

Sestav (logika strojnega risanja): ideja lahko vsebuje kose iz drugih idej kot vezave, ne kopije. Kos = nosilec (Empty z
lastnostjo »kos« = JSON {ideja, razlicica}) + telesa: lokalni objekti, katerih mreža je vezana (link) iz datoteke
<Ideje>/<kos>/R09.blend. Sestav nosi le lego kosa; oblika, materiali in revizija so v ideji kosa. Različica sestava v
ideja.json zapiše »deli« (kateri kos, katera revizija), zato seznam idej ve, kaj je sestav in kje je kos uporabljen.
Ko ima kos novejšo aktivno revizijo, sestav to pokaže (posodobi_kos = prevezava na drugo revizijo z isto lego).

Parametrična oblika: besedilo »oblika.py« v .blend definira `zgradi(p)` (p: ime -> vrednost), parametri so v lastnosti
scene »parametri« (JSON seznam {ime, oznaka, vrednost, min, max, korak, enota}). Objekti, ki jih zgradi, so v zbirki
»Oblika«; ob spremembi drsnika se zbirka izprazni in zgradi znova.
"""

import datetime
import json
import math
import os
import re

import bpy
import numpy as np
from mathutils import Matrix, Vector

ZBIRKA = "Oblika"
BESEDILO = "oblika.py"
VRSTE_GEOMETRIJE = {"MESH", "CURVE", "SURFACE", "META", "FONT", "CURVES"}


def varno_ime(ime, privzeto="Ideja"):
    ime = "".join("_" if (c in '<>:"/\\|?*' or ord(c) < 32) else c for c in str(ime or "")).strip(" .")
    return ime[:60] or privzeto


# ---------------------------------------------------------------------------------------------------------------
# Ideje in različice

class Ideje:
    def __init__(self, mapa_datotek):
        self.koren = os.path.join(mapa_datotek, "Ideje")
        self.mapa = ""          # mapa odprte ideje
        self.razlicica = ""     # id različice, ki je naložena v sceni (ali iz katere izhaja)

    # -- branje --
    def _pot(self, *deli):
        return os.path.join(self.mapa, *deli)

    def podatki(self, mapa=None):
        mapa = mapa or self.mapa
        try:
            with open(os.path.join(mapa, "ideja.json"), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {"ime": os.path.basename(mapa), "opis": "", "razlicice": [], "aktivna": ""}

    def _zapisi(self, podatki):
        os.makedirs(self.mapa, exist_ok=True)
        zacasna = self._pot("ideja.json.delno")
        with open(zacasna, "w", encoding="utf-8") as f:
            json.dump(podatki, f, ensure_ascii=False, indent=1)
        os.replace(zacasna, self._pot("ideja.json"))

    def _vse(self):
        """ime ideje -> podatki (ideja.json) za vse ideje v korenu."""
        vse = {}
        if not os.path.isdir(self.koren):
            return vse
        for ime in os.listdir(self.koren):
            mapa = os.path.join(self.koren, ime)
            if os.path.isfile(os.path.join(mapa, "ideja.json")):
                vse[ime] = self.podatki(mapa)
        return vse

    @staticmethod
    def _aktivna(p):
        razl = p.get("razlicice", [])
        rid = p.get("aktivna") or (razl[-1]["id"] if razl else "")
        return next((r for r in razl if r["id"] == rid), None)

    def uporaba(self, ime, vse=None):
        """Kje je ideja uporabljena kot kos: [{ideja (sestav), v (različica sestava), razlicica (revizija kosa)}]
        po aktivnih različicah drugih idej."""
        izid = []
        for drugo, p in (vse or self._vse()).items():
            r = self._aktivna(p)
            for d in (r or {}).get("deli", []):
                if d.get("ideja") == ime:
                    izid.append({"ideja": drugo, "v": r["id"], "razlicica": d.get("razlicica", "")})
        return izid

    def seznam(self):
        izid = []
        vse = self._vse()
        for ime, p in vse.items():
            mapa = os.path.join(self.koren, ime)
            razl = p.get("razlicice", [])
            akt = self._aktivna(p)
            deli = (akt or {}).get("deli", [])
            izid.append({"ime": ime, "opis": p.get("opis", ""), "razlicic": len(razl),
                         "zadnja": razl[-1]["id"] if razl else "", "aktivna": akt["id"] if akt else "",
                         "spremenjeno": os.path.getmtime(os.path.join(mapa, "ideja.json")),
                         "odprta": os.path.normcase(mapa) == os.path.normcase(self.mapa),
                         "vrsta": "sestav" if deli else "kos", "deli": deli, "uporabljena_v": self.uporaba(ime, vse),
                         "razlicice": [{"id": r["id"], "deli": r.get("deli", [])} for r in razl]})
        izid.sort(key=lambda d: -d["spremenjeno"])
        return izid

    def opis(self):
        if not self.mapa:
            return None
        p = self.podatki()
        for r in p.get("razlicice", []):
            r["slicica"] = os.path.isfile(self._pot(r["id"] + ".png"))
        p["mapa"] = self.mapa
        p["trenutna"] = self.razlicica
        p["uporabljena_v"] = self.uporaba(os.path.basename(self.mapa))
        return p

    # -- dejanja --
    def nova(self, ime, opis=""):
        ime = varno_ime(ime)
        osnova, i = ime, 2
        while os.path.exists(os.path.join(self.koren, ime)):
            ime = "%s %d" % (osnova, i)
            i += 1
        self.mapa = os.path.join(self.koren, ime)
        os.makedirs(self.mapa, exist_ok=True)
        self.razlicica = ""
        self._zapisi({"ime": ime, "opis": opis, "ustvarjeno": datetime.datetime.now().isoformat(timespec="seconds"),
                      "aktivna": "", "razlicice": []})
        return ime

    def odpri(self, ime):
        mapa = os.path.join(self.koren, varno_ime(ime))
        if not os.path.isfile(os.path.join(mapa, "ideja.json")):
            raise ValueError("ni ideje: %s" % ime)
        self.mapa = mapa
        p = self.podatki()
        rid = p.get("aktivna") or (p["razlicice"][-1]["id"] if p.get("razlicice") else "")
        if rid and os.path.isfile(self._pot(rid + ".blend")):
            nalozi_blend(self._pot(rid + ".blend"))
            self.razlicica = rid
        else:
            prazna_scena()
            self.razlicica = ""
        return p

    def shrani_razlicico(self, opomba="", vir="roka"):
        if not self.mapa:
            raise ValueError("Ni odprte ideje.")
        p = self.podatki()
        stevilke = [int(m.group(1)) for r in p.get("razlicice", []) for m in [re.match(r"R(\d+)$", r["id"])] if m]
        rid = "R%02d" % ((max(stevilke) if stevilke else 0) + 1)
        if bpy.data.libraries and bpy.data.filepath:     # vezave na kose relativno (Ideje se selijo kot celota)
            try:
                bpy.ops.file.make_paths_relative()
            except RuntimeError:
                pass
        bpy.ops.wm.save_as_mainfile(filepath=self._pot(rid + ".blend"), copy=True, compress=True)
        p.setdefault("razlicice", []).append({"id": rid, "opomba": (opomba or "").strip()[:300], "vir": vir,
                                             "cas": datetime.datetime.now().isoformat(timespec="seconds"),
                                             "zvezdica": False, "izhaja": self.razlicica, "deli": kosi_povzetek()})
        p["aktivna"] = rid
        self._zapisi(p)
        self.razlicica = rid
        return rid

    def odpri_razlicico(self, rid):
        pot = self._pot(varno_ime(rid) + ".blend")
        if not os.path.isfile(pot):
            raise ValueError("ni različice %s" % rid)
        nalozi_blend(pot)
        self.razlicica = rid
        p = self.podatki()
        p["aktivna"] = rid
        self._zapisi(p)

    def uredi_razlicico(self, rid, **polja):
        p = self.podatki()
        for r in p.get("razlicice", []):
            if r["id"] == rid:
                for k, v in polja.items():
                    if k in ("zvezdica", "opomba"):
                        r[k] = v
        self._zapisi(p)

    def shrani_slicico(self, rid, png):
        if self.mapa and re.match(r"R\d+$", rid or ""):
            with open(self._pot(rid + ".png"), "wb") as f:
                f.write(png)

    def pot_slicice(self, ideja, rid):
        pot = os.path.join(self.koren, varno_ime(ideja), varno_ime(rid) + ".png")
        return pot if os.path.isfile(pot) else None


def prazna_scena():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    nastavi_enote()


def nalozi_blend(pot):
    bpy.ops.wm.open_mainfile(filepath=pot)
    nastavi_enote()


def nastavi_enote(scena=None):
    scena = scena or bpy.context.scene
    us = scena.unit_settings
    us.system = "METRIC"
    us.scale_length = 0.001
    us.length_unit = "MILLIMETERS"


# ---------------------------------------------------------------------------------------------------------------
# Sestav: kosi iz drugih idej (kot v strojništvu: sestav se na kos sklicuje po ideji in reviziji, kopije nima)

LASTNOST_KOSA = "kos"


def pot_razlicice(koren, ideja, rid):
    return os.path.join(koren, varno_ime(ideja), varno_ime(rid) + ".blend")


def aktivna_razlicica(koren, ideja):
    """Aktivna (sicer zadnja) različica ideje po ideja.json; '' če je ni."""
    try:
        with open(os.path.join(koren, varno_ime(ideja), "ideja.json"), encoding="utf-8") as f:
            p = json.load(f)
    except (OSError, ValueError):
        return ""
    razl = p.get("razlicice", [])
    return p.get("aktivna") or (razl[-1]["id"] if razl else "")


def _podatki_kosa(nos):
    if nos is None or nos.type != "EMPTY" or not nos.get(LASTNOST_KOSA):
        return None
    try:
        k = json.loads(nos[LASTNOST_KOSA])
    except (ValueError, TypeError):
        return None
    return k if isinstance(k, dict) and k.get("ideja") else None


def nosilec_kosa(obj):
    """Nosilec kosa, če je objekt telo kosa (ali nosilec sam); sicer None."""
    if obj is None:
        return None
    if _podatki_kosa(obj):
        return obj
    return obj.parent if _podatki_kosa(obj.parent) else None


def _skrit(obj):
    try:
        return obj.hide_get() or obj.hide_viewport
    except RuntimeError:        # ni v pogledu
        return obj.hide_viewport


def _telesa(nos):
    return [o for o in nos.children if o.type in VRSTE_GEOMETRIJE]


def kosi(koren=None):
    """Kosi v sceni: ime nosilca, ideja, revizija, telesa, lega (4 × 4); s korenom še aktivna revizija kosa, novejsa
    (aktivna, če ni ista) in manjka (datoteke revizije ni)."""
    izid = []
    for nos in bpy.context.scene.objects:
        k = _podatki_kosa(nos)
        if not k:
            continue
        rid = k.get("razlicica", "")
        d = {"ime": nos.name, "ideja": k["ideja"], "razlicica": rid, "telesa": [o.name for o in _telesa(nos)],
             "lega": [list(v) for v in nos.matrix_world], "vidno": not _skrit(nos)}
        if koren:
            akt = aktivna_razlicica(koren, k["ideja"])
            d["aktivna"] = akt
            d["novejsa"] = akt if akt and akt != rid else ""
            d["manjka"] = not os.path.isfile(pot_razlicice(koren, k["ideja"], rid))
        izid.append(d)
    return izid


def kosi_povzetek():
    """Za ideja.json: kateri kosi (ideja, revizija) so v sceni."""
    return [{"ime": k["ime"], "ideja": k["ideja"], "razlicica": k["razlicica"]} for k in kosi()]


def _matrika_lege(lega):
    if lega is None:
        return Matrix()
    if isinstance(lega, Matrix):
        return lega.copy()
    lega = list(lega)
    if len(lega) == 3 and not hasattr(lega[0], "__len__"):
        return Matrix.Translation(Vector(lega))
    return Matrix([list(v) for v in lega])


def vstavi_kos(koren, ideja, rid=None, lega=None, ime=None, lastna=""):
    """Kos (različica druge ideje) vstavi v sceno kot vezavo: mreže ostanejo v <Ideje>/<ideja>/<rid>.blend, tu nastanejo
    nosilec (Empty z lastnostjo »kos«) in lokalna telesa z vezano mrežo. lega: (x, y, z) ali matrika 4 × 4 nosilca.
    rid None = aktivna različica kosa. lastna = mapa odprte ideje (ideja ne more vsebovati same sebe)."""
    ideja = varno_ime(ideja)
    if lastna and os.path.normcase(os.path.normpath(lastna)) == os.path.normcase(os.path.normpath(os.path.join(koren, ideja))):
        raise ValueError("Ideja ne more vsebovati same sebe kot kos.")
    rid = varno_ime(rid or aktivna_razlicica(koren, ideja), "")
    pot = pot_razlicice(koren, ideja, rid)
    if not rid or not os.path.isfile(pot):
        raise ValueError("Ideja »%s« nima različice %s." % (ideja, rid or "(nobene)"))
    pred = set(bpy.data.objects)
    with bpy.data.libraries.load(pot, link=True) as (vir, cilj):
        cilj.objects = list(vir.objects)
    scena = bpy.context.scene
    nos = bpy.data.objects.new(varno_ime(ime or ideja), None)
    nos.empty_display_type = "PLAIN_AXES"
    nos.empty_display_size = 10.0
    nos[LASTNOST_KOSA] = json.dumps({"ideja": ideja, "razlicica": rid}, ensure_ascii=False)
    scena.collection.objects.link(nos)
    nos.matrix_world = _matrika_lege(lega)
    telesa = []
    for izvor in cilj.objects:
        if izvor is None or izvor.type not in VRSTE_GEOMETRIJE or izvor.hide_viewport or izvor.hide_render:
            continue
        telo = izvor.copy()            # lokalni objekt (lega, vidnost), mreža ostane vezana iz datoteke kosa
        telo.name = izvor.name
        telo.parent = nos
        telo.matrix_parent_inverse = Matrix()
        telo.matrix_basis = izvor.matrix_world.copy()   # lega telesa znotraj kosa (tudi če je bilo tam v hierarhiji)
        scena.collection.objects.link(telo)
        telesa.append(telo)
    if not telesa:
        bpy.data.objects.remove(nos, do_unlink=True)
        for o in set(bpy.data.objects) - pred:
            if o.library:
                bpy.data.objects.remove(o)
        raise ValueError("Različica %s ideje »%s« nima geometrije." % (rid, ideja))
    return {"ime": nos.name, "ideja": ideja, "razlicica": rid, "telesa": [t.name for t in telesa], "datoteka": pot}


def odstrani_kos(ime):
    """Odstrani kos (nosilec in telesa); knjižnica datoteke kosa se sprosti, če je ne uporablja drug kos."""
    nos = nosilec_kosa(bpy.data.objects.get(ime or ""))
    if nos is None:
        raise ValueError("»%s« ni kos." % ime)
    knjiznice = set()
    for o in list(nos.children):
        if o.data is not None and o.data.library is not None:
            knjiznice.add(o.data.library)
        bpy.data.objects.remove(o, do_unlink=True)
    podatki = _podatki_kosa(nos)
    bpy.data.objects.remove(nos, do_unlink=True)
    for knj in knjiznice:
        if not any(o.library is None and o.data is not None and o.data.library == knj for o in bpy.data.objects):
            bpy.data.libraries.remove(knj)
    return podatki


def posodobi_kos(koren, ime, rid=None, lastna=""):
    """Kos preveže na drugo revizijo (privzeto aktivno) z isto lego in vidnostjo."""
    nos = nosilec_kosa(bpy.data.objects.get(ime or ""))
    k = _podatki_kosa(nos)
    if not k:
        raise ValueError("»%s« ni kos." % ime)
    rid = varno_ime(rid or aktivna_razlicica(koren, k["ideja"]), "")
    if rid == k.get("razlicica"):
        return {"ime": nos.name, "ideja": k["ideja"], "razlicica": rid, "nespremenjeno": True}
    lega, ime_nos, skrit = nos.matrix_world.copy(), nos.name, _skrit(nos)
    odstrani_kos(ime_nos)
    izid = vstavi_kos(koren, k["ideja"], rid, lega, ime_nos, lastna)
    if skrit:
        vidnost_kosa(izid["ime"], False)
    return izid


def vidnost_kosa(ime, vidno):
    nos = nosilec_kosa(bpy.data.objects.get(ime or ""))
    if nos is None:
        return False
    for o in [nos] + list(nos.children):
        o.hide_set(not vidno)
        o.hide_render = not vidno
    return True


# ---------------------------------------------------------------------------------------------------------------
# Parametrična oblika

def parametri():
    try:
        return json.loads(bpy.context.scene.get("parametri", "[]"))
    except ValueError:
        return []


def koda_oblike():
    t = bpy.data.texts.get(BESEDILO)
    return t.as_string() if t else ""


def _preveri_parametre(seznam):
    izid = []
    for p in seznam or []:
        ime = str(p.get("ime", "")).strip()
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", ime):
            raise ValueError("ime parametra mora biti Pythonovo ime: %r" % ime)
        mn, mx = float(p.get("min", 0)), float(p.get("max", 1))
        if mx <= mn:
            raise ValueError("parameter %s: max mora biti večji od min" % ime)
        v = min(max(float(p.get("vrednost", mn)), mn), mx)
        izid.append({"ime": ime, "oznaka": str(p.get("oznaka") or ime), "vrednost": v, "min": mn, "max": mx,
                     "korak": float(p.get("korak") or (mx - mn) / 100.0), "enota": str(p.get("enota") or "")})
    return izid


def zbirka_oblike():
    z = bpy.data.collections.get(ZBIRKA)
    if z is None:
        z = bpy.data.collections.new(ZBIRKA)
    if z.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(z)
    return z


def _pocisti_zbirko(z):
    """Odstrani objekte zbirke in njihove mreže/krivulje, ki jih nihče drug ne uporablja (materiali ostanejo)."""
    podatki = []
    for obj in list(z.objects):
        if obj.data is not None:
            podatki.append(obj.data)
        bpy.data.objects.remove(obj, do_unlink=True)
    zbirke = {bpy.types.Mesh: bpy.data.meshes, bpy.types.Curve: bpy.data.curves, bpy.types.MetaBall: bpy.data.metaballs}
    for d in podatki:
        try:
            if d.users == 0:
                for vrsta, zbirka in zbirke.items():
                    if isinstance(d, vrsta):
                        zbirka.remove(d)
                        break
        except ReferenceError:
            pass


def zgradi_obliko(imenski_prostor, vrednosti=None):
    """Zgradi parametrično obliko iz besedila »oblika.py« z danimi (ali shranjenimi) vrednostmi parametrov."""
    koda = koda_oblike()
    if not koda:
        raise ValueError("Scena nima parametrične oblike (oblika.py).")
    seznam = parametri()
    p = {x["ime"]: x["vrednost"] for x in seznam}
    if vrednosti:
        for x in seznam:
            if x["ime"] in vrednosti:
                x["vrednost"] = min(max(float(vrednosti[x["ime"]]), x["min"]), x["max"])
                p[x["ime"]] = x["vrednost"]
        bpy.context.scene["parametri"] = json.dumps(seznam, ensure_ascii=False)
    z = zbirka_oblike()
    _pocisti_zbirko(z)
    pred = set(bpy.data.objects)
    ns = dict(imenski_prostor)
    exec(compile(koda, BESEDILO, "exec"), ns)
    if "zgradi" not in ns:
        raise ValueError("oblika.py mora definirati funkcijo zgradi(p).")
    ns["zgradi"](p)
    # novi objekti gredo v zbirko Oblika (pomočniki jih povežejo v korensko zbirko scene)
    for obj in set(bpy.data.objects) - pred:
        if obj.name not in z.objects:
            z.objects.link(obj)
        for zb in list(obj.users_collection):
            if zb != z:
                zb.objects.unlink(obj)
    return p


def nastavi_obliko(imenski_prostor, koda, seznam):
    seznam = _preveri_parametre(seznam)
    t = bpy.data.texts.get(BESEDILO) or bpy.data.texts.new(BESEDILO)
    t.clear()
    t.write(koda)
    bpy.context.scene["parametri"] = json.dumps(seznam, ensure_ascii=False)
    return zgradi_obliko(imenski_prostor)


# ---------------------------------------------------------------------------------------------------------------
# Povzetek scene (za AI in stran)

def povzetek():
    dg = bpy.context.evaluated_depsgraph_get()
    vrstice = []
    mn_vse, mx_vse = None, None
    for obj in bpy.context.scene.objects:
        if obj.type not in VRSTE_GEOMETRIJE:
            continue
        ev = obj.evaluated_get(dg)
        tocke = [ev.matrix_world @ Vector(v) for v in ev.bound_box]
        mn = Vector([min(t[i] for t in tocke) for i in range(3)])
        mx = Vector([max(t[i] for t in tocke) for i in range(3)])
        if not obj.hide_get():
            mn_vse = mn if mn_vse is None else Vector(map(min, mn_vse, mn))
            mx_vse = mx if mx_vse is None else Vector(map(max, mx_vse, mx))
        trik = ""
        try:
            m = ev.to_mesh()
            trik = ", %d ploskev" % len(m.polygons)
            ev.to_mesh_clear()
        except RuntimeError:
            pass
        d = mx - mn
        vrstice.append("- %s (%s%s%s): %.1f × %.1f × %.1f mm, od (%.1f, %.1f, %.1f)%s" % (
            obj.name, obj.type.lower(), ", " + ", ".join(m.type.lower() for m in obj.modifiers) if obj.modifiers else "",
            "" if not obj.hide_get() else ", skrit", d.x, d.y, d.z, mn.x, mn.y, mn.z, trik))
    if not vrstice:
        return "Scena je prazna."
    d = mx_vse - mn_vse if mn_vse is not None else Vector()
    glava = "Scena: %d objektov, skupaj %.1f × %.1f × %.1f mm (X × Y × Z)." % (len(vrstice), d.x, d.y, d.z)
    par = parametri()
    if par:
        glava += "\nParametri oblike: " + ", ".join("%s=%g%s" % (x["ime"], x["vrednost"], x["enota"]) for x in par)
    return glava + "\n" + "\n".join(vrstice)


# ---------------------------------------------------------------------------------------------------------------
# Hitri pogledi (Workbench) za AI: štirje pogledi v eni sliki 2 × 2

POGLEDI = [("izometrija", Vector((1.0, -1.25, 0.9))), ("spredaj (-Y)", Vector((0, -1, 0))),
           ("desno (+X)", Vector((1, 0, 0))), ("zgoraj (+Z)", Vector((0, -0.0001, 1)))]


def _okvir_vidnih():
    dg = bpy.context.evaluated_depsgraph_get()
    mn, mx = Vector((1e30,) * 3), Vector((-1e30,) * 3)
    for obj in bpy.context.scene.objects:
        if obj.type not in VRSTE_GEOMETRIJE or obj.hide_get() or obj.hide_render:
            continue
        ev = obj.evaluated_get(dg)
        for v in ev.bound_box:
            w = ev.matrix_world @ Vector(v)
            mn, mx = Vector(map(min, mn, w)), Vector(map(max, mx, w))
    return (mn, mx) if mn.x <= mx.x else (None, None)


def pogledi(pot, velikost=(560, 420)):
    """Štirje pogledi trenutne scene v eno sliko PNG (Workbench, studio luč, robovi, materialne barve).
    Scena se ne spremeni (kamera in nastavitve izrisa se vrnejo)."""
    scena = bpy.context.scene
    mn, mx = _okvir_vidnih()
    if mn is None:
        raise ValueError("Scena nima vidne geometrije.")
    sredisce = (mn + mx) / 2
    polmer = max((mx - mn).length / 2, 1e-3)
    r = scena.render
    staro = (r.engine, r.resolution_x, r.resolution_y, r.resolution_percentage, r.filepath, scena.camera,
             r.film_transparent, r.image_settings.file_format)
    sh = scena.display.shading
    r.engine = "BLENDER_WORKBENCH"
    sh.light, sh.color_type, sh.show_cavity, sh.show_object_outline = "STUDIO", "MATERIAL", True, True
    try:
        sh.show_shadows = True
    except AttributeError:
        pass
    r.resolution_x, r.resolution_y, r.resolution_percentage = velikost[0], velikost[1], 100
    r.film_transparent = False
    r.image_settings.file_format = "PNG"
    svet_prej = scena.world
    svet = bpy.data.worlds.new("_SvetAI")
    svet.color = (0.62, 0.65, 0.7)        # svetlo sivo ozadje, da so obrisi jasni
    scena.world = svet
    cam = bpy.data.objects.new("_PogledAI", bpy.data.cameras.new("_PogledAI"))
    scena.collection.objects.link(cam)
    scena.camera = cam
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = polmer * 2.25
    cam.data.clip_start, cam.data.clip_end = polmer * 0.01, polmer * 20
    slike = []
    mapa = os.path.dirname(pot)
    try:
        for i, (ime, smer) in enumerate(POGLEDI):
            cam.location = sredisce + smer.normalized() * polmer * 6
            cam.rotation_euler = (-smer).to_track_quat("-Z", "Y").to_euler()
            r.filepath = os.path.join(mapa, "_pogled_%d.png" % i)
            bpy.ops.render.render(write_still=True)
            slike.append(r.filepath)
        _sestavi_mrezo(slike, pot, velikost)
    finally:
        podatki = cam.data
        bpy.data.objects.remove(cam, do_unlink=True)
        bpy.data.cameras.remove(podatki)
        scena.world = svet_prej
        bpy.data.worlds.remove(svet)
        (r.engine, r.resolution_x, r.resolution_y, r.resolution_percentage, r.filepath, scena.camera,
         r.film_transparent, r.image_settings.file_format) = staro
        for s in slike:
            try:
                os.remove(s)
            except OSError:
                pass
    return [ime for ime, _ in POGLEDI]


def _sestavi_mrezo(slike, pot, velikost):
    w, h = velikost
    mreza = np.ones((h * 2, w * 2, 4), dtype=np.float32)
    for i, s in enumerate(slike):
        img = bpy.data.images.load(s, check_existing=False)
        px = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
        bpy.data.images.remove(img)
        px = px.reshape(h, w, 4)            # vrstice od spodaj
        vr, st = divmod(i, 2)
        y0 = (1 - vr) * h                    # prva vrsta zgoraj
        mreza[y0:y0 + h, st * w:(st + 1) * w] = px
    # tanke ločilne črte
    mreza[h - 1:h + 1, :, :3] = 0.55
    mreza[:, w - 1:w + 1, :3] = 0.55
    izhod = bpy.data.images.new("_mrezaAI", w * 2, h * 2, alpha=True)
    izhod.pixels.foreach_set(mreza.ravel())
    izhod.filepath_raw = pot
    izhod.file_format = "PNG"
    izhod.save()
    bpy.data.images.remove(izhod)


def nov_pogled_pot(mapa_ideje):
    mapa = os.path.join(mapa_ideje, "pogledi")
    os.makedirs(mapa, exist_ok=True)
    return os.path.join(mapa, "pogled-%s.png" % datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3])


def dolzina_kode(koda):
    return len((koda or "").splitlines())


def stopinje(x):
    return math.radians(x)
