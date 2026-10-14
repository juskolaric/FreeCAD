# -*- coding: utf-8 -*-
"""5. stopnja »Toplota« spletnega FreeCAD-a: toplotna analiza boxa na soncu (od 2026-10-14, plan TOPLOTNA-ANALIZA-PLAN.md).

Stran lastno/toplota/toplota.html je okvir čez 3D pogled (kot Tiskanje, Grafika). Podatki projekta so v
<Oblak/3D modeliranje/<Projekt>>/Toplota/ (nastavitve.json, rezultati bilance, mke/). Projekt se določi iz poti
aktivnega dokumenta, ki jo pošlje stran (ta jo dobi iz staršovske strani), strežnik ne kliče FreeCAD API-ja na niti HTTP.

  GET  /toplota                      stran
  GET  /toplota/stanje?pot=<dokument> projekt, nastavitve, rezultati bilance in MKE, kaj teče
  GET  /toplota/slika?mapa=&pot=     slika iz mape Toplota projekta (samo PNG znotraj Oblak/3D modeliranje)
  POST /toplota/nastavi {mapa, nastavitve}      shrani nastavitve.json
  POST /toplota/izracun {mapa, obseg, lokacije?, barve?}   bilančni model v niti (pvlib + ht; lastno/toplota/bilanca.py)
  POST /toplota/model {mapa, dokument}          glavna nit: poenostavljena kopija sestava + analiza FEM (model_mke.py)
  POST /toplota/mke {mapa}                      FreeCADCmd v ozadju: mreža + CalculiX (mke_zagon.py)
  POST /toplota/odpri {mapa}                    glavna nit: odpre model MKE v FreeCAD-u (brskalnik ga pokaže)
"""
import json
import os
import subprocess
import sys
import threading
import time
import traceback

MAPA_SPLET = os.path.dirname(os.path.abspath(__file__))
# FreeCAD brez PYTHONHOME uporablja site-packages sistemskega Pythona 3.11; pvlib, ht, pandas, matplotlib so v pixi okolju
try:
    import FreeCAD as _App
    _SP = os.path.normpath(os.path.join(_App.getHomePath(), "..", "Lib", "site-packages"))
    if os.path.isdir(_SP) and _SP not in sys.path:
        sys.path.append(_SP)
except Exception:  # noqa: BLE001
    pass
MAPA_TOPLOTA = os.path.normpath(os.path.join(MAPA_SPLET, "..", "toplota"))
if MAPA_TOPLOTA not in sys.path:
    sys.path.insert(0, MAPA_TOPLOTA)

S = None   # modul strežnika (povezi)
STANJE = {"izracun": {"tece": False, "napredek": "", "napaka": "", "konec": 0.0},
          "mke": {"proces": None, "mapa": "", "zacetek": 0.0, "napaka": ""}}


def povezi(modul):
    global S
    S = modul


def _log(s):
    if S is not None and hasattr(S, "_log"):
        S._log("toplota: " + s)


def _oblak():
    return os.path.normpath(getattr(S, "MAPA_OBLAK", os.path.join(os.path.expanduser("~"), "Oblak", "3D modeliranje")))


def _v_oblaku(pot):
    try:
        return os.path.normpath(os.path.abspath(pot)).lower().startswith(_oblak().lower() + os.sep)
    except Exception:  # noqa: BLE001
        return False


def projekt_iz_poti(pot):
    """Mapa projekta (neposredna podmapa Oblak/3D modeliranje) za pot dokumenta; None, če je zunaj."""
    if not pot or not _v_oblaku(pot):
        return None
    rel = os.path.normpath(os.path.abspath(pot))[len(_oblak()) + 1:]
    prvi = rel.split(os.sep)[0]
    return os.path.join(_oblak(), prvi) if prvi else None


def _mapa_toplote(mapa):
    """Preveri in vrne mapo Toplota projekta (iz zahteve: mapa projekta ali mapa Toplota)."""
    if not mapa or not _v_oblaku(mapa):
        raise ValueError("Mapa projekta mora biti v Oblak/3D modeliranje.")
    mapa = os.path.normpath(os.path.abspath(mapa))
    if os.path.basename(mapa).lower() != "toplota":
        mapa = os.path.join(mapa, "Toplota")
    os.makedirs(mapa, exist_ok=True)
    return mapa


