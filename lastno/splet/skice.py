"""Skice za iPad (Free 3D, od 2026-10-21): posnetek pogleda Strojnega risanja gre na iPad, uporabnik po njem riše s
Pencilom in ga pošlje nazaj, AI ga prebere, popravi model in pošlje nov posnetek v pregled.

Skice hrani samostojen strežnik Free 3D (CAD in 3D/Free 3D/streznik/free3d.py, vrata 3038 po Orodja/ports.json, sliši
na domačem omrežju z žetonom iz ~/.free3d/nastavitve.json). Ta modul ga po potrebi zažene (sistemski pythonw brez okna,
kot Grafika Studio) in mu pošilja posnetke; orodje MCP `skice` teče na niti strežnika. Gumb »Na iPad« v brskalniku
kliče isto orodje (POST /mcp/orodje, akcija poslji, izvor uporabnik).

Registracija: mcp_orodja.py na koncu naloži (in ob vroči zamenjavi znova naloži) ta modul.
"""

import base64
import http.client
import json
import os
import subprocess
import time

import FreeCAD as App

import mcp_orodja as M

VRATA = int(os.environ.get("FREE3D_VRATA", "3038"))
NASTAVITVE = os.path.join(os.path.expanduser("~"), ".free3d", "nastavitve.json")
STANJA = ("nova", "poslana", "resena", "arhiv")


def _mapa_free3d():
    prepis = os.environ.get("FREE3D_MAPA", "").strip()
    koren = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))   # repo FreeCAD
    for k in ([prepis] if prepis else []) + [os.path.join(koren, "..", "Free 3D")]:
        if k and os.path.isfile(os.path.join(k, "streznik", "free3d.py")):
            return os.path.normpath(k)
    return ""


def _zeton():
    try:
        with open(NASTAVITVE, encoding="utf-8") as f:
            return json.load(f).get("zeton", "")
    except (OSError, ValueError):
        return ""


def _zahteva(metoda, pot, telo=None, cakaj=15.0):
    """HTTP do strežnika Free 3D na 127.0.0.1; vrne (koda, bajti)."""
    c = http.client.HTTPConnection("127.0.0.1", VRATA, timeout=cakaj)
    try:
        glave = {"X-Free3D": _zeton()}
        podatki = None
        if telo is not None:
            podatki = json.dumps(telo, ensure_ascii=False).encode("utf-8")
            glave["Content-Type"] = "application/json"
        c.request(metoda, pot, body=podatki, headers=glave)
        r = c.getresponse()
        return r.status, r.read()
    finally:
        c.close()


def _json(metoda, pot, telo=None):
    koda, bajti = _zahteva(metoda, pot, telo)
    try:
        podatki = json.loads(bajti.decode("utf-8") or "{}")
    except ValueError:
        podatki = {}
    if koda != 200:
        raise M.Napaka("Strežnik Free 3D: %s (%d)" % (podatki.get("napaka") or "napaka", koda))
    return podatki


def tece():
    try:
        return _zahteva("GET", "/api/stanje", cakaj=1.5)[0] == 200
    except OSError:
        return False


