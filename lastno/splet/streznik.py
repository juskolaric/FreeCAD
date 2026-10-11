# -*- coding: utf-8 -*-
"""Spletni pogled FreeCAD-a: FreeCAD je motor, prikaz in ukazi so v brskalniku.

Zagon (v oknu ali brez okna):
    FreeCAD.exe lastno/splet/streznik.py          (ali ZAZENI-SPLET.bat v tej mapi)
    FreeCADCmd.exe lastno/splet/streznik.py       (brez okna: samo prikaz, brez izbire in ukazov)
    v Python konzoli FreeCAD-a: exec(open(r"...\\lastno\\splet\\streznik.py", encoding="utf-8").read())
Nato v brskalniku: http://127.0.0.1:3020/    (vrata: okoljska spremenljivka SPLET_VRATA)

Zgradba:
  - HTTP strežnik teče v svoji niti in FreeCAD-ovega API-ja NIKOLI ne kliče sam. Bere le
    pripravljene posnetke (bajti JSON), zahteve iz brskalnika pa odloži v vrsto.
  - Glavna nit (časovnik v oknu ali zanka brez okna) obdela vrsto, ob spremembi dokumenta
    znova zgradi posnetek geometrije, vsakih 500 ms preveri stanje ukazov (na voljo ali ne),
    aktivno delovno okolje in urejanje skice ter odjemalcem pošlje dogodke (Server-Sent Events).
  - Izbira: klik v brskalniku -> POST /select -> Gui.Selection -> opazovalec izbire -> dogodek
    "izbira" -> brskalnik obarva ploskev ali rob. Vir resnice je FreeCAD.
  - Ukazi: seznam ukazov (GET /ukazi) nastane iz orodnih vrstic delovnih okolij Snovanje delov,
    Skica in Del (prevedena imena, namigi, ikone, podukazi skupin). Klik v brskalniku
    -> POST /ukaz -> Gui.runCommand na glavni niti.
  - Obrazci: okno FreeCAD-a se ne pokaže. Vsako novo okno (pogovor, sporočilo, izbira datoteke) ostane
    nevidno, podokno Opravila je v skritem glavnem oknu; njihovi gradniki gredo v brskalnik kot obrazec
    (dogodek "obrazec"), vrednosti in kliki se vrnejo prek POST /obrazec.
  - Projekti: stranski meni v brskalniku kaže odprte dokumente, datoteke FCStd iz map projektov
    (Oblak/3D modeliranje in SPLET_PROJEKTI) (GET /projekti, dogodek "projekti");
    klik odpre, aktivira ali zapre dokument (POST /projekt).
  - Drevo dokumenta (drevo.py): posnetek /model nosi "drevo" (koreni, vozli kot v FreeCAD-ovem drevesu:
    claimChildren, vidnost, ikona, urejljive lastnosti); POST /drevo {dejanje: vidnost | lastnost | uredi}.
  - Varnost: vsak POST potrebuje žeton (glava X-Zeton), ki nastane ob zagonu in ga pozna le stran.

Dogodki SSE (GET /events): model {verzija}, izbira [...], aktivni {ime: bool}, okolje {delovnaMiza, urejanje},
skica {...}, obrazec {vrsta, kljuc, naslov, vrstice | datoteka} ali null, projekti {odprti, skupine}.
Oblika posnetka geometrije (GET /model): glej _geometrija().
"""

import http.server
import io
import json
import os
import queue
import secrets
import sys
import threading
import time
import traceback
import webbrowser
import xml.etree.ElementTree as ET
import zipfile

import FreeCAD as App

try:
    import FreeCADGui as Gui
    IMA_OKNO = hasattr(Gui, "getMainWindow") and Gui.getMainWindow() is not None
except Exception:  # noqa: BLE001
    Gui = None
    IMA_OKNO = False

VRATA = int(os.environ.get("SPLET_VRATA", "3020"))
TOLERANCA_PLOSKEV = 0.1   # mm, teselacija (najmanj; večji objekti relativno, glej _natancnost)
ODMIK_ROBOV = 0.05        # mm, diskretizacija robov (najmanj)
RELATIVNA_PLOSKEV = 0.0005   # delež diagonale objekta: sestav 2 m -> 1 mm (sicer 190 MB posnetka in 35 s gradnje)
RELATIVNI_ROB = 0.00025
PRORACUN_TOCK = 150000       # na objekt: gostejša mreža (npr. uvožen hladilnik s 4200 ploskvami) se naredi grobje
MIROVANJE_OGREVANJA = 3.0    # s brez zahtev iz brskalnika, preden strežnik vnaprej pripravlja posnetke (Stanje.ogrej)


def _natancnost(oblika):
    """Natančnost mreže glede na velikost objekta: majhni deli 0,1 mm / 0,05 mm, veliki sestavi sorazmerno grobje."""
    try:
        d = oblika.BoundBox.DiagonalLength
    except Exception:  # noqa: BLE001
        d = 0.0
    return max(TOLERANCA_PLOSKEV, d * RELATIVNA_PLOSKEV), max(ODMIK_ROBOV, d * RELATIVNI_ROB)
ODPRI_BRSKALNIK = os.environ.get("SPLET_BRSKALNIK", "1") == "1"
# Okno FreeCAD-a: "skrito" (privzeto; pokaže se le, ko potrebuje vnos) ali "vidno".
OKNO_SKRITO = os.environ.get("SPLET_OKNO", "skrito") != "vidno"
try:
    MAPA = os.path.dirname(os.path.abspath(__file__))
except NameError:
    MAPA = os.path.join(App.getHomePath(), "lastno", "splet")
ZETON = secrets.token_hex(16)
# Mape s projekti (datoteke FCStd) za stranski meni: Oblak/3D modeliranje (od 2026-10-07, prej lastno/modeli v repozitoriju)
# in dodatne mape iz SPLET_PROJEKTI (ločilo ;).
if MAPA not in sys.path:
    sys.path.insert(0, MAPA)
from drevo import drevo_dejanje, drevo_dokumenta  # noqa: E402
from baza import baza_dejanje, v_bazi as _v_bazi, tarca as _tarca_baze, BAZA as MAPA_BAZE  # noqa: E402
import videz  # noqa: E402
from oblak import Oblak, obdelaj_zahtevo as oblak_zahteva  # noqa: E402
import mcp_orodja  # noqa: E402  (orodja za AI prek MCP: GET /mcp/orodja, POST /mcp/orodje; most lastno/mcp)
import pomocnik  # noqa: E402  (pomočnik AI v stranski plošči strani: GET/POST /pomocnik, isti katalog orodij)

MAPA_OBLAK = os.path.join(os.path.expanduser("~"), "Oblak", "3D modeliranje")
MAPE_PROJEKTOV = [os.path.normpath(MAPA_OBLAK)]
MAPE_PROJEKTOV += [os.path.normpath(m.strip()) for m in os.environ.get("SPLET_PROJEKTI", "").split(";") if m.strip()]
GLOBINA_PROJEKTOV = 4        # podmape pod mapo projektov, ki se še pregledajo

# ---------------------------------------------------------------------------
# Tiskanje: nadzorna plošča Tiskaj (3D print/tiskaj, lasten proces na vratih 3021 po Photolandia-Apps/ports.json).
# V brskalniku je zavihek »Tiskanje« (okvir na ploščo), »Natisni« iz drevesa izvozi STEP v njeno vhodno mapo, vrstica
# stanja kaže tiskalnike. Ta strežnik je le posrednik (GET /tiskaj/stanje, nit strežnika) in zaganjalnik (POST
# /tiskaj/zazeni); plošča teče naprej tudi brez FreeCAD-a (MQTT, kamere, vrsta). Prepis: SPLET_TISKAJ_VRATA, SPLET_TISKAJ_MAPA.
TISKAJ_VRATA = int(os.environ.get("SPLET_TISKAJ_VRATA", "3021"))


def _najdi_tiskaj():
    """Mapa plošče Tiskaj: ob repozitoriju FreeCAD (Apps/3D print/tiskaj do selitve, nato 3D tisk/3D print/tiskaj)."""
    prepis = os.environ.get("SPLET_TISKAJ_MAPA", "").strip()
    koren = os.path.normpath(os.path.join(MAPA, "..", ".."))        # repozitorij FreeCAD
    kandidati = [prepis] if prepis else []
    kandidati += [os.path.join(koren, "..", "3D print", "tiskaj"),
                  os.path.join(koren, "..", "3D tisk", "3D print", "tiskaj"),
                  os.path.join(koren, "..", "..", "3D tisk", "3D print", "tiskaj"),
                  os.path.join(koren, "..", "..", "3D print", "tiskaj")]
    for k in kandidati:
        if k and os.path.isfile(os.path.join(k, "streznik.py")):
            return os.path.normpath(k)
    return ""


TISKAJ_MAPA = _najdi_tiskaj()
_TISKAJ_KLJUCAVNICA = threading.Lock()
_TISKAJ_PREDPOMNILNIK = {"cas": 0.0, "stanje": None}
_TISKAJ_ROCNO_KLJUCAVNICA = threading.Lock()
TISKAJ_ROCNO_CAKA = []        # datoteke, izvožene, ko plošča ni tekla: ob njenem zagonu se ji javijo kot ročne


def _tiskaj_klic(metoda, pot, telo=None, cas=3.0):
    """Klic API-ja plošče (nit strežnika, brez FreeCAD API-ja). Vrne (koda, podatki); (0, None), če plošča ne teče."""
    import http.client
    try:
        p = http.client.HTTPConnection("127.0.0.1", TISKAJ_VRATA, timeout=cas)
        glave = {"Content-Type": "application/json"} if telo is not None else {}
        p.request(metoda, pot, body=json.dumps(telo, ensure_ascii=False).encode("utf-8") if telo is not None else None,
                  headers=glave)
        odg = p.getresponse()
        surovo = odg.read()
        p.close()
    except (OSError, http.client.HTTPException):
        return 0, None
    try:
        return odg.status, json.loads(surovo.decode("utf-8") or "null")
    except ValueError:
        return odg.status, None


def tiskaj_stanje(sveze=False):
    """Stanje plošče za vrstico stanja in zavihek Tiskanje (pomnjeno 2 s): teče, naslov, tiskalniki (skrčeno), vrsta."""
    with _TISKAJ_KLJUCAVNICA:
        zdaj = time.monotonic()
        if not sveze and _TISKAJ_PREDPOMNILNIK["stanje"] is not None and zdaj - _TISKAJ_PREDPOMNILNIK["cas"] < 2.0:
            return _TISKAJ_PREDPOMNILNIK["stanje"]
        koda, s = _tiskaj_klic("GET", "/api/stanje", cas=4.0)
        out = {"tece": koda == 200 and isinstance(s, dict), "vrata": TISKAJ_VRATA, "mapa": TISKAJ_MAPA,
               "url": "http://127.0.0.1:%d/" % TISKAJ_VRATA, "tiskalniki": [], "vrsta": None, "vhod_mapa": ""}
        if out["tece"]:
            polja = ("ime", "serijska", "povezan", "faza", "faza_besedilo", "razred", "prost", "napredek",
                     "preostalo_min", "preostalo_besedilo", "datoteka", "miza")
            for t in s.get("tiskalniki") or []:
                vnos = {k: t.get(k) for k in polja}
                vnos["hms"] = len(t.get("hms") or [])
                vnos["caka"] = sum(1 for x in (t.get("vrsta") or []) if x.get("stanje") == "čaka")
                out["tiskalniki"].append(vnos)
            v = s.get("vrsta") or {}
            out["vrsta"] = {"caka": v.get("caka"), "aktivna": v.get("aktivna")}
            out["vhod_mapa"] = str((s.get("mape") or {}).get("vhod") or "")
        _TISKAJ_PREDPOMNILNIK.update(cas=zdaj, stanje=out)
        return out


def _tiskaj_vhod_mapa():
    """Vhodna mapa plošče (kamor gredo STEP za tisk): iz tekoče plošče, sicer iz njenega config.json (privzeto Desktop/STEPI)."""
    s = tiskaj_stanje()
    if s["vhod_mapa"]:
        return s["vhod_mapa"]
    mapa = ""
    if TISKAJ_MAPA:
        try:
            with open(os.path.join(TISKAJ_MAPA, "config.json"), encoding="utf-8") as f:
                mapa = str(json.load(f).get("vhod_mapa") or "")
        except (OSError, ValueError):
            mapa = ""
    return os.path.expanduser(mapa or "~/Desktop/STEPI")


def _tiskaj_oznaci_rocno(datoteke):
    """Plošči javi datoteke, ki jih je izvozil FreeCAD (pripravo vodi uporabnik v oknu Pripravi, ne samodejna priprava).
    Če plošča ne teče, počakajo na njen zagon (_tiskaj_po_zagonu). Vrne True, če je plošča oznako prejela zdaj."""
    with _TISKAJ_ROCNO_KLJUCAVNICA:
        for d in datoteke:
            if d not in TISKAJ_ROCNO_CAKA:
                TISKAJ_ROCNO_CAKA.append(d)
        cakajoce = list(TISKAJ_ROCNO_CAKA)
    if not cakajoce:
        return True
    koda, _ = _tiskaj_klic("POST", "/api/vhod/rocno", {"datoteke": cakajoce})
    if koda != 200:
        return False
    with _TISKAJ_ROCNO_KLJUCAVNICA:
        TISKAJ_ROCNO_CAKA[:] = [d for d in TISKAJ_ROCNO_CAKA if d not in cakajoce]
    return True


MAPA_TISK_OBLIKOVANJA = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "FreeCAD-splet", "tisk")


def tiskaj_datoteka(pot):
    """3D natisni iz Oblikovanja: STL/STEP, ki ga je Blender izvozil v FreeCAD-splet/tisk, prestavi v vhod plošče in ga
    označi za ročno pripravo (okno Pripravi). Nit strežnika, brez FreeCAD API-ja. Druge poti zavrne."""
    import shutil
    pot = os.path.abspath(pot or "")
    if (os.path.normcase(os.path.dirname(pot)) != os.path.normcase(MAPA_TISK_OBLIKOVANJA)
            or os.path.splitext(pot)[1].lower() not in (".stl", ".step", ".stp") or not os.path.isfile(pot)):
        return {"ok": False, "sporocilo": "Datoteka za tisk ni iz Oblikovanja."}
    mapa = _tiskaj_vhod_mapa()
    os.makedirs(mapa, exist_ok=True)
    ime = os.path.basename(pot)
    cilj = os.path.join(mapa, ime)
    shutil.copyfile(pot, cilj + ".delno")      # plošča bere le .step/.stp/.stl: pol zapisane datoteke ne vidi
    os.replace(cilj + ".delno", cilj)
    _log("tiskaj: iz Oblikovanja %s -> %s" % (ime, mapa))
    return {"ok": True, "datoteke": [ime], "mapa": mapa, "plosca": _tiskaj_oznaci_rocno([ime]),
            "sporocilo": "Za tisk poslan »%s«." % os.path.splitext(ime)[0]}


def _tiskaj_python():
    """Python za ploščo: sistemski (kot Nadzorna plosca.bat), ne pixi-jev iz okolja FreeCAD-a (opencv za sito mize)."""
    import glob
    import shutil
    lokalno = os.environ.get("LOCALAPPDATA", "")
    kandidati = [os.path.join(lokalno, "Programs", "Python", "Python311", "pythonw.exe")]
    kandidati += sorted(glob.glob(os.path.join(lokalno, "Programs", "Python", "Python3*", "pythonw.exe")), reverse=True)
    for k in kandidati:
        if os.path.isfile(k):
            return k
    return shutil.which("pythonw") or shutil.which("python") or ""


