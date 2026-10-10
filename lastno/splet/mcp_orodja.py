# -*- coding: utf-8 -*-
"""Orodja MCP spletnega FreeCAD-a: katalog, izvedba, iskanje, slike (plan MCP-PLAN.md).

AI (Claude Code, Claude Desktop, Cursor) pride do FreeCAD-a prek mostu lastno/mcp/freecad_mcp.py (stdio MCP), ki
vsak klic orodja prevede v POST /mcp/orodje na strežnik (streznik.py). Tu je vse ostalo: katalog orodij z opisi in
shemami (GET /mcp/orodja), viri s pravili (GET /mcp/vir), predloge in izvedba.

Pravilo niti velja tudi tukaj: orodje z nit="streznik" teče na niti HTTP in FreeCAD-ovega API-ja NE kliče (bere le
posnetke, kliče druge strežnike, čaka); orodje z nit="glavna" gre v vrsto glavne niti (STANJE.vrsta, ukaz "mcp") in
sme vse. Orodje na niti strežnika lahko del dela pošlje na glavno nit z `_na_glavni(fn)`.

Novo orodje = ena funkcija z dekoratorjem @orodje. Vroča zamenjava brez ponovnega zagona FreeCAD-a:
    import importlib, mcp_orodja; importlib.reload(mcp_orodja); mcp_orodja.povezi(S)
(stanje — vrsta zahtev brskalniku, opravila, dnevnik — je shranjeno na STANJE.mcp in reload preživi). Most ob
spremenjeni verziji kataloga Claude Code javi notifications/tools/list_changed.
"""

import ast
import base64
import collections
import contextlib
import hashlib
import http.client
import io
import itertools
import json
import math
import os
import re
import sys
import threading
import time
import traceback
import unicodedata
import uuid

import FreeCAD as App

try:
    import FreeCADGui as Gui
except ImportError:  # FreeCADCmd
    Gui = None

S = None           # modul strežnika (streznik.py); nastavi povezi()
ORODJA = {}        # ime -> opis orodja (glej orodje())
NAJVEC_ZNAKOV = 60000   # zgornja meja besedila v odgovoru (varuje kontekst AI)
MAPA = os.path.dirname(os.path.abspath(__file__))
KOREN_REPO = os.path.normpath(os.path.join(MAPA, "..", ".."))
DATOTEKA_KATALOGA = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "FreeCAD-splet",
                                 "mcp-orodja.json")
try:
    VERZIJA_FREECAD = ".".join(App.Version()[:3])
except Exception:  # noqa: BLE001
    VERZIJA_FREECAD = "?"


class Napaka(Exception):
    """Napaka, ki jo AI dobi kot kratko sporočilo (brez sledi klicev)."""


# ---------------------------------------------------------------------------------------------------------------
# Povezava s strežnikom in skupno stanje (preživi reload modula)

def povezi(modul):
    """Pokliče streznik.py ob zagonu (in vroča zamenjava): modul strežnika, ovoj dnevnika, zapis kataloga."""
    global S
    S = modul
    _st()
    stari = getattr(S, "_log", None)
    if stari is not None and not getattr(stari, "_mcp", False):
        def _log(besedilo, _stari=stari):
            _dnevnik("splet", besedilo)
            _stari(besedilo)
        _log._mcp = True
        S._log = _log
    try:
        zapisi_katalog()
    except Exception as e:  # noqa: BLE001
        _dnevnik("mcp", "katalog ni zapisan: %r" % e)


def _st():
    """Skupno stanje MCP na objektu STANJE (zahteve brskalniku, opravila, dnevnik, indeks iskanja)."""
    stanje = S.STANJE
    st = getattr(stanje, "mcp", None)
    if st is None:
        st = {"zahteve": {}, "opravila": {}, "dnevnik": collections.deque(maxlen=500), "indeks": {},
              "kljuc": threading.Lock()}
        stanje.mcp = st
    return st


def _dnevnik(vir, besedilo):
    try:
        _st()["dnevnik"].append((time.time(), vir, str(besedilo)))
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------------------------------------------
# Katalog

def orodje(ime, opis, lastnosti=None, obvezne=(), nit="glavna", samo_branje=False, unicujoce=False, cakaj=120,
           naslov=""):
    """Registrira orodje. `lastnosti`: JSON shema argumentov (ime -> shema), `nit`: "glavna" ali "streznik",
    `cakaj`: privzeti čas čakanja na glavno nit (s; argument `cakaj` ga prepiše)."""
    def ovoj(fn):
        shema = {"type": "object", "properties": dict(lastnosti or {}), "additionalProperties": False}
        if obvezne:
            shema["required"] = list(obvezne)
        ORODJA[ime] = {"ime": ime, "opis": opis.strip(), "shema": shema, "fn": fn, "nit": nit,
                       "samo_branje": samo_branje, "unicujoce": unicujoce, "cakaj": cakaj, "naslov": naslov or ime}
        return fn
    return ovoj