def zagotovi():
    """Zažene strežnik Free 3D, če ne teče (samostojen proces brez okna; preživi konec FreeCAD-a)."""
    if tece():
        return
    mapa = _mapa_free3d()
    if not mapa:
        raise M.Napaka("Mape Free 3D ni (CAD in 3D/Free 3D); nastavi FREE3D_MAPA.")
    py = M.S._tiskaj_python()
    if not py:
        raise M.Napaka("Python za strežnik Free 3D ni najden (pythonw.exe).")
    okolje = {k: v for k, v in os.environ.items() if k not in ("PYTHONHOME", "PYTHONPATH", "PYTHONNOUSERSITE")}
    okolje["FREE3D_VRATA"] = str(VRATA)
    zastavice = (getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                 | getattr(subprocess, "CREATE_NO_WINDOW", 0))
    dnevnik = os.path.join(os.environ.get("LOCALAPPDATA", mapa), "FreeCAD-splet", "free3d.log")
    try:
        os.makedirs(os.path.dirname(dnevnik), exist_ok=True)
        izhod = open(dnevnik, "ab")
    except OSError:
        izhod = subprocess.DEVNULL
    try:
        subprocess.Popen([py, os.path.join("streznik", "free3d.py")], cwd=mapa, env=okolje, stdin=subprocess.DEVNULL,
                         stdout=izhod, stderr=subprocess.STDOUT, close_fds=True, creationflags=zastavice)
    finally:
        if izhod is not subprocess.DEVNULL:
            izhod.close()
    M._dnevnik("splet", "free3d: zaganjam strežnik skic (%s)" % py)
    for _ in range(40):
        time.sleep(0.25)
        if tece():
            return
    raise M.Napaka("Strežnik Free 3D se ni zagnal (dnevnik: %s)." % dnevnik)


def _vrstica(s):
    besedilo = s.get("opomba") if s.get("izvor") != "claude" else s.get("sporocilo")
    return "%s · %s%s · %s / %s · %s%s" % (
        s["id"], s.get("stanje"), " (od AI)" if s.get("izvor") == "claude" else "", s.get("projekt"),
        s.get("dokument") or "-", s.get("ustvarjeno", "").replace("T", " "),
        (" · " + besedilo.replace("\n", " ")[:120]) if besedilo else "")


def _poslji(a):
    odgovor = M.brskalnik("slika", {"pogled": "zaslon", "velikost": int(a.get("velikost") or 1600)}, cakaj=12.0)
    if not odgovor or not odgovor.get("slika"):
        raise M.Napaka("Posnetka zaslona ni (%s). Stran spletnega FreeCAD-a mora biti odprta in vidna." % (
            (odgovor or {}).get("napaka") or "brskalnik ni odgovoril"))
    kamera = (M.brskalnik("kamera", {}, cakaj=6.0) or {}).get("kamera")

    def dokument():
        doc = App.ActiveDocument
        return (doc.Label, doc.FileName or "") if doc else ("", "")
    oznaka, datoteka = M._glavna_vrednost(dokument, 20)
    zagotovi()
    telo = {"slika": odgovor["slika"], "dokument": oznaka, "datoteka": datoteka, "kamera": kamera,
            "izvor": a.get("izvor") or "claude", "sporocilo": a.get("sporocilo") or "",
            "odgovor_na": a.get("odgovor_na") or ""}
    s = _json("POST", "/api/skice", telo)
    return "Poslano na iPad: %s (%s / %s)%s." % (s["id"], s["projekt"], s["dokument"] or "-",
                                                  ("; odgovor na " + telo["odgovor_na"]) if telo["odgovor_na"] else "")