def tiskaj_zazeni():
    """Zažene ploščo kot samostojen proces (brez okna, brez brskalnika; preživi konec FreeCAD-a). Vrne (ok, sporočilo)."""
    import subprocess
    if tiskaj_stanje(sveze=True)["tece"]:
        return True, "Plošča že teče."
    if not TISKAJ_MAPA:
        return False, "Mape plošče Tiskaj ni (3D print/tiskaj); nastavi SPLET_TISKAJ_MAPA."
    py = _tiskaj_python()
    if not py:
        return False, "Python za ploščo ni najden (pythonw.exe)."
    okolje = {k: v for k, v in os.environ.items() if k not in ("PYTHONHOME", "PYTHONPATH", "PYTHONNOUSERSITE")}
    zastavice = (getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                 | getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        subprocess.Popen([py, "streznik.py", "--brez-brskalnika", "--vrata", str(TISKAJ_VRATA)], cwd=TISKAJ_MAPA, env=okolje,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
                         creationflags=zastavice)
    except OSError as e:
        return False, "Zagon plošče ni uspel: %s" % e
    _log("tiskaj: zaganjam ploščo (%s)" % py)
    threading.Thread(target=_tiskaj_po_zagonu, daemon=True, name="tiskaj-zagon").start()
    return True, "Plošča se zaganja."


def _tiskaj_po_zagonu():
    """Počaka, da plošča odgovori (do 30 s), nato ji javi datoteke, izvožene medtem ko ni tekla."""
    for _ in range(60):
        time.sleep(0.5)
        if tiskaj_stanje(sveze=True)["tece"]:
            _tiskaj_oznaci_rocno([])
            return
    _log("tiskaj: plošča se v 30 s ni oglasila na vratih %d" % TISKAJ_VRATA)


def _ime_datoteke_tiska(oznaka):
    """Ime datoteke STEP iz oznake kosa (brez znakov, ki jih Windows ne dovoli)."""
    ime = "".join("_" if (c in '<>:"/\\|?*' or ord(c) < 32) else c for c in str(oznaka)).strip(" .")
    return (ime[:80] or "Kos")


# ---------------------------------------------------------------------------
# Oblikovanje in render (od 2026-10-10, plan OBLIKOVANJE-PLAN.md, mapa lastno/oblikovanje).
# Oblikovanje je Blender v ozadju (streznik_blender.py, vrata 3030 po Photolandia-Apps/ports.json), v brskalniku zavihek
# »Oblikovanje« kot okvir. Ta strežnik ga le zažene (POST /oblikovanje/zazeni) in vpraša, ali teče (GET /oblikovanje/stanje).
# Render tehničnega modela: posnetek aktivnega dokumenta (isti JSON, ki ga riše brskalnik) gre v ločen proces Blenderja
# (upodabljanje.py, render.py); vse na niti strežnika, brez FreeCAD API-ja. Prepis vrat: SPLET_OBLIKOVANJE_VRATA.
MAPA_OBLIKOVANJA = os.path.normpath(os.path.join(MAPA, "..", "oblikovanje"))
if MAPA_OBLIKOVANJA not in sys.path:
    sys.path.insert(0, MAPA_OBLIKOVANJA)
from upodabljanje import UPODABLJANJE, najdi_blender, _cisto_okolje  # noqa: E402
OBLIKOVANJE_VRATA = int(os.environ.get("SPLET_OBLIKOVANJE_VRATA", "3030"))


def oblikovanje_stanje():
    """Ali Oblikovanje (Blender v ozadju) teče; nit strežnika."""
    import http.client
    stanje = {"tece": False, "vrata": OBLIKOVANJE_VRATA, "blender": najdi_blender() or ""}
    try:
        c = http.client.HTTPConnection("127.0.0.1", OBLIKOVANJE_VRATA, timeout=1.0)
        c.request("GET", "/stanje")
        r = c.getresponse()
        if r.status == 200:
            stanje.update(json.loads(r.read().decode("utf-8")), tece=True)
        c.close()
    except (OSError, ValueError):
        pass
    return stanje


def oblikovanje_zazeni():
    """Zažene Oblikovanje kot samostojen proces Blenderja brez okna (preživi Izhod FreeCAD-a). Vrne (ok, sporočilo)."""
    import subprocess
    if oblikovanje_stanje()["tece"]:
        return True, "Oblikovanje že teče."
    blender = najdi_blender()
    if not blender:
        return False, "Blender ni nameščen (Program Files/Blender Foundation; prepis SPLET_BLENDER)."
    zastavice = (getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                 | getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        subprocess.Popen([blender, "-b", "--factory-startup", "--python", os.path.join(MAPA_OBLIKOVANJA, "streznik_blender.py"),
                          "--", "--vrata", str(OBLIKOVANJE_VRATA)], cwd=MAPA_OBLIKOVANJA, env=_cisto_okolje(),
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
                         creationflags=zastavice)
    except OSError as e:
        return False, "Zagon Blenderja ni uspel: %s" % e
    _log("oblikovanje: zaganjam Blender (%s)" % blender)
    return True, "Oblikovanje se zaganja."


def render_modela(podatki):
    """Render aktivnega dokumenta: posnetek (bajti) + kamera iz brskalnika -> naloga upodabljanja. Slika gre tudi v
    mapo Renderji ob datoteki dokumenta. Nit strežnika."""
    ime, kopija = "Render", None
    try:
        for d in json.loads(STANJE.projekti()).get("odprti", []):
            if d.get("aktiven"):
                ime = d.get("oznaka") or d.get("ime") or ime
                if d.get("pot"):
                    # v bazi standardnih delov mapa s podčrtajem: knjižnica (zgradi_knjiznico) mape _* izpusti
                    kopija = os.path.join(os.path.dirname(d["pot"]), "_Renderji" if _v_bazi(d["pot"]) else "Renderji")
    except ValueError:
        pass
    posnetek = STANJE.posnetek()
    if b'"objekti":[]' in posnetek[:200]:
        return {"ok": False, "sporocilo": "Aktivni dokument nima vidne geometrije."}
    try:
        return {"ok": True, "id": UPODABLJANJE.zacni({"posnetek_bajti": posnetek}, podatki, ime=ime, kopija=kopija)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "sporocilo": str(e)}

# Delovna okolja, katerih ukazi so na voljo v brskalniku (ime, slovenski naslov, če ga FreeCAD nima), v vrstnem redu
# zavihkov. Okolja, ki niso nameščena (npr. dodatek SheetMetal), se preskočijo; nameščena okolja, ki jih ni na seznamu
# (dodatki), pridejo na konec. Ob zagonu se naložijo le ZACETNA_OKOLJA, ostala ob prvem kliku na zavihek (BIM, FEM, CAM
# ... bi zagon podaljšala za več sekund).
DELOVNA_OKOLJA = [
    ("PartDesignWorkbench", "Snovanje delov"),
    ("SketcherWorkbench", "Skica"),
    ("PartWorkbench", "Del"),
    ("AssemblyWorkbench", "Sestav"),
    ("TechDrawWorkbench", "Tehnična risba"),
    ("SMWorkbench", "Pločevina"),
    ("DraftWorkbench", "Osnutek"),
    ("BIMWorkbench", "BIM"),
    ("SurfaceWorkbench", "Ploskve"),
    ("MeshWorkbench", "Mreže"),
    ("PointsWorkbench", "Točke"),
    ("ReverseEngineeringWorkbench", "Povratni inženiring"),
    ("InspectionWorkbench", "Pregled odstopanj"),
    ("FemWorkbench", "MKE"),
    ("CAMWorkbench", "CAM"),
    ("OpenSCADWorkbench", "OpenSCAD"),
    ("SpreadsheetWorkbench", "Preglednica"),
    ("MaterialWorkbench", "Material"),
    ("RobotWorkbench", "Robot"),
    ("CablesWorkbench", "Kabli"),   # dodatek Cables (sargo-devel): žice in kabli, pripeti na sponke kosov
]
ZACETNA_OKOLJA = {"PartDesignWorkbench", "SketcherWorkbench", "PartWorkbench", "SMWorkbench"}
# Zavihki, ki so vedno vidni; ostala okolja so v meniju »Več« (zavihek dobijo, ko so dejavna).
GLAVNI_ZAVIHKI = {"PartDesignWorkbench", "SketcherWorkbench", "PartWorkbench", "AssemblyWorkbench",
                  "TechDrawWorkbench", "SMWorkbench"}
IZPUSCENA_OKOLJA = {"NoneWorkbench", "TestWorkbench"}
# Okolja, pri katerih velja slovenski naslov zgoraj tudi, ko ima FreeCAD svojega: FreeCAD-ov slovenski prevod imena
# okolij pušča v angleščini (»Part Design«, »Sketcher«), dodatek SheetMetal pa prevoda nima; zavihki so tako vsi slovenski.
LASTNI_NASLOVI = {ime for ime, _ in DELOVNA_OKOLJA}
# Splošne orodne vrstice (niso del zavihkov okolij).
SPLOSNE_ORODNE = {"File", "Edit", "Clipboard", "Workbench", "Macro", "View", "Individual Views", "Structure", "Help"}
# Vrstica hitrega dostopa (kot v SolidWorksu zgoraj levo).
HITRI_DOSTOP = ["Std_New", "Std_Open", "Std_Save", "Std_Undo", "Std_Redo", "Std_Refresh",
                "Std_ViewFitAll", "Std_ViewFitSelection", "Std_ViewIsometric"]
# Ikone orodij skice v brskalniku: ime orodja -> imena ikon FreeCAD-a po prednosti (prva, ki obstaja).
IKONE_SKICE = {
    "izberi": ["edit-select-all", "Std_SelectAll"],
    "crta": ["Sketcher_CreatePolyline", "Sketcher_CreateLine"],
    "pravokotnik": ["Sketcher_CreateRectangle"],
    "krog": ["Sketcher_CreateCircle"],
    "tocka": ["Sketcher_CreatePoint"],
    "mera": ["Constraint_Dimension", "Constraint_Length"],
    "gradbena": ["Sketcher_ToggleConstruction"],
    "izbrisi": ["edit-delete", "Std_Delete"],
    "zapri": ["Sketcher_LeaveSketch"],
}


def _log(besedilo):
    App.Console.PrintMessage("[splet] %s\n" % besedilo)


# ---------------------------------------------------------------------------
# Geometrija (samo glavna nit)

def _barve(obj, stevilo_ploskev):
    """Osnovna barva objekta in po želji barve po ploskvah (FreeCAD 1.x: ShapeAppearance)."""
    osnovna = (0.78, 0.78, 0.80)
    po_ploskvah = None
    if not IMA_OKNO or not hasattr(obj, "ViewObject") or obj.ViewObject is None:
        return osnovna, po_ploskvah
    # Povezava (App::Link) kaže barvo povezanega objekta, razen če ima lastno (OverrideMaterial).
    for _ in range(8):
        try:
            cilj = obj.LinkedObject if obj.isDerivedFrom("App::Link") else None
            if cilj is None or cilj is obj:
                break
            vo = obj.ViewObject
            if getattr(vo, "OverrideMaterial", False):
                return tuple(vo.ShapeMaterial.DiffuseColor[:3]), None
            obj = cilj
        except Exception:  # noqa: BLE001
            break
    if not hasattr(obj, "ViewObject") or obj.ViewObject is None:
        return osnovna, po_ploskvah
    vo = obj.ViewObject
    try:
        videz = list(vo.ShapeAppearance)
        if videz:
            osnovna = tuple(videz[0].DiffuseColor[:3])
        if len(videz) == stevilo_ploskev and stevilo_ploskev > 1:
            po_ploskvah = [tuple(m.DiffuseColor[:3]) for m in videz]
        return osnovna, po_ploskvah
    except Exception:  # noqa: BLE001
        pass
    try:
        osnovna = tuple(vo.ShapeColor[:3])
        if len(vo.DiffuseColor) == stevilo_ploskev and stevilo_ploskev > 1:
            po_ploskvah = [tuple(c[:3]) for c in vo.DiffuseColor]
    except Exception:  # noqa: BLE001
        pass
    return osnovna, po_ploskvah


def _videz_dejanje(podatki):
    """POST /videz: {dejanje: seznam} | {dejanje: nastavi, ime, videz} (objekt aktivnega dokumenta; povezava ->
    kos v svoji datoteki, ta ostane neshranjena) | {dejanje: plocevina, shrani} (videz »pločevina« vsem kosom iz
    pločevine, ki jih uporablja aktivni dokument — nerjavna / aluminij po MaterialSW; shrani = shrani spremenjene
    datoteke)."""
    dejanje = podatki.get("dejanje", "seznam")
    if dejanje == "seznam":
        return {"ok": True, "videzi": videz.seznam_videzov()}
    doc = App.ActiveDocument
    if doc is None:
        return {"ok": False, "sporocilo": "Ni odprtega dokumenta."}
    if dejanje == "nastavi":
        obj = doc.getObject(podatki.get("ime", ""))
        if obj is None:
            return {"ok": False, "sporocilo": "Objekta ni."}
        kljuc = podatki.get("videz", "")
        doc.openTransaction("Videz")
        try:
            cilj, _ = videz.nastavi_videz(obj, kljuc)
        finally:
            doc.commitTransaction()
        ime = videz.VIDEZI[kljuc]["ime"] if kljuc in videz.VIDEZI else "privzeti videz"
        kje = "" if cilj.Document is doc else " (v datoteki »%s«, shrani jo)" % cilj.Document.Label
        return {"ok": True, "sporocilo": "»%s«: %s%s" % (cilj.Label, ime, kje)}
    if dejanje == "plocevina":
        kosi = {}
        # vsi dokumenti, ki jih aktivni uporablja (povezave čez datoteke, rekurzivno), in aktivni sam
        obiskani, vrsta = set(), [doc]
        while vrsta:
            d = vrsta.pop()
            if d.Name in obiskani:
                continue
            obiskani.add(d.Name)
            for o in d.Objects:
                if o.isDerivedFrom("App::Link"):
                    cilj = o.getLinkedObject(True)
                    if cilj is not None and cilj.Document.Name not in obiskani:
                        vrsta.append(cilj.Document)
                elif "Vrsta" in o.PropertiesList or "Debelina" in o.PropertiesList:
                    if not o.Name.startswith(("Razgrnitev", "DXF")) and videz.je_plocevina(o):
                        kosi[(d.Name, o.Name)] = o
        spremenjeni = []
        for o in kosi.values():
            videz.nastavi_videz(o, videz.videz_plocevine(o))
            if o.Document not in spremenjeni:
                spremenjeni.append(o.Document)
        shranjenih = 0
        if podatki.get("shrani"):
            STANJE.tiho_shranjevanje = True
            try:
                for d in spremenjeni:
                    if d.FileName:
                        d.save()
                        shranjenih += 1
                        if IMA_OKNO:
                            Gui.getDocument(d.Name).Modified = False
            finally:
                STANJE.tiho_shranjevanje = False
        return {"ok": True, "kosi": sorted(o.Label for o in kosi.values()),
                "sporocilo": "Videz pločevine: %d kosov v %d datotekah%s." % (
                    len(kosi), len(spremenjeni), ", shranjeno" if shranjenih else " (neshranjeno)")}
    return {"ok": False, "sporocilo": "Neznano dejanje: %s" % dejanje}


def _je_izhodisce(obj):
    """Izhodišče telesa (osi, ravnine, koordinatni sistem) in podobni pomožni objekti."""
    for tip in ("App::Origin", "App::OriginFeature", "App::Plane", "App::Line", "App::Point",
                "App::LocalCoordinateSystem", "App::DatumElement", "PartDesign::CoordinateSystem"):
        try:
            if obj.isDerivedFrom(tip):
                return True
        except Exception:  # noqa: BLE001
            pass
    return "Origin" in obj.TypeId


def _objekt_v_urejanju(doc):
    """Ime objekta, ki ga FreeCAD trenutno ureja (predogled značilnosti), sicer ''."""
    if not IMA_OKNO:
        return ""
    try:
        vp = Gui.getDocument(doc.Name).getInEdit()
        return vp.Object.Name if vp is not None else ""
    except Exception:  # noqa: BLE001
        return ""


def _v_skritem_vsebniku(obj):
    """Ali je objekt v skritem telesu ali App::Part (tudi posredno)."""
    vsebnik = obj.getParentGeoFeatureGroup() if hasattr(obj, "getParentGeoFeatureGroup") else None
    for _ in range(20):
        if vsebnik is None:
            return False
        if not vsebnik.Visibility:
            return True
        vsebnik = vsebnik.getParentGeoFeatureGroup()
    return False


def _vrsta_objekta(obj):
    """sestav / pločevina / standardni / lastni (iz lastnosti Vrsta, ki jo zapišejo skripte prenosa, sicer po tipu)."""
    v = str(getattr(obj, "Vrsta", "") or "").lower()
    if obj.TypeId == "Assembly::AssemblyObject" or "sestav" in v:
        return "standardni sestav" if "standardni" in v else "sestav"
    if "standardni" in v:
        return "standardni"
    if "pločevina" in v:
        return "pločevina"
    return "del"


def _zgradba_dokumenta(doc, globina=0, pot=()):
    """Drevo sestava: vozel {ime, oznaka, dokument, pot, vrsta, kolicina, skrito, otroci}. Otroci so povezave
    (App::Link) v sestavu, enaki (isti cilj) združeni s količino; sledi povezavam v druge datoteke."""
    asm = next((o for o in doc.Objects if o.TypeId == "Assembly::AssemblyObject"), None)
    koren = asm or next((o for o in doc.Objects if "Izvor" in o.PropertiesList and not o.Name.startswith("Razgrnitev")), None)
    vozel = {"oznaka": doc.Label, "dokument": doc.Name, "pot": doc.FileName,
             "vrsta": _vrsta_objekta(koren) if koren is not None else ("sestav" if asm else "del"), "otroci": []}
    if asm is None or globina > 12 or doc.Name in pot:
        return vozel
    skupine = {}
    for o in asm.Group if hasattr(asm, "Group") else []:
        if o.TypeId != "App::Link":
            continue
        cilj = o.LinkedObject[0] if isinstance(o.LinkedObject, tuple) else o.LinkedObject
        if cilj is None:
            continue
        k = cilj.Document.Name + "#" + cilj.Name
        if k not in skupine:
            otrok = _zgradba_dokumenta(cilj.Document, globina + 1, pot + (doc.Name,))
            otrok.update({"kolicina": 0, "skrito": True, "primerki": []})
            skupine[k] = otrok
            vozel["otroci"].append(otrok)
        skupine[k]["kolicina"] += max(1, int(getattr(o, "ElementCount", 0) or 0))   # vrsta kosov (npr. spone)
        skupine[k]["primerki"].append(o.Label)
        if o.Visibility:
            skupine[k]["skrito"] = False
    vozel["otroci"].sort(key=lambda v: (0 if "sestav" in v["vrsta"] else 1, v["oznaka"].lower()))
    return vozel


def _vidni_objekti(doc):
    v_urejanju = _objekt_v_urejanju(doc)
    for obj in doc.Objects:
        if not hasattr(obj, "Shape"):
            continue
        if STANJE.skica and obj.Name == STANJE.skica:
            continue  # skico, ki se ureja v brskalniku, brskalnik riše sam
        if obj.isDerivedFrom("PartDesign::Body") or obj.isDerivedFrom("App::Part"):
            continue  # vsebnika prikazujemo prek njunih vidnih elementov
        if obj.isDerivedFrom("App::DocumentObjectGroup"):
            continue  # skupina nima lastne geometrije (Shape je le sestav otrok, ki so v posnetku vsak zase)
        if _je_izhodisce(obj):
            continue  # osi in ravnine izhodišča (neskončne pomožne oblike)
        try:
            # Med urejanjem značilnosti (npr. Izboklina z odprtim oknom) je objekt v FreeCAD-u
            # viden kot predogled, čeprav je Visibility še False; pokažemo ga tudi tukaj.
            if not obj.Visibility and obj.Name != v_urejanju:
                continue
            # kot v FreeCAD-u: skrit vsebnik (telo, App::Part) skrije vse v njem, tudi vidno značilnost (konico telesa)
            if obj.Name != v_urejanju and _v_skritem_vsebniku(obj):
                continue
        except Exception:  # noqa: BLE001
            pass
        try:
            if obj.Shape.isNull():
                continue
        except Exception:  # noqa: BLE001
            continue
        yield obj


def _z3(v):
    return (round(v.x, 3), round(v.y, 3), round(v.z, 3))


def _geometrija(obj, faktor=1.0):
    """Posnetek enega objekta: teselirane ploskve (Face{i+1}) in diskretizirani robovi (Edge{j+1}).

    Oblike ne kopiramo: kopija izgubi že izračunano mrežo (BRepMesh) in se teselira znova (3-4x počasneje).
    Teseliramo izvirno obliko in točke po potrebi prestavimo iz lege oblike v globalno lego objekta
    (povezava App::Link vrne obliko povezanega objekta brez lastne lege)."""
    oblika = obj.Shape
    try:
        globalna = obj.getGlobalPlacement()
    except Exception:  # noqa: BLE001
        globalna = oblika.Placement
    premik = globalna.multiply(oblika.Placement.inverse())
    pretvori = None if premik.isIdentity(1e-9) else premik.multVec

    tocke, trikotniki, ploskve = [], [], []
    toleranca, odmik_robov = _natancnost(oblika)
    toleranca *= faktor
    # barva in PBR (kovinskost, hrapavost, zrnatost) po ploskvah; pri sestavu po kosih (videz.py)
    osnovna, po_ploskvah = videz.ploskve_videza(obj, oblika.countElement("Face"), _barve)
    # grobejša mreža velikih objektov: obstoječo finejšo mrežo je treba pobrisati (OCC jo sicer ohrani)
    pobrisi = toleranca > TOLERANCA_PLOSKEV + 1e-9
    try:
        # Vse ploskve naenkrat: OCC jih mreži vzporedno (BRepMesh_IncrementalMesh, isInParallel), branje po
        # ploskvah spodaj mrežo le prebere. Mreženje ploskev eno po eno je teklo na enem jedru (2x počasneje).
        skupaj, _ = oblika.tessellate(toleranca, pobrisi)
        pobrisi = False
        if len(skupaj) > PRORACUN_TOCK and faktor < 30:
            return _geometrija(obj, faktor * 3)   # proračun presežen že brez podvojenih točk na robovih
        del skupaj
    except Exception:  # noqa: BLE001
        pass
    for i, ploskev in enumerate(oblika.Faces):
        try:
            v, t = ploskev.tessellate(toleranca, pobrisi)
            if len(tocke) // 3 + len(v) > PRORACUN_TOCK and faktor < 30:
                # proračun presežen: celoten objekt znova, trikrat grobje (obstoječa mreža se pobriše)
                return _geometrija(obj, faktor * 3)
        except Exception:  # noqa: BLE001
            v, t = [], []
        zacetek_tock = len(tocke) // 3
        zacetek_trik = len(trikotniki) // 3
        if pretvori is None:
            for p in v:
                tocke.extend(_z3(p))
        else:
            for p in v:
                tocke.extend(_z3(pretvori(p)))
        for a, b, c in t:
            trikotniki.extend((a + zacetek_tock, b + zacetek_tock, c + zacetek_tock))
        barva = po_ploskvah[i] if po_ploskvah else osnovna
        ploskve.append([zacetek_tock, len(v), zacetek_trik, len(t)] + [round(c, 3) for c in barva[:7]])

    rob_tocke, robovi, rob_info = [], [], []
    for rob in oblika.Edges:
        try:
            pts = rob.discretize(Deflection=odmik_robov)
        except Exception:  # noqa: BLE001
            pts = [v.Point for v in rob.Vertexes]
        if pretvori is not None:
            pts = [pretvori(p) for p in pts]
        zacetek = len(rob_tocke) // 6
        for a, b in zip(pts, pts[1:]):
            rob_tocke.extend(_z3(a))
            rob_tocke.extend(_z3(b))
        robovi.append([zacetek, max(len(pts) - 1, 0)])
        rob_info.append(_rob_info(rob, pretvori))

    return {
        "ime": obj.Name,
        "oznaka": obj.Label,
        "tocke": tocke,
        "trikotniki": trikotniki,
        "ploskve": ploskve,
        "robTocke": rob_tocke,
        "robovi": robovi,
        "robInfo": rob_info,
    }


# Predpomnilnik posnetkov objektov: (ime dokumenta, ime objekta) -> (ključ, posnetek). Ključ zajame vse, od
# česar je posnetek odvisen (oblika, lega, barve, oznaka); ob preklopu dokumenta ali ponovnem izračunu se
# teselirajo le objekti, ki so se res spremenili. Brez tega je preklop na sobo trajal >10 s.
_PREDPOMNILNIK = {}


def _lega_kljuc(pl):
    b, q = pl.Base, pl.Rotation.Q
    return (round(b.x, 6), round(b.y, 6), round(b.z, 6),
            round(q[0], 9), round(q[1], 9), round(q[2], 9), round(q[3], 9))


def _kljuc_oblike(obj, globina=0):
    """Stabilen ključ oblike objekta. `Shape.hashCode()` je stabilen le pri objektih z lastno obliko
    (Part::Feature, PartDesign); povezava (App::Link) in skupina ob vsakem dostopu zgradita novo obliko,
    zato ključ sestavimo iz povezanega objekta oz. otrok."""
    if globina > 8:
        return ("?", id(obj))
    try:
        povezan = obj.getLinkedObject(True)
    except Exception:  # noqa: BLE001
        povezan = obj
    if povezan is not None and povezan is not obj:
        return ("L", _kljuc_oblike(povezan, globina + 1), _lega_kljuc(obj.Placement) if hasattr(obj, "Placement") else None)
    if obj.isDerivedFrom("App::DocumentObjectGroup"):
        return ("G", tuple(_kljuc_oblike(o, globina + 1) for o in obj.Group))
    if obj.isDerivedFrom("App::Part"):   # tudi Assembly: oblika je sestav otrok, ob vsakem branju nova (hashCode ni stabilen)
        return ("P", tuple(_kljuc_oblike(o, globina + 1) for o in obj.Group if hasattr(o, "Shape")),
                _lega_kljuc(obj.Placement))
    oblika = obj.Shape
    return (oblika.hashCode(), _lega_kljuc(oblika.Placement))


def _geometrija_kljuc(obj):
    oblika = obj.Shape
    try:
        globalna = obj.getGlobalPlacement()
    except Exception:  # noqa: BLE001
        globalna = oblika.Placement
    barve = videz.kljuc_videza(obj, _barve)   # videz vseh kosov (pri sestavu tudi kosov v drugih datotekah)
    return (_kljuc_oblike(obj), _lega_kljuc(oblika.Placement), _lega_kljuc(globalna), obj.Label, barve)


def _geometrija_predpomnjena(doc, obj):
    """Posnetek objekta kot JSON niz iz predpomnilnika, če se ni nič spremenilo; sicer ga zgradi in shrani.
    Vrne (json, zadetek). Hranimo že serializiran JSON, ker je serializacija celega posnetka (več MB) stala
    skoraj pol sekunde na vsako gradnjo."""
    kljuc = _geometrija_kljuc(obj)
    vnos = _PREDPOMNILNIK.get((doc.Name, obj.Name))
    if vnos is not None and vnos[0] == kljuc:
        return vnos[1], True
    posnetek = json.dumps(_geometrija(obj), separators=(",", ":"))
    _PREDPOMNILNIK[(doc.Name, obj.Name)] = (kljuc, posnetek)
    return posnetek, False


def _pozabi_geometrijo(ime_dokumenta, ime_objekta=None):
    for k in [k for k in _PREDPOMNILNIK if k[0] == ime_dokumenta and (ime_objekta is None or k[1] == ime_objekta)]:
        del _PREDPOMNILNIK[k]


# Reference spojev (mate): (dokument, objekt, podpot) -> (ključ oblike, {elementi, tocke}). Iskanje ploskve v
# obliki povezave na podsestav (več tisoč ploskev) traja do 0,3 s, izbira pa se javi večkrat zapored.
_REFERENCE_SPOJEV = {}


def _element_v_obliki(oblika, el):
    """Ime elementa (FaceN, EdgeN) v `oblika`, ki je isti kot `el` iz podpoti spoja (oba v istem koordinatnem
    sistemu: `obj.getSubObject(pot)` in `obj.Shape`). Isti TShape (isPartner) ima lahko več primerkov istega kosa
    v podsestavu; med njimi odloči lega."""
    vrsta = el.ShapeType
    if vrsta not in ("Face", "Edge"):
        return None
    seznam = oblika.Faces if vrsta == "Face" else oblika.Edges
    kandidati = [i for i, x in enumerate(seznam) if x.isPartner(el)]
    if not kandidati:   # rezerva: geometrijsko (težišče in velikost)
        try:
            mera = el.Area if vrsta == "Face" else el.Length
            kandidati = [i for i, x in enumerate(seznam)
                         if abs((x.Area if vrsta == "Face" else x.Length) - mera) <= 1e-6 * max(mera, 1.0)]
        except Exception:  # noqa: BLE001
            return None
    if not kandidati:
        return None
    if len(kandidati) > 1:
        tezisce = el.CenterOfMass
        kandidati.sort(key=lambda i: (seznam[i].CenterOfMass - tezisce).Length)
    return vrsta + str(kandidati[0] + 1)


def _reference_spoja(spoj):
    """Elementi na kosih, ki jih povezuje spoj sestava (Assembly Joint): za vsako referenco
    {objekt, elementi, tocke}. Objekt je objekt dokumenta, ki je v posnetku (povezava na kos ali podsestav),
    element je indeks ploskve ali roba v njegovem posnetku; točke (oglišča) so v svetovnih koordinatah.
    Togi spoj s tlemi (GroundedJoint) označi cel kos."""
    doc = spoj.Document
    if hasattr(spoj, "ObjectToGround"):
        obj = spoj.ObjectToGround
        return [{"objekt": obj.Name, "elementi": [], "tocke": []}] if obj is not None else []
    if not (hasattr(spoj, "Reference1") and hasattr(spoj, "JointType")):
        return None
    izid = []
    for lastnost in ("Reference1", "Reference2"):
        try:
            obj, poti = getattr(spoj, lastnost) or (None, [])
        except Exception:  # noqa: BLE001
            obj, poti = None, []
        if obj is None or not poti:
            continue
        kljuc = (doc.Name, obj.Name, tuple(poti))
        try:
            kljuc_oblike = _kljuc_oblike(obj)
        except Exception:  # noqa: BLE001
            kljuc_oblike = None
        vnos = _REFERENCE_SPOJEV.get(kljuc)
        if vnos is not None and vnos[0] == kljuc_oblike:
            izid.append(dict(vnos[1], objekt=obj.Name))
            continue
        elementi, tocke = [], []
        try:
            oblika = obj.Shape
            globalna = obj.getGlobalPlacement() if hasattr(obj, "getGlobalPlacement") else oblika.Placement
            premik = globalna.multiply(oblika.Placement.inverse())
            for pot in dict.fromkeys(poti):   # element in oglišče sta lahko isti podpoti
                el = obj.getSubObject(pot)
                if el is None or el.isNull():
                    continue
                if el.ShapeType == "Vertex":
                    tocke.append(list(_z3(premik.multVec(el.Point))))
                    continue
                ime = _element_v_obliki(oblika, el)
                if ime and ime not in elementi:
                    elementi.append(ime)
        except Exception as e:  # noqa: BLE001
            App.Console.PrintWarning(f"splet: reference spoja {spoj.Name}: {e}\n")
        podatki = {"elementi": elementi, "tocke": tocke}
        _REFERENCE_SPOJEV[kljuc] = (kljuc_oblike, podatki)
        izid.append(dict(podatki, objekt=obj.Name))
    return izid


def _rob_info(rob, pretvori=None):
    """Analitični podatki roba za pripenjanje v skici (kot v SolidWorksu): krajišči, razpolovišče,
    pri krogih središče, polmer in os. Vse v svetovnih koordinatah (`pretvori` prestavi točke iz lege oblike)."""
    try:
        info = {"tip": type(rob.Curve).__name__}
    except Exception:  # noqa: BLE001
        info = {"tip": ""}  # npr. rob brez krivulje (TypeError: undefined curve type); objekt ostane v posnetku
    t = pretvori if pretvori is not None else (lambda p: p)
    try:
        if rob.Vertexes:
            info["p1"] = _z3(t(rob.Vertexes[0].Point))
            info["p2"] = _z3(t(rob.Vertexes[-1].Point))
        info["sredina"] = _z3(t(rob.valueAt((rob.FirstParameter + rob.LastParameter) / 2.0)))
        info["zaprt"] = bool(rob.isClosed())
        if info["tip"] == "Circle":
            info["sredisce"] = _z3(t(rob.Curve.Center))
            info["r"] = round(rob.Curve.Radius, 4)
            os_ = rob.Curve.Axis
            if pretvori is not None:
                os_ = pretvori(os_) - pretvori(App.Vector(0, 0, 0))
            info["os"] = _z3(os_)
    except Exception:  # noqa: BLE001
        pass
    return info


# ---------------------------------------------------------------------------
# Ukazi (samo glavna nit, samo z oknom)

_IKONE = {}


def _ikona_uri(ikona, kljuc):
    """QIcon (ali funkcija, ki ga vrne) -> PNG kot data URI (64 px), z medpomnilnikom po ključu."""
    if kljuc in _IKONE:
        return _IKONE[kljuc]
    uri = ""
    try:
        from PySide6 import QtCore
        if callable(ikona):
            ikona = ikona()
        if ikona is not None and not ikona.isNull():
            pm = ikona.pixmap(64, 64)
            ba = QtCore.QByteArray()
            buf = QtCore.QBuffer(ba)
            buf.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
            pm.save(buf, "PNG")
            buf.close()
            uri = "data:image/png;base64," + bytes(ba.toBase64().data()).decode("ascii")
    except Exception:  # noqa: BLE001
        uri = ""
    _IKONE[kljuc] = uri
    return uri


def _ikone_skice():
    """Ikone orodij skice (data URI) iz FreeCAD-ovih virov; manjkajoče ostanejo prazne."""
    ikone = {}
    for orodje, imena in IKONE_SKICE.items():
        uri = ""
        for ime in imena:
            try:
                ikona = Gui.getIcon(ime)
            except Exception:  # noqa: BLE001
                ikona = None
            if ikona is not None and not ikona.isNull():
                uri = _ikona_uri(ikona, "skica:" + ime)
                if uri:
                    break
        ikone[orodje] = uri
    return ikone


def _besedilo(qt_besedilo):
    b = (qt_besedilo or "").replace("&", "").strip()
    while b.endswith("...") or b.endswith("…"):
        b = b[:-1] if b.endswith("…") else b[:-3]
        b = b.strip()
    return b


def _ukaz(ime, akcija_orodne):
    """Opis ukaza za brskalnik: prevedeno ime, namig (HTML), ikona, stanje, podukazi skupine."""
    cmd = Gui.Command.get(ime)
    if cmd is None:
        return None
    try:
        seznam = cmd.getAction()
    except Exception:  # noqa: BLE001
        seznam = []
    if not isinstance(seznam, list):
        seznam = [seznam] if seznam else []
    glavna = akcija_orodne or (seznam[0] if seznam else None)
    if glavna is None:
        return None
    info = cmd.getInfo()
    try:
        aktiven = bool(cmd.isActive())
    except Exception:  # noqa: BLE001
        aktiven = False
    u = {
        "ime": ime,
        "naslov": _besedilo(glavna.text()) or info.get("menuText", ime),
        "namig": glavna.toolTip() or info.get("toolTip", ""),
        "ikona": _ikona_uri(glavna.icon(), ime),
        "aktiven": aktiven,
        "podukazi": [],
    }
    if len(seznam) > 1:
        u["podukazi"] = [
            {"indeks": i, "naslov": _besedilo(a.text()), "namig": a.toolTip(), "ikona": _ikona_uri(a.icon(), "%s#%d" % (ime, i))}
            for i, a in enumerate(seznam)
        ]
    return u


def _naslov_okolja(ime, privzeto):
    """Prevedeno ime delovnega okolja iz dejanj izbirnika, sicer privzeto."""
    if ime in LASTNI_NASLOVI:
        return privzeto
    try:
        for a in Gui.Command.get("Std_Workbench").getAction():
            if a.objectName() == ime or a.data() == ime:
                return _besedilo(a.text()) or privzeto
    except Exception:  # noqa: BLE001
        pass
    return privzeto


def _vsa_okolja():
    """Nameščena delovna okolja (ime, privzeti naslov): najprej po DELOVNA_OKOLJA, nato ostala (dodatki)."""
    namescena = Gui.listWorkbenches()
    znana = {ime for ime, _ in DELOVNA_OKOLJA}
    okolja = [(ime, naslov) for ime, naslov in DELOVNA_OKOLJA if ime in namescena]
    for ime, wb in sorted(namescena.items()):
        if ime not in znana and ime not in IZPUSCENA_OKOLJA:
            okolja.append((ime, str(getattr(wb, "MenuText", "") or ime)))
    return okolja


def _okolje_nalozeno(ime):
    """Okolje je naloženo, ko je bilo vsaj enkrat dejavno: šele takrat nastane C++ okolje (__Workbench__)
    z orodnimi vrsticami; prej getToolbarItems ne vrne ničesar."""
    try:
        return hasattr(Gui.getWorkbench(ime), "__Workbench__")
    except Exception:  # noqa: BLE001
        return False


def nalozena_okolja():
    return frozenset(ime for ime, _ in _vsa_okolja() if _okolje_nalozeno(ime))


# Ukazi iz menijev okolja (ime okolja -> [(naslov menija, [[ime ukaza, ...], ...])]). Nekateri ukazi so samo v meniju
# (Inspection nima orodne vrstice), zato dobijo v traku svojo skupino. Menijska vrstica se zgradi ob preklopu okolja,
# zato se zajame takrat, ko je okolje dejavno (ob zagonu in v preveri_okolje).
MENIJI_OKOLIJ = {}


def _zajemi_menije(ime_okolja):
    """Zapomni si ukaze iz menijev dejavnega okolja; splošni meniji (Datoteka, Uredi ...) imajo le ukaze Std_."""
    mw = Gui.getMainWindow()
    meniji = []

    def zberi(meni, skupine, globina=0):
        for a in meni.actions():
            if a.isSeparator() or (a.menu() is not None and globina < 3):
                if skupine[-1]:
                    skupine.append([])
                if a.menu() is not None:
                    zberi(a.menu(), skupine, globina + 1)
                    if skupine[-1]:
                        skupine.append([])
                continue
            d = a.data()
            if isinstance(d, str) and d and not d.startswith("Std_") and Gui.Command.get(d) is not None:
                if all(d not in s for s in skupine):
                    skupine[-1].append(d)

    try:
        for a in mw.menuBar().actions():
            # Meni Pomoč (Start_Start ...) ni orodje; njegov objectName je »&Help« ne glede na jezik.
            if a.menu() is None or a.menu().objectName().replace("&", "") == "Help":
                continue
            skupine = [[]]
            zberi(a.menu(), skupine)
            skupine = [s for s in skupine if s]
            if skupine:
                meniji.append((_besedilo(a.text()), skupine))
    except Exception:  # noqa: BLE001
        _log("menijev okolja %s ni bilo mogoče prebrati: %s" % (ime_okolja, traceback.format_exc()))
    MENIJI_OKOLIJ[ime_okolja] = meniji


def _orodne_iz_menijev(ime_okolja, orodne, imena_ukazov):
    """Ukazi iz menijev okolja, ki jih ni na njegovih orodnih vrsticah (tudi ne kot del skupine), kot dodatne
    orodne vrstice »<meni> (meni)« na koncu traku."""
    na_orodnih = set()
    napisi = set()   # podukazi Python skupin (Part_CompJoinFeatures ...) imena ukaza ne nosijo, le napis
    for o in orodne:
        for s in o["skupine"]:
            for u in s:
                na_orodnih.add(u["ime"])
                napisi.add(u["naslov"])
                for p in u["podukazi"]:
                    napisi.add(p["naslov"])
    dodatne = []
    for naslov, skupine_imen in MENIJI_OKOLIJ.get(ime_okolja, []):
        skupine = []
        for s in skupine_imen:
            ukazi = []
            for ime_ukaza in s:
                if ime_ukaza in na_orodnih:
                    continue
                u = _ukaz(ime_ukaza, None)
                if u and u["naslov"] not in napisi:
                    ukazi.append(u)
                    na_orodnih.add(ime_ukaza)
                    napisi.add(u["naslov"])
                    imena_ukazov.append(ime_ukaza)
            if ukazi:
                skupine.append(ukazi)
        if skupine:
            dodatne.append({"ime": "meni:" + naslov, "naslov": naslov + " (meni)", "skupine": skupine, "meni": True})
    return dodatne


def zgradi_ukaze():
    """Seznam ukazov po delovnih okoljih in orodnih vrsticah (skupine ločene z ločili).
    Nenaložena okolja so v seznamu brez orodnih vrstic (nalozeno: false); naloži jih klik na zavihek."""
    from PySide6 import QtWidgets
    mw = Gui.getMainWindow()
    okolja = []
    imena_ukazov = []
    for ime, privzeti_naslov in _vsa_okolja():
        if not _okolje_nalozeno(ime):
            okolja.append({"ime": ime, "naslov": _naslov_okolja(ime, privzeti_naslov), "orodneVrstice": [],
                           "nalozeno": False, "glavno": ime in GLAVNI_ZAVIHKI})
            continue
        wb = Gui.getWorkbench(ime)
        try:
            predmeti = wb.getToolbarItems()
        except Exception:  # noqa: BLE001
            predmeti = {}
        try:
            vrstni_red = wb.listToolbars()
        except Exception:  # noqa: BLE001
            vrstni_red = list(predmeti.keys())
        orodne = []
        for ime_orodne in vrstni_red:
            if ime_orodne in SPLOSNE_ORODNE:
                continue
            tb = mw.findChild(QtWidgets.QToolBar, ime_orodne)
            naslov = tb.windowTitle() if tb else ime_orodne
            akcije = {}
            if tb:
                for a in tb.actions():
                    d = a.data()
                    if isinstance(d, str) and d:
                        akcije[d] = a
            skupine = [[]]
            for ime_ukaza in predmeti.get(ime_orodne, []):
                if ime_ukaza == "Separator":
                    if skupine[-1]:
                        skupine.append([])
                    continue
                u = _ukaz(ime_ukaza, akcije.get(ime_ukaza))
                if u:
                    skupine[-1].append(u)
                    imena_ukazov.append(ime_ukaza)
            skupine = [s for s in skupine if s]
            if skupine:
                orodne.append({"ime": ime_orodne, "naslov": naslov, "skupine": skupine})
        orodne += _orodne_iz_menijev(ime, orodne, imena_ukazov)
        okolja.append({"ime": ime, "naslov": _naslov_okolja(ime, privzeti_naslov), "orodneVrstice": orodne,
                       "nalozeno": True, "glavno": ime in GLAVNI_ZAVIHKI})
    hitri = []
    for ime_ukaza in HITRI_DOSTOP:
        u = _ukaz(ime_ukaza, None)
        if u:
            hitri.append(u)
            imena_ukazov.append(ime_ukaza)
    return {"delovnaOkolja": okolja, "hitriDostop": hitri, "skica": _ikone_skice()}, sorted(set(imena_ukazov))


def _sprozi_ukaz(ime, indeks):
    """Sproži ukaz tako kot klik na gumb v orodni vrstici: prek Qt-jeve vrste dogodkov, brez
    Python okvirja na skladu. Če ukaz odpre modalno okno, to ne zadrži GIL-a in strežnik
    med njim naprej odgovarja (z Gui.runCommand bi vse niti Pythona obstale)."""
    from PySide6 import QtCore
    cmd = Gui.Command.get(ime)
    akcije = []
    if cmd is not None:
        try:
            akcije = cmd.getAction()
        except Exception:  # noqa: BLE001
            akcije = []
        if not isinstance(akcije, list):
            akcije = [akcije] if akcije else []
    if akcije:
        akcija = akcije[indeks] if 0 <= indeks < len(akcije) else akcije[0]
        # Pri skritem oknu FreeCAD ne osvežuje omogočenosti dejanj (MainWindow::_updateActions
        # teče le, ko je okno vidno), zato bi trigger na onemogočenem dejanju (npr. ukaz, ki
        # zahteva izbiro) ostal brez učinka. Naredimo isto kot Command::testActive za ta ukaz.
        try:
            if not akcija.isEnabled() and cmd.isActive():
                akcija.setEnabled(True)
        except Exception:  # noqa: BLE001
            pass
        QtCore.QMetaObject.invokeMethod(akcija, "trigger", QtCore.Qt.ConnectionType.QueuedConnection)
    else:
        Gui.runCommand(ime, indeks)


def _pokazi_okno():
    """Pokaže okno FreeCAD-a (in morebitno modalno okno) in ga postavi v ospredje ali vsaj utripne v opravilni vrstici."""
    from PySide6 import QtWidgets
    mw = Gui.getMainWindow()
    if not mw.isVisible() or mw.isMinimized():
        mw.showNormal()
    mw.raise_()
    mw.activateWindow()
    modalno = QtWidgets.QApplication.activeModalWidget()
    if modalno is not None:
        modalno.raise_()
        modalno.activateWindow()
    QtWidgets.QApplication.alert(mw, 0)


def _skrij_okno():
    """Skrije okno FreeCAD-a; program teče naprej in streže brskalniku."""
    mw = Gui.getMainWindow()
    if mw.isVisible():
        mw.hide()


def _nalozi_okolja():
    """Aktivira začetna delovna okolja, da nastanejo njihovi ukazi in orodne vrstice (ostala ob prvem kliku)."""
    aktivno = Gui.activeWorkbench().name()
    for ime, _ in DELOVNA_OKOLJA:
        if ime in ZACETNA_OKOLJA and ime in Gui.listWorkbenches():
            try:
                Gui.activateWorkbench(ime)
                _zajemi_menije(ime)
            except Exception:  # noqa: BLE001
                _log("okolja %s ni bilo mogoče naložiti: %s" % (ime, traceback.format_exc()))
    cilj = "PartDesignWorkbench" if "PartDesignWorkbench" in Gui.listWorkbenches() else aktivno
    try:
        Gui.activateWorkbench(cilj)
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# Obrazci: okna FreeCAD-a (pogovorna okna, opravila v podoknu Opravila, izbira datotek) se ne
# pokažejo na zaslonu, ampak se njihovi gradniki preberejo in pošljejo brskalniku, ki jih izriše
# kot obrazec. Spremembe iz brskalnika se vpišejo nazaj v prave gradnike Qt (samo glavna nit).

def _veljaven(w):
    try:
        import shiboken6
        return w is not None and shiboken6.isValid(w)
    except Exception:  # noqa: BLE001
        return w is not None


def _razred(w):
    try:
        return w.metaObject().className()
    except Exception:  # noqa: BLE001
        return ""


def _navadno(besedilo):
    """Besedilo gradnika brez HTML oznak (QLabel, QMessageBox znata obogateno besedilo)."""
    import re
    b = besedilo or ""
    if "<" in b and ">" in b:
        try:
            from PySide6 import QtGui
            d = QtGui.QTextDocument()
            d.setHtml(b)
            b = d.toPlainText()
        except Exception:  # noqa: BLE001
            b = re.sub(r"<[^>]+>", "", b)
    return b.replace("&&", "\x00").replace("&", "").replace("\x00", "&").strip()


def _nevidno_okno(w):
    """Okno ostane odprto (modalna zanka teče), a ga na zaslonu ni: prosojno in zunaj zaslona.
    Skriti ga ne smemo, ker bi QDialog.hide() končal pogovor. Tudi fokusa tipkovnice ne sme
    prevzeti: sicer bi tipke (npr. Enter), namenjene drugemu programu, potrdile nevidno okno."""
    from PySide6 import QtCore
    try:
        w.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        if w.windowHandle() is not None:
            w.windowHandle().setFlag(QtCore.Qt.WindowType.WindowDoesNotAcceptFocus, True)
        w.setWindowOpacity(0.0)
        w.move(-32000, -32000)
    except Exception:  # noqa: BLE001
        pass


def _vidno_okno(w):
    """Vrne okno, skrito z _nevidno_okno, na zaslon (na sredino glavnega okna)."""
    from PySide6 import QtCore
    try:
        w.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        if w.windowHandle() is not None:
            w.windowHandle().setFlag(QtCore.Qt.WindowType.WindowDoesNotAcceptFocus, False)
        w.setWindowOpacity(1.0)
        mw = Gui.getMainWindow()
        sredina = mw.frameGeometry().center()
        w.move(sredina.x() - w.width() // 2, sredina.y() - w.height() // 2)
        w.raise_()
        w.activateWindow()
    except Exception:  # noqa: BLE001
        pass


_TASK_VIEW = [None]


def _task_view():
    """Gradnik podokna Opravila (Gui::TaskView::TaskView) v glavnem oknu."""
    tv = _TASK_VIEW[0]
    if _veljaven(tv):
        return tv
    from PySide6 import QtWidgets
    mw = Gui.getMainWindow()
    for w in QtWidgets.QApplication.allWidgets():
        if _razred(w) == "Gui::TaskView::TaskView" and mw.isAncestorOf(w):
            _TASK_VIEW[0] = w
            return w
    return None


class Zajem:
    """Prebere drevo gradnikov okna v JSON (vrstice po postavitvi) in si zapomni id -> gradnik."""
    PRESKOCI = ("QScrollBar", "QSizeGrip", "QRubberBand", "QSplitterHandle", "QMenu", "QFocusFrame")

    def __init__(self, koren):
        from PySide6 import QtWidgets
        self.W = QtWidgets
        self.koren = koren
        self.mapa = {}

    def _id(self, w, dodatno=None):
        i = len(self.mapa) + 1
        self.mapa[i] = (w, dodatno)
        return i

    def _vidno(self, w):
        try:
            return w is self.koren or w.isVisibleTo(self.koren)
        except Exception:  # noqa: BLE001
            return False

    # -- postavitev: seznam vrstic, vrstica je seznam gradnikov ali ("stolpec", [vrstice]) --
    def vrstice_gradnika(self, w):
        vrstice, videni = [], set()
        lay = w.layout()
        if lay is not None:
            self._iz_postavitve(lay, vrstice, videni)
        for c in w.children():
            if isinstance(c, self.W.QWidget) and not c.isWindow() and id(c) not in videni:
                vrstice.append([c])
        return vrstice

    def _vodoravna(self, lay):
        return isinstance(lay, self.W.QBoxLayout) and lay.direction() in (
            self.W.QBoxLayout.Direction.LeftToRight, self.W.QBoxLayout.Direction.RightToLeft)

    def _iz_postavitve(self, lay, vrstice, videni):
        W = self.W
        if isinstance(lay, W.QGridLayout):
            po_vrsticah = {}
            for k in range(lay.count()):
                r, c, _, _ = lay.getItemPosition(k)
                po_vrsticah.setdefault(r, []).append((c, lay.itemAt(k)))
            for r in sorted(po_vrsticah):
                vrsta = []
                for _, it in sorted(po_vrsticah[r], key=lambda x: x[0]):
                    self._predmet(it, vrsta, videni)
                if vrsta:
                    vrstice.append(vrsta)
        elif isinstance(lay, W.QFormLayout):
            for r in range(lay.rowCount()):
                vrsta = []
                for vloga in (W.QFormLayout.ItemRole.LabelRole, W.QFormLayout.ItemRole.FieldRole,
                              W.QFormLayout.ItemRole.SpanningRole):
                    it = lay.itemAt(r, vloga)
                    if it is not None:
                        self._predmet(it, vrsta, videni)
                if vrsta:
                    vrstice.append(vrsta)
        elif self._vodoravna(lay):
            vrsta = []
            for k in range(lay.count()):
                self._predmet(lay.itemAt(k), vrsta, videni)
            if vrsta:
                vrstice.append(vrsta)
        else:
            for k in range(lay.count()):
                vrsta = []
                self._predmet(lay.itemAt(k), vrsta, videni)
                if vrsta:
                    vrstice.append(vrsta)

    def _predmet(self, it, vrsta, videni):
        if it is None:
            return
        w = it.widget()
        if w is not None:
            videni.add(id(w))
            vrsta.append(w)
            return
        l = it.layout()
        if l is None:
            return
        if self._vodoravna(l):
            for k in range(l.count()):
                self._predmet(l.itemAt(k), vrsta, videni)
        else:
            pod = []
            self._iz_postavitve(l, pod, videni)
            if len(pod) == 1:
                vrsta.extend(pod[0])
            elif pod:
                vrsta.append(("stolpec", pod))

    def json_vrstic(self, vrstice):
        izhod = []
        for vrsta in vrstice:
            elementi = []
            for w in vrsta:
                if isinstance(w, tuple):
                    pod = self.json_vrstic(w[1])
                    if pod:
                        elementi.append({"tip": "stolpec", "vrstice": pod})
                    continue
                e = self.gradnik(w)
                if e is None:
                    continue
                # Skupina brez naslova je le postavitev: njene vrstice gredo na isto raven.
                if e.get("tip") == "skupina" and not e.get("naslov") and not e.get("preklopna") and len(vrsta) == 1:
                    izhod.extend(e["vrstice"])
                    elementi = None
                    break
                elementi.append(e)
            if elementi:
                izhod.append(elementi)
        return izhod

    # -- posamezni gradniki --
    def gradnik(self, w):
        W = self.W
        if not isinstance(w, W.QWidget) or not self._vidno(w):
            return None
        razred = _razred(w)
        if razred in self.PRESKOCI or isinstance(w, (W.QScrollBar, W.QMenu)):
            return None
        omogoceno = w.isEnabled()
        e = None
        if "TaskHeader" in razred:
            naslov = " ".join(_navadno(b.text()) for b in w.findChildren(W.QToolButton) if b.text())
            return {"tip": "naslov", "besedilo": naslov} if naslov else None
        if razred == "QSint::ActionLabel":
            return {"tip": "naslov", "besedilo": _navadno(w.text())} if w.text() else None
        if isinstance(w, W.QLabel):
            t = _navadno(w.text())
            return {"tip": "oznaka", "besedilo": t, "omogoceno": omogoceno} if t else None
        if isinstance(w, W.QAbstractSpinBox):
            e = {"tip": "vnos", "id": self._id(w), "vrednost": w.text(), "stevilo": True,
                 "samoBranje": w.isReadOnly()}
        elif isinstance(w, W.QLineEdit):
            e = {"tip": "vnos", "id": self._id(w), "vrednost": w.text(), "samoBranje": w.isReadOnly(),
                 "geslo": w.echoMode() != W.QLineEdit.EchoMode.Normal, "namig": w.placeholderText()}
        elif isinstance(w, W.QComboBox):
            e = {"tip": "izbira", "id": self._id(w), "moznosti": [w.itemText(k) for k in range(w.count())],
                 "indeks": w.currentIndex(), "urejljivo": w.isEditable(), "vrednost": w.currentText()}
        elif isinstance(w, (W.QCheckBox, W.QRadioButton)):
            e = {"tip": "kljukica", "id": self._id(w), "besedilo": _navadno(w.text()), "izbrano": w.isChecked(),
                 "radio": isinstance(w, W.QRadioButton)}
        elif isinstance(w, W.QAbstractButton):
            besedilo = _navadno(w.text())
            ikona = ""
            if not besedilo:
                try:
                    ikona = _ikona_uri(w.icon(), "gumb:%d" % w.icon().cacheKey())
                except Exception:  # noqa: BLE001
                    ikona = ""
            if not besedilo and not ikona:
                return None
            e = {"tip": "gumb", "id": self._id(w), "besedilo": besedilo, "ikona": ikona,
                 "namig": _navadno(w.toolTip()), "preklopni": w.isCheckable(), "izbrano": w.isChecked(),
                 "privzet": bool(isinstance(w, W.QPushButton) and w.isDefault())}
        elif isinstance(w, W.QAbstractSlider) and not isinstance(w, W.QScrollBar):
            e = {"tip": "drsnik", "id": self._id(w), "min": w.minimum(), "max": w.maximum(), "vrednost": w.value()}
        elif isinstance(w, W.QProgressBar):
            e = {"tip": "napredek", "min": w.minimum(), "max": w.maximum(), "vrednost": w.value()}
        elif isinstance(w, (W.QTextEdit, W.QPlainTextEdit)):
            e = {"tip": "besedilo", "id": self._id(w), "vrednost": w.toPlainText(), "samoBranje": w.isReadOnly()}
        elif isinstance(w, W.QAbstractItemView):
            e = self._seznam(w)
        elif isinstance(w, W.QTabWidget):
            tabs = {"tip": "zavihki", "id": self._id(w), "zavihki": [_navadno(w.tabText(k)) for k in range(w.count())],
                    "indeks": w.currentIndex(), "omogoceno": omogoceno}
            stran = w.currentWidget()
            vsebina = self.json_vrstic(self.vrstice_gradnika(stran)) if stran is not None else []
            return {"tip": "skupina", "naslov": "", "vrstice": [[tabs]] + vsebina}
        elif isinstance(w, W.QScrollArea):
            notranji = w.widget()
            return self.gradnik(notranji) if notranji is not None else None
        elif isinstance(w, W.QGroupBox):
            vrstice = self.json_vrstic(self.vrstice_gradnika(w))
            e = {"tip": "skupina", "naslov": _navadno(w.title()), "vrstice": vrstice}
            if w.isCheckable():
                e.update({"id": self._id(w), "preklopna": True, "izbrano": w.isChecked()})
        else:
            vrstice = self.json_vrstic(self.vrstice_gradnika(w))
            if not vrstice:
                return None
            e = {"tip": "skupina", "naslov": "", "vrstice": vrstice}
        if e is not None:
            e["omogoceno"] = omogoceno
            if "namig" not in e and w.toolTip():
                e["namig"] = _navadno(w.toolTip())
        return e

    def _seznam(self, w):
        from PySide6 import QtCore
        model = w.model()
        if model is None:
            return None
        izbrani = set()
        try:
            for ix in w.selectionModel().selectedIndexes():
                izbrani.add((ix.row(), ix.parent().row(), ix.parent().column()))
        except Exception:  # noqa: BLE001
            pass
        vrstice, indeksi = [], []
        # QAbstractListModel (npr. seznam robov v opravilu Zaokrožitev) ima en stolpec; njegov columnCount je v PySide
        # zaseben (TypeError z argumentom ali brez), zato ga ne kličemo.
        if isinstance(model, QtCore.QAbstractListModel):
            stolpcev = 1
        else:
            stolpcev = min(model.columnCount(QtCore.QModelIndex()), 4)

        def obisci(stars, globina):
            for r in range(model.rowCount(stars)):
                if len(vrstice) >= 300:
                    return
                ix = model.index(r, 0, stars)
                deli = []
                for c in range(max(stolpcev, 1)):
                    d = model.data(model.index(r, c, stars), QtCore.Qt.ItemDataRole.DisplayRole)
                    if d not in (None, ""):
                        deli.append(str(d))
                vrstice.append({"besedilo": " · ".join(deli), "globina": globina,
                                "izbrano": (r, stars.row(), stars.column()) in izbrani})
                indeksi.append(QtCore.QPersistentModelIndex(ix))
                if isinstance(w, self.W.QTreeView) and w.isExpanded(ix):
                    obisci(ix, globina + 1)

        obisci(QtCore.QModelIndex(), 0)
        return {"tip": "seznam", "id": self._id(w, indeksi), "vrstice": vrstice}


def _datotecni_obrazec(w):
    """Posebni obrazec za QFileDialog: mapa, vsebina mape, filter, ime datoteke."""
    import fnmatch
    import re
    from PySide6 import QtCore, QtWidgets
    mapa = w.directory().absolutePath()
    filtri = list(w.nameFilters())
    filter_ = w.selectedNameFilter()
    vzorci = []
    for skupina in re.findall(r"\(([^)]*)\)", filter_ or ""):
        vzorci.extend(v.lower() for v in skupina.split())
    if not vzorci or "*" in vzorci or "*.*" in vzorci:
        vzorci = []
    vnosi = []
    try:
        with os.scandir(mapa) as it:
            for d in it:
                if d.name.startswith("."):
                    continue
                try:
                    je_mapa = d.is_dir()
                except OSError:
                    continue
                if not je_mapa and vzorci and not any(fnmatch.fnmatch(d.name.lower(), v) for v in vzorci):
                    continue
                vnosi.append({"ime": d.name, "mapa": je_mapa})
    except OSError:
        pass
    vnosi.sort(key=lambda v: (not v["mapa"], v["ime"].lower()))
    ime = ""
    vnos = w.findChild(QtWidgets.QLineEdit, "fileNameEdit")
    if vnos is not None:
        ime = vnos.text()
    return {
        "vrsta": "datoteka", "naslov": w.windowTitle() or "Datoteka", "mapa": mapa,
        "vnosi": vnosi[:800], "filtri": filtri, "filter": filter_, "ime": ime,
        "shrani": w.acceptMode() == QtWidgets.QFileDialog.AcceptMode.AcceptSave,
        "samoMape": w.fileMode() == QtWidgets.QFileDialog.FileMode.Directory,
        "pogoni": [QtCore.QDir.toNativeSeparators(d.absolutePath()) for d in QtCore.QDir.drives()],
        "domov": QtCore.QDir.homePath(),
    }


_STEVEC_OKEN = [0]


def _kljuc_okna(koren):
    """Enolična oznaka okna za brskalnik. Naslov Python ovoja (id) se pri naslednjem oknu iste vrste lahko ponovi
    (npr. dve vprašanji QMessageBox drugo za drugim), zato bi klik, namenjen prvemu, zadel drugega: okno dobi svojo
    številko kot dinamično lastnost Qt, ki živi s C++ objektom."""
    n = koren.property("_spletOkno")
    if not n:
        _STEVEC_OKEN[0] += 1
        n = _STEVEC_OKEN[0]
        koren.setProperty("_spletOkno", n)
    return "%s:%d" % (_razred(koren), int(n))


def _zajemi_obrazec(stanje):
    """Poišče okno, ki čaka na uporabnika, in vrne (json, mapa id -> gradnik) ali (None, {})."""
    from PySide6 import QtWidgets
    koren = QtWidgets.QApplication.activeModalWidget()
    vrsta = "pogovor"
    if koren is None:
        for w in reversed(stanje.skrita_okna):
            if _veljaven(w) and w.isVisible():
                koren = w
                break
    if koren is None:
        try:
            opravilo = bool(Gui.Control.activeDialog())
        except Exception:  # noqa: BLE001
            opravilo = False
        if opravilo:
            koren = _task_view()
            vrsta = "opravilo"
    if koren is None:
        return None, {}
    kljuc = _kljuc_okna(koren)
    if isinstance(koren, QtWidgets.QFileDialog):
        obr = _datotecni_obrazec(koren)
        obr["kljuc"] = kljuc
        return obr, {0: (koren, None)}
    zajem = Zajem(koren)
    vrstice = zajem.json_vrstic(zajem.vrstice_gradnika(koren))
    naslov = koren.windowTitle() if vrsta == "pogovor" else ""
    if vrsta == "opravilo":
        try:
            vp = Gui.ActiveDocument.getInEdit() if Gui.ActiveDocument else None
            if vp is not None:
                naslov = vp.Object.Label
        except Exception:  # noqa: BLE001
            pass
    return {"vrsta": vrsta, "kljuc": kljuc, "naslov": naslov or "FreeCAD", "vrstice": vrstice}, zajem.mapa


def _v_vrsto(w, metoda):
    """Pokliče režo gradnika prek Qt-jeve vrste dogodkov (npr. klik, ki odpre modalno okno,
    ne sme teči s Pythonom na skladu: drugače strežniške niti obstanejo)."""
    from PySide6 import QtCore
    QtCore.QMetaObject.invokeMethod(w, metoda, QtCore.Qt.ConnectionType.QueuedConnection)


def _obrazec_se_caka(stanje, kljuc):
    """Okno z oznako `kljuc` je še vedno tisto, ki čaka na uporabnika (zajem obrazca je lahko star do 250 ms)."""
    from PySide6 import QtWidgets
    modal = QtWidgets.QApplication.activeModalWidget()
    if modal is None:
        return True   # nemodalno okno ali podokno Opravila: zajem ga je našel, modalnega nad njim ni
    return _veljaven(modal) and _kljuc_okna(modal) == kljuc


def _obrazec_dejanje(mapa, podatki):
    """Vpiše spremembo iz brskalnika v gradnik Qt."""
    from PySide6 import QtCore, QtWidgets as W
    dejanje = podatki.get("dejanje", "")
    vrednost = podatki.get("vrednost")
    par = mapa.get(int(podatki.get("id", -1) or 0)) if dejanje not in ("mapa", "datoteka", "filter", "preklici") \
        else mapa.get(0)
    if par is None:
        _log("obrazec: gradnik %s ne obstaja več" % podatki.get("id"))
        return
    w, dodatno = par
    if not _veljaven(w):
        return
    if isinstance(w, W.QFileDialog):
        if dejanje == "mapa":
            w.setDirectory(str(vrednost))
        elif dejanje == "filter":
            w.selectNameFilter(str(vrednost))
        elif dejanje == "datoteka":
            w.selectFile(str(vrednost))
            _v_vrsto(w, "accept")
        elif dejanje == "preklici":
            _v_vrsto(w, "reject")
        return
    if dejanje == "vnos":
        besedilo = "" if vrednost is None else str(vrednost)
        if isinstance(w, W.QDoubleSpinBox):
            try:
                w.setValue(float(besedilo.replace(",", ".").split()[0]))
            except (ValueError, IndexError):
                pass
        elif isinstance(w, W.QSpinBox):
            try:
                w.setValue(int(float(besedilo.replace(",", ".").split()[0])))
            except (ValueError, IndexError):
                pass
        elif isinstance(w, W.QAbstractSpinBox):
            # Gui::QuantitySpinBox ipd.: besedilo z enoto ali izrazom gre skozi njihov razčlenjevalnik.
            vnos = w.findChild(W.QLineEdit)
            if vnos is not None:
                vnos.setText(besedilo)
            w.interpretText()
        elif isinstance(w, W.QLineEdit):
            w.setText(besedilo)
        try:
            w.editingFinished.emit()
        except Exception:  # noqa: BLE001
            pass
    elif dejanje == "izbira" and isinstance(w, W.QComboBox):
        if isinstance(vrednost, int) and 0 <= vrednost < w.count():
            w.setCurrentIndex(vrednost)
            try:
                w.activated.emit(vrednost)
            except Exception:  # noqa: BLE001
                pass
        elif w.isEditable():
            w.setEditText(str(vrednost))
    elif dejanje == "kljukica":
        if isinstance(w, W.QGroupBox):
            w.setChecked(bool(vrednost))
        elif w.isChecked() != bool(vrednost):
            _v_vrsto(w, "click")
    elif dejanje == "klik":
        _v_vrsto(w, "click")
    elif dejanje == "drsnik":
        w.setValue(int(vrednost))
    elif dejanje == "besedilo":
        w.setPlainText(str(vrednost or ""))
    elif dejanje == "zavihek":
        w.setCurrentIndex(int(vrednost))
    elif dejanje in ("vrstica", "dvoklik") and dodatno is not None:
        k = int(vrednost)
        if 0 <= k < len(dodatno) and dodatno[k].isValid():
            ix = w.model().index(dodatno[k].row(), dodatno[k].column(), dodatno[k].parent())
            w.setCurrentIndex(ix)
            sm = w.selectionModel()
            if sm is not None:
                sm.select(ix, QtCore.QItemSelectionModel.SelectionFlag.ClearAndSelect
                          | QtCore.QItemSelectionModel.SelectionFlag.Rows)
            try:
                w.clicked.emit(ix)
                if dejanje == "dvoklik":
                    w.doubleClicked.emit(ix)
                    w.activated.emit(ix)
            except Exception:  # noqa: BLE001
                pass


# ---------------------------------------------------------------------------
# Skica v brskalniku: geometrijo in omejitve urejamo prek Python API-ja skice, reševalnik
# je FreeCAD-ov; FreeCAD-ov lastni način urejanja skice (okno) pri tem ni potreben.

def _v2(v):
    return [round(v.x, 4), round(v.y, 4)]


def _geo_json(i, g, gradbena):
    tip = type(g).__name__
    e = {"id": i, "tip": tip, "gradbena": gradbena}
    if tip == "LineSegment":
        e["p1"], e["p2"] = _v2(g.StartPoint), _v2(g.EndPoint)
    elif tip == "Circle":
        e["sredisce"], e["r"] = _v2(g.Center), round(g.Radius, 4)
    elif tip == "ArcOfCircle":
        e["sredisce"], e["r"] = _v2(g.Center), round(g.Radius, 4)
        e["p1"], e["p2"] = _v2(g.StartPoint), _v2(g.EndPoint)
        e["kot1"], e["kot2"] = round(g.FirstParameter, 6), round(g.LastParameter, 6)
    elif tip == "Point":
        e["p"] = [round(g.X, 4), round(g.Y, 4)]
    else:
        try:
            e["tocke"] = [_v2(p) for p in g.toShape().discretize(Deflection=0.05)]
        except Exception:  # noqa: BLE001
            e["tocke"] = []
    return e


def _posnetek_skice(sk, novi=None):
    """Geometrija in omejitve skice v koordinatah skice ter lega skice v prostoru."""
    geometrija = []
    for i, g in enumerate(sk.Geometry):
        try:
            gradbena = bool(sk.getConstruction(i))
        except Exception:  # noqa: BLE001
            gradbena = bool(getattr(g, "Construction", False))
        geometrija.append(_geo_json(i, g, gradbena))
    # Zunanja geometrija (robovi modela, projicirani v ravnino skice): GeoId -3, -4, ...; prva dva sta osi.
    zunanji = []
    try:
        sklici = [[o.Name, sub] for o, subs in sk.ExternalGeometry for sub in subs]
        for k, g in enumerate(list(sk.ExternalGeo)[2:]):
            e = _geo_json(-3 - k, g, True)
            e["sklic"] = sklici[k] if k < len(sklici) else None
            zunanji.append(e)
    except Exception:  # noqa: BLE001
        pass
    omejitve = []
    for i, c in enumerate(sk.Constraints):
        omejitve.append({
            "id": i, "tip": c.Type, "prvi": c.First, "prviPoz": c.FirstPos,
            "drugi": c.Second, "drugiPoz": c.SecondPos, "vrednost": round(c.Value, 4),
            "ime": c.Name, "gonilna": bool(c.Driving),
            # lega kote kot v FreeCAD-u (SoDatumLabel): odmik kotirne črte, premik napisa (pri polmeru kot vodila)
            "razmik": round(float(c.LabelDistance), 4), "polozaj": round(float(c.LabelPosition), 4),
        })
    try:
        pl = sk.getGlobalPlacement()
    except Exception:  # noqa: BLE001
        pl = sk.Placement
    q = pl.Rotation.Q
    try:
        resitev = int(sk.solve())
    except Exception:  # noqa: BLE001
        resitev = -99
    try:
        dolocena = bool(sk.FullyConstrained)   # posodobi ga solve() zgoraj
    except Exception:  # noqa: BLE001
        dolocena = False
    return {
        "ime": sk.Name, "oznaka": sk.Label,
        "polozaj": {"osnova": [round(pl.Base.x, 4), round(pl.Base.y, 4), round(pl.Base.z, 4)],
                    "rotacija": [q[0], q[1], q[2], q[3]]},
        "geometrija": geometrija, "zunanji": zunanji, "omejitve": omejitve, "resitev": resitev, "novi": novi or [],
        "dolocena": dolocena,
    }


def _aktivno_telo(doc):
    try:
        telo = Gui.ActiveDocument.ActiveView.getActiveObject("pdbody")
        if telo is not None and telo.Document.Name == doc.Name:
            return telo
    except Exception:  # noqa: BLE001
        pass
    telesa = [o for o in doc.Objects if o.isDerivedFrom("PartDesign::Body")]
    return telesa[-1] if telesa else None


def _v_telesu(obj):
    try:
        skupina = obj.getParentGeoFeatureGroup()
        return skupina is not None and skupina.isDerivedFrom("PartDesign::Body")
    except Exception:  # noqa: BLE001
        return False


def _nova_skica(podatki):
    """Ustvari skico na ravnini izhodišča ali na izbrani ploskvi; v telesu (Part Design) ali samostojno."""
    doc = App.ActiveDocument or App.newDocument("Neimenovan")
    ploskev = podatki.get("ploskev") or {}
    obj_ploskve = doc.getObject(ploskev.get("objekt", "")) if ploskev.get("objekt") else None
    v_telesu = bool(podatki.get("telo", True))
    if obj_ploskve is not None and not _v_telesu(obj_ploskve):
        v_telesu = False  # ploskev objekta zunaj telesa: samostojna skica (kot v okolju Del)
    odmik = float(podatki.get("odmik", 0) or 0)
    obrni = bool(podatki.get("obrni"))
    ravnina = podatki.get("ravnina", "XY")
    if ravnina not in ("XY", "XZ", "YZ"):
        ravnina = "XY"

    doc.openTransaction("Nova skica")
    telo = None
    if v_telesu:
        telo = _aktivno_telo(doc)
        if telo is None:
            telo = doc.addObject("PartDesign::Body", "Telo")
        try:
            Gui.ActiveDocument.ActiveView.setActiveObject("pdbody", telo)
        except Exception:  # noqa: BLE001
            pass
        sk = telo.newObject("Sketcher::SketchObject", "Skica")
    else:
        sk = doc.addObject("Sketcher::SketchObject", "Skica")

    if obj_ploskve is not None:
        sk.AttachmentSupport = (obj_ploskve, [ploskev.get("element", "")])
        sk.MapMode = "FlatFace"
        sk.MapReversed = obrni
        sk.AttachmentOffset = App.Placement(App.Vector(0, 0, odmik), App.Rotation())
    elif telo is not None:
        osnovne = [f for f in telo.Origin.OriginFeatures if f.Role == ravnina + "_Plane"]
        if osnovne:
            sk.AttachmentSupport = (osnovne[0], [""])
            sk.MapMode = "FlatFace"
            sk.MapReversed = obrni
            sk.AttachmentOffset = App.Placement(App.Vector(0, 0, odmik), App.Rotation())
    else:
        rot = {
            "XY": App.Rotation(0, 0, 0, 1),
            "XZ": App.Rotation(-0.7071068, 0, 0, -0.7071068),
            "YZ": App.Rotation(0.5, 0.5, 0.5, 0.5),
        }[ravnina]
        if obrni:
            rot = rot.multiply(App.Rotation(App.Vector(1, 0, 0), 180))
        normala = rot.multVec(App.Vector(0, 0, 1))
        sk.Placement = App.Placement(normala.multiply(odmik), rot)
    doc.commitTransaction()
    doc.recompute()
    return sk


def _zunanji_geoid(sk, objekt, element):
    """GeoId zunanje geometrije za rob modela; če je še ni, jo doda (addExternal). None, če ni mogoče
    (npr. rob zunaj telesa v Part Designu)."""
    sklici = [(o.Name, sub) for o, subs in sk.ExternalGeometry for sub in subs]
    if (objekt, element) in sklici:
        return -3 - sklici.index((objekt, element))
    try:
        sk.addExternal(objekt, element)
    except Exception as ex:  # noqa: BLE001
        _log("zunanja geometrija %s.%s ni mogoča: %s" % (objekt, element, ex))
        return None
    sklici = [(o.Name, sub) for o, subs in sk.ExternalGeometry for sub in subs]
    if (objekt, element) not in sklici:
        return None
    return -3 - sklici.index((objekt, element))


def _spoji(sk, geo, poz, s):
    """Omejitev točke (geo, poz) na: [id, poz] točko skice, ali {"zunanji": [objekt, element], "poz", "nacin"}
    rob modela. Načini kot v SolidWorksu: Coincident (krajišče/središče), Sredina (razpolovišče, Symmetric),
    NaRobu (PointOnObject). Vrne True, če je bila omejitev dodana."""
    import Sketcher
    if not s:
        return False
    if isinstance(s, dict):
        z = s.get("zunanji") or []
        if len(z) != 2:
            return False
        gid = _zunanji_geoid(sk, str(z[0]), str(z[1]))
        if gid is None:
            return False
        zun = sk.ExternalGeo[-gid - 1] if len(sk.ExternalGeo) >= -gid else None
        tip_zun = type(zun).__name__ if zun is not None else ""
        nacin = s.get("nacin", "Coincident")
        if tip_zun == "Point":
            sk.addConstraint(Sketcher.Constraint("Coincident", geo, poz, gid, 1))
        elif nacin == "Sredina" and tip_zun in ("LineSegment", "ArcOfCircle"):
            sk.addConstraint(Sketcher.Constraint("Symmetric", gid, 1, gid, 2, geo, poz))
        elif nacin == "NaRobu":
            sk.addConstraint(Sketcher.Constraint("PointOnObject", geo, poz, gid))
        else:
            sk.addConstraint(Sketcher.Constraint("Coincident", geo, poz, gid, int(s.get("poz", 1))))
        return True
    sk.addConstraint(Sketcher.Constraint("Coincident", geo, poz, int(s[0]), int(s[1])))
    return True


def _skica_dodaj(sk, op):
    """Doda geometrijo (črta, pravokotnik, krog, točka) s samodejnimi omejitvami; vrne nove indekse."""
    import Part
    import Sketcher
    V = App.Vector
    vrsta = op.get("vrsta")
    gradbena = bool(op.get("gradbena"))
    novi = []
    if vrsta == "crta":
        p1, p2 = op["p1"], op["p2"]
        if abs(p1[0] - p2[0]) < 1e-7 and abs(p1[1] - p2[1]) < 1e-7:
            raise ValueError("črta brez dolžine")
        i = sk.addGeometry(Part.LineSegment(V(p1[0], p1[1], 0), V(p2[0], p2[1], 0)), gradbena)
        novi.append(i)
        for kljuc, poz in (("spoji1", 1), ("spoji2", 2)):
            _spoji(sk, i, poz, op.get(kljuc))
    elif vrsta == "pravokotnik":
        (x1, y1), (x2, y2) = op["p1"], op["p2"]
        if abs(x2 - x1) < 1e-6 or abs(y2 - y1) < 1e-6:
            raise ValueError("pravokotnik brez površine")
        tocke = [V(x1, y1, 0), V(x2, y1, 0), V(x2, y2, 0), V(x1, y2, 0)]
        ids = [sk.addGeometry(Part.LineSegment(tocke[k], tocke[(k + 1) % 4]), gradbena) for k in range(4)]
        for k in range(4):
            sk.addConstraint(Sketcher.Constraint("Coincident", ids[k], 2, ids[(k + 1) % 4], 1))
        sk.addConstraint(Sketcher.Constraint("Horizontal", ids[0]))
        sk.addConstraint(Sketcher.Constraint("Horizontal", ids[2]))
        sk.addConstraint(Sketcher.Constraint("Vertical", ids[1]))
        sk.addConstraint(Sketcher.Constraint("Vertical", ids[3]))
        _spoji(sk, ids[0], 1, op.get("spoji1"))  # prvi ogal (x1, y1)
        _spoji(sk, ids[2], 1, op.get("spoji2"))  # nasprotni ogal (x2, y2)
        novi = ids
    elif vrsta == "krog":
        c, r = op["sredisce"], float(op["r"])
        if r <= 1e-6:
            raise ValueError("krog brez polmera")
        i = sk.addGeometry(Part.Circle(V(c[0], c[1], 0), V(0, 0, 1), r), gradbena)
        novi.append(i)
        _spoji(sk, i, 3, op.get("spoji1"))
    elif vrsta == "tocka":
        p = op["p"]
        i = sk.addGeometry(Part.Point(V(p[0], p[1], 0)), False)
        novi.append(i)
        _spoji(sk, i, 1, op.get("spoji"))
    else:
        raise ValueError("neznana vrsta: %s" % vrsta)
    return novi


def _skica_izvedi(sk, op):
    """Ena sprememba skice znotraj transakcije (deluje Razveljavi); vrne nove indekse geometrije."""
    import Sketcher
    vrsta = op.get("vrsta")
    doc = sk.Document
    doc.openTransaction("Skica: " + str(vrsta))
    novi = []
    try:
        if vrsta in ("crta", "pravokotnik", "krog", "tocka"):
            novi = _skica_dodaj(sk, op)
        elif vrsta == "premakni":
            cilj = App.Vector(float(op["x"]), float(op["y"]), 0)
            try:
                sk.movePoint(int(op["id"]), int(op["poz"]), cilj, False)
            except AttributeError:
                sk.moveGeometry(int(op["id"]), int(op["poz"]), cilj, False)
        elif vrsta == "izbrisi":
            ids = sorted({int(i) for i in op.get("ids", [])}, reverse=True)
            if ids:
                sk.delGeometries(ids)
        elif vrsta == "mera":
            tip, i, vr = op["tip"], int(op["id"]), float(op["vrednost"])
            if tip in ("Radius", "Distance", "Diameter"):
                sk.addConstraint(Sketcher.Constraint(tip, i, vr))
            elif tip in ("DistanceX", "DistanceY"):
                sk.addConstraint(Sketcher.Constraint(tip, i, 1, i, 2, vr))
        elif vrsta == "omejitev":
            tip = op["tip"]
            if tip in ("Horizontal", "Vertical"):
                sk.addConstraint(Sketcher.Constraint(tip, int(op["id"])))
            elif tip == "Coincident":
                a = op["a"]
                _spoji(sk, int(a[0]), int(a[1]), op["b"])
        elif vrsta == "gradbena":
            sk.toggleConstruction(int(op["id"]))
        elif vrsta == "izbrisiOmejitev":
            sk.delConstraint(int(op["id"]))
        elif vrsta == "nastaviMero":
            # obstoječa mera (klik na koto v brskalniku): vrednost v mm, kot v stopinjah
            i, vr = int(op["id"]), float(op["vrednost"])
            if sk.Constraints[i].Type == "Angle":
                import math
                vr = math.radians(vr)
            sk.setDatum(i, vr)
        elif vrsta == "polozajMere":
            # premik kote (vlečenje v brskalniku): LabelDistance in LabelPosition kot v FreeCAD-u; geometrija se ne
            # spremeni, zato brez preračuna (skica in telo se preračunata ob zaprtju skice)
            i = int(op["id"])
            sk.setLabelDistance(i, float(op["razmik"]))
            sk.setLabelPosition(i, float(op["polozaj"]))
        else:
            raise ValueError("neznana vrsta: %s" % vrsta)
        doc.commitTransaction()
    except Exception:
        doc.abortTransaction()
        raise
    if vrsta != "polozajMere":
        doc.recompute()
    return novi


# ---------------------------------------------------------------------------
# Stanje, deljeno med nitmi

# ---------------------------------------------------------------------------
# Projekti: datoteke FCStd v mapah projektov in odprti dokumenti

def _pot(pot):
    return os.path.normpath(pot).replace("\\", "/")


def _ista_pot(a, b):
    return bool(a) and bool(b) and os.path.normcase(os.path.normpath(a)) == os.path.normcase(os.path.normpath(b))


def _vidnost_iz_datoteke(pot):
    """Vidnost objektov (ime -> bool) iz Document.xml datoteke FCStd brez GuiDocument.xml; None, če ga datoteka ima
    ali je ni mogoče prebrati. FreeCAD ob odpiranju skrije vse objekte (Gui::Document::Restore, startRestoring)
    in jih spet pokaže šele iz GuiDocument.xml; datoteke, shranjene brez okna (FreeCADCmd), tega zapisa nimajo,
    zato bi se odprle z vsemi objekti skritimi (prazen pogled)."""
    try:
        with zipfile.ZipFile(pot) as z:
            if "GuiDocument.xml" in z.namelist():
                return None
            koren = ET.fromstring(z.read("Document.xml"))
    except Exception:  # noqa: BLE001
        return None
    vidnost = {}
    for obj in koren.iter("Object"):
        ime = obj.get("name")
        lastnosti = obj.find("Properties")
        if not ime or lastnosti is None:
            continue
        vidnost[ime] = True
        for lastnost in lastnosti.iter("Property"):
            if lastnost.get("name") == "Visibility":
                b = lastnost.find("Bool")
                vidnost[ime] = (b is None) or (b.get("value") == "true")
    return vidnost


def _popravi_vidnost(doc):
    """Po odprtju datoteke brez GuiDocument.xml vrne vidnost objektov, kot je zapisana v Document.xml."""
    if not IMA_OKNO or not doc.FileName:
        return
    vidnost = _vidnost_iz_datoteke(doc.FileName)
    if vidnost is None:
        return
    gdoc = Gui.getDocument(doc.Name)
    spremenjen = gdoc.Modified
    stevilo = 0
    for obj in doc.Objects:
        if vidnost.get(obj.Name, True) and not obj.Visibility:
            vo = gdoc.getObject(obj.Name)
            if vo is not None:
                vo.Visibility = True
            else:
                obj.Visibility = True
            stevilo += 1
    gdoc.Modified = spremenjen
    if stevilo:
        _log("vidnost %d objektov obnovljena (datoteka brez GuiDocument.xml): %s" % (stevilo, doc.FileName))


# Vrsta dokumenta po tipih objektov: "sestav" (Assembly, povezave App::Link na druge kose ali več App::Part),
# "del" (telesa PartDesign ali oblike Part) ali "" (prazen dokument, skice ...). Enako za datoteke (Document.xml v FCStd)
# in odprte dokumente (TypeId), da stran oboje označi enako.
TIPI_TELES = ("PartDesign::Body", "Part::Feature", "Part::Box", "Part::Cylinder", "Part::Cone", "Part::Sphere",
              "Part::Torus", "Part::Cut", "Part::Fuse", "Part::Common", "Part::MultiFuse", "Part::MultiCommon",
              "Part::Extrusion", "Part::Revolution", "Part::Mirroring", "Part::Fillet", "Part::Chamfer", "Part::Loft",
              "Part::Sweep", "Part::Compound", "Part::Prism", "Part::Wedge", "Mesh::Feature")


def _vrsta_iz_tipov(tipi):
    tipi = list(tipi)
    povezav = sum(1 for t in tipi if t in ("App::Link", "App::LinkGroup", "App::LinkElement"))
    delov = sum(1 for t in tipi if t == "App::Part")
    teles = sum(1 for t in tipi if t in TIPI_TELES)
    if any(t.startswith("Assembly::") for t in tipi) or povezav or delov > 1:
        vrsta = "sestav"
    elif teles or delov:
        vrsta = "del"
    else:
        vrsta = ""
    return {"vrsta": vrsta, "teles": teles, "povezav": povezav}


_LASTNOSTI_FCSTD = {}  # (pot, mtime, velikost) -> {vrsta, teles, povezav, slicica}; branje zipa je drago


def _lastnosti_fcstd(pot, st):
    """Vrsta in prisotnost sličice (thumbnails/Thumbnail.png) iz datoteke FCStd; samo datotečni dostop, brez FreeCAD API-ja."""
    kljuc = (os.path.normcase(pot), int(st.st_mtime), st.st_size)
    r = _LASTNOSTI_FCSTD.get(kljuc)
    if r is None:
        r = {"vrsta": "", "teles": 0, "povezav": 0, "slicica": False}
        try:
            with zipfile.ZipFile(pot) as z:
                imena = z.namelist()
                r["slicica"] = "thumbnails/Thumbnail.png" in imena and _uporabna_slicica(z.read("thumbnails/Thumbnail.png"))
                if "Document.xml" in imena:
                    tipi = []
                    # tok zapri izrecno: iterparse ga ne zapre, ZipFile pa datoteko zapre šele, ko so zaprti vsi
                    # tokovi; sicer jo proces drži odprto do pospravljanja smeti in FreeCAD zavrne naslednje
                    # shranjevanje (»file is marked as read-only«, FileInfo::isWritable odpre brez deljenja)
                    with z.open("Document.xml") as tok:
                        for _, e in ET.iterparse(tok):
                            if e.tag == "Object" and e.get("type"):
                                tipi.append(e.get("type"))
                            if e.tag in ("Object", "Property"):
                                e.clear()
                    r.update(_vrsta_iz_tipov(tipi))
        except Exception:  # noqa: BLE001
            _log("lastnosti %s: %s" % (pot, traceback.format_exc().splitlines()[-1]))
        if len(_LASTNOSTI_FCSTD) > 500:
            _LASTNOSTI_FCSTD.clear()
        _LASTNOSTI_FCSTD[kljuc] = r
    return dict(r)


# Sličice modelov (renderji), ki jih izriše stran iz svojega 3D pogleda in pošlje s POST /slicica; shranjene po
# datoteki v %LOCALAPPDATA%/FreeCAD-splet/slicice/<sha1 poti>.png. FreeCAD-ova vgrajena sličica (thumbnails/Thumbnail.png
# v FCStd) je le rezerva in le, če je uporabna: iz skritega okna nastane prazna ali sivo odrezana (_uporabna_slicica).
MAPA_SLICIC = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "FreeCAD-splet", "slicice")


def _uporabna_slicica(png):
    """Ali je FreeCAD-ova vgrajena sličica uporabna: ni prazna in model ni odrezan ob robu slike.

    Ozadje je navpični preliv med barvo zgornjih in spodnjih vogalov (FreeCAD-ovo ozadje je preliv); vsebina so
    piksli, ki od njega očitno odstopajo. Prazna slika ima vsebine skoraj nič, odrezana pa jo ima po robu
    (ali vogali sami niso ozadje, kar prav tako napolni rob). Brez Pillow velja za uporabno, razen prazne.
    Prazna ali neberljiva datoteka ni uporabna: FreeCAD iz skritega okna zapiše Thumbnail.png z 0 bajti, ki je
    prej veljala za sličico, zato stran za take dokumente ni izrisala svoje."""
    if not png or not png.startswith(b"\x89PNG"):
        return False
    try:
        from PIL import Image
    except ImportError:
        return True
    try:
        im = Image.open(io.BytesIO(png)).convert("RGB")
        im.thumbnail((64, 64))
        w, h = im.size
        if w < 4 or h < 4:
            return False
        px = im.load()
        zgoraj = [(a + b) / 2 for a, b in zip(px[0, 0], px[w - 1, 0])]
        spodaj = [(a + b) / 2 for a, b in zip(px[0, h - 1], px[w - 1, h - 1])]

        def vsebina(x, y):
            f = y / (h - 1)
            return max(abs(c - (z + (s - z) * f)) for c, z, s in zip(px[x, y], zgoraj, spodaj)) > 20

        rob = [(x, y) for x in range(w) for y in (0, h - 1)] + [(x, y) for y in range(1, h - 1) for x in (0, w - 1)]
        na_robu = sum(1 for x, y in rob if vsebina(x, y)) / len(rob)
        skupaj = sum(1 for x in range(w) for y in range(h) if vsebina(x, y)) / (w * h)
        return 0.005 < skupaj < 0.85 and na_robu < 0.03
    except Exception:  # noqa: BLE001
        return False


def _pot_slicice(pot):
    import hashlib
    return os.path.join(MAPA_SLICIC, hashlib.sha1(os.path.normcase(os.path.normpath(pot)).encode("utf-8")).hexdigest() + ".png")


_RENDER_OK = {}  # (pot renderja, mtime) -> ali je render uporaben (prazen render se ne upošteva)


def _shranjena_slicica(pot):
    """mtime shranjenega in uporabnega renderja za datoteko ali 0."""
    try:
        r = _pot_slicice(pot)
        mtime = int(os.stat(r).st_mtime)
    except OSError:
        return 0
    ok = _RENDER_OK.get((r, mtime))
    if ok is None:
        try:
            with open(r, "rb") as f:
                ok = _uporabna_slicica(f.read())
        except OSError:
            return 0
        if len(_RENDER_OK) > 500:
            _RENDER_OK.clear()
        _RENDER_OK[(r, mtime)] = ok
    return mtime if ok else 0


def _slicica_fcstd(pot):
    """Bajti PNG sličice: shranjeni render strani, sicer FreeCAD-ova iz FCStd, sicer None (strežniška nit; brez FreeCAD API-ja)."""
    if _shranjena_slicica(pot):
        try:
            with open(_pot_slicice(pot), "rb") as f:
                return f.read()
        except OSError:
            pass
    try:
        with zipfile.ZipFile(pot) as z:
            png = z.read("thumbnails/Thumbnail.png")
        return png if _uporabna_slicica(png) else None
    except Exception:  # noqa: BLE001
        return None


def _shrani_slicico(pot, png):
    os.makedirs(MAPA_SLICIC, exist_ok=True)
    zacasna = _pot_slicice(pot) + ".tmp"
    with open(zacasna, "wb") as f:
        f.write(png)
    os.replace(zacasna, _pot_slicice(pot))


def _datoteka_projekta(pot):
    try:
        st = os.stat(pot)
    except OSError:
        return None
    d = {"ime": os.path.splitext(os.path.basename(pot))[0], "pot": _pot(pot),
         "velikost": st.st_size, "spremenjeno": int(st.st_mtime)}
    d.update(_lastnosti_fcstd(pot, st))
    render = _shranjena_slicica(pot)
    d["slicica"] = d["slicica"] or render > 0
    d["slicicaV"] = max(render, int(st.st_mtime))
    return d


def _projekti_v_mapah():
    skupine = []
    for mapa in MAPE_PROJEKTOV:
        if not os.path.isdir(mapa):
            continue
        datoteke = []
        for koren, podmape, imena in os.walk(mapa):
            globina = 0 if koren == mapa else os.path.relpath(koren, mapa).count(os.sep) + 1
            podmape[:] = sorted(d for d in podmape if not d.startswith((".", "__")) and globina < GLOBINA_PROJEKTOV)
            for ime in sorted(imena, key=str.lower):
                if ime.lower().endswith(".fcstd"):
                    d = _datoteka_projekta(os.path.join(koren, ime))
                    if d is not None:
                        d["projekt"] = "" if koren == mapa else os.path.relpath(koren, mapa).replace("\\", "/")
                        datoteke.append(d)
        skupine.append({"mapa": _pot(mapa), "naslov": os.path.basename(mapa), "datoteke": datoteke})
    return skupine


def _spremenjen(doc):
    """Neshranjene spremembe pozna le dokument na strani Gui (App.Document nima lastnosti Modified)."""
    try:
        return bool(Gui.getDocument(doc.Name).Modified) if IMA_OKNO else False
    except Exception:  # noqa: BLE001
        return False


def zgradi_projekte():
    aktivni = App.ActiveDocument.Name if App.ActiveDocument is not None else ""
    odprti = []
    for d in App.listDocuments().values():
        if getattr(d, "Temporary", False):
            continue
        o = {"ime": d.Name, "oznaka": d.Label, "pot": _pot(d.FileName) if d.FileName else "",
             "spremenjen": _spremenjen(d), "aktiven": d.Name == aktivni, "slicica": False, "spremenjeno": 0, "slicicaV": 0}
        o.update(_vrsta_iz_tipov(x.TypeId for x in d.Objects))
        if d.FileName:
            try:
                # PDM: zaklep datoteke (iz predpomnilnika; ob prvem odprtju se sproži samodejni zaklep v ozadju)
                o["zaklep"] = OBLAK.zaklep_dokumenta(d.FileName)
            except Exception as e:  # noqa: BLE001
                _log("oblak: zaklep za seznam: %r" % e)
            try:
                st = os.stat(d.FileName)
                render = _shranjena_slicica(d.FileName)
                o["spremenjeno"] = int(st.st_mtime)
                o["slicica"] = _lastnosti_fcstd(d.FileName, st)["slicica"] or render > 0
                o["slicicaV"] = max(render, int(st.st_mtime))
            except OSError:
                pass
        odprti.append(o)
    return {"odprti": odprti, "skupine": _projekti_v_mapah()}


# ---------------------------------------------------------------- knjižnica standardnih delov (gumb Knjižnica)
# GET /knjiznica: kosi iz baze po kategorijah (samo datotečni dostop, nit strežnika); POST /knjiznica {dejanje: vstavi,
# pot}: glavna nit kos odpre in ga kot povezavo (App::Link / Assembly::AssemblyLink) doda v sestav aktivnega dokumenta.
MAPE_BAZE_IZPUSCENE = ("DXF",)


def zgradi_knjiznico():
    kategorije = []
    if not os.path.isdir(MAPA_BAZE):
        return {"baza": _pot(MAPA_BAZE), "kategorije": [], "napaka": "Mape baze ni: %s" % MAPA_BAZE}
    for koren, podmape, imena in os.walk(MAPA_BAZE):
        podmape[:] = sorted((d for d in podmape if not d.startswith((".", "_")) and d not in MAPE_BAZE_IZPUSCENE), key=str.lower)
        kosi = []
        for ime in sorted(imena, key=str.lower):
            if ime.lower().endswith(".fcstd"):
                d = _datoteka_projekta(os.path.join(koren, ime))
                if d is not None:
                    kosi.append(d)
        if kosi:
            rel = os.path.relpath(koren, MAPA_BAZE).replace("\\", "/")
            kategorije.append({"ime": "" if rel == "." else rel, "kosi": kosi})
    return {"baza": _pot(MAPA_BAZE), "kategorije": kategorije}


def _knjiznica_dejanje(stanje, podatki):
    dejanje = podatki.get("dejanje", "")
    pot = podatki.get("pot", "")
    if not _v_bazi(pot) or not os.path.isfile(pot):
        return {"ok": False, "sporocilo": "Kosa ni v bazi: %s" % pot}
    if dejanje == "odpri":
        _projekt_dejanje(stanje, {"dejanje": "odpri", "pot": pot})
        return {"ok": True, "sporocilo": "Odprt: %s" % os.path.splitext(os.path.basename(pot))[0]}
    if dejanje != "vstavi":
        return {"ok": False, "sporocilo": "Neznano dejanje: %s" % dejanje}
    # Ciljni dokument je tisti, ki ga brskalnik kaže kot aktivnega (ime v zahtevi), ne App.ActiveDocument: drugo sejo
    # ali skripto, ki medtem preklopi dokument, kos ne sme zadeti.
    ime_doc = podatki.get("dokument", "")   # ime ali oznaka (posnetek /model nosi oznako)
    cilj_doc = App.getDocument(ime_doc) if ime_doc in App.listDocuments() else next(
        (d for d in App.listDocuments().values() if d.Label == ime_doc), None)
    if cilj_doc is None:
        return {"ok": False, "sporocilo": "Dokument »%s« ni odprt: odpri sestav, v katerega naj gre kos." % (ime_doc or "?")}
    if not cilj_doc.FileName:
        return {"ok": False, "sporocilo": "Aktivni dokument »%s« še ni shranjen; povezava na kos iz baze zahteva shranjen sestav." % cilj_doc.Label}
    if _ista_pot(cilj_doc.FileName, pot):
        return {"ok": False, "sporocilo": "Kos ne more vsebovati samega sebe."}
    asm = next((o for o in cilj_doc.Objects if o.TypeId == "Assembly::AssemblyObject"), None)
    doc = next((d for d in App.listDocuments().values() if _ista_pot(d.FileName, pot)), None)
    if doc is None:
        _log("knjižnica: odpiram %s" % pot)
        doc = App.openDocument(pot, True)
    if getattr(doc, "Partial", False):
        doc.restore()
    kos = _tarca_baze(doc)
    if kos is None:
        return {"ok": False, "sporocilo": "»%s« nima glavnega objekta (dela ali sestava)." % doc.Label}
    tip = "Assembly::AssemblyLink" if (asm is not None and kos.TypeId == "Assembly::AssemblyObject") else "App::Link"
    ime = "".join(c if c.isalnum() else "_" for c in kos.Label)[:48] or "Kos"   # newObject z ne-ASCII imenom pade (#12164)
    povezava = asm.newObject(tip, ime) if asm is not None else cilj_doc.addObject(tip, ime)
    povezava.LinkedObject = kos
    povezava.Label = kos.Label
    cilj_doc.recompute()
    App.setActiveDocument(cilj_doc.Name)
    if IMA_OKNO:
        try:
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(cilj_doc.Name, povezava.Name)
        except Exception as e:  # noqa: BLE001
            _log("knjižnica: izbira: %r" % e)
    kam = ("v sestav »%s«" % asm.Label) if asm is not None else ("v dokument »%s«" % cilj_doc.Label)
    _log("knjižnica: vstavljen %s %s" % (kos.Label, kam))
    return {"ok": True, "sporocilo": "»%s« vstavljen %s." % (kos.Label, kam), "ime": povezava.Name}


def _kosi_za_tisk(doc, imena, napake):
    """Kosi za tisk iz objektov `imena`: (objekt, oznaka, oblika, premik). Objekt z več telesi da več kosov (_1, _2 ...).
    Oblika je v koordinatah, kot gre v STEP (Part.getShape); `premik` jo prestavi v globalno lego posnetka (kot _geometrija),
    da se smer iz analize lege ujema s 3D pogledom v brskalniku."""
    import Part
    for ime in imena:
        obj = doc.getObject(ime)
        if obj is None:
            napake.append("%s: ni v dokumentu" % ime)
            continue
        try:
            oblika = Part.getShape(obj)
        except Exception as e:  # noqa: BLE001
            napake.append("%s: %s" % (obj.Label, e))
            continue
        if oblika is None or oblika.isNull():
            napake.append("%s: brez oblike" % obj.Label)
            continue
        try:
            premik = obj.getGlobalPlacement().multiply(oblika.Placement.inverse())
        except Exception:  # noqa: BLE001
            premik = App.Placement()
        telesa = oblika.Solids
        if len(telesa) <= 1:
            yield obj, obj.Label, oblika, premik
        else:
            for i, t in enumerate(telesa):
                yield obj, "%s_%d" % (obj.Label, i + 1), t, premik


def _tisk_mreze(podatki):
    """Glavna nit: trikotniške mreže kosov za analizo lege (tisk_lega.py računa na niti strežnika). Mreža je v
    koordinatah STEP-a za tisk; `v_pogled` (3x3 po vrsticah) prestavi smer v globalne koordinate pogleda."""
    ime_doc = podatki.get("dokument", "")
    doc = App.getDocument(ime_doc) if ime_doc in App.listDocuments() else next(
        (d for d in App.listDocuments().values() if d.Label == ime_doc), None)
    if doc is None:
        return {"ok": False, "sporocilo": "Dokument »%s« ni odprt." % (ime_doc or "?")}
    imena = [i for i in (podatki.get("imena") or []) if isinstance(i, str)]
    napake, kosi = [], []
    for obj, oznaka, kos, premik in _kosi_za_tisk(doc, imena, napake):
        bb = kos.BoundBox
        toleranca = max(0.05, bb.DiagonalLength * 0.0015)
        try:
            v, t = kos.tessellate(toleranca)
            while len(t) > 400_000 and toleranca < bb.DiagonalLength * 0.05:
                toleranca *= 2
                v, t = kos.tessellate(toleranca, True)
        except Exception as e:  # noqa: BLE001
            napake.append("%s: mreža: %s" % (oznaka, e))
            continue
        if not t:
            napake.append("%s: brez ploskev" % oznaka)
            continue
        m = premik.Rotation.toMatrix()
        kosi.append({"ime": obj.Name, "oznaka": oznaka, "datoteka": _ime_datoteke_tiska(oznaka) + ".step",
                     "tocke": [c for p in v for c in (p.x, p.y, p.z)], "trikotniki": [i for tr in t for i in tr],
                     "v_pogled": [m.A11, m.A12, m.A13, m.A21, m.A22, m.A23, m.A31, m.A32, m.A33]})
    return {"ok": bool(kosi), "kosi": kosi, "napake": napake,
            "sporocilo": "" if kosi else "Ni kosov z geometrijo" + (": " + "; ".join(napake) if napake else ".")}


def tisk_lega_kosov(mreze, kot_previsa):
    """Nit strežnika: analiza lege vsakega kosa (tisk_lega.analiziraj); smer gor doda še v koordinatah pogleda."""
    import tisk_lega
    kosi = []
    for k in mreze["kosi"]:
        t0 = time.time()
        r = tisk_lega.analiziraj(k["tocke"], k["trikotniki"], kot_previsa)
        M = k["v_pogled"]
        for kand in r.get("kandidati", []) + ([r["kot_je"]] if r.get("kot_je") else []):
            g = kand["gor"]
            kand["gor_pogled"] = [round(M[3 * i] * g[0] + M[3 * i + 1] * g[1] + M[3 * i + 2] * g[2], 6) for i in range(3)]
        _log("lega za tisk: %s, %d trikotnikov, %d smeri, %.1f s" % (k["oznaka"], r.get("trikotnikov", 0), r.get("smeri", 0),
                                                                    time.time() - t0))
        kosi.append({"ime": k["ime"], "oznaka": k["oznaka"], "datoteka": k["datoteka"], **r})
    return {"ok": bool(kosi), "kosi": kosi, "napake": mreze.get("napake", []), "kot_previsa": kot_previsa}


def _tiskaj_natisni(stanje, podatki):
    """»Natisni« iz drevesa (glavna nit): objekte (`imena` = kosi z geometrijo pod vozlom, kot jih riše stran) izvozi kot
    STEP v vhodno mapo plošče Tiskaj (`mapa` določi nit strežnika); objekt z več telesi gre v več datotek (_1, _2 ...),
    ime datoteke je oznaka kosa, obstoječa datoteka z istim imenom je nova različica. Orientacijo, polnilo in tiskalnik
    uporabnik potrdi v oknu Pripravi plošče (zavihek Tiskanje); lego iz analize (tisk_lega.py) stran pošlje plošči
    kot začetni zasuk."""
    ime_doc = podatki.get("dokument", "")
    doc = App.getDocument(ime_doc) if ime_doc in App.listDocuments() else next(
        (d for d in App.listDocuments().values() if d.Label == ime_doc), None)
    if doc is None:
        return {"ok": False, "sporocilo": "Dokument »%s« ni odprt." % (ime_doc or "?")}
    imena = [i for i in (podatki.get("imena") or []) if isinstance(i, str)]
    if not imena and podatki.get("ime"):
        imena = [str(podatki["ime"])]
    mapa = str(podatki.get("mapa") or "")
    if not mapa:
        return {"ok": False, "sporocilo": "Vhodna mapa plošče Tiskaj ni znana (3D print/tiskaj/config.json, vhod_mapa)."}
    try:
        os.makedirs(mapa, exist_ok=True)
    except OSError as e:
        return {"ok": False, "sporocilo": "Vhodne mape %s ni mogoče ustvariti: %s" % (mapa, e)}
    datoteke, napake = [], []
    for _obj, oznaka, kos, _ in _kosi_za_tisk(doc, imena, napake):
        ime_dat = _ime_datoteke_tiska(oznaka) + ".step"
        pot = os.path.join(mapa, ime_dat)
        zacasna = pot + ".delno"      # plošča bere le .step/.stp/.stl: pol zapisane datoteke ne vidi
        try:
            kos.exportStep(zacasna)
            os.replace(zacasna, pot)
        except Exception as e:  # noqa: BLE001
            napake.append("%s: izvoz ni uspel: %s" % (oznaka, e))
            try:
                os.remove(zacasna)
            except OSError:
                pass
            continue
        datoteke.append(ime_dat)
    _log("tiskaj: izvoz za tisk iz »%s«: %s%s" % (doc.Label, ", ".join(datoteke) or "nič",
                                                    ("; napake: " + "; ".join(napake)) if napake else ""))
    if not datoteke:
        return {"ok": False, "sporocilo": "Za tisk ni bilo kaj izvoziti" + (": " + "; ".join(napake) if napake else "."),
                "napake": napake}
    sporocilo = ("Za tisk izvožen »%s«" % datoteke[0][:-5]) if len(datoteke) == 1 else ("Za tisk izvoženih %d kosov" % len(datoteke))
    if napake:
        sporocilo += " (brez: " + "; ".join(napake) + ")"
    return {"ok": True, "datoteke": datoteke, "mapa": mapa, "napake": napake, "sporocilo": sporocilo + "."}


def _projekt_dejanje(stanje, podatki):
    dejanje = podatki.get("dejanje", "")
    if dejanje == "odpri":
        pot = podatki.get("pot", "")
        for d in App.listDocuments().values():
            if _ista_pot(d.FileName, pot):
                App.setActiveDocument(d.Name)
                break
        else:
            if os.path.isfile(pot):
                _log("odpiram %s" % pot)
                doc = App.openDocument(pot)
                App.setActiveDocument(doc.Name)
            else:
                _log("projekt: datoteke ni: %s" % pot)  # seznam se spodaj osveži, vnos izgine
    elif dejanje == "aktiviraj":
        ime = podatki.get("ime", "")
        pot = podatki.get("pot", "")
        if ime in App.listDocuments():
            App.setActiveDocument(ime)
        elif pot and os.path.isfile(pot):
            # Seznam v brskalniku je bil zastarel (dokument je medtem zaprt): datoteko odpremo znova.
            _log("projekt: dokument %s ni več odprt, odpiram %s" % (ime, pot))
            doc = App.openDocument(pot)
            App.setActiveDocument(doc.Name)
        else:
            _log("projekt: dokumenta %s ni več (zastarel seznam v brskalniku)" % ime)
    elif dejanje == "odpri-razlicico":
        # Prenesena različica iz oblaka (oblak.py): kopija v mapi različic, odprta za ogled; oznaka pove, katera.
        pot = podatki.get("pot", "")
        for d in App.listDocuments().values():
            if _ista_pot(d.FileName, pot):
                App.closeDocument(d.Name)   # sveže prenesena vsebina naj zamenja prejšnji ogled iste različice
                break
        if os.path.isfile(pot):
            # Oznaka dokumenta ostane ime datoteke (»ime · različica N«); nastavljanje Label bi dokument označilo
            # kot spremenjen in ob zapiranju vprašalo za shranjevanje.
            _log("odpiram različico %s" % pot)
            doc = App.openDocument(pot)
            App.setActiveDocument(doc.Name)
        else:
            _log("projekt: različice ni: %s" % pot)
    elif dejanje == "osvezi":
        # Odjemalec oblaka je datoteko na disku zamenjal (obnova različice): odprt dokument brez neshranjenih
        # sprememb znova naložimo; spremenjenega ne, da uporabnik ne izgubi dela.
        pot = podatki.get("pot", "")
        for d in list(App.listDocuments().values()):
            if _ista_pot(d.FileName, pot):
                if _spremenjen(d):
                    _log("projekt: %s ima neshranjene spremembe, ne osvežim" % d.Name)
                    stanje.oddaj("oblak", {"vrsta": "neosvezeno", "pot": pot,
                                           "sporocilo": "Dokument »%s« ima neshranjene spremembe, zato ni bil osvežen na obnovljeno različico." % d.Label})
                    return
                aktiven = App.ActiveDocument is not None and App.ActiveDocument.Name == d.Name
                _log("osvežujem %s iz diska" % pot)
                App.closeDocument(d.Name)
                nov = App.openDocument(pot)
                if aktiven:
                    App.setActiveDocument(nov.Name)
                break
    elif dejanje == "zapri":
        # Brskalnik je pri neshranjenih spremembah že vprašal za potrditev.
        ime = podatki.get("ime", "")
        if ime in App.listDocuments():
            if stanje.skica and App.ActiveDocument is not None and App.ActiveDocument.Name == ime:
                stanje.skica = ""
                stanje.oddaj("skica", None)
            _log("zapiram dokument %s" % ime)
            App.closeDocument(ime)
    elif dejanje == "osvezi-seznam":
        # Zaklep se je spremenil (oblak.py v ozadju): samo znova zgradi seznam odprtih dokumentov.
        stanje.zadnji_projekti = 0.0
        return
    else:
        return
    if IMA_OKNO:
        Gui.Selection.clearSelection()
    stanje.umazano = True
    stanje.zadnji_projekti = 0.0


class Stanje:
    def __init__(self):
        self.vrsta = queue.Queue()          # zahteve iz brskalnika -> glavna nit
        self.vrsta_ozadje = queue.Queue()   # nizka prednost (geometrija za sličice): le ko ni drugega dela, ena na obhod
        self.odjemalci = []                 # vrste SSE odjemalcev
        self.kljuc = threading.Lock()
        self._posnetek = b'{"dokument":"","verzija":0,"objekti":[]}'
        self._ukazi = b'{"delovnaOkolja":[],"hitriDostop":[]}'
        self.imena_ukazov = []
        self.aktivni = {}
        self.okolje = {"delovnaMiza": "", "urejanje": ""}
        self.verzija = 0
        self.izbira = []
        self.umazano = True
        self.zadnja_gradnja = 0.0
        self.zadnji_pregled = 0.0
        self.zadnji_videz = 0.0
        self.odtis_videza = None           # _videz_kljuc ob zadnjem pregledu (namesto opazovalca pogleda)
        self.napaka = ""
        self.skica = ""                    # ime skice, ki se ureja v brskalniku
        self.samodejno_prikazano = False   # okno smo pokazali sami zaradi vnosa; po koncu ga spet skrijemo
        self.okno_na_zahtevo = False       # uporabnik je z gumbom zahteval vidno okno
        self.zapiranje_okna = False        # uporabnik je zaprl okno (X); ko ni več vprašanj, program konča
        self.skrita_okna = []              # okna (pogovori), ki smo jih ob prikazu naredili nevidna
        self.obrazec = None                # JSON obrazca, ki je trenutno v brskalniku (ali None)
        self.obrazec_mapa = {}             # id -> (gradnik, dodatno) zadnjega zajema
        self.zadnji_obrazec = 0.0
        self.zadnji_klik_obrazca = (None, 0.0)   # (kljuc, id, dejanje), čas: ponovljen klik se zavrne
        self._projekti = b'{"odprti":[],"skupine":[]}'
        self.zadnji_projekti = 0.0
        self.za_vidnost = set()      # imena novo odprtih dokumentov, ki jim je treba po obnovi preveriti vidnost
        self.za_dvojnike = 0.0       # čas zadnjega novega dokumenta; ko se odpiranje umiri, se zaprejo dvojniki
        self.zadnja_zahteva = time.time()   # zadnja zahteva iz brskalnika (ogrevanje teče le v mirovanju)
        self.ogrevanje = None        # naloge ogrevanja predpomnilnika (generator) ali None, ko je vse pripravljeno
        self.ogrevanje_odtis = None  # imena odprtih dokumentov, za katera je bilo ogrevanje zastavljeno

    def skrivaj_okna(self):
        """Ali naj nova okna FreeCAD-a ostanejo nevidna (vse se dela v brskalniku)."""
        return OKNO_SKRITO and not self.okno_na_zahtevo and not self.zapiranje_okna

    # -- niti strežnika --
    def nov_odjemalec(self):
        q = queue.Queue()
        with self.kljuc:
            self.odjemalci.append(q)
        return q

    def odstrani_odjemalca(self, q):
        with self.kljuc:
            if q in self.odjemalci:
                self.odjemalci.remove(q)

    def oddaj(self, dogodek, podatki):
        with self.kljuc:
            for q in self.odjemalci:
                q.put((dogodek, podatki))

    def posnetek(self):
        return self._posnetek

    def ukazi(self):
        return self._ukazi

    def projekti(self):
        return self._projekti

    def stanje(self):
        return {
            "verzija": self.verzija,
            "izbira": self.izbira,
            "okolje": self.okolje,
            "vrata": VRATA,
            "okno": IMA_OKNO,
            "odjemalcev": len(self.odjemalci),
            "ukazov": len(self.imena_ukazov),
            "napaka": self.napaka,
            "obrazec": self.obrazec is not None,
            "projektov": sum(len(s["datoteke"]) for s in json.loads(self._projekti)["skupine"]),
        }

    # -- glavna nit --
    def obdelaj(self):
        ozadje = False
        while True:
            try:
                ukaz, podatki, odgovor = self.vrsta.get_nowait()
            except queue.Empty:
                if ozadje:
                    break
                ozadje = True   # zahteve iz ozadja (sličice) šele, ko je vrsta prazna, in samo ena
                try:
                    ukaz, podatki, odgovor = self.vrsta_ozadje.get_nowait()
                except queue.Empty:
                    break
            else:
                self.zadnja_zahteva = time.time()
            try:
                self._izvedi(ukaz, podatki, odgovor)
            except Exception:  # noqa: BLE001
                self.napaka = traceback.format_exc()
                _log("napaka pri ukazu %s: %s" % (ukaz, self.napaka))
                if odgovor is not None:
                    odgovor["napaka"] = self.napaka
            if odgovor is not None:
                odgovor["konec"].set()
        zdaj = time.time()
        if IMA_OKNO and zdaj - self.zadnji_obrazec > 0.25:
            self.zadnji_obrazec = zdaj
            try:
                self.preveri_obrazec()
            except Exception:  # noqa: BLE001
                self.napaka = traceback.format_exc()
                _log("obrazec: %s" % self.napaka)
        if self.za_vidnost:
            self.preveri_vidnost()
        if self.za_dvojnike and zdaj - self.za_dvojnike > 1.5:
            self.preveri_dvojnike()
        if IMA_OKNO and zdaj - self.zadnji_videz > 1.0:
            self.zadnji_videz = zdaj
            try:
                odtis = _videz_kljuc(App.ActiveDocument)
                if odtis != self.odtis_videza:
                    if self.odtis_videza is not None:
                        self.umazano = True
                    self.odtis_videza = odtis
            except Exception:  # noqa: BLE001
                _log("videz: %s" % traceback.format_exc())
        if self.umazano and zdaj - self.zadnja_gradnja > 0.3:
            self.zgradi()
        if zdaj - self.zadnji_projekti > 2.0:
            self.zadnji_projekti = zdaj
            try:
                self.preveri_projekte()
            except Exception:  # noqa: BLE001
                self.napaka = traceback.format_exc()
                _log("projekti: %s" % self.napaka)
        if IMA_OKNO and zdaj - self.zadnji_pregled > 0.5:
            self.zadnji_pregled = zdaj
            try:
                self.preveri_okolje()
            except Exception:  # noqa: BLE001
                self.napaka = traceback.format_exc()
        if not self.umazano and time.time() - self.zadnja_zahteva > MIROVANJE_OGREVANJA:
            try:
                self.ogrej()
            except Exception:  # noqa: BLE001
                self.ogrevanje = None
                _log("ogrevanje: %s" % traceback.format_exc())

    def ogrej(self):
        """Posnetke objektov odprtih dokumentov zgradi vnaprej, ko brskalnik miruje. Prvi preklop na še ne pregledan
        sestav je sicer čakal na mreženje (Slim A ~1 min, Slim spredaj A 12 s), ponovni traja le še sekundo. Na obhod
        največ en objekt, ki ga je treba mrežiti (do nekaj sekund): klik v brskalniku počaka le nanj."""
        if self.skica or self.obrazec is not None or not self.odjemalci:
            return
        dokumenti = App.listDocuments()
        odtis = tuple(sorted(dokumenti))
        if odtis != self.ogrevanje_odtis:
            self.ogrevanje_odtis = odtis
            self.ogrevanje = self._naloge_ogrevanja()
        if self.ogrevanje is None:
            return
        if any(getattr(d, "Restoring", False) for d in dokumenti.values()):
            return
        if IMA_OKNO:
            from PySide6 import QtWidgets
            if QtWidgets.QApplication.activeModalWidget() is not None:
                return
        konec = time.time() + 0.05
        while time.time() < konec:
            try:
                naloga = next(self.ogrevanje)
            except StopIteration:
                self.ogrevanje = None
                _log("ogrevanje: posnetki vseh odprtih dokumentov so pripravljeni")
                return
            if naloga():   # zahtevno delo (mreženje, prostornina): naslednje šele v naslednjem obhodu
                return

    def _naloge_ogrevanja(self):
        """Naloge ogrevanja po dokumentih: sestavi pred deli (te uporabnik odpira največ), za objekti dokumenta še
        drevo (prostornine teles). Vsaka naloga dokument in objekt poišče znova, ker se je vmes lahko zaprl."""
        def je_sestav(d):
            return any(o.TypeId.startswith("Assembly::") for o in d.Objects)

        def objekt(ime_dok, ime_obj):
            doc = App.listDocuments().get(ime_dok)
            obj = doc.getObject(ime_obj) if doc is not None else None
            if obj is None:
                return False
            return not _geometrija_predpomnjena(doc, obj)[1]

        def drevo(ime_dok):
            doc = App.listDocuments().get(ime_dok)
            if doc is not None:
                drevo_dokumenta(doc, None, _kljuc_oblike)
            return True

        for doc in sorted(App.listDocuments().values(), key=lambda d: not je_sestav(d)):
            ime_dok = doc.Name
            doc = App.listDocuments().get(ime_dok)
            if doc is None or getattr(doc, "Partial", False):
                continue
            for obj in list(_vidni_objekti(doc)):
                yield lambda d=ime_dok, o=obj.Name: objekt(d, o)
            yield lambda d=ime_dok: drevo(d)

    def zgradi(self):
        zacetek = time.time()
        doc = App.ActiveDocument
        objekti = []
        zadetki = 0
        if doc is not None:
            for obj in _vidni_objekti(doc):
                try:
                    posnetek, zadetek = _geometrija_predpomnjena(doc, obj)
                    objekti.append(posnetek)
                    zadetki += zadetek
                except Exception:  # noqa: BLE001
                    _log("objekt %s preskočen: %s" % (obj.Name, traceback.format_exc()))
        try:
            drevo = drevo_dokumenta(doc, _ikona_uri, _kljuc_oblike)
        except Exception:  # noqa: BLE001
            drevo = {"koreni": [], "vozli": {}}
            _log("drevo dokumenta: %s" % traceback.format_exc())
        self.verzija += 1
        self._posnetek = ('{"dokument":%s,"verzija":%d,"objekti":[%s],"drevo":%s}' % (
            json.dumps(doc.Label if doc else ""), self.verzija, ",".join(objekti),
            json.dumps(drevo, separators=(",", ":")))).encode("utf-8")
        self.umazano = False
        self.zadnja_gradnja = time.time()
        self.oddaj("model", {"verzija": self.verzija})
        _log("posnetek %d: %d objektov (%d iz predpomnilnika), %.1f kB, %.2f s"
             % (self.verzija, len(objekti), zadetki, len(self._posnetek) / 1024.0, time.time() - zacetek))

    def zgradi_ukaze(self):
        self.nalozena = nalozena_okolja()
        podatki, self.imena_ukazov = zgradi_ukaze()
        self._ukazi = json.dumps(podatki, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.aktivni = {}
        _log("ukazov: %d, %.0f kB" % (len(self.imena_ukazov), len(self._ukazi) / 1024.0))

    def preveri_okolje(self):
        """Stanje ukazov (na voljo), aktivno delovno okolje in urejanje skice; pošlje le spremembe."""
        spremembe = {}
        for ime in self.imena_ukazov:
            cmd = Gui.Command.get(ime)
            try:
                a = bool(cmd.isActive()) if cmd else False
            except Exception:  # noqa: BLE001
                a = False
            if self.aktivni.get(ime) != a:
                self.aktivni[ime] = a
                spremembe[ime] = a
        if spremembe:
            self.oddaj("aktivni", spremembe)
        urejanje = ""
        try:
            vp = Gui.ActiveDocument.getInEdit() if Gui.ActiveDocument else None
            if vp is not None:
                urejanje = vp.Object.TypeId
        except Exception:  # noqa: BLE001
            urejanje = ""
        pogovor = ""
        try:
            from PySide6 import QtWidgets
            modalno = QtWidgets.QApplication.activeModalWidget()
            if modalno is not None:
                pogovor = modalno.windowTitle() or "pogovorno okno"
        except Exception:  # noqa: BLE001
            pogovor = ""
        try:
            opravilo = bool(Gui.Control.activeDialog())
        except Exception:  # noqa: BLE001
            opravilo = False
        from PySide6 import QtWidgets
        mw = Gui.getMainWindow()
        if self.skrivaj_okna():
            # Okno FreeCAD-a ostane skrito: pogovori in opravila gredo v brskalnik kot obrazec
            # (preveri_obrazec). Če ga FreeCAD pokaže sam (npr. ob novem dokumentu), ga skrijemo.
            if mw.isVisible():
                _skrij_okno()
            # Urejanje skice, ki ga je začel FreeCAD (ne brskalnik), prestavimo v brskalnik.
            if urejanje.startswith("Sketcher::") and not pogovor:
                try:
                    ime = Gui.ActiveDocument.getInEdit().Object.Name
                    Gui.ActiveDocument.resetEdit()
                    self.skica = ime
                    self.umazano = True
                    self.oddaj_skico()
                    _log("urejanje skice %s preneseno v brskalnik" % ime)
                    urejanje = ""
                    opravilo = bool(Gui.Control.activeDialog())
                except Exception:  # noqa: BLE001
                    _log("skice ni bilo mogoče prenesti v brskalnik: %s" % traceback.format_exc())
        if self.zapiranje_okna and not pogovor:
            if mw.isVisible():
                self.zapiranje_okna = False  # zapiranje preklicano (npr. pri vprašanju o shranjevanju)
            else:
                _log("okno zaprto, program se konča")
                QtWidgets.QApplication.instance().quit()
        spremenjeno = any(_spremenjen(d) for d in App.listDocuments().values())
        okolje = {"delovnaMiza": Gui.activeWorkbench().name(), "urejanje": urejanje,
                  "pogovor": pogovor, "opravilo": opravilo, "oknoVidno": mw.isVisible(),
                  "spremenjeno": spremenjeno}
        if okolje != self.okolje:
            self.okolje = okolje
            self.oddaj("okolje", okolje)
        # Novo naloženo okolje (klik na zavihek ali preklop v FreeCAD-u) ali okolje, katerega menijev še nismo
        # prebrali: ukazi znova, brskalnik jih prebere ob dogodku.
        prej = getattr(self, "nalozena", None)   # None: ukazi še niso zgrajeni (zagon)
        dejavno = okolje["delovnaMiza"]
        novi_meniji = dejavno not in MENIJI_OKOLIJ and dejavno not in IZPUSCENA_OKOLJA
        if prej is not None and (nalozena_okolja() != prej or novi_meniji):
            if novi_meniji:
                _zajemi_menije(dejavno)
            self.zgradi_ukaze()
            self.oddaj("ukazi", {})

    def preveri_vidnost(self):
        """Novo odprtim dokumentom (ko obnova konča) vrne vidnost iz datoteke, če ta nima GuiDocument.xml."""
        for ime in list(self.za_vidnost):
            doc = App.getDocument(ime) if ime in App.listDocuments() else None
            if doc is None:
                self.za_vidnost.discard(ime)
            elif not getattr(doc, "Restoring", False):
                self.za_vidnost.discard(ime)
                try:
                    _popravi_vidnost(doc)
                except Exception:  # noqa: BLE001
                    _log("vidnost %s: %s" % (ime, traceback.format_exc()))
                self.umazano = True

    def preveri_dvojnike(self):
        """Ko se odpiranje dokumentov umiri (noben se ne nalaga, ni modalnega okna, npr. Obnove dokumentov),
        zapre dvojnike iste datoteke in odvečne vzorčne dokumente."""
        if any(getattr(d, "Restoring", False) for d in App.listDocuments().values()):
            return
        if IMA_OKNO:
            from PySide6 import QtWidgets
            if QtWidgets.QApplication.activeModalWidget() is not None:
                return
        self.za_dvojnike = 0.0
        try:
            if _zapri_dvojnike():
                self.umazano = True
                self.zadnji_projekti = 0.0
        except Exception:  # noqa: BLE001
            _log("dvojniki: %s" % traceback.format_exc())

    def preveri_projekte(self):
        """Seznam projektov in odprtih dokumentov; pošlje le ob spremembi."""
        novi = json.dumps(zgradi_projekte(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if novi != self._projekti:
            self._projekti = novi
            self.oddaj("projekti", json.loads(novi))

    def preveri_obrazec(self):
        """Okno, ki čaka na vnos, pošlje brskalniku kot obrazec (le ob spremembi)."""
        obr, mapa = _zajemi_obrazec(self)
        self.obrazec_mapa = mapa
        if obr != self.obrazec:
            self.obrazec = obr
            self.oddaj("obrazec", obr)

    def skica_objekt(self):
        doc = App.ActiveDocument
        if not self.skica or doc is None:
            return None
        sk = doc.getObject(self.skica)
        if sk is None or not sk.isDerivedFrom("Sketcher::SketchObject"):
            self.skica = ""
            return None
        return sk

    def oddaj_skico(self, novi=None):
        sk = self.skica_objekt()
        posnetek = _posnetek_skice(sk, novi) if sk is not None else None
        self.oddaj("skica", posnetek)
        return posnetek

    def posodobi_izbiro(self):
        if not IMA_OKNO:
            return
        izbira = []
        for s in Gui.Selection.getSelectionEx():
            vnos = {"objekt": s.ObjectName, "elementi": list(s.SubElementNames)}
            # izbran spoj (mate): brskalnik obarva ploskve, ki jih povezuje, na obeh kosih (kot SolidWorks)
            try:
                reference = _reference_spoja(s.Object) if not s.SubElementNames else None
            except Exception:  # noqa: BLE001
                reference = None
            if reference:
                vnos["spoj"] = reference
            izbira.append(vnos)
        self.izbira = izbira
        self.oddaj("izbira", izbira)

    def _izvedi(self, ukaz, podatki, odgovor=None):
        if ukaz == "mcp":
            # orodje MCP (mcp_orodja.py), ki potrebuje FreeCAD API: funkcija iz niti strežnika teče tukaj
            mcp_orodja.glavna(self, podatki, odgovor)
            return
        if ukaz == "izbira":
            if not IMA_OKNO:
                return
            doc = App.ActiveDocument
            if doc is None:
                return
            if not podatki.get("dodaj"):
                Gui.Selection.clearSelection()
            obj = doc.getObject(podatki.get("objekt", ""))
            if obj is not None:
                Gui.Selection.addSelection(doc.Name, obj.Name, podatki.get("element", ""))
        elif ukaz == "ukaz":
            if not IMA_OKNO:
                return
            ime = podatki.get("ime", "")
            indeks = int(podatki.get("indeks", 0) or 0)
            if ime in self.imena_ukazov or ime.startswith("Std_"):
                _sprozi_ukaz(ime, indeks)
                self.zadnji_pregled = 0.0  # stanje ukazov preveri takoj
        elif ukaz == "okno":
            if IMA_OKNO:
                self.samodejno_prikazano = False
                self.okno_na_zahtevo = bool(podatki.get("prikazi", True))
                if self.okno_na_zahtevo:
                    _pokazi_okno()
                    for w in self.skrita_okna:
                        if _veljaven(w) and w.isVisible():
                            _vidno_okno(w)
                    self.skrita_okna = []
                else:
                    _skrij_okno()
                self.zadnji_pregled = 0.0
        elif ukaz == "izhod":
            try:
                OBLAK.odkleni_vse()   # PDM: zaklepi tega primerka ne smejo ostati v oblaku
            except Exception as e:  # noqa: BLE001
                _log("oblak: odklep ob izhodu: %r" % e)
            if IMA_OKNO:
                # Brskalnik je že vprašal za potrditev; neshranjene spremembe se zavržejo.
                from PySide6 import QtCore, QtWidgets
                _log("izhod na zahtevo iz brskalnika")
                for d in list(App.listDocuments().values()):
                    try:
                        App.closeDocument(d.Name)
                    except Exception:  # noqa: BLE001
                        pass
                QtCore.QTimer.singleShot(200, QtWidgets.QApplication.instance().quit)
        elif ukaz == "okolje":
            if IMA_OKNO and podatki.get("ime") in Gui.listWorkbenches():
                Gui.activateWorkbench(podatki.get("ime"))
                self.zadnji_pregled = 0.0
        elif ukaz == "znacilnost":
            # Izboklina ali ugrez iz skice brez FreeCAD-ovega okna z nastavitvami.
            doc = App.ActiveDocument
            sk = doc.getObject(podatki.get("skica", "")) if doc else None
            if sk is None or not sk.isDerivedFrom("Sketcher::SketchObject"):
                _log("značilnost: %s ni skica" % podatki.get("skica"))
                return
            vrsta = podatki.get("vrsta", "izboklina")
            tip = "PartDesign::Pad" if vrsta == "izboklina" else "PartDesign::Pocket"
            doc.openTransaction("Izboklina" if vrsta == "izboklina" else "Ugrez")
            try:
                telo = sk.getParentGeoFeatureGroup()
                if telo is None or not telo.isDerivedFrom("PartDesign::Body"):
                    telo = _aktivno_telo(doc) or doc.addObject("PartDesign::Body", "Telo")
                    telo.addObject(sk)
                try:
                    Gui.ActiveDocument.ActiveView.setActiveObject("pdbody", telo)
                except Exception:  # noqa: BLE001
                    pass
                zn = telo.newObject(tip, "Pad" if vrsta == "izboklina" else "Pocket")
                zn.Profile = sk
                zn.Length = float(podatki.get("dolzina", 10) or 10)
                zn.Reversed = bool(podatki.get("obrni"))
                zn.Midplane = bool(podatki.get("simetricno"))
                sk.Visibility = False
                for o in telo.Group:
                    if o is not zn and o.isDerivedFrom("PartDesign::Feature"):
                        o.Visibility = False
                zn.Visibility = True
                doc.commitTransaction()
            except Exception:
                doc.abortTransaction()
                raise
            doc.recompute()
            self.umazano = True
            if IMA_OKNO:
                Gui.Selection.clearSelection()
        elif ukaz == "skica-posnetek":
            if self.skica:
                self.oddaj_skico()
        elif ukaz == "skica":
            vrsta = podatki.get("vrsta")
            doc = App.ActiveDocument
            if vrsta == "nova":
                sk = _nova_skica(podatki)
                self.skica = sk.Name
                self.umazano = True
                self.oddaj_skico()
            elif vrsta == "odpri":
                obj = doc.getObject(podatki.get("ime", "")) if doc else None
                if obj is not None and obj.isDerivedFrom("Sketcher::SketchObject"):
                    self.skica = obj.Name
                    self.umazano = True
                    self.oddaj_skico()
                else:
                    _log("odpri skico: %s ni skica" % podatki.get("ime"))
            elif vrsta == "zapri":
                ime = self.skica
                self.skica = ""
                self.umazano = True
                if doc is not None:
                    doc.recompute()
                self.oddaj("skica", None)
                if IMA_OKNO and doc is not None and ime and doc.getObject(ime) is not None:
                    Gui.Selection.clearSelection()
                    Gui.Selection.addSelection(doc.Name, ime)
            else:
                sk = self.skica_objekt()
                if sk is None:
                    return
                novi = _skica_izvedi(sk, podatki)
                self.umazano = True
                self.oddaj_skico(novi)
        elif ukaz == "projekt":
            _projekt_dejanje(self, podatki)
        elif ukaz == "drevo":
            drevo_dejanje(self, podatki)
        elif ukaz == "knjiznica":
            rezultat = _knjiznica_dejanje(self, podatki)
            if odgovor is not None:
                odgovor["rezultat"] = rezultat
        elif ukaz == "tiskaj":
            rezultat = _tiskaj_natisni(self, podatki)
            if odgovor is not None:
                odgovor["rezultat"] = rezultat
        elif ukaz == "tisk_mreze":
            rezultat = _tisk_mreze(podatki)
            if odgovor is not None:
                odgovor["rezultat"] = rezultat
        elif ukaz == "standardni":
            # Baza standardnih delov (baza.py): označi kos kot standardni -> premik v bazo, preusmeritev sestavov.
            rezultat = baza_dejanje(self, podatki)
            for stara in getattr(self, "premaknjene_poti", []):
                try:
                    OBLAK.dokument_zaprt(stara)   # PDM: zaklep stare poti ne sme ostati
                except Exception as e:  # noqa: BLE001
                    _log("oblak: odklep premaknjenega: %r" % e)
            self.premaknjene_poti = []
            _log("standardni: %s" % rezultat.get("sporocilo", ""))
            if odgovor is not None:
                odgovor["rezultat"] = rezultat
        elif ukaz == "videz":
            rezultat = _videz_dejanje(podatki)
            self.umazano = True
            if odgovor is not None:
                odgovor["rezultat"] = rezultat
        elif ukaz == "obrazec":
            if IMA_OKNO and self.obrazec is not None and podatki.get("kljuc") == self.obrazec.get("kljuc"):
                # Ponovljen klik na isti gumb istega okna (dvojni klik, dva zavihka) se ne izvede: klik gre v Qt-jevo
                # vrsto mimo modalnosti, zato bi drugi zadel okno, ki ga je prvi že blokiral z novim vprašanjem
                # (9. 10. 2026: »Počisti« v Obnovitvi dokumentov je odprl obnovo). Okno mora biti še tisto, ki čaka.
                zdaj = time.monotonic()
                odtis = (podatki.get("kljuc"), podatki.get("id"), podatki.get("dejanje"))
                if podatki.get("dejanje") == "klik" and odtis == self.zadnji_klik_obrazca[0]                         and zdaj - self.zadnji_klik_obrazca[1] < 1.5:
                    _log("obrazec: ponovljen klik %s zavrnjen" % (odtis,))
                elif _obrazec_se_caka(self, podatki.get("kljuc")):
                    if podatki.get("dejanje") == "klik":
                        self.zadnji_klik_obrazca = (odtis, zdaj)
                    _obrazec_dejanje(self.obrazec_mapa, podatki)
                else:
                    _log("obrazec: okno %s ne čaka več, dejanje zavrnjeno" % podatki.get("kljuc"))
                self.zadnji_obrazec = 0.0  # novo stanje obrazca takoj nazaj v brskalnik
        elif ukaz == "zgradba":
            doc = App.listDocuments().get(podatki.get("ime", "")) or App.ActiveDocument
            if doc is not None and odgovor is not None:
                odgovor["rezultat"] = _zgradba_dokumenta(doc)
        elif ukaz == "posnetek":
            doc = App.listDocuments().get(podatki.get("ime", ""))
            if doc is not None and odgovor is not None:
                objekti = []
                for obj in _vidni_objekti(doc):
                    try:
                        objekti.append(_geometrija_predpomnjena(doc, obj)[0])
                    except Exception:  # noqa: BLE001
                        pass
                odgovor["rezultat"] = ('{"dokument":%s,"objekti":[%s]}' % (
                    json.dumps(doc.Label), ",".join(objekti))).encode("utf-8")
        elif ukaz == "python":
            # Koda iz brskalnika ali iz izvedi.py; izpis in spremenljivka "rezultat" gresta v odgovor.
            import contextlib
            import io
            izpis = io.StringIO()
            okolje = {"App": App, "FreeCAD": App, "Gui": Gui, "FreeCADGui": Gui, "STANJE": self}
            try:
                with contextlib.redirect_stdout(izpis), contextlib.redirect_stderr(izpis):
                    exec(podatki.get("koda", ""), okolje)
            finally:
                self.umazano = True
                if odgovor is not None:
                    odgovor["izpis"] = izpis.getvalue()
                    odgovor["rezultat"] = okolje.get("rezultat")


STANJE = Stanje()
OBLAK = Oblak(_log, STANJE.vrsta, STANJE.oddaj)   # različice datotek iz lastnega oblaka (PDM)
mcp_orodja.povezi(sys.modules[__name__])          # orodja MCP: modul strežnika, dnevnik, zapis kataloga za most


# ---------------------------------------------------------------------------
# Opazovalci (klici pridejo na glavni niti)

class OpazovalecDokumenta:
    def slotRecomputedDocument(self, doc):
        STANJE.umazano = True

    def slotChangedObject(self, obj, prop):
        if prop in ("Visibility", "Shape", "Placement", "Label"):
            STANJE.umazano = True

    def slotDeletedObject(self, obj):
        STANJE.umazano = True
        try:
            _pozabi_geometrijo(obj.Document.Name, obj.Name)
        except Exception:  # noqa: BLE001
            pass

    def slotActivateDocument(self, doc):
        STANJE.umazano = True
        STANJE.zadnja_gradnja = 0.0  # preklop dokumenta: posnetek takoj, brez zamika za združevanje sprememb
        STANJE.zadnji_projekti = 0.0

    def slotCreatedDocument(self, doc):
        STANJE.umazano = True
        STANJE.zadnji_projekti = 0.0
        STANJE.za_vidnost.add(doc.Name)  # Python opazovalec nima slotFinishRestoreDocument; preveri se v zanki
        STANJE.za_dvojnike = time.time()

    def slotDeletedDocument(self, doc):
        STANJE.umazano = True
        STANJE.zadnji_projekti = 0.0
        _pozabi_geometrijo(doc.Name)
        try:
            if doc.FileName:
                OBLAK.dokument_zaprt(doc.FileName)   # PDM: sprosti zaklep tega primerka (v ozadju)
        except Exception as e:  # noqa: BLE001
            _log("oblak: odklep ob zaprtju: %r" % e)

    def slotFinishSaveDocument(self, doc, ime):
        # PDM (oblak.py): po shranjevanju datoteke iz mape oblaka brskalnik vpraša »Kaj si spremenil?«;
        # komentar se zapiše k reviziji, ki jo bo oblaku poslal odjemalec oblaka.
        STANJE.zadnji_projekti = 0.0
        if getattr(STANJE, "tiho_shranjevanje", False):
            return   # premik v bazo standardnih delov shrani več sestavov naenkrat; vsebina se ni spremenila
        try:
            if ime and OBLAK.prijavljen() and OBLAK.v_oblaku(ime) and not OBLAK.je_razlicica(ime):
                STANJE.oddaj("oblak", {"vrsta": "shranjeno", "pot": ime, "ime": doc.Label})
        except Exception as e:  # noqa: BLE001
            _log("oblak: dogodek shranjevanja: %r" % e)


# Opazovalca pogleda (Gui.addDocumentObserver s slotChangedObject) NE uporabljamo: FreeCAD ta signal
# odda že iz konstruktorja ViewProviderja (ViewProvider::onChanged), DocumentObserverPython takrat
# pokliče getPyObject() še na osnovnem razredu in si zapomni ViewProviderGeometryObjectPy namesto
# ViewProviderPartExtPy. Objekti Part, ustvarjeni med delovanjem strežnika, potem nimajo `DiffuseColor`
# (npr. SheetMetal Make Wall pade z AttributeError). Spremembe videza zato preverja `_videz_kljuc`.
def _videz_kljuc(doc):
    """Odtis videza (vidnost, prosojnost, barve) vseh objektov dokumenta, za periodično primerjavo."""
    if doc is None:
        return None
    odtis = []
    for obj in doc.Objects:
        vo = getattr(obj, "ViewObject", None)
        if vo is None:
            continue
        try:
            barve = tuple(tuple(m.DiffuseColor[:3]) for m in vo.ShapeAppearance) if hasattr(vo, "ShapeAppearance") else ()
        except Exception:  # noqa: BLE001
            barve = ()
        odtis.append((obj.Name, bool(getattr(vo, "Visibility", True)), getattr(vo, "Transparency", 0), barve))
    return (doc.Name, tuple(odtis))


class OpazovalecIzbire:
    def addSelection(self, doc, obj, sub, pnt):
        STANJE.posodobi_izbiro()

    def removeSelection(self, doc, obj, sub):
        STANJE.posodobi_izbiro()

    def setSelection(self, doc):
        STANJE.posodobi_izbiro()

    def clearSelection(self, doc):
        STANJE.posodobi_izbiro()


# ---------------------------------------------------------------------------
# HTTP

class Streznik(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False  # Windows bi sicer dovolil dva strežnika na istih vratih

    def handle_error(self, request, client_address):
        vrsta = sys.exc_info()[0]
        if vrsta and issubclass(vrsta, (ConnectionAbortedError, ConnectionResetError, BrokenPipeError)):
            return  # brskalnik je zaprl povezavo (osvežitev strani), ni napaka
        super().handle_error(request, client_address)


class Zahteva(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # tiho
        pass

    def _znana_datoteka(self, pot):
        """Pot je med datotekami trenutnega seznama projektov (odprti dokumenti, mape projektov ...)."""
        p = json.loads(STANJE.projekti())
        znane = [d["pot"] for d in p.get("odprti", [])] + [d["pot"] for d in p.get("nedavne", [])]
        znane += [d["pot"] for sk in p.get("skupine", []) for d in sk["datoteke"]]
        if _v_bazi(pot) and os.path.isfile(pot):   # kosi iz knjižnice standardnih delov
            return True
        return any(_ista_pot(pot, z) for z in znane)

    def _odgovor(self, telo, vrsta="application/json; charset=utf-8", koda=200, predpomni=False):
        self.send_response(koda)
        self.send_header("Content-Type", vrsta)
        self.send_header("Content-Length", str(len(telo)))
        self.send_header("Cache-Control", "max-age=86400" if predpomni else "no-store")
        self.end_headers()
        self.wfile.write(telo)

    def do_GET(self):
        pot = self.path.split("?")[0]
        if pot == "/":
            with open(os.path.join(MAPA, "index.html"), "rb") as f:
                stran = f.read().replace(b"__ZETON__", ZETON.encode("ascii"))
            self._odgovor(stran, "text/html; charset=utf-8")
        elif pot == "/ikona.svg":
            with open(os.path.join(MAPA, "ikona.svg"), "rb") as f:
                self._odgovor(f.read(), "image/svg+xml", predpomni=True)
        elif pot == "/ikona.png":
            with open(os.path.join(MAPA, "ikona.png"), "rb") as f:
                self._odgovor(f.read(), "image/png", predpomni=True)
        elif pot == "/favicon.ico":
            # Pravi ICO (iz ikona.png, več velikosti); PNG pod imenom .ico nekateri brskalniki zavrnejo.
            with open(os.path.join(MAPA, "favicon.ico"), "rb") as f:
                self._odgovor(f.read(), "image/x-icon", predpomni=True)
        elif pot == "/slicica":
            # Sličica modela (render strani ali FreeCAD-ova iz FCStd); samo za datoteke iz seznama projektov, ne poljubne poti.
            import urllib.parse
            q = urllib.parse.parse_qs(self.path.partition("?")[2])
            iskana = (q.get("pot") or [""])[0]
            if not self._znana_datoteka(iskana):
                self._odgovor(b"", "text/plain", 404)
                return
            slika = _slicica_fcstd(iskana)
            if slika is None:
                self._odgovor(b"", "text/plain", 404)
            else:
                self._odgovor(slika, "image/png", predpomni=True)
        elif pot == "/model":
            self._odgovor(STANJE.posnetek())
        elif pot == "/zgradba":
            # Drevesna shema sestava čez datoteke (povezave App::Link); zgradi jo glavna nit.
            import urllib.parse
            q = urllib.parse.parse_qs(self.path.partition("?")[2])
            odgovor = {"konec": threading.Event(), "izpis": "", "napaka": "", "rezultat": None}
            STANJE.vrsta.put(("zgradba", {"ime": (q.get("ime") or [""])[0]}, odgovor))
            if not odgovor["konec"].wait(60) or odgovor["rezultat"] is None:
                self._odgovor(b'{"napaka":"ni zgradbe"}', koda=404)
            else:
                self._odgovor(json.dumps(odgovor["rezultat"], ensure_ascii=False).encode("utf-8"))
        elif pot == "/posnetek":
            # Geometrija poljubnega odprtega dokumenta (brez preklopa nanj) za sličico v seznamu odprtih dokumentov;
            # zgradi jo glavna nit (FreeCAD API), nit strežnika le počaka.
            import urllib.parse
            q = urllib.parse.parse_qs(self.path.partition("?")[2])
            odgovor = {"konec": threading.Event(), "izpis": "", "napaka": "", "rezultat": None}
            STANJE.vrsta_ozadje.put(("posnetek", {"ime": (q.get("ime") or [""])[0]}, odgovor))
            if not odgovor["konec"].wait(60) or odgovor["rezultat"] is None:
                self._odgovor(b'{"napaka":"ni posnetka"}', koda=404)
            else:
                self._odgovor(odgovor["rezultat"])
        elif pot == "/ukazi":
            self._odgovor(STANJE.ukazi())
        elif pot == "/projekti":
            self._odgovor(STANJE.projekti())
        elif pot == "/knjiznica":
            self._odgovor(json.dumps(zgradi_knjiznico(), ensure_ascii=False).encode("utf-8"))
        elif pot.startswith("/oblak/"):
            # Različice iz oblaka (oblak.py): klici v oblak tečejo tu, na niti strežnika.
            import urllib.parse
            q = {k: v[0] for k, v in urllib.parse.parse_qs(self.path.partition("?")[2]).items()}
            koda, telo = oblak_zahteva(OBLAK, "GET", pot, q)
            self._odgovor(json.dumps(telo, ensure_ascii=False).encode("utf-8"), koda=koda)
        elif pot == "/stanje":
            self._odgovor(json.dumps(STANJE.stanje(), ensure_ascii=False).encode("utf-8"))
        elif pot == "/mcp/orodja":
            # katalog orodij za AI (most lastno/mcp/freecad_mcp.py): orodja, viri, predloge, navodila
            self._odgovor(json.dumps(mcp_orodja.katalog(), ensure_ascii=False).encode("utf-8"))
        elif pot in ("/pomocnik", "/pomocnik/slika"):
            # pomočnik AI (pomocnik.py): stanje in koraki pogovora od N, slike orodij
            import urllib.parse
            q = {k: v[0] for k, v in urllib.parse.parse_qs(self.path.partition("?")[2]).items()}
            koda, vrsta, telo = pomocnik.zahteva_get(sys.modules[__name__], pot, q)
            self._odgovor(telo, vrsta, koda)
        elif pot == "/mcp/vir":
            import urllib.parse
            uri = (urllib.parse.parse_qs(self.path.partition("?")[2]).get("uri") or [""])[0]
            try:
                vir = mcp_orodja.vir(uri)
            except Exception as e:  # noqa: BLE001
                vir = {"uri": uri, "mimeType": "text/plain", "text": "Vir ni na voljo: %s" % e}
            self._odgovor(json.dumps(vir, ensure_ascii=False).encode("utf-8"), koda=200 if vir else 404)
        elif pot == "/tiskaj/stanje":
            # Plošča Tiskaj (nit strežnika, pomnjeno 2 s): za čipe tiskalnikov v vrstici stanja in zavihek Tiskanje.
            self._odgovor(json.dumps(tiskaj_stanje(), ensure_ascii=False).encode("utf-8"))
        elif pot == "/oblikovanje/stanje":
            self._odgovor(json.dumps(oblikovanje_stanje(), ensure_ascii=False).encode("utf-8"))
        elif pot == "/oblikovanje/render-plosca.js":
            with open(os.path.join(MAPA_OBLIKOVANJA, "render-plosca.js"), "rb") as f:
                self._odgovor(f.read(), "text/javascript; charset=utf-8")
        elif pot in ("/render/stanje", "/render/slika", "/render/seznam"):
            # Render (upodabljanje.py): stanje naloge, končna slika ali video, seznam renderjev te seje.
            import urllib.parse
            nid = (urllib.parse.parse_qs(self.path.partition("?")[2]).get("id") or [""])[0]
            if pot == "/render/seznam":
                self._odgovor(json.dumps(UPODABLJANJE.seznam(), ensure_ascii=False).encode("utf-8"))
            elif pot == "/render/stanje":
                s = UPODABLJANJE.stanje(nid)
                self._odgovor(json.dumps(s or {"napaka": "ni naloge"}, ensure_ascii=False).encode("utf-8"), koda=200 if s else 404)
            else:
                datoteka = UPODABLJANJE.datoteka(nid)
                if not datoteka or not os.path.isfile(datoteka):
                    self._odgovor(b"", "text/plain", 404)
                else:
                    with open(datoteka, "rb") as f:
                        self._odgovor(f.read(), "video/mp4" if datoteka.endswith(".mp4") else "image/png")
        elif pot == "/events":
            self._sse()
        else:
            self._odgovor(b"ni", "text/plain", 404)

    def do_POST(self):
        dolzina = int(self.headers.get("Content-Length") or 0)
        telo = self.rfile.read(dolzina) if dolzina else b""
        if self.headers.get("X-Zeton") != ZETON:
            self._odgovor(b'{"napaka":"zeton"}', koda=403)
            return
        try:
            podatki = json.loads(telo.decode("utf-8") or "{}")
        except ValueError:
            self._odgovor(b'{"napaka":"json"}', koda=400)
            return
        pot = self.path.split("?")[0]
        poti = {"/select": "izbira", "/ukaz": "ukaz", "/okolje": "okolje", "/okno": "okno",
                "/izhod": "izhod", "/skica": "skica", "/znacilnost": "znacilnost", "/obrazec": "obrazec",
                "/projekt": "projekt", "/drevo": "drevo"}
        if pot == "/mcp/orodje":
            # orodje za AI: teče na tej niti ali (FreeCAD API) prek vrste na glavni niti; odgovor {ok, vsebina, katalog}
            self._odgovor(mcp_orodja.izvedi(podatki.get("ime", ""), podatki.get("argumenti") or {},
                                            self.headers.get("X-Seja") or ""))
            return
        if pot == "/pomocnik":
            # pomočnik AI: poslji (besedilo, nastavitve) | potrdi (id, odobri) | ustavi | nov; zanka teče v svoji niti
            telo = pomocnik.zahteva_post(sys.modules[__name__], podatki)
            self._odgovor(json.dumps(telo, ensure_ascii=False).encode("utf-8"))
            return
        if pot == "/mcp/odgovor":
            # stran v brskalniku odgovarja na zahtevo orodja (slika pogleda, kamera, okno Pripravi)
            self._odgovor(json.dumps({"ok": mcp_orodja.brskalnik_odgovor(podatki)}).encode("utf-8"))
            return
        if pot == "/tiskaj/natisni":
            # Natisni iz drevesa: glavna nit izvozi STEP v vhodno mapo plošče (mapo določi tukaj nit strežnika, da glavna
            # nit ne čaka na omrežje), nato plošča dobi oznako, da pripravo vodi uporabnik (sicer bi datoteko narezala sama).
            podatki["mapa"] = _tiskaj_vhod_mapa()
            odgovor = {"konec": threading.Event(), "izpis": "", "napaka": "", "rezultat": None}
            STANJE.vrsta.put(("tiskaj", podatki, odgovor))
            if not odgovor["konec"].wait(120):
                telo = {"ok": False, "sporocilo": "FreeCAD še dela; poglej čez nekaj časa."}
            elif odgovor["napaka"]:
                telo = {"ok": False, "sporocilo": "Napaka v FreeCAD-u: " + odgovor["napaka"].strip().splitlines()[-1]}
            else:
                telo = odgovor["rezultat"] or {"ok": False, "sporocilo": "Brez odgovora."}
            if telo.get("ok") and telo.get("datoteke"):
                telo["plosca"] = _tiskaj_oznaci_rocno(list(telo["datoteke"]))
            self._odgovor(json.dumps(telo, ensure_ascii=False).encode("utf-8"))
            return
        if pot == "/tisk/lega":
            # Lega za tisk (tisk_lega.py): glavna nit le zmreži kose, iskanje orientacije (numpy) teče tu, na niti strežnika.
            odgovor = {"konec": threading.Event(), "izpis": "", "napaka": "", "rezultat": None}
            STANJE.vrsta.put(("tisk_mreze", podatki, odgovor))
            if not odgovor["konec"].wait(120):
                telo = {"ok": False, "sporocilo": "FreeCAD še dela; poglej čez nekaj časa."}
            elif odgovor["napaka"]:
                telo = {"ok": False, "sporocilo": "Napaka v FreeCAD-u: " + odgovor["napaka"].strip().splitlines()[-1]}
            elif not (odgovor["rezultat"] or {}).get("ok"):
                telo = odgovor["rezultat"] or {"ok": False, "sporocilo": "Brez odgovora."}
            else:
                try:
                    kot = min(max(float(podatki.get("kot_previsa") or 45), 20.0), 70.0)
                    telo = tisk_lega_kosov(odgovor["rezultat"], kot)
                except Exception:  # noqa: BLE001
                    _log("lega za tisk: %s" % traceback.format_exc())
                    telo = {"ok": False, "sporocilo": "Analiza lege ni uspela: " + traceback.format_exc().strip().splitlines()[-1]}
            self._odgovor(json.dumps(telo, ensure_ascii=False).encode("utf-8"))
            return
        if pot == "/render":
            self._odgovor(json.dumps(render_modela(podatki), ensure_ascii=False).encode("utf-8"))
            return
        if pot == "/render/ustavi":
            self._odgovor(json.dumps({"ok": UPODABLJANJE.ustavi(podatki.get("id", ""))}).encode("utf-8"))
            return
        if pot == "/oblikovanje/zazeni":
            ok, sporocilo = oblikovanje_zazeni()
            self._odgovor(json.dumps({"ok": ok, "sporocilo": sporocilo}, ensure_ascii=False).encode("utf-8"))
            return
        if pot == "/tiskaj/datoteka":
            self._odgovor(json.dumps(tiskaj_datoteka(podatki.get("pot", "")), ensure_ascii=False).encode("utf-8"))
            return
        if pot == "/tiskaj/zazeni":
            ok, sporocilo = tiskaj_zazeni()
            self._odgovor(json.dumps({"ok": ok, "sporocilo": sporocilo}, ensure_ascii=False).encode("utf-8"))
            return
        if pot == "/videz":
            # Videz kosov (videz.py): seznam prednastavitev, nastavitev kosu, pločevina vsem kosom iz pločevine.
            odgovor = {"konec": threading.Event(), "izpis": "", "napaka": "", "rezultat": None}
            STANJE.vrsta.put(("videz", podatki, odgovor))
            if not odgovor["konec"].wait(120):
                telo = {"ok": False, "sporocilo": "FreeCAD še dela; poglej čez nekaj časa."}
            elif odgovor["napaka"]:
                telo = {"ok": False, "sporocilo": "Napaka v FreeCAD-u: " + odgovor["napaka"].strip().splitlines()[-1]}
            else:
                telo = odgovor["rezultat"]
            self._odgovor(json.dumps(telo, ensure_ascii=False).encode("utf-8"))
            return
        if pot == "/slicica":
            # Render modela iz strani (PNG kot data URL) za datoteko dokumenta; shrani se v niti strežnika (samo datoteke).
            import base64
            iskana = podatki.get("pot", "")
            png = podatki.get("png", "")
            if not self._znana_datoteka(iskana):
                self._odgovor(b'{"napaka":"neznana datoteka"}', koda=404)
                return
            try:
                bajti = base64.b64decode(png.partition(",")[2] if png.startswith("data:") else png)
            except (ValueError, TypeError):
                bajti = b""
            if not bajti.startswith(b"\x89PNG") or len(bajti) > 2_000_000 or not _uporabna_slicica(bajti):
                self._odgovor(b'{"napaka":"png"}', koda=400)   # tudi prazen render (npr. še brez geometrije) se ne shrani
                return
            try:
                _shrani_slicico(iskana, bajti)
            except OSError as e:
                self._odgovor(json.dumps({"napaka": str(e)}).encode("utf-8"), koda=500)
                return
            STANJE.zadnji_projekti = 0.0   # seznam se pošlje znova z novo različico sličice
            self._odgovor(b'{"ok":true}')
        elif pot == "/python":
            # Počaka na izvedbo na glavni niti in vrne izpis, napako in spremenljivko "rezultat".
            odgovor = {"konec": threading.Event(), "izpis": "", "napaka": "", "rezultat": None}
            STANJE.vrsta.put(("python", podatki, odgovor))
            koncano = odgovor["konec"].wait(float(podatki.get("cakaj", 120) or 120))
            telo = {"ok": koncano and not odgovor["napaka"], "koncano": koncano, "izpis": odgovor["izpis"],
                    "napaka": odgovor["napaka"], "rezultat": odgovor["rezultat"]}
            self._odgovor(json.dumps(telo, ensure_ascii=False, default=str).encode("utf-8"))
        elif pot.startswith("/oblak/"):
            koda, telo = oblak_zahteva(OBLAK, "POST", pot, podatki)
            self._odgovor(json.dumps(telo, ensure_ascii=False).encode("utf-8"), koda=koda)
        elif pot == "/knjiznica":
            # Knjižnica standardnih delov: glavna nit odpre kos in ga vstavi v aktivni sestav; brskalnik počaka.
            odgovor = {"konec": threading.Event(), "izpis": "", "napaka": "", "rezultat": None}
            STANJE.vrsta.put(("knjiznica", podatki, odgovor))
            if not odgovor["konec"].wait(120):
                telo = {"ok": False, "sporocilo": "FreeCAD še dela; poglej čez nekaj časa."}
            elif odgovor["napaka"]:
                telo = {"ok": False, "sporocilo": "Napaka v FreeCAD-u: " + odgovor["napaka"].strip().splitlines()[-1]}
            else:
                telo = odgovor["rezultat"]
            self._odgovor(json.dumps(telo, ensure_ascii=False).encode("utf-8"))
        elif pot == "/standardni":
            # Baza standardnih delov: glavna nit premakne kos in shrani sestave; brskalnik počaka na sporočilo.
            odgovor = {"konec": threading.Event(), "izpis": "", "napaka": "", "rezultat": None}
            STANJE.vrsta.put(("standardni", podatki, odgovor))
            if not odgovor["konec"].wait(300):
                telo = {"ok": False, "sporocilo": "FreeCAD še dela (premik traja dlje kot 5 min); poglej čez nekaj časa."}
            elif odgovor["napaka"]:
                telo = {"ok": False, "sporocilo": "Napaka v FreeCAD-u: " + odgovor["napaka"].strip().splitlines()[-1]}
            else:
                telo = odgovor["rezultat"]
            self._odgovor(json.dumps(telo, ensure_ascii=False).encode("utf-8"))
        elif pot in poti:
            STANJE.vrsta.put((poti[pot], podatki, None))
            self._odgovor(b'{"ok":true}')
        else:
            self._odgovor(b"ni", "text/plain", 404)

    def _poslji_sse(self, dogodek, podatki):
        vrstica = "event: %s\ndata: %s\n\n" % (dogodek, json.dumps(podatki, ensure_ascii=False))
        self.wfile.write(vrstica.encode("utf-8"))
        self.wfile.flush()

    def _sse(self):
        q = STANJE.nov_odjemalec()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        try:
            # Žeton ob vsaki povezavi: zavihek, odprt pred ponovnim zagonom FreeCAD-a, dobi novega.
            self._poslji_sse("zeton", {"zeton": ZETON})
            self._poslji_sse("model", {"verzija": STANJE.verzija})
            self._poslji_sse("izbira", STANJE.izbira)
            self._poslji_sse("aktivni", dict(STANJE.aktivni))
            self._poslji_sse("okolje", dict(STANJE.okolje))
            self._poslji_sse("obrazec", STANJE.obrazec)
            self._poslji_sse("projekti", json.loads(STANJE.projekti()))
            STANJE.vrsta.put(("skica-posnetek", {}, None))
            while True:
                try:
                    dogodek, podatki = q.get(timeout=15)
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                    continue
                self._poslji_sse(dogodek, podatki)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass
        finally:
            STANJE.odstrani_odjemalca(q)


# ---------------------------------------------------------------------------
# Vzorčni dokument, če ni odprtega

def _vzorcni_dokument():
    import Part
    doc = App.newDocument("Preizkus")
    skatla = Part.makeBox(60, 40, 20)
    luknja = Part.makeCylinder(8, 20, App.Vector(30, 20, 0))
    ohisje = skatla.cut(luknja)
    navpicni = [e for e in ohisje.Edges if e.Curve.__class__.__name__ == "Line" and abs(e.Length - 20) < 1e-6]
    ohisje = ohisje.makeFillet(3, navpicni)
    o1 = doc.addObject("Part::Feature", "Ohisje")
    o1.Label = "Ohisje"
    o1.Shape = ohisje
    o2 = doc.addObject("Part::Feature", "Cep")
    o2.Label = "Cep"
    o2.Shape = Part.makeCylinder(5, 12, App.Vector(50, 10, 20))
    doc.recompute()
    if IMA_OKNO:
        try:
            v1 = o1.ViewObject.ShapeAppearance[0]
            v1.DiffuseColor = (0.55, 0.65, 0.85, 1.0)
            o1.ViewObject.ShapeAppearance = (v1,)
            v2 = o2.ViewObject.ShapeAppearance[0]
            v2.DiffuseColor = (0.90, 0.55, 0.25, 1.0)
            o2.ViewObject.ShapeAppearance = (v2,)
        except Exception:  # noqa: BLE001
            pass
        if Gui.getMainWindow().isVisible():
            try:
                Gui.SendMsgToActiveView("ViewFit")
            except Exception:  # noqa: BLE001
                pass
    return doc


def _je_vzorec(doc):
    """Nedotaknjen vzorčni dokument (_vzorcni_dokument): brez datoteke, le Ohisje in Cep, brez korakov razveljavitve.
    Tak dokument nastane tudi iz Obnove dokumentov po nasilnem koncu prejšnjega primerka (ime Unnamed, oznaka Preizkus)."""
    return (not doc.FileName and doc.Label.startswith("Preizkus")
            and sorted(o.Name for o in doc.Objects) == ["Cep", "Ohisje"]
            and not doc.UndoCount and not doc.RedoCount)


# Kopije zaprtih dvojnikov (morda nosijo obnovljene spremembe), da se nič ne izgubi.
MAPA_DVOJNIKOV = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "FreeCAD-splet", "dvojniki")


def _zapri_dvojnike():
    """Zapre dvojnike, ki jih pusti FreeCAD-ova Obnova dokumentov: ta odpre kopijo vsakega dokumenta iz vsakega
    nasilno končanega primerka in ne preveri, ali je ista datoteka že odprta. Od dokumentov z isto datoteko ostane
    tisti z najnovejšim LastModifiedDate (ob enakem prvi), ostali se pred zaprtjem shranijo kot kopija v
    MAPA_DVOJNIKOV. Vzorčni dokumenti se zaprejo, ko je odprt kakšen drug dokument; sicer ostane en.
    Vrne število zaprtih dokumentov."""
    dokumenti = list(App.listDocuments().values())
    zapri = []
    vzorci = [d for d in dokumenti if _je_vzorec(d)]
    zapri += vzorci if len(vzorci) < len(dokumenti) else vzorci[1:]
    namesto = {}   # ime zaprtega dvojnika -> ime dokumenta, ki ostane (ta postane aktiven namesto njega)
    po_poti = {}
    for d in dokumenti:
        if d.FileName:
            po_poti.setdefault(os.path.normcase(os.path.normpath(d.FileName)), []).append(d)

    def cas(d):
        c = d.LastModifiedDate
        return c if c and c[0].isdigit() else ""

    for skupina in po_poti.values():
        if len(skupina) < 2:
            continue
        ostane = max(skupina, key=cas)
        for d in skupina:
            if d is ostane:
                continue
            try:
                os.makedirs(MAPA_DVOJNIKOV, exist_ok=True)
                kopija = os.path.join(MAPA_DVOJNIKOV, "%s (%s) %s.FCStd" % (
                    os.path.splitext(os.path.basename(d.FileName))[0], d.Name, time.strftime("%Y%m%d-%H%M%S")))
                d.saveCopy(kopija)
                _log("dvojnik %s (%s): kopija %s" % (d.Name, d.FileName, kopija))
            except Exception as e:  # noqa: BLE001
                _log("dvojnik %s ostane odprt, kopija ni uspela: %r" % (d.Name, e))
                continue
            zapri.append(d)
            namesto[d.Name] = ostane.Name
    imena = [d.Name for d in zapri]
    aktivni = App.ActiveDocument.Name if App.ActiveDocument is not None else None
    if aktivni in imena:
        ostali = [d.Name for d in dokumenti if d.Name not in imena]
        if aktivni in namesto:
            App.setActiveDocument(namesto[aktivni])
        elif ostali:
            App.setActiveDocument(ostali[0])
    for ime in imena:
        _log("zapiram dvojnik ali vzorec: %s" % ime)
        App.closeDocument(ime)
    return len(imena)


# ---------------------------------------------------------------------------
# Zagon

# Povezava za druga orodja (izvedi.py, druge seje): vrata in žeton tega primerka.
DATOTEKA_POVEZAVE = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
                                 "FreeCAD-splet", "povezava.json")


def _zapisi_povezavo():
    try:
        os.makedirs(os.path.dirname(DATOTEKA_POVEZAVE), exist_ok=True)
        with open(DATOTEKA_POVEZAVE, "w", encoding="utf-8") as f:
            json.dump({"vrata": VRATA, "zeton": ZETON, "pid": os.getpid(), "zacetek": time.time()}, f)
    except OSError as e:
        _log("povezave ni bilo mogoče zapisati: %s" % e)


def _pobrisi_povezavo():
    try:
        with open(DATOTEKA_POVEZAVE, encoding="utf-8") as f:
            moja = json.load(f).get("pid") == os.getpid()
        if moja:  # brisati šele po zaprtju datoteke (Windows)
            os.remove(DATOTEKA_POVEZAVE)
    except (OSError, ValueError):
        pass


def _qt_izbira_datotek(aplikacija):
    """FreeCAD naj za izbiro datotek uporablja Qt-jevo okno namesto okna Windows: le tega je mogoče
    prebrati in upravljati iz brskalnika. Nastavitev je skupna z nameščenim FreeCAD-om, zato jo ob
    izhodu vrnemo, kot je bila."""
    skupina = App.ParamGet("User parameter:BaseApp/Preferences/Dialog")
    imela = "DontUseNativeDialog" in skupina.GetBools()
    prej = skupina.GetBool("DontUseNativeDialog", False)
    skupina.SetBool("DontUseNativeDialog", True)

    def vrni():
        if imela:
            skupina.SetBool("DontUseNativeDialog", prej)
        else:
            skupina.RemBool("DontUseNativeDialog")
        try:
            OBLAK.odkleni_vse()   # PDM: tudi ob zaprtju okna z X zaklepi ne ostanejo v oblaku
        except Exception as e:  # noqa: BLE001
            _log("oblak: odklep ob koncu: %r" % e)
        _pobrisi_povezavo()

    aplikacija.aboutToQuit.connect(vrni)


def zazeni():
    global _FILTER
    if IMA_OKNO:
        # Najprej skrijemo okno (možnost --hidden ni uporabna: FreeCAD se z njo po skripti konča).
        from PySide6 import QtCore, QtWidgets
        mw = Gui.getMainWindow()

        class ZapiranjeOkna(QtCore.QObject):
            """Ko uporabnik zapre okno FreeCAD-a (X), program konča, ko ni več odprtih vprašanj."""
            def eventFilter(self, obj, dogodek):
                if obj is mw and dogodek.type() == QtCore.QEvent.Type.Close:
                    STANJE.zapiranje_okna = True
                    STANJE.zadnji_pregled = 0.0
                return False

        class NevidnaOkna(QtCore.QObject):
            """Vsako novo okno FreeCAD-a (pogovor, sporočilo, izbira datoteke) ostane nevidno;
            njegovo vsebino brskalnik dobi kot obrazec (preveri_obrazec)."""
            def eventFilter(self, obj, dogodek):
                if dogodek.type() == QtCore.QEvent.Type.Show and STANJE.skrivaj_okna():
                    try:
                        if isinstance(obj, QtWidgets.QWidget) and obj.isWindow() and obj is not mw \
                                and obj.windowType() in (QtCore.Qt.WindowType.Window, QtCore.Qt.WindowType.Dialog,
                                                         QtCore.Qt.WindowType.Tool, QtCore.Qt.WindowType.Sheet):
                            _nevidno_okno(obj)
                            STANJE.skrita_okna = [w for w in STANJE.skrita_okna if _veljaven(w)] + [obj]
                            STANJE.zadnji_obrazec = 0.0
                    except Exception:  # noqa: BLE001
                        pass
                return False

        # Skrito glavno okno ne sme pomeniti, da se program konča ob zaprtju zadnjega pogovornega okna.
        aplikacija = QtWidgets.QApplication.instance()
        aplikacija.setQuitOnLastWindowClosed(False)
        _FILTER = ZapiranjeOkna()
        mw.installEventFilter(_FILTER)
        if OKNO_SKRITO:
            _skrij_okno()
            global _FILTER_OKEN
            _FILTER_OKEN = NevidnaOkna()
            aplikacija.installEventFilter(_FILTER_OKEN)
            _qt_izbira_datotek(aplikacija)
            _log("okno FreeCAD-a je skrito; pogovori in opravila so obrazci v brskalniku")

    if App.ActiveDocument is None:
        _vzorcni_dokument()

    App.addDocumentObserver(OpazovalecDokumenta())
    if IMA_OKNO:
        Gui.Selection.addObserver(OpazovalecIzbire())
        _nalozi_okolja()
        try:
            STANJE.zgradi_ukaze()
        except Exception:  # noqa: BLE001
            _log("ukazov ni bilo mogoče zgraditi: %s" % traceback.format_exc())

    naslov = "http://127.0.0.1:%d/" % VRATA
    try:
        streznik = Streznik(("127.0.0.1", VRATA), Zahteva)
    except OSError as e:
        _log("vrata %d so že zasedena (%s): spletni strežnik že teče v drugem FreeCAD-u; ta primerek ostane brez njega. "
             "Zapri drugega ali nastavi SPLET_VRATA." % (VRATA, e))
        return
    nit = threading.Thread(target=streznik.serve_forever, name="splet-streznik", daemon=True)
    nit.start()
    _log("strežnik teče na %s (okno: %s)" % (naslov, "da" if IMA_OKNO else "ne"))
    _zapisi_povezavo()

    STANJE.zgradi()
    if IMA_OKNO:
        STANJE.posodobi_izbiro()

    if ODPRI_BRSKALNIK:
        try:
            webbrowser.open(naslov)
        except Exception:  # noqa: BLE001
            pass

    if IMA_OKNO:
        from PySide6 import QtCore
        global _CASOVNIK
        _CASOVNIK = QtCore.QTimer()
        _CASOVNIK.timeout.connect(STANJE.obdelaj)
        _CASOVNIK.start(50)
    else:
        _log("brez okna: zanka teče, prekini s Ctrl+C")
        try:
            while True:
                STANJE.obdelaj()
                time.sleep(0.05)
        except KeyboardInterrupt:
            pass
        finally:
            streznik.shutdown()


_CASOVNIK = None
_FILTER = None
_FILTER_OKEN = None
zazeni()