def _json(pot):
    try:
        with open(pot, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return None


# ----------------------------------------------------------------------------- GET
def stran():
    with open(os.path.join(MAPA_TOPLOTA, "toplota.html"), "rb") as f:
        return f.read()


def stanje(q):
    import bilanca
    pot_dok = (q.get("pot") or [""])[0]
    rocno = (q.get("mapa") or [""])[0]
    projekt = projekt_iz_poti(rocno) if rocno else None
    if projekt is None:
        projekt = projekt_iz_poti(pot_dok)
    try:
        projekti = sorted(d for d in os.listdir(_oblak()) if os.path.isdir(os.path.join(_oblak(), d)) and not d.startswith((".", "_")))
    except OSError:
        projekti = []
    out = {"ok": True, "projekt": projekt, "ime_projekta": os.path.basename(projekt) if projekt else "", "projekti": projekti,
           "s_toploto": [d for d in projekti if os.path.isdir(os.path.join(_oblak(), d, "Toplota"))], "oblak": _oblak(),
           "dokument": pot_dok, "izracun": {k: v for k, v in STANJE["izracun"].items()},
           "mke_tece": STANJE["mke"]["proces"] is not None and STANJE["mke"]["proces"].poll() is None}
    if projekt:
        mapa = _mapa_toplote(projekt)
        out["mapa"] = mapa
        sestavi = []
        try:
            for o in json.loads(S.STANJE._projekti.decode("utf-8") if isinstance(S.STANJE._projekti, bytes) else S.STANJE._projekti).get("odprti", []):
                if o.get("vrsta") == "sestav" and o.get("pot") and projekt_iz_poti(o["pot"]) and os.path.normcase(projekt_iz_poti(o["pot"])) == os.path.normcase(projekt):
                    sestavi.append({"oznaka": o["oznaka"], "pot": o["pot"], "v_korenu": os.path.normcase(os.path.dirname(os.path.normpath(o["pot"]))) == os.path.normcase(projekt)})
        except Exception:  # noqa: BLE001
            pass
        sestavi.sort(key=lambda x: (not x["v_korenu"], x["oznaka"]))
        out["sestavi"] = sestavi
        out["nastavitve"] = bilanca.nalozi(mapa)
        out["rezultati"] = _json(os.path.join(mapa, "rezultati.json"))
        mke = os.path.join(mapa, "mke")
        out["mke"] = {"model": _json(os.path.join(mke, "model.json")), "rezultati": _json(os.path.join(mke, "rezultati.json")),
                      "stanje": _json(os.path.join(mke, "stanje.json")), "napaka": STANJE["mke"]["napaka"]}
        if STANJE["mke"]["proces"] is not None and STANJE["mke"]["proces"].poll() is not None and STANJE["mke"]["proces"].returncode:
            out["mke"]["napaka"] = out["mke"]["napaka"] or ("mke_zagon.py se je končal s kodo %d (dnevnik.txt)" % STANJE["mke"]["proces"].returncode)
    return out


def slika(q):
    """(telo, vrsta, koda) za PNG iz mape Toplota projekta."""
    mapa = (q.get("mapa") or [""])[0]
    rel = (q.get("pot") or [""])[0].replace("\\", "/")
    if not mapa or not rel or ".." in rel or not rel.lower().endswith(".png"):
        return b"", "text/plain", 404
    try:
        pot = os.path.normpath(os.path.join(_mapa_toplote(mapa), rel))
    except ValueError:
        return b"", "text/plain", 404
    if not os.path.isfile(pot):
        return b"", "text/plain", 404
    with open(pot, "rb") as f:
        return f.read(), "image/png", 200


# ----------------------------------------------------------------------------- POST (nit strežnika)
def nastavi(podatki):
    import bilanca
    mapa = _mapa_toplote(podatki.get("mapa", ""))
    nast = podatki.get("nastavitve")
    if not isinstance(nast, dict):
        return {"ok": False, "sporocilo": "manjkajo nastavitve"}
    staro = bilanca.nalozi(mapa)
    for k, v in nast.items():
        if isinstance(v, dict) and isinstance(staro.get(k), dict) and k not in ("naprave_W", "lokacije", "barve"):
            staro[k].update(v)
        else:
            staro[k] = v
    bilanca.shrani(mapa, staro)
    return {"ok": True, "nastavitve": staro}


def izracun(podatki):
    """Bilančni model v niti; napredek v STANJE['izracun']."""
    import bilanca
    if STANJE["izracun"]["tece"]:
        return {"ok": False, "sporocilo": "Izračun že teče."}
    mapa = _mapa_toplote(podatki.get("mapa", ""))
    obseg = "leto" if podatki.get("obseg") == "leto" else "teden"
    lokacije = podatki.get("lokacije") or None
    barve = podatki.get("barve") or None
    nast = bilanca.nalozi(mapa)
    st = STANJE["izracun"]
    st.update({"tece": True, "napredek": "začenjam", "napaka": "", "konec": 0.0, "mapa": mapa})

    def delo():
        try:
            bilanca.izracun(mapa, nast, obseg=obseg, lokacije=lokacije, barve=barve,
                            napredek=lambda s: st.__setitem__("napredek", s))
            st["napredek"] = "končano"
        except Exception:  # noqa: BLE001
            st["napaka"] = traceback.format_exc().strip().splitlines()[-1]
            _log("izračun: " + traceback.format_exc())
        finally:
            st["tece"] = False
            st["konec"] = time.time()

    threading.Thread(target=delo, name="toplota-izracun", daemon=True).start()
    return {"ok": True}


def _freecadcmd():
    import FreeCAD as App
    for k in (os.path.join(os.path.dirname(App.getHomePath().rstrip("/\\")), "bin", "FreeCADCmd.exe"),
              os.path.join(App.getHomePath(), "bin", "FreeCADCmd.exe")):
        if os.path.isfile(k):
            return k
    return ""


def mke(podatki):
    """FreeCADCmd v ozadju: mreža + CalculiX na modelu v <Toplota>/mke."""
    p = STANJE["mke"]["proces"]
    if p is not None and p.poll() is None:
        return {"ok": False, "sporocilo": "MKE že teče."}
    mapa = os.path.join(_mapa_toplote(podatki.get("mapa", "")), "mke")
    if not os.path.isfile(os.path.join(mapa, "model.json")):
        return {"ok": False, "sporocilo": "Najprej zgradi model (gumb Zgradi model za MKE)."}
    cmd = _freecadcmd()
    if not cmd:
        return {"ok": False, "sporocilo": "FreeCADCmd.exe ni najden."}
    for ime in ("stanje.json", "rezultati.json"):
        try:
            os.remove(os.path.join(mapa, ime))
        except OSError:
            pass
    okolje = dict(os.environ)
    okolje["PYTHONIOENCODING"] = "utf-8"
    okolje["TOPLOTA_MKE_MAPA"] = mapa
    dnevnik = open(os.path.join(mapa, "izpis.txt"), "w", encoding="utf-8")
    STANJE["mke"].update({"proces": subprocess.Popen([cmd, os.path.join(MAPA_TOPLOTA, "mke_zagon.py")], stdout=dnevnik,
                                                     stderr=subprocess.STDOUT, env=okolje, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)),
                          "mapa": mapa, "zacetek": time.time(), "napaka": ""})
    _log("MKE zagnan: %s" % mapa)
    return {"ok": True}