def katalog():
    orodja = []
    for o in ORODJA.values():
        orodja.append({
            "name": o["ime"], "title": o["naslov"], "description": o["opis"], "inputSchema": o["shema"],
            "annotations": {"title": o["naslov"], "readOnlyHint": o["samo_branje"],
                            "destructiveHint": o["unicujoce"], "openWorldHint": False},
        })
    jedro = {"orodja": orodja, "viri": [{k: v for k, v in r.items() if k != "fn"} for r in VIRI],
             "predloge": PREDLOGE, "navodila": NAVODILA}
    verzija = hashlib.sha1(json.dumps(jedro, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]
    jedro.update({"verzija": verzija, "freecad": VERZIJA_FREECAD, "vrata": getattr(S, "VRATA", 0)})
    return jedro


def zapisi_katalog():
    """Zadnji znani katalog za most, ko strežnik ne teče (most takrat ponudi orodja in zazeni)."""
    os.makedirs(os.path.dirname(DATOTEKA_KATALOGA), exist_ok=True)
    zacasna = DATOTEKA_KATALOGA + ".delno"
    with open(zacasna, "w", encoding="utf-8") as f:
        json.dump(katalog(), f, ensure_ascii=False)
    os.replace(zacasna, DATOTEKA_KATALOGA)


# ---------------------------------------------------------------------------------------------------------------
# Izvedba (nit strežnika -> po potrebi glavna nit)

def izvedi(ime, argumenti, seja=""):
    """POST /mcp/orodje (nit strežnika). Vrne JSON bajte: {ok, napaka, vsebina: [...], katalog}."""
    zacetek = time.time()
    izid = izvedi_slovar(ime, argumenti, seja)
    vsebina = []
    if izid.get("besedilo"):
        vsebina.append({"vrsta": "besedilo", "besedilo": izid["besedilo"]})
    for mime, bajti in izid.get("slike") or []:
        vsebina.append({"vrsta": "slika", "mime": mime, "podatki": base64.b64encode(bajti).decode("ascii")})
    odgovor = {"ok": not izid.get("napaka"), "napaka": bool(izid.get("napaka")), "vsebina": vsebina,
               "katalog": katalog()["verzija"], "cas": round(time.time() - zacetek, 2)}
    return json.dumps(odgovor, ensure_ascii=False, default=str).encode("utf-8")


def izvedi_slovar(ime, argumenti, seja=""):
    """Izvede orodje (katera koli nit razen glavne) in vrne {napaka, besedilo, slike: [(mime, bajti)]}; uporabljata
    ga POST /mcp/orodje in pomočnik v brskalniku (pomocnik.py)."""
    zacetek = time.time()
    o = ORODJA.get(ime)
    argumenti = argumenti if isinstance(argumenti, dict) else {}
    try:
        if o is None:
            raise Napaka("Orodje »%s« ne obstaja. Orodja: %s" % (ime, ", ".join(sorted(ORODJA))))
        if o["nit"] == "streznik":
            izid = o["fn"](argumenti)
        else:
            izid = _na_glavni(lambda: o["fn"](argumenti), _cakaj(argumenti, o["cakaj"]), ime)
        izid = _normaliziraj(izid)
        nadaljuj = izid.pop("_nadaljuj", None)
        if callable(nadaljuj):
            izid["besedilo"] = (izid.get("besedilo") or "") + "\n" + str(nadaljuj())
    except Napaka as e:
        izid = {"napaka": True, "besedilo": str(e)}
    except Exception:  # noqa: BLE001
        izid = {"napaka": True, "besedilo": "Napaka v orodju %s:\n%s" % (ime, _kratka_sled(traceback.format_exc()))}
    trajanje = time.time() - zacetek
    argi = json.dumps(argumenti, ensure_ascii=False)
    _dnevnik("mcp", "%s %s %s %.2f s%s" % (seja or "?", ime, argi if len(argi) <= 160 else argi[:160] + " …",
                                          trajanje, " NAPAKA" if izid.get("napaka") else ""))
    if izid.get("besedilo"):
        izid["besedilo"] = _kratko(izid["besedilo"], NAJVEC_ZNAKOV)
    return izid


def _cakaj(argumenti, privzeto):
    try:
        return max(1.0, min(float(argumenti.get("cakaj") or privzeto), 1800.0))
    except (TypeError, ValueError):
        return float(privzeto)


def _normaliziraj(izid):
    if izid is None:
        return {"besedilo": "Opravljeno."}
    if isinstance(izid, str):
        return {"besedilo": izid}
    return izid


def glavna(stanje, podatki, odgovor):
    """Stanje._izvedi za ukaz "mcp" (glavna nit): izvede funkcijo iz _na_glavni. Napake vrne kot rezultat, da ne
    pristanejo v STANJE.napaka (to je zadnja napaka strežnika, ne AI)."""
    fn = podatki.get("fn")
    try:
        rezultat = fn()
    except Napaka as e:
        rezultat = {"napaka": True, "besedilo": str(e)}
    except Exception:  # noqa: BLE001
        rezultat = {"napaka": True, "besedilo": _kratka_sled(traceback.format_exc())}
    if odgovor is not None:
        odgovor["rezultat"] = rezultat


def _na_glavni(fn, cakaj=120.0, ime="", ozadje=False):
    """Izvede fn na glavni niti FreeCAD-a in vrne njen rezultat. Če ne konča v `cakaj` s, vrne oznako opravila
    (`opravilo` počaka nanj kasneje); glavna nit ga vseeno dokonča."""
    odgovor = {"konec": threading.Event(), "izpis": "", "napaka": "", "rezultat": None}
    (S.STANJE.vrsta_ozadje if ozadje else S.STANJE.vrsta).put(("mcp", {"fn": fn}, odgovor))
    if not odgovor["konec"].wait(cakaj):
        oid = uuid.uuid4().hex[:8]
        _st()["opravila"][oid] = {"odgovor": odgovor, "ime": ime, "zacetek": time.time()}
        return {"besedilo": "Še teče na glavni niti FreeCAD-a (več kot %d s). Opravilo %s: počakaj nanj z "
                            "`opravilo` {\"id\": \"%s\"}." % (cakaj, oid, oid), "opravilo": oid}
    if odgovor["napaka"]:
        return {"napaka": True, "besedilo": _kratka_sled(odgovor["napaka"])}
    return odgovor["rezultat"]


def _glavna_vrednost(fn, cakaj=60.0):
    """Kot _na_glavni, a vrne surovo vrednost fn ali dvigne Napaka (za pomožne klice iz orodij na niti strežnika)."""
    izid = _na_glavni(lambda: {"vrednost": fn()}, cakaj)
    if izid.get("opravilo"):
        raise Napaka("FreeCAD je zaseden (glavna nit ne odgovori v %d s). Poskusi znova ali poglej `stanje`." % cakaj)
    if izid.get("napaka"):
        raise Napaka(izid["besedilo"])
    return izid["vrednost"]


def _kratka_sled(sled, vrstic=14):
    vrstice = sled.strip().splitlines()
    if len(vrstice) <= vrstic:
        return "\n".join(vrstice)
    return "\n".join(["…"] + vrstice[-vrstic:])


def _kratko(besedilo, n):
    besedilo = str(besedilo)
    if len(besedilo) <= n:
        return besedilo
    return besedilo[:n] + "\n… (odrezano: %d znakov od %d)" % (len(besedilo) - n, len(besedilo))


# ---------------------------------------------------------------------------------------------------------------
# Zahteve brskalniku (slika pogleda, kamera, okno Pripravi): dogodek SSE "mcp" -> POST /mcp/odgovor

def brskalnik(zahteva, podatki=None, cakaj=10.0):
    """Pošlje zahtevo odprtim zavihkom strani in počaka na prvi odgovor (dict) ali vrne None. Brez čakanja, če ni
    zavihka ali se od zagona strežnika ni oglasila nobena stran, ki zahteve pozna (starejša stran jih prezre)."""
    if not S.STANJE.odjemalci or not _st().get("zdravo"):
        return None
    zid = uuid.uuid4().hex[:12]
    vnos = {"dogodek": threading.Event(), "odgovor": None, "cas": time.time()}
    _st()["zahteve"][zid] = vnos
    try:
        S.STANJE.oddaj("mcp", dict(podatki or {}, id=zid, zahteva=zahteva))
        vnos["dogodek"].wait(cakaj)
    finally:
        _st()["zahteve"].pop(zid, None)
    return vnos["odgovor"]


def brskalnik_odgovor(podatki):
    """POST /mcp/odgovor (nit strežnika): odgovor zavihka na zahtevo; velja prvi. id »zdravo«: stran ob povezavi javi,
    da zahteve pozna."""
    if podatki.get("id") == "zdravo":
        _st()["zdravo"] = time.time()
        return True
    vnos = _st()["zahteve"].get(str(podatki.get("id", "")))
    if vnos is None or vnos["odgovor"] is not None:
        return False
    vnos["odgovor"] = podatki
    vnos["dogodek"].set()
    return True


# ---------------------------------------------------------------------------------------------------------------
# Pomožne funkcije (glavna nit, razen kjer piše drugače)

def _normaliziraj_besedilo(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def _dokumenti():
    return list(App.listDocuments().values())


def _dokument(ime=None, obvezen=True):
    """Dokument po imenu (Name), oznaki (Label) ali poti; brez imena aktivni."""
    if not ime:
        doc = App.ActiveDocument
        if doc is None and obvezen:
            raise Napaka("Ni aktivnega dokumenta. Odpri ali ustvari ga z `dokumenti`.")
        return doc
    ime = str(ime)
    dokumenti = App.listDocuments()
    if ime in dokumenti:
        return dokumenti[ime]
    for d in dokumenti.values():
        if d.Label == ime:
            return d
    norm = os.path.normcase(os.path.normpath(ime))
    for d in dokumenti.values():
        if d.FileName and os.path.normcase(os.path.normpath(d.FileName)) == norm:
            return d
    kandidati = [d for d in dokumenti.values() if _normaliziraj_besedilo(ime) in _normaliziraj_besedilo(d.Label)]
    if len(kandidati) == 1:
        return kandidati[0]
    if obvezen:
        predlogi = ", ".join("»%s«" % d.Label for d in kandidati[:10])
        raise Napaka("Dokument »%s« ni odprt.%s Seznam: `dokumenti`." % (
            ime, (" Podobni: " + predlogi + ".") if predlogi else ""))
    return None


def _objekt(doc, ime):
    obj = doc.getObject(ime)
    if obj is not None:
        return obj
    zadetki = doc.getObjectsByLabel(ime)
    if zadetki:
        return zadetki[0]
    norm = _normaliziraj_besedilo(ime)
    podobni = [o for o in doc.Objects if norm in _normaliziraj_besedilo(o.Label) or norm in o.Name.lower()]
    if len(podobni) == 1:
        return podobni[0]
    raise Napaka("Objekta »%s« v dokumentu »%s« ni.%s Strukturo pokaže `drevo`." % (
        ime, doc.Label, (" Podobni: " + ", ".join("%s [%s]" % (o.Label, o.Name) for o in podobni[:12]) + ".")
        if podobni else ""))


def _spremenjen(doc):
    try:
        return bool(Gui.getDocument(doc.Name).Modified) if (Gui is not None and App.GuiUp) else False
    except Exception:  # noqa: BLE001
        return False


def _cisto_podime(sub):
    """Podime iz izbire brez FreeCAD-ovih preslikanih imen elementov (»Posnetje.;Edge3;:G…;:H…,E.Edge12« ->
    »Posnetje.Edge12«)."""
    return ".".join(d for d in str(sub).split(".") if d and not d.startswith(";"))


def _je_element(ime):
    return bool(re.match(r"^(Face|Edge|Vertex)\d+$", ime or ""))


def _razresi(doc, ref):
    """Sklic »Objekt«, »Objekt.Face3« ali pot »Sestav.Povezava.Face2« -> (koren, podpot, element, objekt).
    Vgnezden objekt (v telesu, App::Part, sestavu) se razreši od korena (obj.Parents), da je geometrija globalna."""
    deli = [d for d in str(ref).split(".") if d != ""]
    if not deli:
        raise Napaka("Prazen sklic na objekt.")
    element = deli[-1] if _je_element(deli[-1]) else ""
    pot = deli[1:-1] if element else deli[1:]
    obj = _objekt(doc, deli[0])
    koren, predpona = obj, ""
    try:
        starsi = obj.Parents
    except Exception:  # noqa: BLE001
        starsi = []
    if starsi:
        koren, predpona = starsi[0][0], starsi[0][1]
    podpot = predpona + "".join(p + "." for p in pot)
    if not predpona and not pot:
        podpot = ""
    return koren, podpot, element, obj


def _oblika(doc, ref):
    import Part
    koren, podpot, element, obj = _razresi(doc, ref)
    if podpot or element:
        oblika = Part.getShape(koren, podpot + element, needSubElement=bool(element), transform=True)
    else:
        oblika = Part.getShape(koren, "", needSubElement=False, transform=True)
    if oblika is None or oblika.isNull():
        raise Napaka("»%s« nima geometrije." % ref)
    return oblika, obj


def _st_mm(v, dec=2):
    s = ("%." + str(dec) + "f") % (v + 0.0)
    if s.startswith("-") and float(s) == 0:
        s = s[1:]   # brez »-0«
    s = s.rstrip("0").rstrip(".") if "." in s else s
    return s.replace(".", ",")


def _vektor(v, dec=2):
    return "(%s; %s; %s)" % (_st_mm(v.x, dec), _st_mm(v.y, dec), _st_mm(v.z, dec))


def _odtis_objektov():
    return {d.Name: {o.Name: o.TypeId for o in d.Objects} for d in _dokumenti()}


def _dotaknjeni():
    izid = {}
    for d in _dokumenti():
        try:
            izid[d.Name] = {o.Name for o in d.Objects if "Touched" in o.State}
        except Exception:  # noqa: BLE001
            izid[d.Name] = set()
    return izid


def _razlika_objektov(pred, po):
    vrstice = []
    for ime, objekti in po.items():
        doc = App.getDocument(ime)
        prej = pred.get(ime)
        if prej is None:
            vrstice.append("Nov dokument »%s« (%s), objektov: %d." % (doc.Label, ime, len(objekti)))
            continue
        novi = [n for n in objekti if n not in prej]
        if novi:
            opisi = []
            for n in novi[:40]:
                o = doc.getObject(n)
                opisi.append("%s [%s] %s" % (o.Label if o else n, n, objekti[n]))
            vrstice.append("Novi objekti v »%s«: %s%s" % (doc.Label, "; ".join(opisi),
                                                          " … (+%d)" % (len(novi) - 40) if len(novi) > 40 else ""))
        odstranjeni = [n for n in prej if n not in objekti]
        if odstranjeni:
            vrstice.append("Odstranjeni iz »%s«: %s" % (doc.Label, ", ".join(odstranjeni[:40])))
    for ime in pred:
        if ime not in po:
            vrstice.append("Zaprt dokument %s." % ime)
    return vrstice


def _neveljavni(doc):
    """Objekti z napako po preračunu (Invalid / Error) in kratko sporočilo."""
    izid = []
    for o in doc.Objects:
        try:
            stanje = o.State
        except Exception:  # noqa: BLE001
            continue
        if "Invalid" in stanje or "Error" in stanje:
            try:
                sporocilo = o.getStatusString()
            except Exception:  # noqa: BLE001
                sporocilo = ""
            izid.append("%s [%s]: %s" % (o.Label, o.Name, sporocilo or ", ".join(stanje)))
    return izid


def _json_vrednost(v):
    if isinstance(v, App.Vector):
        return [round(v.x, 6), round(v.y, 6), round(v.z, 6)]
    if hasattr(v, "Value") and hasattr(v, "Unit"):
        return str(v)
    if hasattr(v, "Name") and hasattr(v, "TypeId") and hasattr(v, "Label"):
        return "%s [%s]" % (v.Label, v.Name)
    if isinstance(v, (set, frozenset, tuple)):
        return list(v)
    return str(v)


# ---------------------------------------------------------------------------------------------------------------
# Besedila za AI

NAVODILA = r"""
Spletni FreeCAD je lastna gradnja FreeCAD 1.1 na tem računalniku: okno je skrito, uporabnik dela v brskalniku
(http://127.0.0.1:3020/). Orodja delajo v istem primerku, ki ga uporabnik gleda: vsaka sprememba je takoj vidna,
odprtih je lahko več deset njegovih dokumentov.
- Pregled: `stanje`, `dokumenti`, `drevo` (struktura; z `objekt` vse lastnosti in napake objekta), `slika` (poglej
  model, preden trdiš, da je prav), `izmeri` (mere, razdalje, kot, trki).
- Ne veš, kako? `isci`: ukazi okolij, FreeCAD API (Part, Sketcher, PartDesign …, tipi objektov z lastnostmi), naši
  moduli, skripte projektov, končne točke spletnega strežnika, pravila.
- Delo: `python` (celoten FreeCAD API na glavni niti; vrne izpis in spremenljivko `rezultat`), `ukaz` + `obrazec` za
  ukaze z okni (Zaokrožitev, Make Wall …), `izberi` za ploskve in robove pred ukazom.
- Vsak klic `python` je ena transakcija: ob napaki se razveljavi sam, sicer ga vrne `razveljavi`.
- Na disk piše samo `shrani` (s `komentar` za različico v oblaku). `python` ne shranjuje, ne zapira dokumentov in ne
  briše datotek. `izhod` konča program le z izrecno potrditvijo uporabnika.
- Boolovih operacij (common, cut, fuse) ne poganjaj v zankah čez veliko kosov: glavna nit obvisi za minute. Trke
  preverjaj z `izmeri`.
- Modeli: C:\Users\Uporabnik\Oblak\3D modeliranje\<Projekt>\ (skripte v Skripte\, PREBERI.txt); standardni deli v
  Standardni deli\. Poti v Python nizih piši kot r"C:\..." ali z "/".
- Postopki dela (nov kos, okna ukazov, pločevina, sestav, pregled, tisk, render): orodje `postopki`.
- Podrobna pravila in pasti: vir freecad://pravila ali `isci` z vrsta "pravilo". Če strežnik ne teče: `zazeni`.
""".strip()

PRAVILA = r"""
# Pravila in pasti spletnega FreeCAD-a

## Niti in odzivnost
- Koda iz `python` teče na glavni niti FreeCAD-a; med izvajanjem stran v brskalniku zamrzne. Dolgo delo razdeli na več
  klicev ali nastavi `cakaj` in nadaljuj z `opravilo`.
- Boolove operacije (common, cut, fuse) v zankah čez veliko kosov (npr. pločevinaste lupine) obesijo glavno nit za več
  deset minut in strežnik ne sprejema povezav. Za trke uporabi `izmeri` (razdalja, oglišča, obsegi).
- Krog zapis-branje STEP v procesu spletnega FreeCAD-a lahko sproži Access violation: tak krog delaj v FreeCADCmd.
- V kodi `python` ne kliči Gui.runCommand za ukaze, ki odprejo okno (glavna nit obstane): uporabi orodje `ukaz` in
  okno izpolni z `obrazec`.

## Dokumenti in shranjevanje
- Shranjuje samo orodje `shrani`. Po shranjevanju iz skripte bi ostala oznaka »neshranjeno«; `shrani` jo počisti.
- Datoteko, ki jo drži drug proces (odjemalec oblaka), FreeCAD zavrne kot »read-only«: poskusi znova čez nekaj sekund.
- Povezava (App::Link) na drug dokument zahteva, da je ciljni dokument shranjen. Ime objekta (Name) naj bo ASCII
  (newObject z ne-ASCII imenom pade), oznaka (Label) je lahko slovenska.
- Ciljni dokument določi po imenu ali oznaki (argument `dokument`, v kodi `doc`), ne zanašaj se na App.ActiveDocument:
  uporabnik ali druga seja ga lahko medtem zamenja.
- Za slike uporabi `slika`; saveImage v skritem oknu da prazno sliko za dokumente, odprte z openDocument.

## Skice (Sketcher)
- Lok podaj s središčem in kotoma: Part.ArcOfCircle(Part.Circle(sredisce, App.Vector(0,0,1), r), a0, a1). Iz treh točk
  ga ne gradi: skicirnik vodi loke le v nasprotni smeri urinega kazalca, sovpadanja nato potegnejo napačno krajišče.
- Po omejitvah preveri sk.solve() == 0 in sk.FullyConstrained; odvečne (sk.RedundantConstraints) odstrani.
- Rob objekta zunaj telesa v skico telesa ne gre kot zunanja geometrija.

## Sestavi (Assembly)
- Spoj iz skripte: najprej Offset1/Offset2 (in Distance), šele nato Reference1/Reference2; sprememba odmika ob
  nastavljenih referencah kos premakne prezgodaj.
- Povezava z več elementi (ElementCount, ShowElement = True) mora imeti ničelno lego; lego nosi vsak element.
- Gibljiv podsestav: Assembly::AssemblyLink z Rigid = False. Povezave ne dajaj v vsebnik z lego.

## Pločevina
- Pred modeliranjem preberi lastno/raziskava/plocevina.md (v repozitoriju FreeCAD). Lastna parametrična objekta
  TeloVPlocevino in Razgrnitev (lastno/plocevina/lastna_plocevina.py) iščeta ploskve geometrijsko; SheetMetal objekti s
  shranjenimi imeni (Face4, Edge14) se ob spremembi mer pokvarijo.
- Lastnosti ne poimenuj `Debelina` (baza standardnih delov po njej prepozna pločevino).

## Videz, elektro, kabli
- Videz kosa: `splet` POST /videz {dejanje: "nastavi", ime, videz}; prednastavitve vrne {dejanje: "seznam"}.
- Ne dodajaj Gui.addDocumentObserver s slotChangedObject (objekti Part potem nimajo DiffuseColor).
- Elektronski kosi nosijo lastnost Prikljucki in točke Prikljucek_<ime>; kable napelji s Plosca.povezi (Skripte/
  elektro_kabli.py v projektu Photobox Slim A). Po spremembi kataloga priključkov preračunaj nosilce in sestave.

## Datoteke
- Modeli: C:\Users\Uporabnik\Oblak\3D modeliranje\<Projekt>\ (FCStd, STEP, slike v korenu; skripte v Skripte\ pišejo
  izhod eno raven višje; PREBERI.txt opiše projekt).
- Baza standardnih delov: Oblak\3D modeliranje\Standardni deli\<kategorija>\. Kos v bazo premakne `splet` POST
  /standardni {dejanje: "oznaci", dokument, kategorija}, ne ročno premikanje datotek (sestavi bi izgubili povezave).
- Ne briši uporabnikovih datotek in objektov, ki jih nisi ustvaril sam, brez izrecnega naročila.
""".strip()

KONCNE_TOCKE = [
    ("GET", "/stanje", "stanje strežnika (verzija posnetka, izbira, okolje, napaka)", ""),
    ("GET", "/projekti", "odprti dokumenti in datoteke projektov", ""),
    ("GET", "/ukazi", "ukazi vseh okolij (velik odgovor, raje `isci`)", ""),
    ("GET", "/knjiznica", "baza standardnih delov po kategorijah", ""),
    ("GET", "/zgradba", "zgradba sestava čez datoteke (količine kosov)", "?ime=<dokument>"),
    ("GET", "/tiskaj/stanje", "plošča tiskalnikov Tiskaj: teče, tiskalniki, vrsta", ""),
    ("GET", "/oblikovanje/stanje", "Blender (Oblikovanje): teče, vrata", ""),
    ("GET", "/render/seznam", "renderji te seje", ""),
    ("GET", "/render/stanje", "stanje renderja", "?id=<id>"),
    ("GET", "/oblak/zgodovina", "različice datoteke v oblaku", "?pot=<pot>"),
    ("GET", "/oblak/zaklep", "zaklep datoteke v oblaku", "?pot=<pot>"),
    ("GET", "/oblak/reference", "reference in kosovnica datoteke iz oblaka", "?pot=<pot>"),
    ("POST", "/select", "izbira (raje orodje `izberi`)", "{objekt, element, dodaj}"),
    ("POST", "/ukaz", "sproži ukaz (raje orodje `ukaz`)", "{ime, indeks}"),
    ("POST", "/okolje", "aktiviraj delovno okolje", "{ime}"),
    ("POST", "/okno", "pokaži ali skrij okno FreeCAD-a", "{prikazi}"),
    ("POST", "/skica", "skica v brskalniku", "{vrsta: nova|odpri|zapri|crta|pravokotnik|krog|tocka|premakni|izbrisi|"
                                               "mera|omejitev|gradbena|nastaviMero|polozajMere, ...}"),
    ("POST", "/znacilnost", "izboklina ali ugrez iz skice", "{skica, vrsta: izboklina|ugrez, dolzina, obrni, simetricno}"),
    ("POST", "/obrazec", "dejanje v obrazcu (raje orodje `obrazec`)", "{kljuc, id, dejanje, vrednost}"),
    ("POST", "/projekt", "odpri ali aktiviraj dokument (raje `dokumenti`)", "{dejanje: odpri|aktiviraj, pot|ime}"),
    ("POST", "/drevo", "dejanja drevesa", "{dejanje: vidnost|lastnost|uredi|kosov, ime, vidno|lastnost+vrednost|stevilo}"),
    ("POST", "/knjiznica", "vstavi kos iz baze v sestav", "{dejanje: vstavi|odpri, pot, dokument}"),
    ("POST", "/standardni", "baza standardnih delov", "{dejanje: podatki|oznaci|odznaci, dokument, kategorija}"),
    ("POST", "/videz", "videz kosov (materiali)", "{dejanje: seznam|nastavi|plocevina, ime, videz}"),
    ("POST", "/tisk/lega", "analiza lege za 3D tisk", "{dokument, imena, kot_previsa}"),
    ("POST", "/tiskaj/zazeni", "zaženi ploščo Tiskaj", "{}"),
    ("POST", "/oblikovanje/zazeni", "zaženi Blender (Oblikovanje)", "{}"),
    ("POST", "/render/ustavi", "ustavi render", "{id}"),
    ("POST", "/oblak/odpri", "odpri različico iz oblaka", "{pot, rev}"),
    ("POST", "/oblak/obnovi", "povrni različico (nova revizija)", "{pot, rev}"),
    ("POST", "/oblak/komentar", "komentar k zadnji reviziji", "{pot, komentar}"),
    ("POST", "/oblak/revizija", "komentar ali stanje revizije", "{pot, rev, komentar?, stanje?: osnutek|v_pregledu|izdano}"),
    ("POST", "/oblak/zakleni", "zakleni datoteko v oblaku", "{pot}"),
    ("POST", "/oblak/odkleni", "odkleni datoteko v oblaku", "{pot}"),
]
PREPOVEDANE_POTI = {"/izhod": "uporabi orodje `izhod`", "/python": "uporabi orodje `python`",
                    "/events": "tok dogodkov SSE ni za orodja", "/model": "posnetek geometrije je prevelik; uporabi "
                    "`slika`, `drevo` ali `izmeri`", "/posnetek": "posnetek geometrije je prevelik",
                    "/slicica": "sličice ureja stran sama"}


def _vir_okolja():
    try:
        ukazi = json.loads(S.STANJE.ukazi())
    except ValueError:
        return "Seznam ukazov še ni pripravljen."
    vrstice = ["# Delovna okolja in ukazi", "",
               "Ukaz sproži orodje `ukaz` {\"ime\": ...}; nenaloženo okolje naloži `ukaz` {\"okolje\": ...}.", ""]
    for o in ukazi.get("delovnaOkolja", []):
        vrstice.append("## %s (%s)%s" % (o.get("naslov") or o["ime"], o["ime"], "" if o.get("nalozeno", True)
                                         else " — še ni naloženo"))
        for t in o.get("orodneVrstice", []):
            imena = []
            for skupina in t.get("skupine", []):
                for u in skupina:
                    imena.append("%s (%s)" % (u.get("ime"), u.get("naslov", "")))
                    for p in u.get("podukazi") or []:
                        if isinstance(p, dict):
                            imena.append("%s (%s)" % (p.get("ime"), p.get("naslov", "")))
            if imena:
                vrstice.append("- %s: %s" % (t.get("naslov") or t.get("ime"), ", ".join(imena)))
        vrstice.append("")
    return "\n".join(vrstice)


def _vir_splet():
    vrstice = ["# Končne točke spletnega strežnika (orodje `splet`)", "",
               "Vsak POST potrebuje žeton; orodje `splet` ga doda samo. Telo je JSON.", ""]
    for metoda, pot, opis, telo in KONCNE_TOCKE:
        vrstice.append("- %s %s%s — %s" % (metoda, pot, (" " + telo) if telo else "", opis))
    vrstice += ["", "Ne prek `splet`: " + "; ".join("%s (%s)" % (p, r) for p, r in PREPOVEDANE_POTI.items())]
    return "\n".join(vrstice)


VIRI = [
    {"uri": "freecad://pravila", "name": "Pravila in pasti spletnega FreeCAD-a", "mimeType": "text/markdown",
     "description": "Niti, shranjevanje, skice, sestavi, pločevina, datoteke: kaj ne deluje in kako prav.",
     "fn": lambda: PRAVILA},
    {"uri": "freecad://okolja", "name": "Delovna okolja in ukazi", "mimeType": "text/markdown",
     "description": "Vsa okolja z orodnimi vrsticami in imeni ukazov (za orodje ukaz).", "fn": _vir_okolja},
    {"uri": "freecad://splet", "name": "Končne točke spletnega strežnika", "mimeType": "text/markdown",
     "description": "Katalog končnih točk za orodje splet.", "fn": _vir_splet},
    {"uri": "freecad://postopki", "name": "Postopki dela v spletnem FreeCAD-u", "mimeType": "text/markdown",
     "description": "Kako upravljati FreeCAD s temi orodji (isto kot skill freecad in orodje postopki).",
     "fn": lambda: _postopki_besedilo()},
]


def vir(uri):
    for r in VIRI:
        if r["uri"] == uri:
            return {"uri": uri, "mimeType": r["mimeType"], "text": r["fn"]()}
    return None


PREDLOGE = [
    {"name": "nov_kos", "description": "Nov parametričen kos (telo, skice z omejitvami, značilnosti) in preverba.",
     "arguments": [{"name": "opis", "description": "kaj naj kos je, z merami", "required": True},
                   {"name": "projekt", "description": "mapa projekta v Oblak/3D modeliranje", "required": False}],
     "besedilo": "V spletnem FreeCAD-u naredi nov parametričen kos: {opis}.\n"
                 "1. `dokumenti` {{\"dejanje\": \"nov\"}} z jasnim imenom; telo PartDesign, skice na ravninah izhodišča.\n"
                 "2. Mere naj bodo na enem mestu (spremenljivke na vrhu kode ali preglednica), skice popolnoma omejene "
                 "(sk.FullyConstrained), loki s središčem in kotoma.\n"
                 "3. Po vsakem koraku: `drevo` (brez napak), `izmeri` (okvir, prostornina), `slika` izo in dva "
                 "pravokotna pogleda.\n"
                 "4. Uporabniku pokaži slike in mere; shrani (`shrani`) šele na njegovo željo, v "
                 "Oblak/3D modeliranje/{projekt}/."},
    {"name": "plocevina", "description": "Kos iz pločevine z razgrnitvijo (DXF).",
     "arguments": [{"name": "opis", "description": "kos, debelina, material", "required": True}],
     "besedilo": "Naredi kos iz pločevine: {opis}.\nNajprej preberi lastno/raziskava/plocevina.md v repozitoriju "
                 "FreeCAD (C:/Users/Uporabnik/Desktop/Apps/FreeCAD). Uporabi lastna objekta TeloVPlocevino in "
                 "Razgrnitev (lastno/plocevina/lastna_plocevina.py), ne SheetMetal z imeni ploskev. Preveri z `slika` "
                 "in `izmeri`; razgrnitev naj bo skrita. Lastnosti ne imenuj Debelina."},
    {"name": "sestav", "description": "Sestav iz shranjenih kosov s spoji.",
     "arguments": [{"name": "kosi", "description": "kateri kosi in kako so povezani", "required": True}],
     "besedilo": "Sestavi: {kosi}.\nOkolje Assembly: kosi kot App::Link na shranjene dokumente, en kos pritrjen "
                 "(GroundedJoint), spoji s Offset1/Offset2 pred Reference1/Reference2. Preveri gibanje in trke "
                 "(`izmeri` z vsi=true), pokaži `slika`."},
    {"name": "pregled", "description": "Pregled modela brez sprememb: napake, mere, trki, slike.",
     "arguments": [{"name": "dokument", "description": "ime ali oznaka dokumenta (privzeto aktivni)",
                    "required": False}],
     "besedilo": "Preglej dokument »{dokument}« (prazno = aktivni) v spletnem FreeCAD-u, ničesar ne spreminjaj: `drevo` (napake, "
                 "neveljavni objekti), `izmeri` z vsi=true (trki med telesi), `slika` iz izo, spredaj in zgoraj. "
                 "Na koncu kratek seznam ugotovitev po pomembnosti."},
    {"name": "v_bazo", "description": "Kos ali sestav v bazo standardnih delov.",
     "arguments": [{"name": "kos", "description": "dokument kosa", "required": True},
                   {"name": "kategorija", "description": "mapa v Standardni deli (npr. Elektro)", "required": True}],
     "besedilo": "Kos {kos} premakni v bazo standardnih delov, kategorija {kategorija}: najprej `splet` POST "
                 "/standardni {{\"dejanje\": \"podatki\", \"dokument\": \"{kos}\"}}, nato po potrditvi uporabnika "
                 "{{\"dejanje\": \"oznaci\", \"dokument\": \"{kos}\", \"kategorija\": \"{kategorija}\"}}."},
    {"name": "natisni_kos", "description": "Priprava kosa za 3D tisk (Bambu P2S) in okno Pripravi.",
     "arguments": [{"name": "kos", "description": "objekt ali dokument", "required": True}],
     "besedilo": "Pripravi {kos} za 3D tisk: `izmeri` (okvir mora biti znotraj 256 x 256 x 256 mm), `splet` POST "
                 "/tisk/lega za lego brez podpor, nato `natisni`. Tiskalnik, predal in polnilo potrdi uporabnik v oknu "
                 "Pripravi; tisk se ne zažene sam."},
]


# ---------------------------------------------------------------------------------------------------------------
# Orodja: pregled

@orodje("stanje", naslov="Stanje FreeCAD-a", nit="streznik", samo_branje=True, opis="""
Stanje spletnega FreeCAD-a: aktivni dokument, odprti in neshranjeni dokumenti, izbira, okolje, odprt obrazec,
urejanje skice, zadnja napaka strežnika, opravila v teku, zavihki brskalnika, plošča tiskalnikov. Začni tukaj.""")
def t_stanje(a):
    st = S.STANJE.stanje()
    try:
        projekti = json.loads(S.STANJE.projekti())
    except ValueError:
        projekti = {"odprti": []}
    odprti = projekti.get("odprti", [])
    aktivni = next((d for d in odprti if d.get("aktiven")), None)
    neshranjeni = [d["oznaka"] for d in odprti if d.get("spremenjen")]
    v = ["FreeCAD %s (lastna gradnja), strežnik http://127.0.0.1:%d, zavihkov brskalnika: %d" % (
        VERZIJA_FREECAD, S.VRATA, st.get("odjemalcev", 0))]
    if aktivni:
        v.append("Aktivni dokument: »%s« (%s) · %s · %s%s" % (
            aktivni["oznaka"], aktivni["ime"], aktivni.get("vrsta", "?"), aktivni.get("pot") or "ni shranjen",
            " · NESHRANJEN" if aktivni.get("spremenjen") else ""))
    else:
        v.append("Ni aktivnega dokumenta.")
    v.append("Odprtih dokumentov: %d%s" % (len(odprti), (" · neshranjeni: " + ", ".join(neshranjeni[:15]) +
                                                         (" …" if len(neshranjeni) > 15 else "")) if neshranjeni else ""))
    okolje = st.get("okolje") or {}
    v.append("Okolje: %s%s%s" % (okolje.get("delovnaMiza", "?"),
                                 (" · v urejanju: " + okolje["urejanje"]) if okolje.get("urejanje") else "",
                                 (" · modalno okno: " + okolje["pogovor"]) if okolje.get("pogovor") else ""))
    if S.STANJE.obrazec is not None:
        o = S.STANJE.obrazec
        v.append("Odprt obrazec »%s« (%s) čaka na vnos → `obrazec`." % (o.get("naslov", ""), o.get("vrsta", "")))
    if S.STANJE.skica:
        v.append("V brskalniku se ureja skica %s." % S.STANJE.skica)
    izbira = st.get("izbira") or []
    if izbira:
        v.append("Izbira: " + "; ".join("%s%s" % (i["objekt"], ("." + ",".join(i["elementi"])) if i.get("elementi")
                                                  else "") for i in izbira[:20]))
    opravila = _st()["opravila"]
    if opravila:
        v.append("Opravila AI: " + ", ".join("%s (%s, %s)" % (k, o["ime"], "končano" if o["odgovor"]["konec"].is_set()
                                                              else "teče %d s" % (time.time() - o["zacetek"]))
                                             for k, o in opravila.items()))
    try:
        t = S.tiskaj_stanje()
        if t.get("tece"):
            v.append("Plošča tiskalnikov teče: " + "; ".join("%s %s" % (p.get("ime") or "?", p.get("faza_besedilo", ""))
                                                              for p in t.get("tiskalniki") or []))
        else:
            v.append("Plošča tiskalnikov (Tiskaj) ne teče.")
    except Exception:  # noqa: BLE001
        pass
    if st.get("napaka"):
        v.append("Zadnja napaka strežnika (lahko stara): " + st["napaka"].strip().splitlines()[-1][:300])
    return "\n".join(v)


@orodje("dokumenti", naslov="Dokumenti", lastnosti={
    "dejanje": {"type": "string", "enum": ["seznam", "aktiviraj", "odpri", "nov", "zapri", "datoteke"],
                "description": "seznam odprtih (privzeto), aktiviraj, odpri datoteko, nov dokument, zapri "
                               "(le shranjenega), datoteke = FCStd v mapah projektov"},
    "dokument": {"type": "string", "description": "ime, oznaka ali pot (aktiviraj, zapri; pri nov ime)"},
    "pot": {"type": "string", "description": "pot do .FCStd (odpri)"},
    "isci": {"type": "string", "description": "filter imen (seznam, datoteke)"},
}, opis="""
Odprti dokumenti in datoteke. seznam: ime, oznaka, vrsta (del/sestav), pot, neshranjen, aktiven. aktiviraj/odpri/nov
spremeni aktivni dokument tudi v brskalniku uporabnika. zapri zapre le dokument brez neshranjenih sprememb.
datoteke: modeli FCStd v Oblak/3D modeliranje.""")
def t_dokumenti(a):
    dejanje = a.get("dejanje") or "seznam"
    filt = _normaliziraj_besedilo(a.get("isci") or "")
    if dejanje == "datoteke":
        vrstice = []
        for sk in S._projekti_v_mapah():
            for d in sk.get("datoteke", []):
                if filt and filt not in _normaliziraj_besedilo(d.get("pot", "")):
                    continue
                vrstice.append("%s%s" % (d.get("pot"), "  (%s)" % d["vrsta"] if d.get("vrsta") else ""))
        if not vrstice:
            return "Ni datotek%s." % (" za »%s«" % a.get("isci") if filt else "")
        return "Datoteke FCStd (%d):\n%s" % (len(vrstice), "\n".join(vrstice[:400]))
    if dejanje == "nov":
        ime = (a.get("dokument") or "Nov").strip()
        ascii_ime = re.sub(r"[^A-Za-z0-9_]", "_", _normaliziraj_besedilo(ime)) or "Nov"
        doc = App.newDocument(ascii_ime)
        if doc.Label != ime:
            doc.Label = ime
        App.setActiveDocument(doc.Name)
        if Gui is not None and App.GuiUp:
            Gui.activeDocument()
        S.STANJE.umazano = True
        S.STANJE.zadnji_projekti = 0.0
        return "Nov dokument »%s« (%s) je aktiven (še ni shranjen; `shrani` s potjo)." % (doc.Label, doc.Name)
    if dejanje == "odpri":
        pot = a.get("pot") or a.get("dokument") or ""
        if not pot.lower().endswith(".fcstd") or not os.path.isfile(pot):
            raise Napaka("Datoteke »%s« ni (pričakujem obstoječo .FCStd)." % pot)
        S._projekt_dejanje(S.STANJE, {"dejanje": "odpri", "pot": pot})
        doc = App.ActiveDocument
        return "Odprt in aktiven: »%s« (%s), objektov: %d." % (doc.Label, doc.Name, len(doc.Objects))
    if dejanje == "aktiviraj":
        doc = _dokument(a.get("dokument"))
        S._projekt_dejanje(S.STANJE, {"dejanje": "aktiviraj", "ime": doc.Name})
        return "Aktiven: »%s« (%s)." % (doc.Label, doc.Name)
    if dejanje == "zapri":
        doc = _dokument(a.get("dokument"))
        if _spremenjen(doc):
            raise Napaka("»%s« ima neshranjene spremembe: najprej `shrani` (ali naj uporabnik odloči)." % doc.Label)
        S._projekt_dejanje(S.STANJE, {"dejanje": "zapri", "ime": doc.Name})
        return "Zaprt: »%s«." % doc.Label
    aktivni = App.ActiveDocument
    vrstice = []
    for d in _dokumenti():
        if getattr(d, "Temporary", False):
            continue
        if filt and filt not in _normaliziraj_besedilo(d.Label + " " + d.Name + " " + (d.FileName or "")):
            continue
        vrsta = S._vrsta_iz_tipov(o.TypeId for o in d.Objects).get("vrsta", "")
        vrstice.append("%s »%s« [%s] %s, objektov %d%s · %s" % (
            "*" if aktivni is not None and d.Name == aktivni.Name else "-", d.Label, d.Name, vrsta or "?",
            len(d.Objects), " · NESHRANJEN" if _spremenjen(d) else "", d.FileName or "ni shranjen"))
    return "Odprti dokumenti (%d; * = aktivni):\n%s" % (len(vrstice), "\n".join(vrstice) or "(ni jih)")


TIPI_BREZ_MER = ("Sketcher::", "App::Origin", "App::Line", "App::Plane", "App::DocumentObjectGroup", "PartDesign::Plane",
                 "PartDesign::Line", "PartDesign::Point", "PartDesign::CoordinateSystem", "Spreadsheet::",
                 "Assembly::JointGroup", "Assembly::Joint", "App::FeaturePython")


@orodje("drevo", naslov="Drevo dokumenta", samo_branje=True, cakaj=60, lastnosti={
    "dokument": {"type": "string", "description": "ime ali oznaka (privzeto aktivni)"},
    "objekt": {"type": "string", "description": "podrobnosti enega objekta: vse lastnosti z vrednostmi in izrazi, "
                                                "oblika, odvisnosti, napaka"},
    "isci": {"type": "string", "description": "pokaži le objekte, katerih ime, oznaka ali tip vsebuje besedilo"},
    "globina": {"type": "integer", "description": "največja globina (privzeto 8)"},
    "mere": {"type": "boolean", "description": "prostornina teles (privzeto true)"},
    "skrite": {"type": "boolean", "description": "pri objekt: tudi skrite lastnosti"},
}, opis="""
Drevo dokumenta kot zamaknjeno besedilo, kot ga kaže FreeCAD (otroci = claimChildren): oznaka [ime] tip, skrit,
prostornina, ⚠ napake po preračunu, povezave na druge datoteke (→), spoji (kosa). Z `objekt` vrne vse lastnosti
enega objekta (tip, vrednost, izraz, opis), obliko (telesa, ploskve, okvir) in napako.""")
def t_drevo(a):
    import drevo as D
    doc = _dokument(a.get("dokument"))
    if a.get("objekt"):
        return _objekt_podrobno(doc, _objekt(doc, a["objekt"]), bool(a.get("skrite")))
    globina = max(1, min(int(a.get("globina") or 8), 30))
    mere = a.get("mere", True) is not False
    filt = _normaliziraj_besedilo(a.get("isci") or "")
    otroci = {o.Name: [c for c in D._otroci(o) if c.Document is doc] for o in doc.Objects}
    zahtevani = {c.Name for sez in otroci.values() for c in sez}
    koreni = [o for o in doc.Objects if o.Name not in zahtevani]
    urejan = None
    try:
        vp = Gui.getDocument(doc.Name).getInEdit() if (Gui is not None and App.GuiUp) else None
        urejan = vp.Object.Name if vp is not None else None
    except Exception:  # noqa: BLE001
        urejan = None

    def ujema(o):
        return not filt or filt in _normaliziraj_besedilo("%s %s %s" % (o.Label, o.Name, o.TypeId))

    potrebni = None
    if filt:   # zadetki in njihovi predniki
        potrebni = set()

        def poisci(o, pot):
            zadetek = ujema(o)
            for c in otroci.get(o.Name, []):
                if c.Name not in pot and poisci(c, pot | {c.Name}):
                    zadetek = True
            if zadetek:
                potrebni.add(o.Name)
            return zadetek
        for k in koreni:
            poisci(k, {k.Name})

    vrstice, stevec = [], [0]
    najvec = 600

    def opis(o):
        deli = ["%s [%s] %s" % (o.Label, o.Name, o.TypeId)]
        try:
            if not o.Visibility:
                deli.append("skrit")
        except Exception:  # noqa: BLE001
            pass
        try:
            stanje = o.State
            if "Invalid" in stanje or "Error" in stanje:
                deli.append("⚠ " + (o.getStatusString() or "napaka"))
            elif "Touched" in stanje:
                deli.append("potreben preračun")
        except Exception:  # noqa: BLE001
            pass
        if o.Name == urejan:
            deli.append("✎ v urejanju")
        cilj = D._cilj_povezave(o)
        if cilj is not None:
            deli.append("→ »%s« / %s" % (cilj.Document.Label, cilj.Label))
        try:
            dl = D._deli_spoja(o)
        except Exception:  # noqa: BLE001
            dl = []
        if dl:
            deli.append("spoj %s: %s" % (getattr(o, "JointType", ""), " ↔ ".join(dl)))
        if mere and hasattr(o, "Shape") and not o.TypeId.startswith(TIPI_BREZ_MER):
            try:
                stevilo, prostornina = D._telo(doc, o, S._kljuc_oblike)
                if stevilo:
                    deli.append("%s cm³%s" % (_st_mm(prostornina or 0, 1), "" if stevilo == 1 else
                                                " (%d teles)" % stevilo))
            except Exception:  # noqa: BLE001
                pass
        return " · ".join(deli)

    def obisci(o, nivo, pot):
        if stevec[0] >= najvec:
            return
        if potrebni is not None and o.Name not in potrebni:
            return
        stevec[0] += 1
        vrstice.append("  " * nivo + "- " + opis(o))
        if nivo + 1 >= globina:
            if otroci.get(o.Name):
                vrstice.append("  " * (nivo + 1) + "… (%d otrok, povečaj `globina`)" % len(otroci[o.Name]))
            return
        for c in otroci.get(o.Name, []):
            if c.Name in pot:
                continue
            obisci(c, nivo + 1, pot | {c.Name})

    for k in koreni:
        obisci(k, 0, {k.Name})
    glava = "Dokument »%s« [%s] · %s · objektov %d%s" % (
        doc.Label, doc.Name, doc.FileName or "ni shranjen", len(doc.Objects), " · NESHRANJEN" if _spremenjen(doc) else "")
    if stevec[0] >= najvec:
        vrstice.append("… odrezano pri %d vrsticah: zoži z `isci` ali `globina`." % najvec)
    napake = _neveljavni(doc)
    if napake:
        vrstice += ["", "⚠ Objekti z napako (%d): " % len(napake)] + ["  " + n for n in napake[:30]]
    return glava + "\n" + ("\n".join(vrstice) if vrstice else "(ni zadetkov)")


def _vrednost_lastnosti(obj, ime):
    try:
        v = getattr(obj, ime)
    except Exception as e:  # noqa: BLE001
        return "<%s>" % e
    if hasattr(v, "TypeId") and hasattr(v, "Label"):
        return "%s [%s]" % (v.Label, v.Name)
    if isinstance(v, (list, tuple)) and v and all(hasattr(x, "Label") for x in v if x is not None):
        return "[" + ", ".join("%s [%s]" % (x.Label, x.Name) for x in v if x is not None) + "]"
    if isinstance(v, tuple) and len(v) == 2 and hasattr(v[0], "Label"):
        return "%s [%s] %s" % (v[0].Label, v[0].Name, v[1])
    if type(v).__name__ in ("Shape", "TopoShape", "Solid", "Compound", "Face", "Edge", "Wire", "Shell", "Vertex"):
        return "<oblika>"   # tudi prazna oblika (hasattr na njej dvigne FreeCADError, ne AttributeError)
    return _kratko(repr(v) if not hasattr(v, "UserString") else v.UserString, 240)


def _objekt_podrobno(doc, obj, skrite):
    v = ["Objekt »%s« [%s] %s v dokumentu »%s«" % (obj.Label, obj.Name, obj.TypeId, doc.Label)]
    try:
        v.append("Stanje: %s%s" % (", ".join(obj.State) or "v redu",
                                   (" · " + obj.getStatusString()) if "Invalid" in obj.State else ""))
    except Exception:  # noqa: BLE001
        pass
    try:
        starsi = obj.Parents
        if starsi:
            v.append("Pot v drevesu: " + "; ".join("%s.%s" % (p.Name, s) for p, s in starsi[:5]))
    except Exception:  # noqa: BLE001
        pass
    try:
        v.append("Uporablja (OutList): " + (", ".join("%s [%s]" % (o.Label, o.Name) for o in obj.OutList[:25]) or "–"))
        v.append("Uporabljajo ga (InList): " + (", ".join("%s [%s]" % (o.Label, o.Name) for o in obj.InList[:25]) or "–"))
    except Exception:  # noqa: BLE001
        pass
    izrazi = {}
    try:
        for pot, izraz in obj.ExpressionEngine:
            izrazi[pot.split(".")[0]] = izraz
    except Exception:  # noqa: BLE001
        pass
    skupine = collections.OrderedDict()
    for ime in obj.PropertiesList:
        try:
            nacin = obj.getEditorMode(ime)
        except Exception:  # noqa: BLE001
            nacin = []
        if "Hidden" in nacin and not skrite:
            continue
        if ime in ("Shape", "Proxy", "ExpressionEngine"):
            continue
        try:
            skupina = obj.getGroupOfProperty(ime) or "Osnovno"
            tip = obj.getTypeIdOfProperty(ime).replace("App::Property", "")
        except Exception:  # noqa: BLE001
            skupina, tip = "Osnovno", "?"
        vrstica = "  %s (%s) = %s" % (ime, tip, _vrednost_lastnosti(obj, ime))
        if ime in izrazi:
            vrstica += "  [izraz: %s]" % izrazi[ime]
        if "ReadOnly" in nacin:
            vrstica += "  (samo branje)"
        try:
            if tip == "Enumeration":
                vrstica += "  možnosti: " + ", ".join(obj.getEnumerationsOfProperty(ime) or [])
        except Exception:  # noqa: BLE001
            pass
        skupine.setdefault(skupina, []).append(vrstica)
    for skupina, vrstice in skupine.items():
        v.append("[%s]" % skupina)
        v.extend(vrstice)
    try:
        import Part
        oblika = Part.getShape(obj)
        if not oblika.isNull():
            bb = oblika.BoundBox
            v.append("Oblika: %s, telesa %d, lupine %d, ploskve %d, robovi %d, oglišča %d, veljavna: %s" % (
                oblika.ShapeType, len(oblika.Solids), len(oblika.Shells), len(oblika.Faces), len(oblika.Edges),
                len(oblika.Vertexes), "da" if oblika.isValid() else "NE"))
            v.append("Okvir (lokalno): %s × %s × %s mm, od %s do %s" % (
                _st_mm(bb.XLength), _st_mm(bb.YLength), _st_mm(bb.ZLength), _vektor(App.Vector(bb.XMin, bb.YMin, bb.ZMin)),
                _vektor(App.Vector(bb.XMax, bb.YMax, bb.ZMax))))
            if oblika.Solids:
                v.append("Prostornina %s cm³, površina %s cm²" % (_st_mm(oblika.Volume / 1000.0, 3),
                                                                  _st_mm(oblika.Area / 100.0, 2)))
    except Exception:  # noqa: BLE001
        pass
    try:
        if obj.TypeId.startswith("Sketcher::SketchObject"):
            v.append("Skica: geometrij %d, omejitev %d, prostostnih stopenj: %s, v celoti določena: %s" % (
                obj.GeometryCount, obj.ConstraintCount, obj.solve(), "da" if obj.FullyConstrained else "ne"))
    except Exception:  # noqa: BLE001
        pass
    try:
        vo = obj.ViewObject
        if vo is not None:
            v.append("Videz: vidnost %s, prosojnost %s" % (vo.Visibility, getattr(vo, "Transparency", "?")))
    except Exception:  # noqa: BLE001
        pass
    return "\n".join(v)


# ---------------------------------------------------------------------------------------------------------------
# Orodja: delo

PREPOVEDANO_V_KODI = [
    (r"\.(save|saveAs|saveCopy)\s*\(", "shranjevanje dokumenta (uporabi orodje `shrani`)"),
    (r"closeDocument\s*\(", "zapiranje dokumenta (uporabi `dokumenti` zapri ali vprašaj uporabnika)"),
    (r"\.restore\s*\(\s*\)", "ponovno nalaganje dokumenta zavrže neshranjene spremembe"),
    (r"\bos\.(remove|unlink|rmdir|removedirs)\s*\(", "brisanje datotek"),
    (r"\bshutil\.(rmtree|move)\s*\(", "brisanje ali premikanje map"),
    (r"\.unlink\s*\(", "brisanje datotek"),
    (r"\bos\.(replace|rename)\s*\(", "premikanje ali prepisovanje datotek"),
    (r"(^|[^.\w])(quit|exit)\s*\(", "končanje programa (uporabi `izhod`)"),
    (r"\bsys\.exit\s*\(", "končanje programa"),
]


@orodje("python", naslov="Python v FreeCAD-u", unicujoce=True, cakaj=120, lastnosti={
    "koda": {"type": "string", "description": "Python koda; imena: App/FreeCAD, Gui/FreeCADGui, doc (ciljni dokument), "
                                             "Vector, Placement, Rotation, Part (uvozi ostalo sam). Nastavi `rezultat` "
                                             "za vrnjeno vrednost (JSON)."},
    "datoteka": {"type": "string", "description": "namesto kode izvedi skripto s to potjo (__file__ je nastavljen)"},
    "dokument": {"type": "string", "description": "ciljni dokument za `doc` (ime ali oznaka; privzeto aktivni)"},
    "transakcija": {"type": "string", "description": "ime koraka za Razveljavi (privzeto AI: python)"},
    "atomarno": {"type": "boolean", "description": "ob napaki razveljavi vse spremembe klica (privzeto true)"},
    "preracunaj": {"type": "boolean", "description": "na koncu preračunaj spremenjene dokumente (privzeto true)"},
    "dovoli_pisanje": {"type": "boolean", "description": "dovoli save/close/brisanje datotek v kodi; samo z izrecnim "
                                                         "dovoljenjem uporabnika"},
    "cakaj": {"type": "number", "description": "največ sekund čakanja (privzeto 120); potem `opravilo`"},
}, opis="""
Izvede Python kodo na glavni niti tekočega FreeCAD-a (celoten API: Part, PartDesign, Sketcher, Assembly, Draft, Mesh
…). Vrne izpis (print), spremenljivko `rezultat`, nove in odstranjene objekte ter napake po preračunu. Klic je ena
transakcija (ob napaki razveljavljen, sicer ga vrne `razveljavi`). Brez dovoli_pisanje ne shranjuje, ne zapira
dokumentov in ne briše datotek. Med izvajanjem stran zamrzne: dolgo delo razdeli.""")
def t_python(a):
    koda = a.get("koda") or ""
    ime_datoteke = "<mcp>"
    if a.get("datoteka"):
        ime_datoteke = os.path.normpath(a["datoteka"])
        try:
            with open(ime_datoteke, encoding="utf-8-sig") as f:
                koda = f.read()
        except OSError as e:
            raise Napaka("Skripte ni mogoče prebrati: %s" % e)
    if not koda.strip():
        raise Napaka("Ni kode (argument koda ali datoteka).")
    if not a.get("dovoli_pisanje"):
        for vzorec, razlog in PREPOVEDANO_V_KODI:
            if re.search(vzorec, koda, re.M):
                raise Napaka("Koda ni izvedena: %s. Če je uporabnik to izrecno dovolil, ponovi z "
                             "dovoli_pisanje: true." % razlog)
    try:
        prevedeno = compile(koda, ime_datoteke, "exec")
    except SyntaxError as e:
        raise Napaka("Skladenjska napaka v vrstici %s: %s\n%s" % (e.lineno, e.msg, (e.text or "").rstrip()))
    doc = _dokument(a.get("dokument"), obvezen=bool(a.get("dokument")))
    import Part
    okolje = {"__name__": "__mcp__", "__file__": ime_datoteke if ime_datoteke != "<mcp>" else "",
              "App": App, "FreeCAD": App, "Gui": Gui, "FreeCADGui": Gui, "doc": doc, "Part": Part,
              "Vector": App.Vector, "Placement": App.Placement, "Rotation": App.Rotation, "S": S, "STANJE": S.STANJE}
    if ime_datoteke != "<mcp>":
        mapa = os.path.dirname(ime_datoteke)
        if mapa not in sys.path:
            sys.path.insert(0, mapa)
    pred = _odtis_objektov()
    dotaknjeni_pred = _dotaknjeni()
    izpis = io.StringIO()
    atomarno = a.get("atomarno", True) is not False
    ime_transakcije = "AI: " + (a.get("transakcija") or "python")
    transakcija = 0
    try:
        transakcija = App.setActiveTransaction(ime_transakcije)
    except Exception:  # noqa: BLE001
        transakcija = 0
    zacetek = time.time()
    napaka = ""
    try:
        with contextlib.redirect_stdout(izpis), contextlib.redirect_stderr(izpis):
            exec(prevedeno, okolje)
    except BaseException as e:  # noqa: BLE001  (tudi SystemExit iz skripte)
        vrstice = traceback.format_exception(type(e), e, e.__traceback__)
        uporabniske = [v for v in vrstice if "mcp_orodja.py" not in v]
        napaka = "".join(uporabniske[-12:])
    trajanje = time.time() - zacetek
    try:
        App.closeActiveTransaction(bool(napaka) and atomarno, transakcija)
    except Exception:  # noqa: BLE001
        pass
    po = _odtis_objektov()
    preracunani, napake_po = [], []
    if not napaka and a.get("preracunaj", True) is not False:
        dotaknjeni_po = _dotaknjeni()
        for d in _dokumenti():
            # le dokumenti, ki jih je spremenil ta klic: uporabnikovih (npr. velik sestav) ne preračunavamo
            if dotaknjeni_po.get(d.Name, set()) - dotaknjeni_pred.get(d.Name, set()) or \
                    (d.Name in po and pred.get(d.Name) != po[d.Name] and dotaknjeni_po.get(d.Name)):
                try:
                    d.recompute()
                    preracunani.append(d.Label)
                except Exception:  # noqa: BLE001
                    pass
    for d in _dokumenti():
        if d.Name in po and (d.Name not in pred or pred[d.Name] != po[d.Name] or d.Label in preracunani):
            for n in _neveljavni(d):
                napake_po.append("»%s«: %s" % (d.Label, n))
    S.STANJE.umazano = True
    v = []
    if napaka:
        v.append("NAPAKA v kodi (%.1f s)%s:\n%s" % (trajanje, "; spremembe klica so razveljavljene" if atomarno else "",
                                                     napaka.rstrip()))
    else:
        v.append("Koda je tekla %s s%s." % (_st_mm(trajanje, 2), (" (dokument »%s«)" % doc.Label) if doc else ""))
    besedilo = izpis.getvalue()
    if besedilo:
        v.append("Izpis:\n" + _kratko(besedilo.rstrip(), 30000))
    rezultat = okolje.get("rezultat")
    if rezultat is not None and not napaka:
        v.append("rezultat = " + _kratko(json.dumps(rezultat, ensure_ascii=False, default=_json_vrednost, indent=1), 20000))
    if not napaka:
        v.extend(_razlika_objektov(pred, po))
        if preracunani:
            v.append("Preračunano: " + ", ".join(preracunani[:10]))
        if napake_po:
            v.append("⚠ Napake po preračunu:\n  " + "\n  ".join(napake_po[:30]))
    return {"napaka": bool(napaka), "besedilo": "\n".join(v)}


@orodje("ukaz", naslov="Ukaz FreeCAD-a", nit="streznik", unicujoce=True, lastnosti={
    "ime": {"type": "string", "description": "ime ukaza, npr. PartDesign_Fillet, SheetMetal_AddWall, Std_ViewFitAll"},
    "indeks": {"type": "integer", "description": "podukaz skupine (privzeto 0)"},
    "okolje": {"type": "string", "description": "namesto ukaza aktiviraj (in naloži) delovno okolje, npr. "
                                               "AssemblyWorkbench, FemWorkbench"},
    "cakaj": {"type": "number", "description": "sekunde čakanja na okno ukaza (privzeto 2)"},
}, opis="""
Sproži ukaz FreeCAD-a kot klik na gumb (vseh ~200 ukazov okolij in dodatkov; imena najde `isci`). Če ukaz
potrebuje izbiro, najprej `izberi`. Vrne, ali je ukaz na voljo, nove objekte in obrazec, ki ga je ukaz odprl
(izpolni ga z `obrazec`). Z `okolje` aktivira delovno okolje in vrne njegove ukaze.""")
def t_ukaz(a):
    if a.get("okolje"):
        ime_okolja = a["okolje"]

        def aktiviraj():
            vsa = Gui.listWorkbenches()
            if ime_okolja not in vsa:
                kandidati = [k for k in vsa if _normaliziraj_besedilo(ime_okolja) in _normaliziraj_besedilo(k)]
                if len(kandidati) != 1:
                    raise Napaka("Okolja »%s« ni. Okolja: %s" % (ime_okolja, ", ".join(sorted(vsa))))
                return kandidati[0]
            return ime_okolja
        pravo = _glavna_vrednost(aktiviraj)
        S.STANJE.vrsta.put(("okolje", {"ime": pravo}, None))
        time.sleep(1.0)
        _glavna_vrednost(lambda: S.STANJE.preveri_okolje(), 60)
        time.sleep(0.3)
        besedilo = _vir_okolja()
        odsek = re.search(r"## [^\n]*\(%s\)[^\n]*\n(.*?)(\n## |\Z)" % re.escape(pravo), besedilo, re.S)
        return "Okolje %s je aktivno.\n%s" % (pravo, odsek.group(1).strip() if odsek else "")
    ime = (a.get("ime") or "").strip()
    if not ime:
        raise Napaka("Manjka ime ukaza (ali okolje).")
    indeks = int(a.get("indeks") or 0)

    def sprozi():
        cmd = Gui.Command.get(ime)
        if cmd is None:
            raise Napaka("Ukaza »%s« ni (morda okolje še ni naloženo: `ukaz` {\"okolje\": ...}); poišči ga z `isci`."
                         % ime)
        try:
            aktiven = bool(cmd.isActive())
        except Exception:  # noqa: BLE001
            aktiven = True
        if not aktiven:
            return {"aktiven": False}
        pred = _odtis_objektov()
        S._sprozi_ukaz(ime, indeks)
        return {"aktiven": True, "pred": pred}
    izid = _glavna_vrednost(sprozi)
    if not izid["aktiven"]:
        izbira = S.STANJE.izbira
        return {"napaka": True, "besedilo": "Ukaz %s zdaj ni na voljo (FreeCAD ga ima za neaktivnega). Pogosto potrebuje "
                                              "izbiro (zdaj: %s) ali aktivno telo/skico; nastavi z `izberi`." % (
                                                  ime, "; ".join(i["objekt"] + (("." + ",".join(i["elementi"]))
                                                                                if i.get("elementi") else "")
                                                                 for i in izbira) or "nič")}
    konec = time.time() + _cakaj(a, 2.0)
    obrazec = None
    while time.time() < konec:
        time.sleep(0.15)
        obrazec = S.STANJE.obrazec
        if obrazec is not None:
            time.sleep(0.4)   # zajem obrazca je lahko star do 250 ms; počakaj na polno stanje
            obrazec = S.STANJE.obrazec
            break
    po = _glavna_vrednost(_odtis_objektov)
    v = ["Ukaz %s sprožen." % ime]
    v.extend(_razlika_objektov(izid["pred"], po))
    if obrazec is not None:
        v.append("Ukaz je odprl obrazec (izpolni ga z `obrazec`, nato potrdi):")
        v.append(_obrazec_besedilo(obrazec))
    return "\n".join(v)


def _obrazec_besedilo(obr):
    if obr is None:
        return "Ni odprtega obrazca."
    if obr.get("vrsta") == "datoteka":
        v = ["Izbira datoteke »%s« (%s) · mapa: %s" % (obr.get("naslov", ""), "shrani" if obr.get("shrani") else "odpri",
                                                       obr.get("mapa", "")),
             "Filter: %s (možnosti: %s)" % (obr.get("filter", ""), " | ".join(obr.get("filtri") or [])),
             "Ime: «%s»" % obr.get("ime", "")]
        vnosi = obr.get("vnosi") or []
        v.append("Vsebina mape (%d): %s%s" % (len(vnosi), ", ".join(("%s/" % x["ime"]) if x.get("mapa") else x["ime"]
                                                                     for x in vnosi[:60]), " …" if len(vnosi) > 60 else ""))
        v.append("Dejanja: datoteka (vrednost = polna pot), mapa, filter, preklici.")
        return "\n".join(v)
    v = ["Obrazec »%s« (%s)" % (obr.get("naslov", ""), "opravilo" if obr.get("vrsta") == "opravilo" else "pogovorno okno")]

    def element(e):
        tip = e.get("tip")
        izklop = "" if e.get("omogoceno", True) else " (onemogočeno)"
        if tip == "oznaka":
            return e.get("besedilo", "")
        if tip == "naslov":
            return "== %s ==" % e.get("besedilo", "")
        if tip == "vnos":
            return "[#%s vnos%s = «%s»%s]%s" % (e["id"], " (število)" if e.get("stevilo") else "", e.get("vrednost", ""),
                                               " samo branje" if e.get("samoBranje") else "", izklop)
        if tip == "izbira":
            return "[#%s izbira = «%s» iz: %s]%s" % (e["id"], e.get("vrednost", ""), " | ".join(
                "%d:%s" % (i, m) for i, m in enumerate(e.get("moznosti") or [])), izklop)
        if tip == "kljukica":
            return "[#%s %s %s]%s" % (e["id"], "☑" if e.get("izbrano") else "☐", e.get("besedilo", ""), izklop)
        if tip == "gumb":
            ime = e.get("besedilo") or e.get("namig") or "(ikona)"
            return "[#%s gumb «%s»%s%s]%s" % (e["id"], ime, " privzet" if e.get("privzet") else "",
                                              " vklopljen" if e.get("preklopni") and e.get("izbrano") else "", izklop)
        if tip == "drsnik":
            return "[#%s drsnik %s (%s–%s)]" % (e["id"], e.get("vrednost"), e.get("min"), e.get("max"))
        if tip == "napredek":
            return "[napredek %s/%s]" % (e.get("vrednost"), e.get("max"))
        if tip == "besedilo":
            return "[#%s besedilo = «%s»]" % (e["id"], _kratko(e.get("vrednost", ""), 400))
        if tip == "seznam":
            vrstice = e.get("vrstice") or []
            deli = ["[#%s seznam, %d vrstic; dejanje vrstica/dvoklik z vrednost = številka]" % (e["id"], len(vrstice))]
            for i, r in enumerate(vrstice[:40]):
                deli.append("    %d: %s%s%s" % (i, "  " * r.get("globina", 0), "* " if r.get("izbrano") else "",
                                                r.get("besedilo", "")))
            return "\n".join(deli)
        if tip == "zavihki":
            return "[#%s zavihki: %s]" % (e["id"], " | ".join(("*%d:%s*" if i == e.get("indeks") else "%d:%s") % (i, z)
                                                            for i, z in enumerate(e.get("zavihki") or [])))
        return ""

    def vrstice(rows, nivo):
        for vrsta in rows:
            deli = []
            for e in vrsta:
                if e.get("tip") == "stolpec":
                    if deli:
                        v.append("  " * nivo + " | ".join(deli))
                        deli = []
                    vrstice(e.get("vrstice") or [], nivo + 1)
                elif e.get("tip") == "skupina":
                    if deli:
                        v.append("  " * nivo + " | ".join(deli))
                        deli = []
                    naslov = e.get("naslov") or ""
                    if e.get("preklopna"):
                        naslov = "[#%s %s] %s" % (e["id"], "☑" if e.get("izbrano") else "☐", naslov)
                    if naslov:
                        v.append("  " * nivo + "--- %s ---" % naslov)
                    vrstice(e.get("vrstice") or [], nivo + 1)
                else:
                    t = element(e)
                    if t:
                        deli.append(t)
            if deli:
                v.append("  " * nivo + " | ".join(deli))
    vrstice(obr.get("vrstice") or [], 0)
    v.append("Dejanja (`obrazec`): vpisi (id, vrednost npr. \"5 mm\"), izberi (id, vrednost indeks ali besedilo), "
             "kljukica (id, vrednost true/false), klik (id), vrstica (id, vrednost), zavihek, potrdi, preklici.")
    return "\n".join(v)


def _gumbi_obrazca(obr):
    gumbi = []

    def obisci(rows):
        for vrsta in rows or []:
            for e in vrsta:
                if e.get("tip") == "gumb":
                    gumbi.append(e)
                elif e.get("tip") in ("skupina", "stolpec"):
                    obisci(e.get("vrstice"))
    obisci(obr.get("vrstice"))
    return gumbi


def _id_elementa(obr, eid):
    najdeni = {}

    def obisci(rows):
        for vrsta in rows or []:
            for e in vrsta:
                if "id" in e:
                    najdeni[int(e["id"])] = e
                if e.get("tip") in ("skupina", "stolpec"):
                    obisci(e.get("vrstice"))
    obisci(obr.get("vrstice"))
    return najdeni.get(int(eid))


POTRDI = ("ok", "v redu", "potrdi", "yes", "da", "accept", "sprejmi", "apply", "uporabi")
PREKLICI = ("cancel", "preklici", "prekliči", "close", "zapri", "no", "ne", "discard")


@orodje("obrazec", naslov="Obrazec (okno FreeCAD-a)", nit="streznik", unicujoce=True, lastnosti={
    "dejanje": {"type": "string", "enum": ["preberi", "vpisi", "izberi", "kljukica", "klik", "vrstica", "dvoklik",
                                           "zavihek", "besedilo", "drsnik", "potrdi", "preklici", "datoteka", "mapa",
                                           "filter"],
                "description": "preberi (privzeto) ali dejanje na gradniku #id"},
    "id": {"type": "integer", "description": "številka gradnika (#id iz izpisa)"},
    "vrednost": {"description": "vrednost: besedilo z enoto (\"5 mm\"), število, indeks, true/false, pot"},
}, opis="""
Okno, ki ga je odprl FreeCAD (nastavitve ukaza v podoknu Opravila, pogovor, sporočilo, izbira datoteke): preberi
izpiše vse gradnike s številkami (#id) in vrednostmi; ostala dejanja vpišejo vrednost, kliknejo gumb, izberejo vrstico
ali zavihek. potrdi/preklici poiščeta gumb OK/Cancel. Vrne novo stanje okna. Okno vidi tudi uporabnik v brskalniku.""")
def t_obrazec(a):
    dejanje = a.get("dejanje") or "preberi"
    obr = S.STANJE.obrazec
    if dejanje == "preberi":
        return _obrazec_besedilo(obr)
    if obr is None:
        raise Napaka("Ni odprtega obrazca.")
    podatki = {"kljuc": obr.get("kljuc")}
    vrednost = a.get("vrednost")
    if obr.get("vrsta") == "datoteka":
        if dejanje not in ("datoteka", "mapa", "filter", "preklici", "potrdi"):
            raise Napaka("Izbira datoteke pozna dejanja: datoteka (vrednost = pot), mapa, filter, preklici.")
        if dejanje == "potrdi":
            dejanje = "datoteka"
            if not vrednost:
                vrednost = os.path.join(obr.get("mapa", ""), obr.get("ime", ""))
        podatki.update({"dejanje": dejanje, "vrednost": vrednost, "id": 0})
    elif dejanje in ("potrdi", "preklici"):
        besede = POTRDI if dejanje == "potrdi" else PREKLICI
        gumbi = [g for g in _gumbi_obrazca(obr) if g.get("omogoceno", True)]
        izbran = None
        for beseda in besede:
            for g in gumbi:
                t = _normaliziraj_besedilo((g.get("besedilo") or "") + " " + (g.get("namig") or "")).replace("&", "")
                if t.split() and (t.split()[0] == _normaliziraj_besedilo(beseda) or t.strip() == _normaliziraj_besedilo(beseda)):
                    izbran = g
                    break
            if izbran:
                break
        if izbran is None and dejanje == "potrdi":
            izbran = next((g for g in gumbi if g.get("privzet")), None)
        if izbran is None:
            raise Napaka("Gumba za %s ne najdem. Gumbi: %s" % (dejanje, ", ".join(
                "#%s «%s»" % (g["id"], g.get("besedilo") or g.get("namig")) for g in gumbi) or "ni jih"))
        podatki.update({"dejanje": "klik", "id": izbran["id"]})
    else:
        if a.get("id") is None:
            raise Napaka("Manjka id gradnika (#id iz `obrazec` preberi).")
        e = _id_elementa(obr, a["id"])
        if e is None:
            raise Napaka("Gradnika #%s ni v obrazcu (preberi ga znova)." % a["id"])
        preslikava = {"vpisi": "vnos", "izberi": "izbira", "kljukica": "kljukica", "klik": "klik", "vrstica": "vrstica",
                      "dvoklik": "dvoklik", "zavihek": "zavihek", "besedilo": "besedilo", "drsnik": "drsnik"}
        podatki.update({"dejanje": preslikava.get(dejanje, dejanje), "id": int(a["id"])})
        if dejanje == "izberi":
            moznosti = e.get("moznosti") or []
            if isinstance(vrednost, str) and not vrednost.isdigit():
                norm = _normaliziraj_besedilo(vrednost)
                kandidati = [i for i, m in enumerate(moznosti) if _normaliziraj_besedilo(m) == norm] or \
                            [i for i, m in enumerate(moznosti) if norm in _normaliziraj_besedilo(m)]
                if not kandidati and not e.get("urejljivo"):
                    raise Napaka("Možnosti »%s« ni: %s" % (vrednost, " | ".join(moznosti)))
                vrednost = kandidati[0] if kandidati else vrednost
            elif vrednost is not None:
                vrednost = int(vrednost)
        elif dejanje == "kljukica":
            vrednost = vrednost if isinstance(vrednost, bool) else str(vrednost).lower() in ("1", "true", "da", "yes")
        elif dejanje in ("vrstica", "dvoklik", "zavihek", "drsnik"):
            vrednost = int(vrednost or 0)
        podatki["vrednost"] = vrednost
    kljuc = obr.get("kljuc")
    S.STANJE.vrsta.put(("obrazec", podatki, None))
    konec = time.time() + 1.2
    time.sleep(0.5)
    while time.time() < konec:
        nov = S.STANJE.obrazec
        if nov is None or nov.get("kljuc") != kljuc or nov is not obr:
            break
        time.sleep(0.1)
    time.sleep(0.3)
    nov = S.STANJE.obrazec
    if nov is None:
        return "Dejanje izvedeno; obrazec je zaprt."
    return "Dejanje izvedeno. Stanje okna:\n" + _obrazec_besedilo(nov)


@orodje("izberi", naslov="Izbira", cakaj=30, lastnosti={
    "objekti": {"type": "array", "items": {"type": "string"},
                "description": "sklici: »Objekt«, »Objekt.Face3«, »Sestav.Povezava.Edge2« (ime ali oznaka)"},
    "dodaj": {"type": "boolean", "description": "dodaj k obstoječi izbiri (privzeto zamenjaj)"},
    "pocisti": {"type": "boolean", "description": "samo počisti izbiro"},
    "dokument": {"type": "string", "description": "ime ali oznaka (privzeto aktivni)"},
}, opis="""
Izbere objekte, ploskve, robove ali oglišča (kot klik v pogledu) za ukaze, ki delajo na izbiri (Zaokrožitev, Posnetje,
Make Wall, skica na ploskvi …). Brez objektov vrne trenutno izbiro z vrsto in merami elementov.""")
def t_izberi(a):
    doc = _dokument(a.get("dokument"))
    if a.get("pocisti") or (a.get("objekti") and not a.get("dodaj")):
        Gui.Selection.clearSelection()
    for ref in a.get("objekti") or []:
        koren, podpot, element, _obj = _razresi(doc, ref)
        Gui.Selection.addSelection(koren.Document.Name, koren.Name, podpot + element)
    S.STANJE.posodobi_izbiro()
    v = []
    for s in Gui.Selection.getSelectionEx("", 0):
        imena = list(s.SubElementNames) or [""]
        for i, sub in enumerate(imena):
            opis = "%s [%s]%s" % (s.Object.Label, s.Object.Name, ("." + _cisto_podime(sub)) if sub else "")
            try:
                el = s.SubObjects[i] if sub and i < len(s.SubObjects) else None
            except Exception:  # noqa: BLE001
                el = None
            if el is not None:
                opis += " · " + _opis_elementa(el)
            v.append(opis)
    return "Izbira (%d):\n%s" % (len(v), "\n".join(v) if v else "(prazna)")


def _opis_elementa(el):
    t = el.ShapeType
    try:
        if t == "Face":
            ploskev = el.Surface
            ime = type(ploskev).__name__
            dod = ""
            if ime == "Plane":
                dod = " normala %s" % _vektor(el.normalAt(*el.Surface.parameter(el.CenterOfMass)), 3)
            elif hasattr(ploskev, "Radius"):
                dod = " polmer %s mm, os %s" % (_st_mm(ploskev.Radius), _vektor(getattr(ploskev, "Axis", App.Vector()), 3))
            return "ploskev %s, %s cm²%s, središče %s" % (ime, _st_mm(el.Area / 100.0, 3), dod, _vektor(el.CenterOfMass))
        if t == "Edge":
            krivulja = type(el.Curve).__name__
            dod = ""
            if hasattr(el.Curve, "Radius"):
                dod = " polmer %s mm, središče %s" % (_st_mm(el.Curve.Radius), _vektor(el.Curve.Center))
            elif krivulja in ("Line", "LineSegment"):
                smer = el.Vertexes[-1].Point - el.Vertexes[0].Point
                dod = " smer %s" % _vektor(smer.normalize() if smer.Length else smer, 3)
            return "rob %s, dolžina %s mm%s" % (krivulja, _st_mm(el.Length), dod)
        if t == "Vertex":
            return "oglišče %s" % _vektor(el.Point)
    except Exception:  # noqa: BLE001
        pass
    return t


@orodje("izmeri", naslov="Meritve", samo_branje=True, cakaj=180, lastnosti={
    "objekti": {"type": "array", "items": {"type": "string"},
                "description": "sklici (»Objekt«, »Objekt.Face3«, pot »Sestav.Povezava.Edge2«) ali [\"izbira\"]"},
    "vsi": {"type": "boolean", "description": "vsa vidna telesa dokumenta: mere in trki med njimi"},
    "dokument": {"type": "string", "description": "ime ali oznaka (privzeto aktivni)"},
    "gostota": {"type": "number", "description": "g/cm³ za maso (jeklo 7,85, aluminij 2,7, PETG 1,27)"},
    "prekrivanje": {"type": "boolean", "description": "pri trkih izračunaj še prostornino prekrivanja (Boolova "
                                                     "operacija; največ 6 parov)"},
}, opis="""
Mere v globalnih koordinatah: okvir, prostornina, površina, težišče, masa; za ploskve in robove vrsta, polmer, dolžina,
normala. Za več sklicev še najmanjša razdalja, kot med ravninami ali premicami in trk (prekrivanje ali dotik). vsi=true
preveri trke med vsemi vidnimi telesi (brez Boolovih operacij, razen s prekrivanje).""")
def t_izmeri(a):
    doc = _dokument(a.get("dokument"))
    refs = list(a.get("objekti") or [])
    if refs == ["izbira"] or (not refs and not a.get("vsi")):
        refs = []
        for s in Gui.Selection.getSelectionEx("", 0):
            if s.SubElementNames:
                refs.extend("%s.%s" % (s.Object.Name, _cisto_podime(sub)) for sub in s.SubElementNames)
            else:
                refs.append(s.Object.Name)
        if not refs:
            raise Napaka("Ni sklicev in izbira je prazna: podaj objekti ali vsi=true.")
    oblike = []
    if a.get("vsi"):
        for o in _telesa_dokumenta(doc):
            try:
                oblika, _ = _oblika(doc, o.Name)
            except Exception:  # noqa: BLE001
                continue
            if oblika.Solids or oblika.Faces:
                oblike.append((o.Label, oblika))
    else:
        for r in refs:
            oblika, obj = _oblika(doc, r)
            oblike.append((r if "." in r else obj.Label, oblika))
    if not oblike:
        raise Napaka("Ni geometrije za merjenje.")
    v = []
    skupni = None
    for ime, o in oblike:
        bb = o.BoundBox
        skupni = bb if skupni is None else skupni.united(bb)
        if o.ShapeType in ("Face", "Edge", "Vertex"):
            v.append("%s: %s" % (ime, _opis_elementa(o)))
            continue
        vrstica = "%s: okvir %s × %s × %s mm (od %s do %s)" % (
            ime, _st_mm(bb.XLength), _st_mm(bb.YLength), _st_mm(bb.ZLength),
            _vektor(App.Vector(bb.XMin, bb.YMin, bb.ZMin)), _vektor(App.Vector(bb.XMax, bb.YMax, bb.ZMax)))
        if o.Solids:
            vrstica += "; prostornina %s cm³, površina %s cm², težišče %s, teles %d" % (
                _st_mm(o.Volume / 1000.0, 3), _st_mm(o.Area / 100.0, 2), _vektor(_tezisce(o)), len(o.Solids))
            if a.get("gostota"):
                vrstica += ", masa %s g" % _st_mm(o.Volume / 1000.0 * float(a["gostota"]), 1)
        elif o.Faces:
            vrstica += "; ni trdno telo (lupina), površina %s cm²" % _st_mm(o.Area / 100.0, 2)
        if not o.isValid():
            vrstica += " · ⚠ oblika ni veljavna"
        v.append(vrstica)
    if len(oblike) > 1 and skupni is not None:
        v.append("Skupni okvir: %s × %s × %s mm" % (_st_mm(skupni.XLength), _st_mm(skupni.YLength), _st_mm(skupni.ZLength)))
    pari = list(itertools.combinations(range(len(oblike)), 2))
    if a.get("vsi"):
        trki, dotiki, prekrivanj = [], [], 0
        for i, j in pari:
            (ia, oa), (ib, ob) = oblike[i], oblike[j]
            if not oa.BoundBox.intersect(ob.BoundBox):
                continue
            try:
                d = oa.distToShape(ob)[0]
            except Exception:  # noqa: BLE001
                continue
            if d > 1e-6:
                continue
            vrsta = _vrsta_stika(oa, ob)
            if vrsta == "prekrivanje":
                opis = "%s ↔ %s" % (ia, ib)
                if a.get("prekrivanje") and prekrivanj < 6:
                    prekrivanj += 1
                    try:
                        opis += " (%s cm³)" % _st_mm(oa.common(ob).Volume / 1000.0, 3)
                    except Exception:  # noqa: BLE001
                        pass
                trki.append(opis)
            else:
                dotiki.append("%s ↔ %s" % (ia, ib))
        v.append("Teles: %d. Trki (prekrivanje): %s" % (len(oblike), "; ".join(trki) if trki else "ni jih"))
        if dotiki:
            v.append("Dotiki (razdalja 0 brez prekrivanja): " + "; ".join(dotiki[:60]))
        return "\n".join(v)
    if len(pari) > 45:
        raise Napaka("Preveč sklicev za medsebojne razdalje (največ 10); za trke uporabi vsi=true.")
    for i, j in pari:
        (ia, oa), (ib, ob) = oblike[i], oblike[j]
        try:
            d, tocke, _ = oa.distToShape(ob)
        except Exception as e:  # noqa: BLE001
            v.append("%s ↔ %s: razdalje ni mogoče izračunati (%s)" % (ia, ib, e))
            continue
        vrstica = "%s ↔ %s: najmanjša razdalja %s mm" % (ia, ib, _st_mm(d, 3))
        if tocke:
            vrstica += " (med %s in %s)" % (_vektor(tocke[0][0]), _vektor(tocke[0][1]))
        kot = _kot(oa, ob)
        if kot is not None:
            vrstica += ", kot %s°" % _st_mm(kot, 2)
        if d < 1e-6 and oa.Solids and ob.Solids:
            vrstica += ", " + _vrsta_stika(oa, ob)
        v.append(vrstica)
    return "\n".join(v)


VSEBNIKI = ("App::Part", "Assembly::AssemblyObject", "App::DocumentObjectGroup", "App::Origin")


def _telesa_dokumenta(doc):
    """Vidni kosi dokumenta kot ločena telesa: telesa PartDesign, oblike Part in povezave (kosi sestava), ki jih ne
    porabi druga značilnost (Cut, Fillet ...); vsebniki (App::Part, sestav, skupina) se razgrnejo."""
    import drevo as D
    lastnik = {}
    for o0 in doc.Objects:
        for o in D._otroci(o0):
            if o.Document is doc:
                lastnik.setdefault(o.Name, o0)
    izid = []
    for o in doc.Objects:
        if o.TypeId.startswith(TIPI_BREZ_MER) or o.TypeId.startswith(VSEBNIKI):
            continue
        if not (o.TypeId == "PartDesign::Body" or o.TypeId in ("App::Link", "Assembly::AssemblyLink")
                or (o.TypeId.startswith("Part::") and hasattr(o, "Shape"))):
            continue
        st = lastnik.get(o.Name)
        if st is not None and not st.TypeId.startswith(VSEBNIKI):
            continue   # porabljen (vhod značilnosti) ali značilnost telesa
        try:
            if not o.Visibility:
                continue
        except Exception:  # noqa: BLE001
            pass
        izid.append(o)
    return izid


def _tezisce(o):
    try:
        return o.CenterOfGravity
    except Exception:  # noqa: BLE001
        try:
            return o.Solids[0].CenterOfMass
        except Exception:  # noqa: BLE001
            return o.BoundBox.Center


def _smer(o):
    try:
        if o.ShapeType == "Face" and type(o.Surface).__name__ == "Plane":
            return o.normalAt(*o.Surface.parameter(o.CenterOfMass)), "ravnina"
        if o.ShapeType == "Edge" and type(o.Curve).__name__ in ("Line", "LineSegment"):
            s = o.Vertexes[-1].Point - o.Vertexes[0].Point
            return (s.normalize() if s.Length else s), "premica"
        if o.ShapeType == "Face" and hasattr(o.Surface, "Axis"):
            return o.Surface.Axis, "os"
    except Exception:  # noqa: BLE001
        pass
    return None, None


def _kot(a, b):
    sa, _ = _smer(a)
    sb, _ = _smer(b)
    if sa is None or sb is None or not sa.Length or not sb.Length:
        return None
    c = max(-1.0, min(1.0, sa.dot(sb) / (sa.Length * sb.Length)))
    return math.degrees(math.acos(c))


def _vrsta_stika(a, b):
    """Razdalja 0: »prekrivanje«, če je kako oglišče enega strogo v drugem (brez Boolove operacije), sicer »dotik«."""
    for x, y in ((a, b), (b, a)):
        tocke = [t.Point for t in x.Vertexes[:300]]
        try:
            tocke += [e.valueAt((e.FirstParameter + e.LastParameter) / 2) for e in x.Edges[:300]]
            tocke += [f.CenterOfMass for f in x.Faces[:200]]
        except Exception:  # noqa: BLE001
            pass
        for p in tocke:
            try:
                if y.isInside(p, 1e-4, False):
                    return "prekrivanje"
            except Exception:  # noqa: BLE001
                break
    try:
        for x, y in ((a, b), (b, a)):
            if y.isInside(x.BoundBox.Center, 1e-4, False) and x.isInside(x.BoundBox.Center, 1e-4, False):
                return "prekrivanje"
    except Exception:  # noqa: BLE001
        pass
    return "dotik"


@orodje("razveljavi", naslov="Razveljavi / uveljavi", cakaj=60, lastnosti={
    "dokument": {"type": "string", "description": "ime ali oznaka (privzeto aktivni)"},
    "korakov": {"type": "integer", "description": "koliko korakov (privzeto 1; 0 = samo seznam)"},
    "ponovi": {"type": "boolean", "description": "uveljavi znova (redo) namesto razveljavi"},
}, opis="""
Razveljavi (ali z ponovi uveljavi znova) zadnje korake dokumenta; vsak klic python ali ukaza je en korak. korakov 0
vrne seznam korakov za razveljavitev in ponovitev.""")
def t_razveljavi(a):
    doc = _dokument(a.get("dokument"))
    n = int(a.get("korakov", 1) if a.get("korakov") is not None else 1)
    narejeni = []
    for _ in range(max(0, min(n, 50))):
        imena = doc.RedoNames if a.get("ponovi") else doc.UndoNames
        if not imena:
            break
        narejeni.append(imena[0])
        if a.get("ponovi"):
            doc.redo()
        else:
            doc.undo()
    if narejeni:
        doc.recompute()
        S.STANJE.umazano = True
    v = []
    if narejeni:
        v.append("%s: %s" % ("Uveljavljeno znova" if a.get("ponovi") else "Razveljavljeno", "; ".join(narejeni)))
    elif n:
        v.append("Ni korakov za %s." % ("ponovitev" if a.get("ponovi") else "razveljavitev"))
    v.append("Razveljavi lahko še: %s" % ("; ".join(list(doc.UndoNames)[:12]) or "nič"))
    v.append("Ponovi lahko: %s" % ("; ".join(list(doc.RedoNames)[:12]) or "nič"))
    return "\n".join(v)


@orodje("shrani", naslov="Shrani dokument", unicujoce=True, cakaj=180, lastnosti={
    "dokument": {"type": "string", "description": "ime ali oznaka (privzeto aktivni)"},
    "pot": {"type": "string", "description": "shrani kot (.FCStd); obvezno za še neshranjen dokument"},
    "kopija": {"type": "boolean", "description": "shrani le kopijo na pot (dokument ostane na stari poti)"},
    "komentar": {"type": "string", "description": "kaj se je spremenilo: komentar k različici v oblaku (PDM)"},
}, opis="""
Shrani dokument na disk (edino orodje, ki to sme). Brez poti na obstoječo datoteko; s potjo »shrani kot« (mapa mora
obstajati, obstoječe datoteke druge vsebine ne prepiše brez kopija). Za datoteke v mapi oblaka komentar zapiše opis
spremembe k novi različici.""")
def t_shrani(a):
    doc = _dokument(a.get("dokument"))
    pot = a.get("pot") or ""
    if pot:
        pot = os.path.normpath(pot)
        if not pot.lower().endswith(".fcstd"):
            pot += ".FCStd"
        if not os.path.isdir(os.path.dirname(pot)):
            raise Napaka("Mapa »%s« ne obstaja." % os.path.dirname(pot))
        if os.path.exists(pot) and not (doc.FileName and os.path.normcase(doc.FileName) == os.path.normcase(pot)) \
                and not a.get("kopija"):
            raise Napaka("Datoteka »%s« že obstaja in ni ta dokument; izberi drugo ime (prepisa ne delam)." % pot)
    elif not doc.FileName:
        raise Napaka("»%s« še ni shranjen: podaj pot (.FCStd)." % doc.Label)
    tiho = bool(a.get("komentar"))
    if tiho:
        S.STANJE.tiho_shranjevanje = True   # brskalnik ne vpraša »Kaj si spremenil?«; komentar pošljemo sami
    try:
        if a.get("kopija"):
            if not pot:
                raise Napaka("Kopija potrebuje pot.")
            doc.saveCopy(pot)
            izhod = pot
        elif pot and (not doc.FileName or os.path.normcase(doc.FileName) != os.path.normcase(pot)):
            doc.saveAs(pot)
            izhod = doc.FileName
        else:
            doc.save()
            izhod = doc.FileName
    finally:
        if tiho:
            S.STANJE.tiho_shranjevanje = False
    if not a.get("kopija"):
        try:
            Gui.getDocument(doc.Name).Modified = False
        except Exception:  # noqa: BLE001
            pass
    S.STANJE.zadnji_projekti = 0.0
    izid = {"besedilo": "Shranjeno: %s" % izhod}
    if a.get("komentar") and not a.get("kopija"):
        komentar, datoteka = a["komentar"], izhod

        def nadaljuj():   # nit strežnika: klic v oblak ne sme teči na glavni niti
            try:
                if not (S.OBLAK.prijavljen() and S.OBLAK.v_oblaku(datoteka)):
                    return "Datoteka ni v mapi oblaka; komentar ni zapisan."
                koda, telo = S.oblak_zahteva(S.OBLAK, "POST", "/oblak/komentar", {"pot": datoteka, "komentar": komentar})
                if koda == 200 and telo.get("takoj"):
                    return "Komentar zapisan k različici #%s." % telo.get("st")
                return "Komentar bo zapisan, ko odjemalec oblaka pošlje novo različico." if koda == 200 else \
                    "Komentar ni zapisan: %s" % telo
            except Exception as e:  # noqa: BLE001
                return "Komentar ni zapisan: %s" % e
        izid["_nadaljuj"] = nadaljuj
    return izid


# ---------------------------------------------------------------------------------------------------------------
# Orodja: slika in render

POGLEDI = {   # smer od modela proti kameri (»nazaj«) in »gor«, kot STANDARDNI_POGLEDI v index.html (Z gor, spredaj = -Y)
    "spredaj": ((0, -1, 0), (0, 0, 1)), "zadaj": ((0, 1, 0), (0, 0, 1)), "levo": ((-1, 0, 0), (0, 0, 1)),
    "desno": ((1, 0, 0), (0, 0, 1)), "zgoraj": ((0, 0, 1), (0, 1, 0)), "spodaj": ((0, 0, -1), (0, -1, 0)),
    "izo": ((1, -1, 1), (0, 0, 1)), "izo_zadaj": ((-1, 1, 1), (0, 0, 1)), "izo_spodaj": ((1, -1, -1), (0, 0, 1)),
}


@orodje("slika", naslov="Slika modela", nit="streznik", samo_branje=True, lastnosti={
    "pogled": {"type": "string", "enum": list(POGLEDI) + ["zaslon"],
               "description": "izo (privzeto), spredaj, zadaj, levo, desno, zgoraj, spodaj, izo_zadaj, izo_spodaj, "
                              "zaslon = točno to, kar uporabnik vidi v brskalniku"},
    "dokument": {"type": "string", "description": "ime ali oznaka (privzeto aktivni; drug dokument se ne aktivira)"},
    "objekti": {"type": "array", "items": {"type": "string"}, "description": "samo ti objekti (imena)"},
    "velikost": {"type": "integer", "description": "stranica v px (privzeto 800, 256–1600)"},
    "rezerva": {"type": "boolean", "description": "izriši brez brskalnika (preprosto senčenje)"},
}, opis="""
Slika modela, ki jo vidiš: izris istega 3D pogleda kot v brskalniku (pravokotna projekcija, prileganje, belo ozadje) iz
izbrane smeri ali posnetek zaslona uporabnika. Uporabi jo po vsaki spremembi oblike. Brez odprtega brskalnika preprost
izris iz mreže.""")
def t_slika(a):
    pogled = a.get("pogled") or "izo"
    velikost = max(256, min(int(a.get("velikost") or 800), 1600))
    objekti = [str(x) for x in (a.get("objekti") or [])]
    dokument = a.get("dokument") or ""
    if dokument or objekti:   # imena v Name (stran pozna Name objektov in dokumentov)
        def imena():
            doc = _dokument(dokument) if dokument else App.ActiveDocument
            if doc is None:
                raise Napaka("Ni aktivnega dokumenta.")
            return doc.Name, doc.Label, doc is App.ActiveDocument, [_objekt(doc, o).Name for o in objekti]
        ime_doc, oznaka_doc, aktiven, objekti = _glavna_vrednost(imena)
    else:
        ime_doc, oznaka_doc, aktiven = "", "", True
    if pogled == "zaslon" and not aktiven:
        raise Napaka("Pogled zaslon kaže le aktivni dokument.")
    opomba = ""
    if not a.get("rezerva"):
        odgovor = brskalnik("slika", {"pogled": pogled, "velikost": velikost, "objekti": objekti,
                                      "dokument": "" if aktiven else ime_doc,
                                      "smer": POGLEDI.get(pogled)}, cakaj=15.0 if not aktiven else 10.0)
        if odgovor and odgovor.get("slika"):
            bajti = base64.b64decode(odgovor["slika"].partition(",")[2])
            mime = "image/jpeg" if odgovor["slika"].startswith("data:image/jpeg") else "image/png"
            besedilo = "Pogled %s%s, %d px, izris v brskalniku%s." % (
                pogled, (" · »%s«" % oznaka_doc) if oznaka_doc else "", velikost,
                (" · " + odgovor["opis"]) if odgovor.get("opis") else "")
            return {"besedilo": besedilo, "slike": [(mime, bajti)]}
        if odgovor and odgovor.get("napaka"):
            opomba = " (brskalnik: %s)" % odgovor["napaka"]
        elif not S.STANJE.odjemalci:
            opomba = " (stran v brskalniku ni odprta: http://127.0.0.1:%d/)" % S.VRATA
        elif not _st().get("zdravo"):
            opomba = " (stran v brskalniku je starejša: uporabnik naj osveži zavihek, F5)"
        else:
            opomba = " (brskalnik ni odgovoril: stran je starejša ali zaposlena — osveži zavihek)"
    if pogled == "zaslon":
        raise Napaka("Posnetka zaslona ni%s." % opomba)
    if aktiven and not dokument:
        posnetek = S.STANJE.posnetek()
    else:
        posnetek = _glavna_vrednost(lambda: _posnetek_dokumenta(ime_doc), 120)
    podatki = json.loads(posnetek.decode("utf-8") if isinstance(posnetek, bytes) else posnetek)
    jpeg, opis = izris_mreze(podatki.get("objekti") or [], POGLEDI.get(pogled, POGLEDI["izo"]), velikost, objekti)
    return {"besedilo": "Pogled %s, %d px, preprost izris iz mreže%s. %s" % (pogled, velikost, opomba, opis),
            "slike": [("image/jpeg", jpeg)]}


def _posnetek_dokumenta(ime):
    doc = App.getDocument(ime)
    objekti = []
    for obj in S._vidni_objekti(doc):
        try:
            objekti.append(S._geometrija_predpomnjena(doc, obj)[0])
        except Exception:  # noqa: BLE001
            pass
    return '{"dokument":%s,"objekti":[%s]}' % (json.dumps(doc.Label), ",".join(objekti))


def izris_mreze(objekti, smer, velikost, samo=None):
    """Rezervni izris brez brskalnika (nit strežnika, numpy + Pillow): pravokotna projekcija, slikarjev algoritem po
    globini, senčenje po normali, robovi. Vrne (JPEG bajti, opis)."""
    import numpy as np
    from PIL import Image, ImageDraw
    nazaj = np.array(smer[0], float)
    nazaj /= np.linalg.norm(nazaj)
    gor = np.array(smer[1], float)
    desno = np.cross(gor, nazaj)
    desno /= np.linalg.norm(desno)
    gor = np.cross(nazaj, desno)
    R = np.stack([desno, gor, nazaj])
    tri, barve, robovi = [], [], []
    for o in objekti:
        if samo and o.get("ime") not in samo:
            continue
        t = np.array(o.get("tocke") or [], float).reshape(-1, 3)
        idx = np.array(o.get("trikotniki") or [], int).reshape(-1, 3)
        if len(t) and len(idx):
            bt = np.tile(np.array([0.8, 0.8, 0.82]), (len(idx), 1))
            for p in o.get("ploskve") or []:
                if len(p) >= 7:
                    bt[p[2]:p[2] + p[3]] = p[4:7]
            tri.append(t[idx])
            barve.append(bt)
        rt = np.array(o.get("robTocke") or [], float).reshape(-1, 2, 3)
        if len(rt):
            robovi.append(rt)
    if not tri:
        raise Napaka("Ni geometrije za izris (prazen dokument ali skriti objekti).")
    tri = np.concatenate(tri) @ R.T
    barve = np.concatenate(barve)
    robovi = (np.concatenate(robovi) @ R.T) if robovi else np.zeros((0, 2, 3))
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    dol = np.linalg.norm(n, axis=1)
    ok = dol > 1e-12
    tri, barve, n = tri[ok], barve[ok], n[ok] / dol[ok][:, None]
    luc = np.array([0.35, 0.55, 0.76])
    luc /= np.linalg.norm(luc)
    svet = np.abs(n[:, 2]) * 0.45 + np.clip(n @ luc, 0, 1) * 0.25 + 0.38
    mn = tri[:, :, :2].reshape(-1, 2).min(0)
    mx = tri[:, :, :2].reshape(-1, 2).max(0)
    V = velikost * 2
    merilo = (V * 0.9) / max(float((mx - mn).max()), 1e-6)
    zamik = (V - (mx - mn) * merilo) / 2
    # slikarjev algoritem razvršča cele trikotnike: velike (ploskve zaslona, strehe) razdeli na manjše, da se vrstni
    # red po globini ne zmoti ob drobnih sosedih
    meja = V / 14.0 / merilo
    for _ in range(5):
        dolzine = np.maximum.reduce([np.linalg.norm((tri[:, i, :2] - tri[:, (i + 1) % 3, :2]), axis=1) for i in range(3)])
        veliki = dolzine > meja
        if not veliki.any() or len(tri) + 3 * int(veliki.sum()) > 900000:
            break
        a, b, c = tri[veliki, 0], tri[veliki, 1], tri[veliki, 2]
        ab, bc, ca = (a + b) / 2, (b + c) / 2, (c + a) / 2
        novi = np.concatenate([np.stack(t, axis=1) for t in ((a, ab, ca), (ab, b, bc), (ca, bc, c), (ab, bc, ca))])
        tri = np.concatenate([tri[~veliki], novi])
        barve = np.concatenate([barve[~veliki]] + [barve[veliki]] * 4)
        svet = np.concatenate([svet[~veliki]] + [svet[veliki]] * 4)

    diag = float(np.linalg.norm(mx - mn)) or 1.0
    globine = np.concatenate([tri[:, :, 2].mean(1),
                              (robovi[:, :, 2].mean(1) + diag * 0.002) if len(robovi) else np.zeros(0)])
    red = np.argsort(globine, kind="stable")
    n_tri = len(tri)
    # zaslonske koordinate in barve vnaprej (numpy), v zanki le risanje
    zt = np.empty(tri.shape[:2] + (2,))
    zt[..., 0] = (tri[..., 0] - mn[0]) * merilo + zamik[0]
    zt[..., 1] = V - ((tri[..., 1] - mn[1]) * merilo + zamik[1])
    rgb = np.clip(barve[:, :3] * 255 * svet[:, None], 0, 255).astype(int)
    if len(robovi):
        zr = np.empty(robovi.shape[:2] + (2,))
        zr[..., 0] = (robovi[..., 0] - mn[0]) * merilo + zamik[0]
        zr[..., 1] = V - ((robovi[..., 1] - mn[1]) * merilo + zamik[1])
        zr = zr.tolist()
    zt, rgb = zt.tolist(), rgb.tolist()
    img = Image.new("RGB", (V, V), (255, 255, 255))
    d = ImageDraw.Draw(img)
    debelina = max(1, V // 700)
    for k in red.tolist():
        if k < n_tri:
            b = tuple(rgb[k])
            d.polygon([tuple(p) for p in zt[k]], fill=b, outline=b)
        else:
            r = zr[k - n_tri]
            d.line([tuple(r[0]), tuple(r[1])], fill=(40, 44, 52), width=debelina)
    img = img.resize((velikost, velikost), Image.LANCZOS)
    izhod = io.BytesIO()
    img.save(izhod, "JPEG", quality=88)
    velikost_modela = (mx - mn)
    return izhod.getvalue(), "Trikotnikov %d; širina × višina na sliki %s × %s mm." % (
        len(tri), _st_mm(float(velikost_modela[0]), 1), _st_mm(float(velikost_modela[1]), 1))


@orodje("render", naslov="Fotorealističen render", nit="streznik", lastnosti={
    "pogled": {"type": "string", "enum": ["privzet", "zaslon"] + list(POGLEDI),
               "description": "privzet (3/4 od spredaj), zaslon (kamera brskalnika) ali standardni pogled"},
    "osvetlitev": {"type": "string", "enum": ["studio", "mehka", "soncni", "mesto", "gozd", "notranjost", "noc"]},
    "ozadje": {"type": "string", "enum": ["svetlo", "belo", "temno", "prozorno", "okolje"]},
    "kakovost": {"type": "string", "enum": ["osnutek", "dobro", "najboljse"], "description": "privzeto osnutek"},
    "sirina": {"type": "integer", "description": "px (privzeto 1600)"},
    "visina": {"type": "integer", "description": "px (privzeto 1000)"},
    "video": {"type": "boolean", "description": "video 360° namesto slike (vrne pot do MP4)"},
    "cakaj": {"type": "number", "description": "sekunde čakanja (privzeto 300)"},
}, opis="""
Fotorealističen render aktivnega dokumenta (Blender Cycles na grafični kartici, materiali iz Videza). Vrne sliko in pot
datoteke (tudi v mapo Renderji ob modelu). Traja od nekaj sekund (osnutek) do minute; video 360° nekaj minut.""")
def t_render(a):
    pogled = a.get("pogled") or "privzet"
    kamera, premiki = None, None
    if pogled == "zaslon":
        odgovor = brskalnik("kamera", {}, cakaj=8.0)
        if not odgovor or not odgovor.get("kamera"):
            raise Napaka("Brskalnik ni vrnil kamere (stran ni odprta ali je starejša — osveži zavihek).")
        kamera, premiki = odgovor["kamera"], odgovor.get("premiki")
    elif pogled in POGLEDI:
        podatki = json.loads(S.STANJE.posnetek().decode("utf-8"))
        tocke = [t for o in podatki.get("objekti") or [] for t in (o.get("tocke") or [])]
        if not tocke:
            raise Napaka("Aktivni dokument nima vidne geometrije.")
        xs, ys, zs = tocke[0::3], tocke[1::3], tocke[2::3]
        c = App.Vector((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, (min(zs) + max(zs)) / 2)
        r = max(App.Vector(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)).Length / 2, 1.0)
        nazaj, gor = POGLEDI[pogled]
        d = App.Vector(*nazaj)
        d.normalize()
        fov = 30.0
        razdalja = r / math.sin(math.radians(fov / 2)) * 1.05
        p = c + d * razdalja
        kamera = {"polozaj": [p.x, p.y, p.z], "cilj": [c.x, c.y, c.z], "gor": list(gor), "fov": fov, "pravokotna": False}
    sirina = max(64, min(int(a.get("sirina") or 1600), 7680))
    visina = max(64, min(int(a.get("visina") or 1000), 4320))
    telo = {"kamera": kamera, "premiki": premiki, "osvetlitev": a.get("osvetlitev") or "studio",
            "ozadje": a.get("ozadje") or "svetlo", "kakovost": a.get("kakovost") or "osnutek",
            "sirina": sirina, "visina": visina, "vrtenje": 120 if a.get("video") else 0}
    zacetek = S.render_modela(telo)
    if not zacetek.get("ok"):
        raise Napaka(zacetek.get("sporocilo") or "Render se ni začel.")
    return _cakaj_render(zacetek["id"], _cakaj(a, 300))


def _cakaj_render(nid, cakaj):
    konec = time.time() + cakaj
    stanje = None
    while time.time() < konec:
        stanje = S.UPODABLJANJE.stanje(nid) or {}
        if stanje.get("stanje") in ("koncano", "napaka", "ustavljeno"):
            break
        time.sleep(1.0)
    if not stanje or stanje.get("stanje") not in ("koncano", "napaka", "ustavljeno"):
        return {"besedilo": "Render %s še teče (%s, %d %%). Počakaj z `opravilo` {\"id\": \"render:%s\"}." % (
            nid, (stanje or {}).get("sporocilo", ""), round(100 * float((stanje or {}).get("napredek") or 0)), nid)}
    if stanje["stanje"] != "koncano":
        raise Napaka("Render %s: %s" % (stanje["stanje"], stanje.get("sporocilo", "")))
    datoteka = stanje.get("datoteka") or ""
    v = "Render končan v %s s: %s%s" % (_st_mm(stanje.get("cas") or 0, 1), datoteka,
                                         (" (kopija: %s)" % stanje["shranjeno"]) if stanje.get("shranjeno") else "")
    if not datoteka.lower().endswith(".png") or not os.path.isfile(datoteka):
        return v
    from PIL import Image
    with Image.open(datoteka) as slika:
        slika = slika.convert("RGBA")
        podlaga = Image.new("RGB", slika.size, (255, 255, 255))
        podlaga.paste(slika, mask=slika.split()[3])
        podlaga.thumbnail((1280, 1280))
        izhod = io.BytesIO()
        podlaga.save(izhod, "JPEG", quality=88)
    return {"besedilo": v, "slike": [("image/jpeg", izhod.getvalue())]}


def _oblikovanje_povezava():
    pot = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "FreeCAD-splet", "oblikovanje.json")
    try:
        with open(pot, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _oblikovanje_klic(metoda, pot, telo=None, cas=60.0):
    p = _oblikovanje_povezava()
    if p is None:
        raise Napaka("Oblikovanje ne teče (ni oblikovanje.json).")
    c = http.client.HTTPConnection("127.0.0.1", int(p.get("vrata") or S.OBLIKOVANJE_VRATA), timeout=cas)
    try:
        glave = {"X-Zeton": p.get("zeton", "")}
        podatki = None
        if telo is not None:
            podatki = json.dumps(telo, ensure_ascii=False).encode("utf-8")
            glave["Content-Type"] = "application/json"
        c.request(metoda, pot, body=podatki, headers=glave)
        r = c.getresponse()
        return r.status, r.read()
    finally:
        c.close()


@orodje("oblikovanje", naslov="Oblikovanje (Blender)", nit="streznik", unicujoce=True, cakaj=300, lastnosti={
    "koda": {"type": "string", "description": "Python v Blenderju (bpy, bmesh, np, Vector, Matrix, math, C, D in "
                                             "pomočniki dodaj_obliko(vrsta, velikost, lega), gladko(obj), "
                                             "material(ime, barva, kovinskost, hrapavost), pocisti()); 1 enota = 1 mm; "
                                             "nastavi `rezultat`"},
    "datoteka": {"type": "string", "description": "namesto kode izvedi skripto s to potjo"},
    "slika": {"type": "boolean", "description": "vrni še sliko scene (preprost izris mreže)"},
    "pogled": {"type": "string", "enum": list(POGLEDI), "description": "smer slike (privzeto izo)"},
    "cakaj": {"type": "number", "description": "sekunde čakanja (privzeto 300)"},
}, opis="""
Prosto oblikovanje v Blenderju (zavihek Oblikovanje: organske, gladke oblike, različice, render). Izvede Python v
Blenderju, ki teče v ozadju (če ne teče, ga zažene), in vrne izpis, `rezultat` ter po želji sliko scene. Brez kode in
slike vrne stanje (odprta datoteka, ideja, objekti).""")
def t_oblikovanje(a):
    if not S.oblikovanje_stanje().get("tece"):
        ok, sporocilo = S.oblikovanje_zazeni()
        if not ok:
            raise Napaka(sporocilo)
        konec = time.time() + 90
        while time.time() < konec and not S.oblikovanje_stanje().get("tece"):
            time.sleep(1.5)
        if not S.oblikovanje_stanje().get("tece"):
            raise Napaka("Blender se v 90 s ni oglasil (%s)." % sporocilo)
    v, slike = [], []
    koda = a.get("koda") or ""
    if a.get("datoteka"):
        try:
            with open(a["datoteka"], encoding="utf-8-sig") as f:
                koda = f.read()
        except OSError as e:
            raise Napaka("Skripte ni mogoče prebrati: %s" % e)
    napaka = False
    if koda.strip():
        cakaj = _cakaj(a, 300)
        status, telo = _oblikovanje_klic("POST", "/python", {"koda": koda, "cakaj": cakaj}, cas=cakaj + 30)
        try:
            o = json.loads(telo.decode("utf-8"))
        except ValueError:
            raise Napaka("Blender je vrnil %d: %s" % (status, telo[:300]))
        napaka = bool(o.get("napaka")) or not o.get("ok", True)
        if o.get("izpis"):
            v.append("Izpis:\n" + _kratko(o["izpis"].rstrip(), 30000))
        if o.get("napaka"):
            v.append("NAPAKA:\n" + _kratka_sled(o["napaka"], 14))
        if o.get("rezultat") is not None:
            v.append("rezultat = " + _kratko(json.dumps(o["rezultat"], ensure_ascii=False, default=str, indent=1), 20000))
        if not v:
            v.append("Koda v Blenderju je tekla.")
    if a.get("slika"):
        status, telo = _oblikovanje_klic("GET", "/model", cas=60)
        model = json.loads(telo.decode("utf-8"))
        objekti = []
        for o in model.get("objekti") or []:
            mat = o.get("materiali") or [{}]
            ploskve = [[0, 0, z, n] + list((mat[m] if m < len(mat) else mat[0]).get("barva", [0.8, 0.8, 0.8]))[:3]
                       for z, n, m in o.get("skupine") or []]
            objekti.append({"ime": o.get("ime"), "tocke": o.get("tocke"), "trikotniki": o.get("trikotniki"),
                            "ploskve": ploskve})
        jpeg, opis = izris_mreze(objekti, POGLEDI.get(a.get("pogled") or "izo", POGLEDI["izo"]), 800)
        slike.append(("image/jpeg", jpeg))
        v.append("Slika scene Oblikovanja (%d objektov). %s" % (len(objekti), opis))
    if not koda.strip() and not a.get("slika"):
        status, telo = _oblikovanje_klic("GET", "/stanje", cas=10)
        s = json.loads(telo.decode("utf-8"))
        v.append("Oblikovanje (Blender %s) teče. Datoteka: %s%s. Ideja: %s." % (
            s.get("blender", "?"), s.get("datoteka") or "ni shranjena", " (neshranjena)" if s.get("spremenjeno") else "",
            (s.get("ideja") or {}).get("ime") if isinstance(s.get("ideja"), dict) else s.get("ideja") or "–"))
    return {"napaka": napaka, "besedilo": "\n".join(v), "slike": slike}


@orodje("natisni", naslov="Natisni (3D tisk)", nit="streznik", lastnosti={
    "dokument": {"type": "string", "description": "ime ali oznaka (privzeto aktivni)"},
    "objekti": {"type": "array", "items": {"type": "string"},
                "description": "kosi za tisk (imena ali oznake); privzeto vsa vidna telesa"},
}, opis="""
Kose izvozi kot STEP v vhodno mapo plošče tiskalnikov (Tiskaj) in v brskalniku odpre zavihek Tiskanje z oknom Pripravi.
Tiskalnik, predal, lego in polnilo potrdi uporabnik; tisk se nikoli ne zažene sam.""")
def t_natisni(a):
    def pripravi():
        doc = _dokument(a.get("dokument"))
        if a.get("objekti"):
            imena = [_objekt(doc, o).Name for o in a["objekti"]]
        else:
            imena = []
            for o in _telesa_dokumenta(doc):
                try:
                    if _oblika(doc, o.Name)[0].Solids:
                        imena.append(o.Name)
                except Exception:  # noqa: BLE001
                    pass
        if not imena:
            raise Napaka("Ni kosov s trdnim telesom za tisk.")
        return doc.Name, imena
    ime_doc, imena = _glavna_vrednost(pripravi)
    podatki = {"dokument": ime_doc, "imena": imena, "mapa": S._tiskaj_vhod_mapa()}
    odgovor = {"konec": threading.Event(), "izpis": "", "napaka": "", "rezultat": None}
    S.STANJE.vrsta.put(("tiskaj", podatki, odgovor))
    if not odgovor["konec"].wait(180):
        raise Napaka("Izvoz za tisk še teče; poglej mapo plošče kasneje.")
    if odgovor["napaka"]:
        raise Napaka("Izvoz ni uspel: " + odgovor["napaka"].strip().splitlines()[-1])
    izid = odgovor["rezultat"] or {}
    if not izid.get("ok"):
        raise Napaka(izid.get("sporocilo") or "Izvoz za tisk ni uspel.")
    plosca = S._tiskaj_oznaci_rocno(list(izid["datoteke"]))
    odziv = brskalnik("natisni", {"datoteke": izid["datoteke"]}, cakaj=4.0)
    v = [izid.get("sporocilo", ""), "Mapa: %s" % izid.get("mapa", ""), "Datoteke: " + ", ".join(izid["datoteke"])]
    if plosca is False:
        v.append("Plošča Tiskaj ne teče: uporabnik jo zažene v zavihku Tiskanje (datoteke počakajo).")
    v.append("Okno Pripravi je odprto v brskalniku; tiskalnik, predal in polnilo potrdi uporabnik." if odziv else
             "Brskalnik ni odprt: okno Pripravi se odpre v zavihku Tiskanje, ko ga uporabnik odpre.")
    return "\n".join(v)


# ---------------------------------------------------------------------------------------------------------------
# Orodja: odkrivanje (iskanje)

MODULI_API = ["FreeCAD", "FreeCADGui", "Part", "Sketcher", "PartDesign", "Mesh", "MeshPart", "Import", "ImportGui",
              "Draft", "DraftGeomUtils", "DraftVecUtils", "Spreadsheet", "TechDraw", "Assembly", "UtilsAssembly",
              "JointObject", "Materials", "Measure", "Points", "Surface", "BOPTools", "BOPTools.SplitFeatures",
              "CompoundTools", "Show", "SheetMetalTools", "SheetMetalCmd",
              "freecad.cables.wireFlex", "freecad.cables.archCable"]


def _indeks_glavna():
    """Glavna nit: ukazi (vsi registrirani), API modulov in tipi objektov. Enkrat na zagon (ukazi ob spremembi)."""
    import importlib
    import inspect
    vnosi = []
    # ukazi
    okolja_ukaza = {}
    try:
        ukazi = json.loads(S.STANJE.ukazi())
        for o in ukazi.get("delovnaOkolja", []):
            for t in o.get("orodneVrstice", []):
                for skupina in t.get("skupine", []):
                    for u in skupina:
                        for x in [u] + [p for p in (u.get("podukazi") or []) if isinstance(p, dict)]:
                            okolja_ukaza.setdefault(x.get("ime"), "%s / %s" % (o.get("naslov") or o["ime"],
                                                                                 t.get("naslov") or t.get("ime")))
    except ValueError:
        pass
    try:
        imena = Gui.Command.listAll()
    except Exception:  # noqa: BLE001
        imena = list(okolja_ukaza)
    for ime in imena:
        try:
            cmd = Gui.Command.get(ime)
            info = cmd.getInfo() if cmd is not None else {}
        except Exception:  # noqa: BLE001
            info = {}
        naslov = re.sub(r"&(?!&)", "", str(info.get("menuText") or ""))
        opis = re.sub(r"<[^>]+>", " ", str(info.get("toolTip") or info.get("statusTip") or ""))
        vnosi.append({"vrsta": "ukaz", "ime": ime, "naslov": naslov, "opis": " ".join(opis.split())[:300],
                      "raba": "ukaz {\"ime\": \"%s\"}%s" % (ime, ("  · " + okolja_ukaza[ime]) if ime in okolja_ukaza
                                                            else "")})
    # tipi objektov
    try:
        doc = App.ActiveDocument or next(iter(App.listDocuments().values()), None)
        tipi = doc.supportedTypes() if doc is not None else []
    except Exception:  # noqa: BLE001
        tipi = []
    for tip in tipi:
        vnosi.append({"vrsta": "tip", "ime": tip, "naslov": "", "opis": "tip objekta",
                      "raba": "doc.addObject(\"%s\", \"Ime\") · lastnosti: isci {\"podrobno\": \"%s\"}" % (tip, tip)})
    # API
    for ime_mod in MODULI_API:
        try:
            mod = importlib.import_module(ime_mod)
        except Exception:  # noqa: BLE001
            continue
        for ime in dir(mod):
            if ime.startswith("_"):
                continue
            try:
                x = getattr(mod, ime)
            except Exception:  # noqa: BLE001
                continue
            if inspect.ismodule(x):
                continue
            polno = "%s.%s" % (ime_mod, ime)
            vnosi.append({"vrsta": "api", "ime": polno, "naslov": "", "opis": _prva_vrstica(x), "raba": _podpis(x, polno)})
            if inspect.isclass(x) and len(vnosi) < 60000:
                for m in dir(x):
                    if m.startswith("_"):
                        continue
                    try:
                        y = getattr(x, m)
                    except Exception:  # noqa: BLE001
                        continue
                    vnosi.append({"vrsta": "api", "ime": "%s.%s" % (polno, m), "naslov": "",
                                  "opis": _prva_vrstica(y), "raba": ""})
    return vnosi


def _prva_vrstica(x):
    try:
        doc = x.__doc__ if not isinstance(x, (int, float, str, bool)) else ""
    except Exception:  # noqa: BLE001
        doc = ""
    if not doc or not isinstance(doc, str):
        return ""
    for v in doc.strip().splitlines():
        if v.strip():
            return v.strip()[:240]
    return ""


def _podpis(x, ime):
    import inspect
    try:
        return ime + str(inspect.signature(x))
    except Exception:  # noqa: BLE001
        return ""


def _indeks_datotek():
    """Nit strežnika: naši moduli (lastno/**.py) in skripte projektov (Skripte/, _Skripte/, PREBERI.txt) prek ast."""
    st = _st()
    predpomnilnik = st.setdefault("datoteke", {})
    vnosi = []
    poti = []
    for koren, mape, datoteke in os.walk(os.path.join(KOREN_REPO, "lastno")):
        mape[:] = [m for m in mape if m not in ("__pycache__",) and not m.startswith(".")]
        poti += [("modul", os.path.join(koren, d)) for d in datoteke if d.endswith(".py")]
    oblak = getattr(S, "MAPA_OBLAK", "")
    if oblak and os.path.isdir(oblak):
        for koren, mape, datoteke in os.walk(oblak):
            globina = koren[len(oblak):].count(os.sep)
            mape[:] = [m for m in mape if not m.startswith(".") and m not in ("DXF", "_Renderji", "Renderji")
                       and globina < 4]
            ime_mape = os.path.basename(koren)
            if ime_mape in ("Skripte", "_Skripte"):
                poti += [("skripta", os.path.join(koren, d)) for d in datoteke if d.endswith(".py")]
            poti += [("skripta", os.path.join(koren, d)) for d in datoteke if d.upper() in ("PREBERI.TXT", "README.MD")]
    for vrsta, pot in poti:
        try:
            st_ = os.stat(pot)
        except OSError:
            continue
        kljuc = (pot, st_.st_mtime, st_.st_size)
        if kljuc in predpomnilnik:
            vnosi += predpomnilnik[kljuc]
            continue
        lastni = _opis_datoteke(vrsta, pot)
        predpomnilnik[kljuc] = lastni
        vnosi += lastni
    return vnosi


def _opis_datoteke(vrsta, pot):
    ime = os.path.basename(pot)
    try:
        with open(pot, encoding="utf-8-sig", errors="replace") as f:
            besedilo = f.read(400000)
    except OSError:
        return []
    if not pot.endswith(".py"):
        prve = " ".join(besedilo.strip().splitlines()[:6])[:400]
        return [{"vrsta": vrsta, "ime": pot, "naslov": ime, "opis": prve, "raba": "preberi datoteko"}]
    try:
        drevo = ast.parse(besedilo)
    except SyntaxError:
        return [{"vrsta": vrsta, "ime": pot, "naslov": ime, "opis": "(skladenjska napaka)", "raba": ""}]
    doc = (ast.get_docstring(drevo) or "").strip()
    funkcije = [n for n in drevo.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
    raba = ("python {\"datoteka\": \"%s\"}" % pot.replace("\\", "/")) if vrsta == "skripta" else \
        "modul %s (mapa %s)" % (ime[:-3], os.path.dirname(pot).replace("\\", "/"))
    vnosi = [{"vrsta": vrsta, "ime": pot, "naslov": ime, "opis": " ".join(doc.split())[:400] +
              (" · funkcije: " + ", ".join(n.name for n in funkcije[:30]) if funkcije else ""), "raba": raba}]
    if vrsta == "modul":
        for n in funkcije:
            if n.name.startswith("__"):
                continue
            argi = ""
            if isinstance(n, ast.FunctionDef):
                argi = "(" + ", ".join(x.arg for x in n.args.args) + ")"
            vnosi.append({"vrsta": "modul", "ime": "%s.%s" % (ime[:-3], n.name), "naslov": "",
                          "opis": (" ".join((ast.get_docstring(n) or "").split()))[:300],
                          "raba": "%s.%s%s v %s" % (ime[:-3], n.name, argi, pot.replace("\\", "/"))})
    return vnosi


def _indeks_ostalo():
    vnosi = [{"vrsta": "splet", "ime": "%s %s" % (m, p), "naslov": "", "opis": opis,
              "raba": "splet {\"metoda\": \"%s\", \"pot\": \"%s\"%s}" % (m, p, (", \"telo\": " + t) if t.startswith("{")
                                                                        else "")}
              for m, p, opis, t in KONCNE_TOCKE]
    odsek = ""
    for vrstica in PRAVILA.splitlines():
        if vrstica.startswith("## "):
            odsek = vrstica[3:]
        elif vrstica.startswith("- "):
            vnosi.append({"vrsta": "pravilo", "ime": odsek, "naslov": "", "opis": vrstica[2:], "raba": ""})
    for o in ORODJA.values():
        vnosi.append({"vrsta": "orodje", "ime": o["ime"], "naslov": o["naslov"], "opis": " ".join(o["opis"].split())[:300],
                      "raba": "orodje MCP %s" % o["ime"]})
    return vnosi


def _indeks(vrsta):
    st = _st()
    indeks = st["indeks"]
    if vrsta in ("vse", "ukaz", "api", "tip"):
        stevilo = len(S.STANJE.imena_ukazov)
        nalozena = tuple(sorted(getattr(S.STANJE, "nalozena", []) or []))
        if indeks.get("glavna") is None or indeks.get("glavna_kljuc") != (stevilo, nalozena):
            indeks["glavna"] = _glavna_vrednost(_indeks_glavna, 180)
            indeks["glavna_kljuc"] = (stevilo, nalozena)
    vnosi = []
    if vrsta in ("vse", "ukaz", "api", "tip"):
        vnosi += indeks["glavna"]
    if vrsta in ("vse", "modul", "skripta"):
        vnosi += _indeks_datotek()
    if vrsta in ("vse", "splet", "pravilo", "orodje"):
        vnosi += _indeks_ostalo()
    if vrsta != "vse":
        vnosi = [v for v in vnosi if v["vrsta"] == vrsta]
    return vnosi


@orodje("isci", naslov="Iskanje funkcij", nit="streznik", samo_branje=True, lastnosti={
    "poizvedba": {"type": "string", "description": "besede (angleško za API in ukaze, slovensko za naše module, "
                                                  "skripte in pravila), npr. \"fillet edges\", \"loft\", \"razgrnitev\""},
    "vrsta": {"type": "string", "enum": ["vse", "ukaz", "api", "tip", "modul", "skripta", "splet", "pravilo", "orodje"],
              "description": "omeji na vrsto (privzeto vse)"},
    "podrobno": {"type": "string", "description": "celoten opis enega zadetka: ukaz (PartDesign_Fillet), API "
                                                 "(Part.makeLoft, Part.Shape.makeFillet), tip z lastnostmi "
                                                 "(PartDesign::Pad), modul (drevo._otroci) ali pot skripte"},
    "najvec": {"type": "integer", "description": "največ zadetkov (privzeto 25)"},
}, opis="""
Poišče, kaj program zna, ne da bi bral izvorno kodo: ukaze vseh okolij (ime, naslov, namig, okolje), FreeCAD API
(funkcije in metode modulov Part, Sketcher, PartDesign, Mesh, Draft, Assembly …), tipe objektov, funkcije naših modulov
(lastno/), skripte projektov v Oblaku, končne točke strežnika in pravila. podrobno vrne celoten opis (docstring,
podpis, pri tipu vse lastnosti z opisi).""")
def t_isci(a):
    if a.get("podrobno"):
        return _podrobno(a["podrobno"].strip())
    poizvedba = _normaliziraj_besedilo(a.get("poizvedba") or "")
    besede = [b for b in re.split(r"[\s,;]+", poizvedba) if b]
    if not besede:
        raise Napaka("Manjka poizvedba (ali podrobno).")
    vrsta = a.get("vrsta") or "vse"
    najvec = max(1, min(int(a.get("najvec") or 25), 100))
    vnosi = _indeks(vrsta)
    zadetki = []
    for v in vnosi:
        ime = _normaliziraj_besedilo(v["ime"])
        naslov = _normaliziraj_besedilo(v.get("naslov", ""))
        opis = _normaliziraj_besedilo(v.get("opis", ""))
        tocke, vse = 0, True
        for b in besede:
            if ime == b or ime.endswith("." + b) or ime.endswith("_" + b):
                tocke += 14
            elif b in ime:
                tocke += 7
            elif b in naslov:
                tocke += 5
            elif b in opis:
                tocke += 2
            else:
                vse = False
        if tocke and vse:
            if v["vrsta"] == "ukaz":
                tocke += 2
            elif v["vrsta"] == "api" and v["ime"].count(".") > 1:
                tocke -= 1
            zadetki.append((tocke, v))
    if not zadetki:
        return "Ni zadetkov za »%s« (%s). Poskusi angleške besede za API in ukaze ali drugo vrsto." % (
            a.get("poizvedba"), vrsta)
    zadetki.sort(key=lambda z: (-z[0], len(z[1]["ime"])))
    v = ["Zadetki za »%s« (%d, prikazanih %d; celoten opis: isci {\"podrobno\": ime}):" % (
        a.get("poizvedba"), len(zadetki), min(najvec, len(zadetki)))]
    for _, z in zadetki[:najvec]:
        vrstica = "[%s] %s" % (z["vrsta"], z["ime"])
        if z.get("naslov") and z["naslov"] != z["ime"]:
            vrstica += " — " + z["naslov"]
        if z.get("opis"):
            vrstica += ": " + (z["opis"] if len(z["opis"]) <= 220 else z["opis"][:220].rstrip() + " …")
        if z.get("raba"):
            vrstica += "\n    → " + z["raba"]
        v.append(vrstica)
    return "\n".join(v)


def _podrobno(ime):
    # ukaz
    if re.match(r"^[A-Za-z]+_[A-Za-z0-9_]+$", ime) and "::" not in ime:
        def ukaz():
            cmd = Gui.Command.get(ime)
            if cmd is None:
                return None
            info = cmd.getInfo()
            try:
                aktiven = cmd.isActive()
            except Exception:  # noqa: BLE001
                aktiven = None
            return {"info": {k: str(v) for k, v in info.items() if k != "pixmap"}, "aktiven": aktiven}
        izid = _glavna_vrednost(ukaz)
        if izid is not None:
            info = izid["info"]
            return "Ukaz %s\nNaslov: %s\nNamig: %s\nKaj dela: %s\nBližnjica: %s\nZdaj na voljo: %s\nRaba: ukaz {\"ime\": \"%s\"}" % (
                ime, info.get("menuText", ""), re.sub(r"<[^>]+>", " ", info.get("toolTip", "")),
                re.sub(r"<[^>]+>", " ", info.get("whatsThis", "")), info.get("shortcut", ""),
                {True: "da", False: "ne (potrebuje izbiro ali drugo stanje)", None: "?"}[izid["aktiven"]], ime)
    # tip objekta
    if "::" in ime:
        return _glavna_vrednost(lambda: _opis_tipa(ime), 60)
    # skripta ali modul po poti
    if os.path.isfile(ime):
        vnosi = _opis_datoteke("skripta", ime)
        try:
            with open(ime, encoding="utf-8-sig", errors="replace") as f:
                vsebina = f.read(6000)
        except OSError:
            vsebina = ""
        return "%s\n%s\n--- začetek datoteke ---\n%s" % (ime, vnosi[0]["opis"] if vnosi else "", vsebina)
    # naš modul
    for v in _indeks_datotek():
        if v["vrsta"] == "modul" and v["ime"] == ime:
            pot = v["raba"].rsplit(" v ", 1)[-1]
            return _izvorni_odsek(pot, ime.split(".")[-1]) or v["raba"]
    # API
    return _glavna_vrednost(lambda: _opis_api(ime), 60)


def _izvorni_odsek(pot, ime_funkcije):
    try:
        with open(pot, encoding="utf-8-sig") as f:
            besedilo = f.read()
        drevo = ast.parse(besedilo)
    except (OSError, SyntaxError):
        return ""
    vrstice = besedilo.splitlines()
    for n in drevo.body:
        if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == ime_funkcije:
            konec = getattr(n, "end_lineno", n.lineno + 40)
            odsek = vrstice[n.lineno - 1:min(konec, n.lineno + 80)]
            return "%s (%s, vrstica %d)\n%s" % (ime_funkcije, pot, n.lineno, "\n".join(odsek))
    return ""


def _opis_api(ime):
    import importlib
    import inspect
    deli = ime.split(".")
    x, mod = None, None
    for i in range(len(deli), 0, -1):
        try:
            mod = importlib.import_module(".".join(deli[:i]))
        except Exception:  # noqa: BLE001
            continue
        x = mod
        try:
            for d in deli[i:]:
                x = getattr(x, d)
        except AttributeError:
            raise Napaka("»%s« ne obstaja (modul %s nima %s). Poišči z `isci`." % (ime, ".".join(deli[:i]), d))
        break
    if x is None:
        raise Napaka("Modula za »%s« ni. Poišči z `isci`." % ime)
    v = [ime]
    podpis = _podpis(x, ime)
    if podpis:
        v.append("Podpis: " + podpis)
    doc = inspect.getdoc(x) or ""
    v.append(_kratko(doc, 8000) if doc else "(brez opisa)")
    if inspect.isclass(x) or inspect.ismodule(x):
        clani = [m for m in dir(x) if not m.startswith("_")]
        v.append("Člani (%d): %s" % (len(clani), ", ".join(clani[:300])))
    return "\n".join(v)


def _opis_tipa(tip):
    """Lastnosti tipa objekta: objekt v začasnem skritem dokumentu (takoj zaprt)."""
    doc = App.newDocument("MCP_tip", hidden=True, temp=True)
    try:
        try:
            obj = doc.addObject(tip, "Primer")
        except Exception as e:  # noqa: BLE001
            raise Napaka("Tipa »%s« ni mogoče ustvariti: %s" % (tip, e))
        v = ["Tip %s — lastnosti (skupina, tip, privzeta vrednost, opis):" % tip]
        for ime in obj.PropertiesList:
            try:
                skupina = obj.getGroupOfProperty(ime)
                vrsta = obj.getTypeIdOfProperty(ime).replace("App::Property", "")
                opis = obj.getDocumentationOfProperty(ime) or ""
                nacin = obj.getEditorMode(ime)
            except Exception:  # noqa: BLE001
                continue
            if "Hidden" in nacin:
                continue
            vrednost = _vrednost_lastnosti(obj, ime)
            dod = ""
            if vrsta == "Enumeration":
                try:
                    dod = " možnosti: " + ", ".join(obj.getEnumerationsOfProperty(ime) or [])
                except Exception:  # noqa: BLE001
                    pass
            v.append("  [%s] %s (%s) = %s%s%s" % (skupina, ime, vrsta, _kratko(vrednost, 80), dod,
                                                  (" — " + " ".join(opis.split())[:200]) if opis else ""))
        return "\n".join(v)
    finally:
        App.closeDocument(doc.Name)


# ---------------------------------------------------------------------------------------------------------------
# Orodja: splet, opravila, dnevnik, izhod

POT_POSTOPKOV = os.path.join(KOREN_REPO, "lastno", "mcp", "skill", "freecad", "SKILL.md")


def _postopki_besedilo():
    """Delovni postopki (isto besedilo kot skill »freecad«), brez glave YAML."""
    try:
        with open(POT_POSTOPKOV, encoding="utf-8") as f:
            besedilo = f.read()
    except OSError:
        return "Postopki niso na voljo (%s)." % POT_POSTOPKOV
    if besedilo.startswith("---"):
        besedilo = besedilo.split("---", 2)[-1]
    return besedilo.strip()


@orodje("postopki", naslov="Postopki dela", nit="streznik", samo_branje=True, lastnosti={
    "tema": {"type": "string", "description": "samo poglavje ali vrstice s to besedo (npr. pločevina, sestav, tisk)"},
}, opis="""
Kako upravljati spletni FreeCAD s temi orodji: prvi koraki, spremembe (python, ukaz + obrazec), nov kos, pločevina,
sestav, pregled, 3D tisk, render, Oblikovanje, česa ne delati. Preberi na začetku večje naloge.""")
def t_postopki(a):
    besedilo = _postopki_besedilo()
    tema = _normaliziraj_besedilo(a.get("tema") or "")
    if not tema:
        return besedilo
    odseki = re.split(r"\n(?=## )", besedilo)
    zadetki = [o for o in odseki if tema in _normaliziraj_besedilo(o.splitlines()[0] if o else "")]
    if not zadetki:
        zadetki = [v for v in besedilo.splitlines() if tema in _normaliziraj_besedilo(v)]
        return "\n".join(zadetki) if zadetki else "Za »%s« ni posebnega postopka; celoten opis: postopki brez teme." % a["tema"]
    return "\n\n".join(zadetki)


@orodje("splet", naslov="Končna točka strežnika", nit="streznik", unicujoce=True, lastnosti={
    "metoda": {"type": "string", "enum": ["GET", "POST"], "description": "privzeto GET (POST, če je telo)"},
    "pot": {"type": "string", "description": "npr. /videz, /standardni, /knjiznica, /drevo, /skica, /tisk/lega"},
    "telo": {"type": "object", "description": "JSON telo za POST"},
    "katalog": {"type": "boolean", "description": "samo seznam končnih točk"},
}, opis="""
Klic katere koli končne točke spletnega strežnika (videz kosov, baza standardnih delov, knjižnica, drevo, skica v
brskalniku, lega za tisk, oblak in različice, zgradba sestava …). katalog=true jih našteje z oblikami teles. Žeton doda
samo. Izhod, Python in geometrija niso dovoljeni (za to so namenska orodja).""")
def t_splet(a):
    if a.get("katalog") or not a.get("pot"):
        return _vir_splet()
    pot = str(a["pot"])
    if not pot.startswith("/"):
        pot = "/" + pot
    osnova = pot.split("?")[0]
    if osnova in PREPOVEDANE_POTI or osnova.startswith("/mcp/"):
        raise Napaka("%s ni dovoljen prek `splet`: %s." % (osnova, PREPOVEDANE_POTI.get(osnova, "notranja pot")))
    telo = a.get("telo")
    metoda = (a.get("metoda") or ("POST" if telo is not None else "GET")).upper()
    if osnova == "/projekt" and isinstance(telo, dict) and telo.get("dejanje") == "zapri":
        raise Napaka("Zapiranje dokumentov: `dokumenti` {\"dejanje\": \"zapri\"} (zavrne neshranjene).")
    povezava = http.client.HTTPConnection("127.0.0.1", S.VRATA, timeout=600)
    try:
        glave = {"X-Zeton": S.ZETON}
        podatki = None
        if metoda == "POST":
            podatki = json.dumps(telo or {}, ensure_ascii=False).encode("utf-8")
            glave["Content-Type"] = "application/json"
        povezava.request(metoda, pot, body=podatki, headers=glave)
        r = povezava.getresponse()
        vsebina = r.read()
        vrsta = r.getheader("Content-Type") or ""
    finally:
        povezava.close()
    if vrsta.startswith("image/"):
        return {"besedilo": "%s %s → %d (%s, %d B)" % (metoda, pot, r.status, vrsta, len(vsebina)),
                "slike": [(vrsta.split(";")[0], vsebina)]}
    besedilo = vsebina.decode("utf-8", "replace")
    try:
        besedilo = json.dumps(json.loads(besedilo), ensure_ascii=False, indent=1)
    except ValueError:
        pass
    return {"napaka": r.status >= 400, "besedilo": "%s %s → %d\n%s" % (metoda, pot, r.status, _kratko(besedilo, 40000))}


@orodje("opravilo", naslov="Opravilo v teku", nit="streznik", samo_branje=True, lastnosti={
    "id": {"type": "string", "description": "oznaka opravila (iz odgovora, ki je potekel) ali render:<id>"},
    "cakaj": {"type": "number", "description": "sekunde čakanja (privzeto 60)"},
}, opis="""
Počaka na klic, ki je presegel čas čakanja (python, render …), in vrne njegov rezultat. Brez id našteje opravila.""")
def t_opravilo(a):
    opravila = _st()["opravila"]
    oid = a.get("id") or ""
    if not oid:
        if not opravila:
            return "Ni opravil v teku."
        return "\n".join("%s: %s, %s" % (k, o["ime"], "končano" if o["odgovor"]["konec"].is_set() else
                                         "teče %d s" % (time.time() - o["zacetek"])) for k, o in opravila.items())
    if oid.startswith("render:"):
        return _cakaj_render(oid[7:], _cakaj(a, 60))
    o = opravila.get(oid)
    if o is None:
        raise Napaka("Opravila %s ni (morda je že prebrano)." % oid)
    if not o["odgovor"]["konec"].wait(_cakaj(a, 60)):
        return "Opravilo %s še teče (%d s)." % (oid, time.time() - o["zacetek"])
    opravila.pop(oid, None)
    if o["odgovor"]["napaka"]:
        return {"napaka": True, "besedilo": _kratka_sled(o["odgovor"]["napaka"])}
    return _normaliziraj(o["odgovor"]["rezultat"])


@orodje("dnevnik", naslov="Dnevnik strežnika", nit="streznik", samo_branje=True, lastnosti={
    "vrstic": {"type": "integer", "description": "koliko zadnjih vrstic (privzeto 60)"},
    "isci": {"type": "string", "description": "le vrstice s tem besedilom (npr. napaka)"},
    "vir": {"type": "string", "enum": ["vse", "splet", "mcp"], "description": "splet = strežnik, mcp = klici orodij"},
}, opis="""
Zadnje vrstice dnevnika spletnega strežnika (posnetki, napake, oblak, tisk) in klicev orodij MCP (seja, orodje, čas,
napaka) ter zadnja napaka strežnika s sledjo.""")
def t_dnevnik(a):
    n = max(1, min(int(a.get("vrstic") or 60), 500))
    filt = _normaliziraj_besedilo(a.get("isci") or "")
    vir_f = a.get("vir") or "vse"
    vrstice = []
    for cas, vir_, besedilo in list(_st()["dnevnik"]):
        if vir_f != "vse" and vir_ != vir_f:
            continue
        if filt and filt not in _normaliziraj_besedilo(besedilo):
            continue
        vrstice.append("%s [%s] %s" % (time.strftime("%H:%M:%S", time.localtime(cas)), vir_, besedilo))
    v = vrstice[-n:] or ["(dnevnik je prazen%s)" % (" za ta filter" if filt or vir_f != "vse" else "")]
    if S.STANJE.napaka and vir_f in ("vse", "splet"):
        v.append("\nZadnja napaka strežnika:\n" + _kratka_sled(S.STANJE.napaka, 20))
    return "\n".join(v)


@orodje("izhod", naslov="Končaj FreeCAD", nit="streznik", unicujoce=True, lastnosti={
    "potrdi": {"type": "boolean", "description": "true samo, če je uporabnik izrecno rekel, naj se program konča"},
    "zavrzi_spremembe": {"type": "boolean", "description": "zavrzi neshranjene spremembe (samo z dovoljenjem)"},
}, obvezne=("potrdi",), opis="""
Konča spletni FreeCAD (zapre vse dokumente in strežnik). Samo na izrecno zahtevo uporabnika; z neshranjenimi
dokumenti le z zavrzi_spremembe.""")
def t_izhod(a):
    if a.get("potrdi") is not True:
        raise Napaka("Izhod potrebuje potrdi: true (le na izrecno zahtevo uporabnika).")
    try:
        neshranjeni = [d["oznaka"] for d in json.loads(S.STANJE.projekti()).get("odprti", []) if d.get("spremenjen")]
    except ValueError:
        neshranjeni = []
    if neshranjeni and not a.get("zavrzi_spremembe"):
        raise Napaka("Neshranjeni dokumenti: %s. Shrani jih (`shrani`) ali ponovi z zavrzi_spremembe: true (le z "
                     "dovoljenjem uporabnika)." % ", ".join(neshranjeni))
    S.STANJE.vrsta.put(("izhod", {}, None))
    return "FreeCAD se končuje%s. Znova ga zažene `zazeni`." % (
        (" (zavrženo: " + ", ".join(neshranjeni) + ")") if neshranjeni else "")
