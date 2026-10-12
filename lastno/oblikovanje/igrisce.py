# -*- coding: utf-8 -*-
"""Igrišče Oblikovanja (faza 3): ideje in različice, parametrična oblika z drsniki, hitri pogledi za AI.

Teče v Blenderju (strežnik streznik_blender.py), vse funkcije kliče samo glavna nit.

Projekt = mapa <MAPA_DATOTEK>/Projekti/<projekt>/ (od 2026-10-12; prej so bile vse ideje v eni mapi <MAPA_DATOTEK>/Ideje, ki jo
strežnik ob prvem zagonu preseli v projekt »Photobox Slim«). Vsak projekt ima svoje ideje; odprt je en projekt naenkrat
(stolpec Projekti čisto desno na strani), kosi sestava so iz idej istega projekta.

Ideja = mapa <projekt>/Ideje/<ime>/ z:
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
        self.koren = os.path.join(mapa_datotek, "Ideje")   # do odprtja projekta: stara skupna mapa (glej Projekti.preseli)
        self.mapa = ""          # mapa odprte ideje
        self.razlicica = ""     # id različice, ki je naložena v sceni (ali iz katere izhaja)

    def nastavi_koren(self, mapa_projekta):
        """Ideje so odslej iz tega projekta; odprta ideja se zapre (scene ne spremeni)."""
        self.koren = os.path.join(mapa_projekta, "Ideje")
        self.mapa = ""
        self.razlicica = ""

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
                         "razlicice": [{"id": r["id"], "deli": r.get("deli", [])} for r in razl], "arhiv": bool(p.get("arhiv"))})
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
            nalozi_blend(self._pot(rid + ".blend"), self.koren)
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
        pot = self._pot(rid + ".blend")
        vezave = any(getattr(o.data, "library", None) for o in bpy.context.scene.objects)
        nastavitve = bpy.context.preferences.filepaths
        staro_st, nastavitve.save_version = nastavitve.save_version, 0     # brez .blend1 ob dvojnem shranjevanju
        try:
            if vezave:     # vezave na kose relativno (Ideje se selijo kot celota)
                if not bpy.data.filepath:   # scena iz nič: najprej shrani, da imajo relativne poti izhodišče
                    bpy.ops.wm.save_as_mainfile(filepath=pot, compress=True)
                try:
                    bpy.ops.file.make_paths_relative()
                except RuntimeError:
                    pass
            bpy.ops.wm.save_as_mainfile(filepath=pot, copy=True, compress=True)
        finally:
            nastavitve.save_version = staro_st
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
        nalozi_blend(pot, self.koren)
        self.razlicica = rid
        p = self.podatki()
        p["aktivna"] = rid
        self._zapisi(p)

    def uredi_idejo(self, ime, **polja):
        """Opis ali arhiv ideje (arhiv: skrita v drevesu, datoteke ostanejo)."""
        mapa = os.path.join(self.koren, varno_ime(ime))
        if not os.path.isfile(os.path.join(mapa, "ideja.json")):
            raise ValueError("ni ideje: %s" % ime)
        p = self.podatki(mapa)
        for k, v in polja.items():
            if k == "arhiv":
                p["arhiv"] = bool(v)
            elif k == "opis":
                p["opis"] = str(v)[:500]
        stara, self.mapa = self.mapa, mapa
        try:
            self._zapisi(p)
        finally:
            self.mapa = stara

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


MAPA_PROJEKTOV = "Projekti"
PRVI_PROJEKT = "Photobox Slim"      # ime, ki ga dobi stara skupna mapa Ideje ob selitvi (uporabnik ga lahko preimenuje)


class Projekti:
    """Projekti Oblikovanja: podmape <MAPA_DATOTEK>/Projekti/<ime>/, vsaka s svojo mapo Ideje. Brez bpy, le disk."""

    def __init__(self, mapa_datotek):
        self.mapa_datotek = mapa_datotek
        self.koren = os.path.join(mapa_datotek, MAPA_PROJEKTOV)
        self.ime = ""           # odprt projekt

    def mapa(self, ime):
        return os.path.join(self.koren, varno_ime(ime, "Projekt"))

    def preseli(self, dnevnik=print):
        """Enkratna selitev: skupna mapa Ideje iz časa pred projekti postane projekt PRVI_PROJEKT (mapa se preimenuje,
        datoteke ostanejo nedotaknjene). Vrne ime projekta, če je selil, sicer ''."""
        staro = os.path.join(self.mapa_datotek, "Ideje")
        if not os.path.isdir(staro):
            return ""
        cilj = os.path.join(self.mapa(PRVI_PROJEKT), "Ideje")
        if os.path.exists(cilj):
            dnevnik("projekti: %s že obstaja, stare mape %s ne selim" % (cilj, staro))
            return ""
        os.makedirs(os.path.dirname(cilj), exist_ok=True)
        os.rename(staro, cilj)
        dnevnik("projekti: mapa Ideje preseljena v projekt »%s« (%s)" % (PRVI_PROJEKT, cilj))
        return PRVI_PROJEKT

    def seznam(self):
        """[{ime, idej (brez arhiva), arhiv, spremenjeno, odprt}] po abecedi."""
        izid = []
        if not os.path.isdir(self.koren):
            return izid
        for ime in os.listdir(self.koren):
            mapa = os.path.join(self.koren, ime)
            if not os.path.isdir(mapa) or ime.startswith((".", "_")):
                continue
            ideje = os.path.join(mapa, "Ideje")
            st, arhiv, zadnje = 0, 0, 0.0
            if os.path.isdir(ideje):
                for i in os.listdir(ideje):
                    pot = os.path.join(ideje, i, "ideja.json")
                    if not os.path.isfile(pot):
                        continue
                    try:
                        with open(pot, encoding="utf-8") as f:
                            v_arhivu = bool(json.load(f).get("arhiv"))
                    except (OSError, ValueError):
                        v_arhivu = False
                    if v_arhivu:
                        arhiv += 1
                    else:
                        st += 1
                    zadnje = max(zadnje, os.path.getmtime(pot))
            izid.append({"ime": ime, "idej": st, "arhiv": arhiv, "spremenjeno": zadnje or os.path.getmtime(mapa),
                         "odprt": ime == self.ime})
        izid.sort(key=lambda p: p["ime"].lower())
        return izid

    def nov(self, ime):
        ime = varno_ime(ime, "Projekt")
        osnova, i = ime, 2
        while os.path.exists(self.mapa(ime)):
            ime = "%s %d" % (osnova, i)
            i += 1
        os.makedirs(os.path.join(self.mapa(ime), "Ideje"), exist_ok=True)
        return ime

    def preimenuj(self, ime, novo):
        """Preimenuje mapo projekta; vrne novo ime. Če je projekt odprt, kličoči popravi še poti odprte ideje."""
        novo = varno_ime(novo, "Projekt")
        if not os.path.isdir(self.mapa(ime)):
            raise ValueError("ni projekta: %s" % ime)
        if novo == ime:
            return ime
        if os.path.exists(self.mapa(novo)):
            raise ValueError("projekt »%s« že obstaja" % novo)
        os.rename(self.mapa(ime), self.mapa(novo))
        if self.ime == ime:
            self.ime = novo
        return novo


def prazna_scena():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    nastavi_enote()


def nalozi_blend(pot, koren=""):
    bpy.ops.wm.open_mainfile(filepath=pot)
    nastavi_enote()
    if koren:
        popravi_vezave(koren)


def popravi_vezave(koren):
    """Vezave na kose, ki kažejo na staro mesto (npr. skupna mapa Ideje pred projekti ali absolutna pot z drugega
    računalnika), preveže na <koren>/<ideja>/<Rxx>.blend, če ta obstaja. Vrne število popravljenih vezav."""
    popravljene = 0
    for lib in list(bpy.data.libraries):
        try:
            stara = bpy.path.abspath(lib.filepath)
        except (ValueError, TypeError):
            continue
        if os.path.isfile(stara):
            continue
        deli = os.path.normpath(stara).split(os.sep)
        if len(deli) < 2:
            continue
        nova = os.path.join(koren, deli[-2], deli[-1])
        if not os.path.isfile(nova):
            continue
        try:
            lib.filepath = bpy.path.relpath(nova) if bpy.data.filepath else nova
        except ValueError:      # drug disk: absolutna pot
            lib.filepath = nova
        lib.reload()
        popravljene += 1
    return popravljene


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


def lega_v_datoteki(obj):
    """Svetovna lega objekta iz datoteke kosa, izračunana po verigi staršev iz shranjenih lastnosti (lega, zasuk, merilo).
    matrix_world vezanega objekta, ki ni v nobenem pogledu, ni izračunana (ostane enotska)."""
    m = obj.matrix_basis.copy()
    if obj.parent is not None:
        return lega_v_datoteki(obj.parent) @ obj.matrix_parent_inverse @ m
    return m


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
        telo.matrix_basis = lega_v_datoteki(izvor)    # lega telesa znotraj kosa (tudi če je bilo tam v hierarhiji)
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
# Izvoz DXF: obrisi ploskih kosov (nalepka, pločevina, rezanje) — zgornje ploskve (normala +Z) vsakega vidnega objekta,
# njihovi robni robovi zvezani v zaprte poligone, v mm v svetovnih XY; plast = ime objekta. Zapis DXF R12 (POLYLINE),
# ki ga berejo Illustrator, VersaWorks, FreeCAD, LibreCAD.

def obrisi_xy(obj, dg=None, najmanj_z=0.5):
    """Zaprti obrisi zgornjih ploskev objekta v svetovnih XY: [[(x, y), ...], ...]."""
    dg = dg or bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    try:
        me = ev.to_mesh()
    except RuntimeError:
        return []
    try:
        if me is None or not len(me.polygons):
            return []
        mw = ev.matrix_world
        nm = mw.to_3x3().inverted().transposed()
        zgornje = [p for p in me.polygons if (nm @ p.normal).normalized().z >= najmanj_z]
        stevec = {}
        for p in zgornje:
            for k in p.edge_keys:
                stevec[k] = stevec.get(k, 0) + 1
        robni = [k for k, n in stevec.items() if n == 1]
        sosedi = {}
        for a, b in robni:
            sosedi.setdefault(a, []).append(b)
            sosedi.setdefault(b, []).append(a)
        obiskani, obrisi = set(), []
        for zacetek in sosedi:
            if zacetek in obiskani:
                continue
            veriga, prej, v = [zacetek], None, zacetek
            obiskani.add(v)
            while True:
                naslednji = [s for s in sosedi[v] if s != prej and s not in obiskani]
                if not naslednji:
                    break
                prej, v = v, naslednji[0]
                obiskani.add(v)
                veriga.append(v)
            if len(veriga) >= 3:
                obrisi.append([tuple((mw @ me.vertices[i].co).xy) for i in veriga])
        return obrisi
    finally:
        ev.to_mesh_clear()


def zapisi_dxf(pot, plasti):
    """plasti: [(ime_plasti, [[(x, y), ...], ...]), ...] -> datoteka DXF R12 v mm."""
    def v(koda, vrednost):
        return "%d\n%s\n" % (koda, vrednost)
    deli = [v(0, "SECTION"), v(2, "HEADER"), v(9, "$INSUNITS"), v(70, 4), v(0, "ENDSEC"),
            v(0, "SECTION"), v(2, "TABLES"), v(0, "TABLE"), v(2, "LAYER"), v(70, len(plasti))]
    for i, (ime, _) in enumerate(plasti):
        deli += [v(0, "LAYER"), v(2, ime), v(70, 0), v(62, (i % 7) + 1), v(6, "CONTINUOUS")]
    deli += [v(0, "ENDTAB"), v(0, "ENDSEC"), v(0, "SECTION"), v(2, "ENTITIES")]
    for ime, obrisi in plasti:
        for obris in obrisi:
            deli += [v(0, "POLYLINE"), v(8, ime), v(66, 1), v(70, 1)]
            for x, y in obris:
                deli += [v(0, "VERTEX"), v(8, ime), v(10, "%.4f" % x), v(20, "%.4f" % y), v(30, "0.0")]
            deli += [v(0, "SEQEND"), v(8, ime)]
    deli += [v(0, "ENDSEC"), v(0, "EOF")]
    os.makedirs(os.path.dirname(pot), exist_ok=True)
    with open(pot, "w", encoding="ascii", errors="replace", newline="\r\n") as f:
        f.write("".join(deli))
    return sum(len(o) for _, o in plasti)


def izvozi_dxf(pot, objekti=None):
    """DXF obrisov vidnih objektov scene (ali naštetih imen): plast = ime objekta (ASCII). Vrne {pot, plasti, obrisov}."""
    dg = bpy.context.evaluated_depsgraph_get()
    plasti = []
    for obj in bpy.context.scene.objects:
        if obj.type not in VRSTE_GEOMETRIJE or (objekti and obj.name not in objekti):
            continue
        try:
            if obj.hide_get() or obj.hide_viewport:
                continue
        except RuntimeError:
            pass
        obrisi = obrisi_xy(obj, dg)
        if obrisi:
            ime = "".join(c if (c.isascii() and (c.isalnum() or c in "-_ ")) else "_" for c in obj.name).strip() or "Obris"
            plasti.append((ime, obrisi))
    st = zapisi_dxf(pot, plasti)
    return {"pot": pot, "plasti": [ime for ime, _ in plasti], "obrisov": st}


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