# ----------------------------------------------------------------------------- glavna nit
def glavna(stanje_streznika, podatki):
    """Ukaz »toplota« na glavni niti: model (zgradi kopijo sestava + FEM) ali odpri (model v FreeCAD-u)."""
    import FreeCAD as App
    dejanje = podatki.get("dejanje")
    mapa = _mapa_toplote(podatki.get("mapa", ""))
    if dejanje == "model":
        import bilanca
        import model_mke
        import importlib
        importlib.reload(model_mke)
        ime = podatki.get("dokument", "")
        doc = None
        for d in App.listDocuments().values():
            if ime and (d.Label == ime or d.Name == ime or os.path.normcase(d.FileName) == os.path.normcase(ime)):
                doc = d
                break
        if doc is None:
            # sestav projekta: najprej tisti v korenu mape projekta (npr. Slim A.FCStd)
            projekt = os.path.dirname(mapa)
            kandidati = [d for d in App.listDocuments().values() if d.FileName and projekt_iz_poti(d.FileName)
                         and os.path.normcase(projekt_iz_poti(d.FileName)) == os.path.normcase(projekt)
                         and any(o.TypeId == "Assembly::AssemblyObject" for o in d.Objects)]
            kandidati.sort(key=lambda d: (os.path.normcase(os.path.dirname(d.FileName)) != os.path.normcase(projekt), d.Label))
            doc = kandidati[0] if kandidati else None
        if doc is None or not any(o.TypeId == "Assembly::AssemblyObject" for o in doc.Objects):
            return {"ok": False, "sporocilo": "V projektu ni odprtega sestava (odpri npr. Slim A v 2. stopnji)."}
        nast = bilanca.nalozi(mapa)
        # že odprt stari model zapri (brez shranjevanja), da ga nova gradnja ne podvoji
        for d in list(App.listDocuments().values()):
            if d.Label == doc.Label + " toplota":
                App.closeDocument(d.Name)
        opis, novi = model_mke.zgradi(doc, nast, os.path.join(mapa, "mke"), log=_log)
        try:
            import FreeCADGui as Gui
            if Gui.getDocument(novi.Name):
                Gui.getDocument(novi.Name).Modified = False
        except Exception:  # noqa: BLE001
            pass
        # aktivnega dokumenta ne zamenja (druge seje delajo v svojih); model odpre gumb »Odpri model« (dejanje odpri)
        if doc is not None and doc.Name in App.listDocuments():
            App.setActiveDocument(doc.Name)
        stanje_streznika.umazano = True
        return {"ok": True, "opis": {k: v for k, v in opis.items() if k != "telesa"}, "teles": len(opis["telesa"]), "dokument": novi.Label}
    if dejanje == "odpri":
        model = _json(os.path.join(mapa, "mke", "model.json"))
        if not model or not os.path.isfile(model.get("pot", "")):
            return {"ok": False, "sporocilo": "Modela še ni."}
        pot = model["pot"]
        for d in App.listDocuments().values():
            if os.path.normcase(d.FileName) == os.path.normcase(pot):
                App.setActiveDocument(d.Name)
                stanje_streznika.umazano = True
                return {"ok": True, "dokument": d.Label}
        d = App.openDocument(pot)
        App.setActiveDocument(d.Name)
        stanje_streznika.umazano = True
        return {"ok": True, "dokument": d.Label}
    return {"ok": False, "sporocilo": "neznano dejanje"}
