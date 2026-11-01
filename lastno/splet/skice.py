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


def _mm_ss(t):
    t = float(t or 0)
    return "%d:%02d" % (int(t) // 60, int(t) % 60)


def _vrstica(s):
    besedilo = s.get("opomba") if s.get("izvor") != "claude" else s.get("sporocilo")
    return "%s · %s%s · %s / %s · %s%s%s" % (
        s["id"], s.get("stanje"), " (od AI)" if s.get("izvor") == "claude" else "", s.get("projekt"),
        s.get("dokument") or "-", s.get("ustvarjeno", "").replace("T", " "),
        (" · video " + _mm_ss(s["video"].get("trajanje"))) if s.get("video") else "",
        (" · " + besedilo.replace("\n", " ")[:120]) if besedilo else "")


# ---------------------------------------------------------------------------------------------------------------
# Video skice (od 2026-10-29): iPad med risanjem posname zaslon in glas; strežnik skic po prejemu v ozadju požene
# Free 3D/streznik/obdelaj_video.py (prepis faster-whisper + sličice ob koncu povedi) v <mapa skice>/video-<posneto>/.

def _obdelaj_video(mapa, *argumenti, cakaj=300):
    skripta = os.path.join(_mapa_free3d(), "streznik", "obdelaj_video.py")
    py = M.S._tiskaj_python() or ""
    if py.lower().endswith("pythonw.exe") and os.path.isfile(py[:-5] + ".exe"):
        py = py[:-5] + ".exe"
    if not py or not os.path.isfile(skripta):
        raise M.Napaka("Obdelave videa ni (Python ali %s manjka)." % skripta)
    okolje = {k: v for k, v in os.environ.items() if k not in ("PYTHONHOME", "PYTHONPATH", "PYTHONNOUSERSITE")}
    r = subprocess.run([py, skripta, mapa] + list(argumenti), env=okolje, capture_output=True, timeout=cakaj,
                       stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return r.stdout.decode("utf-8", "replace")


def _stanje_obdelave(izhod):
    try:
        with open(os.path.join(izhod, "stanje.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _video(s, a):
    """Besedilo o videu (trajanje, velikost, pot, prepis govora) in sličice [(mime, bajti)]."""
    v = s["video"]
    mapa = s.get("mapa") or ""
    pot = os.path.join(mapa, v.get("datoteka") or "video.mp4")
    izhod = os.path.join(mapa, v.get("obdelava") or "video-obdelava")
    trajanje = float(v.get("trajanje") or 0)
    mb = (v.get("velikost") or 0) / 1e6
    vrstice = ["Video (posnetek zaslona iPada med risanjem, z glasom uporabnika): %s, %.1f MB%s · %s" % (
        _mm_ss(trajanje), mb, (" (%.1f MB/min)" % (mb * 60 / trajanje)) if trajanje else "", pot)]
    stanje = _stanje_obdelave(izhod)
    if stanje.get("stanje") != "koncano" and mapa:
        kljucavnica = os.path.join(izhod, "obdelava.lock")
        if os.path.isfile(kljucavnica) and time.time() - os.path.getmtime(kljucavnica) < 20 * 60:
            for _ in range(150):                    # strežnik skic obdelavo že poganja (prepis traja nekaj sekund)
                time.sleep(1)
                stanje = _stanje_obdelave(izhod)
                if stanje.get("stanje") in ("koncano", "napaka"):
                    break
        else:
            _obdelaj_video(mapa)
            stanje = _stanje_obdelave(izhod)
    slike = []
    if stanje.get("stanje") != "koncano":
        vrstice.append("Obdelava videa še ni končana (%s); poskusi znova čez minuto ali poglej %s." % (
            stanje.get("napaka") or stanje.get("stanje") or "ni začeta", izhod))
        return vrstice, slike
    povedi = stanje.get("prepis") or []
    if povedi:
        vrstice.append("Prepis govora (Whisper, samodejno, lahko ima napake v strokovnih izrazih):")
        vrstice += ["  [%s–%s] %s" % (_mm_ss(p["od"]), _mm_ss(p["do"]), p["besedilo"]) for p in povedi]
    elif stanje.get("napaka_prepisa"):
        vrstice.append("Prepisa ni (%s); zvok je v videu." % stanje["napaka_prepisa"])
    else:
        vrstice.append("V videu ni govora.")
    slicice = stanje.get("slicice") or []
    if a.get("cas"):
        casi = [c for c in str(a["cas"]).replace(" ", ",").split(",") if c.strip()]
        try:
            slicice = json.loads(_obdelaj_video(mapa, "--cas", ";".join(casi), cakaj=120)).get("slicice", [])
        except ValueError:
            raise M.Napaka("Sličic ob časih %s ni bilo mogoče izvleči." % ", ".join(casi))
    for sl in slicice:
        try:
            with open(os.path.join(izhod, sl["datoteka"]), "rb") as f:
                slike.append(("image/jpeg", f.read()))
        except OSError:
            pass
    if slicice:
        vrstice.append("Sličice videa (po risbi) ob: %s%s. Druge čase: pokazi s cas (npr. \"0:12, 0:40\")." % (
            ", ".join(_mm_ss(sl["cas"]) for sl in slicice), "" if a.get("cas") else " (konci povedi, zadnja = končno stanje)"))
    return vrstice, slike


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


@M.orodje("skice", naslov="Skice z iPada", nit="streznik", cakaj=400, lastnosti={
    "akcija": {"type": "string", "enum": ["seznam", "pokazi", "poslji", "stanje"],
               "description": "seznam (privzeto) | pokazi: risba in opomba uporabnika | poslji: posnetek zaslona na "
                              "iPad | stanje: nastavi stanje skice"},
    "id": {"type": "string", "description": "id skice (pokazi: privzeto najnovejša poslana; stanje: obvezno)"},
    "stanje": {"type": "string", "enum": list(STANJA),
               "description": "seznam: samo to stanje; akcija stanje: novo stanje (resena, ko je popravljeno)"},
    "sporocilo": {"type": "string", "description": "poslji: kratko besedilo za uporabnika na iPadu (kaj si popravil)"},
    "odgovor_na": {"type": "string", "description": "poslji: id skice, na katero odgovarjaš (ta postane rešena)"},
    "izvirnik": {"type": "boolean", "description": "pokazi: vrni tudi posnetek brez risbe"},
    "video": {"type": "boolean", "description": "pokazi: prepis govora in sličice videa, če ga skica ima (privzeto da)"},
    "cas": {"type": "string", "description": "pokazi: sličice videa ob teh časih (s ali m:ss, ločeno z vejico) "
                                             "namesto samodejnih"},
    "izvor": {"type": "string", "enum": ["claude", "uporabnik"], "description": "poslji: kdo pošilja (gumb Na iPad: uporabnik)"},
}, opis="""
Skice z iPada (aplikacija Free 3D): uporabnik pošlje posnetek pogleda na iPad (gumb »Na iPad« v Strojnem risanju), po
njem riše s Pencilom (puščice, krogi, opombe) in ga pošlje nazaj. `seznam` pokaže skice, `pokazi` vrne označeno sliko,
opombo, dokument in kamero (stanje »poslana« = čaka nate). Popravi model, nato `poslji` z odgovor_na in sporocilo (nov
posnetek zaslona gre na iPad v pregled, izvirnik postane rešen). Ko uporabnik reče »poglej skice«, začni s `pokazi`.
Skica ima lahko video (uporabnik med risanjem snema zaslon in govori): `pokazi` takrat doda prepis govora s časi in
sličice ob koncu povedi; govor je glavno navodilo, risba ga dopolni. Druge trenutke videa vrne `cas`.""")
def t_skice(a):
    akcija = a.get("akcija") or "seznam"
    if akcija == "poslji":
        return _poslji(a)
    zagotovi()
    if akcija == "seznam":
        skice = _json("GET", "/api/skice" + ("?stanje=" + a["stanje"] if a.get("stanje") else "")).get("skice", [])
        skice = [s for s in skice if s.get("namen") != "podpis"]   # liste za podpis prevzame Podpisnik
        if not a.get("stanje"):
            skice = [s for s in skice if s.get("stanje") != "arhiv"]
        if not skice:
            return "Ni skic%s." % (" v stanju " + a["stanje"] if a.get("stanje") else "")
        cakajo = sum(1 for s in skice if s.get("stanje") == "poslana")
        return ("Skic: %d, čaka nate (poslana): %d\n" % (len(skice), cakajo)) + "\n".join(_vrstica(s) for s in skice[:40])
    if akcija == "pokazi":
        sid = a.get("id")
        if not sid:
            poslane = [s for s in _json("GET", "/api/skice?stanje=poslana").get("skice", []) if s.get("namen") != "podpis"]
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
        if s.get("video") and "video.mp4" in s.get("datoteke", []) and a.get("video") is not False:
            vrstice, sl = _video(s, a)
            besedilo += "\n" + "\n".join(vrstice)
            slike += sl
        return {"besedilo": besedilo, "slike": slike}
    if akcija == "stanje":
        if not a.get("id") or a.get("stanje") not in STANJA:
            raise M.Napaka("Akcija stanje potrebuje id in stanje (%s)." % ", ".join(STANJA))
        s = _json("POST", "/api/skice/%s/stanje" % a["id"], {"stanje": a["stanje"]})
        return "Skica %s: %s." % (s["id"], s["stanje"])
    raise M.Napaka("Neznana akcija: %s" % akcija)