@M.orodje("skice", naslov="Skice z iPada", nit="streznik", lastnosti={
    "akcija": {"type": "string", "enum": ["seznam", "pokazi", "poslji", "stanje"],
               "description": "seznam (privzeto) | pokazi: risba in opomba uporabnika | poslji: posnetek zaslona na "
                              "iPad | stanje: nastavi stanje skice"},
    "id": {"type": "string", "description": "id skice (pokazi: privzeto najnovejša poslana; stanje: obvezno)"},
    "stanje": {"type": "string", "enum": list(STANJA),
               "description": "seznam: samo to stanje; akcija stanje: novo stanje (resena, ko je popravljeno)"},
    "sporocilo": {"type": "string", "description": "poslji: kratko besedilo za uporabnika na iPadu (kaj si popravil)"},
    "odgovor_na": {"type": "string", "description": "poslji: id skice, na katero odgovarjaš (ta postane rešena)"},
    "izvirnik": {"type": "boolean", "description": "pokazi: vrni tudi posnetek brez risbe"},
    "izvor": {"type": "string", "enum": ["claude", "uporabnik"], "description": "poslji: kdo pošilja (gumb Na iPad: uporabnik)"},
}, opis="""
Skice z iPada (aplikacija Free 3D): uporabnik pošlje posnetek pogleda na iPad (gumb »Na iPad« v Strojnem risanju), po
njem riše s Pencilom (puščice, krogi, opombe) in ga pošlje nazaj. `seznam` pokaže skice, `pokazi` vrne označeno sliko,
opombo, dokument in kamero (stanje »poslana« = čaka nate). Popravi model, nato `poslji` z odgovor_na in sporocilo (nov
posnetek zaslona gre na iPad v pregled, izvirnik postane rešen). Ko uporabnik reče »poglej skice«, začni s `pokazi`.""")
def t_skice(a):
    akcija = a.get("akcija") or "seznam"
    if akcija == "poslji":
        return _poslji(a)
    zagotovi()
    if akcija == "seznam":
        skice = _json("GET", "/api/skice" + ("?stanje=" + a["stanje"] if a.get("stanje") else "")).get("skice", [])
        if not a.get("stanje"):
            skice = [s for s in skice if s.get("stanje") != "arhiv"]
        if not skice:
            return "Ni skic%s." % (" v stanju " + a["stanje"] if a.get("stanje") else "")
        cakajo = sum(1 for s in skice if s.get("stanje") == "poslana")
        return ("Skic: %d, čaka nate (poslana): %d\n" % (len(skice), cakajo)) + "\n".join(_vrstica(s) for s in skice[:40])
    if akcija == "pokazi":
        sid = a.get("id")
        if not sid:
            poslane = _json("GET", "/api/skice?stanje=poslana").get("skice", [])
            if not poslane:
                raise M.Napaka("Ni poslanih skic. Seznam: skice {\"akcija\": \"seznam\"}.")
            sid = poslane[0]["id"]
        s = _json("GET", "/api/skice/" + sid)
        slike = []
        imena = ["oznaceno.jpg"] if "oznaceno.jpg" in s.get("datoteke", []) else ["posnetek.jpg"]
        if a.get("izvirnik") and imena[0] != "posnetek.jpg":
            imena.append("posnetek.jpg")
        for ime in imena:
            koda, bajti = _zahteva("GET", "/api/skice/%s/%s" % (sid, ime))
            if koda == 200:
                slike.append(("image/jpeg", bajti))
        k = s.get("kamera") or {}
        besedilo = "\n".join(filter(None, [
            "Skica %s · %s%s" % (sid, s.get("stanje"), " (od AI)" if s.get("izvor") == "claude" else ""),
            "Projekt: %s · dokument: %s" % (s.get("projekt"), s.get("dokument") or "-"),
            ("Datoteka: " + s["datoteka"]) if s.get("datoteka") else "",
            ("Opomba uporabnika: " + s["opomba"]) if s.get("opomba") else "Opombe ni (samo risba).",
            ("Sporočilo AI: " + s["sporocilo"]) if s.get("sporocilo") else "",
            ("Kamera: položaj %s, cilj %s, %s" % (k.get("polozaj"), k.get("cilj"),
                                                  "pravokotna" if k.get("pravokotna") else "perspektiva")) if k else "",
            "Slike: " + " + ".join("risba čez posnetek" if i == "oznaceno.jpg" else "posnetek" for i in imena),
            ("Odgovor: " + s["odgovor"]) if s.get("odgovor") else "",
        ]))
        return {"besedilo": besedilo, "slike": slike}
    if akcija == "stanje":
        if not a.get("id") or a.get("stanje") not in STANJA:
            raise M.Napaka("Akcija stanje potrebuje id in stanje (%s)." % ", ".join(STANJA))
        s = _json("POST", "/api/skice/%s/stanje" % a["id"], {"stanje": a["stanje"]})
        return "Skica %s: %s." % (s["id"], s["stanje"])
    raise M.Napaka("Neznana akcija: %s" % akcija)
