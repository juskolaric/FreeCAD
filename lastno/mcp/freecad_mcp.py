#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
freecad-mcp: MCP strežnik (stdio) za spletni FreeCAD (lastno/splet, vrata 3020). Plan: MCP-PLAN.md.

Most brez odvisnosti (Python 3.10+, standardna knjižnica): vsak klic orodja prevede v POST /mcp/orodje na tekoči
spletni FreeCAD; katalog orodij, viri in predloge pridejo s strežnika (GET /mcp/orodja), zato novo orodje ne zahteva
spremembe mostu. Ko FreeCAD ne teče, most ponudi zadnji znani katalog (%LOCALAPPDATA%/FreeCAD-splet/mcp-orodja.json)
in orodje `zazeni` (ZAZENI-SPLET.bat). Vrata in žeton: %LOCALAPPDATA%/FreeCAD-splet/povezava.json (zapiše strežnik).

Uporaba:
  python freecad_mcp.py                       MCP strežnik prek stdin/stdout (za Claude Code, Claude Desktop, Cursor)
  python freecad_mcp.py test                  preveri povezavo, katalog in orodje stanje
  python freecad_mcp.py tools                 seznam orodij
  python freecad_mcp.py call <orodje> [json]  pokliči orodje (slike shrani v začasno mapo in izpiše pot)
  python freecad_mcp.py viri | vir <uri> | predloge

Okolje: FREECAD_MCP_POVEZAVA (pot do povezava.json, za preizkusni primerek), FREECAD_MCP_KATALOG.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

VERZIJA = "1.0.0"
TU = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(TU, "..", ".."))
MAPA_SPLET = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "FreeCAD-splet")
POVEZAVA = os.environ.get("FREECAD_MCP_POVEZAVA") or os.path.join(MAPA_SPLET, "povezava.json")
KATALOG = os.environ.get("FREECAD_MCP_KATALOG") or os.path.join(os.path.dirname(POVEZAVA), "mcp-orodja.json")
ZAZENI_BAT = os.path.join(REPO, "lastno", "splet", "ZAZENI-SPLET.bat")
PROTOKOL = "2025-06-18"

NAVODILA_REZERVA = ("Spletni FreeCAD (lastna gradnja FreeCAD 1.1, vmesnik v brskalniku na http://127.0.0.1:3020/). "
                    "Strežnik zdaj ne teče: zaženi ga z orodjem `zazeni`, nato začni s `stanje`.")

ORODJE_ZAZENI = {
    "name": "zazeni", "title": "Zaženi spletni FreeCAD",
    "description": "Zažene spletni FreeCAD (lastna gradnja, okno skrito, brskalnik na http://127.0.0.1:3020/), če še "
                   "ne teče, in počaka, da strežnik odgovori (do 4 min; prvič z obnovo dokumentov lahko dlje).",
    "inputSchema": {"type": "object", "additionalProperties": False, "properties": {
        "brskalnik": {"type": "boolean", "description": "odpri brskalnik (privzeto true; potreben za orodje slika)"},
        "cakaj": {"type": "number", "description": "sekunde čakanja na strežnik (privzeto 240)"}}},
    "annotations": {"title": "Zaženi spletni FreeCAD", "readOnlyHint": False, "destructiveHint": False,
                    "openWorldHint": False},
}

FREECADCMD = os.environ.get("FREECAD_MCP_FREECADCMD") or r"C:\Program Files\FreeCAD 1.1\bin\FreeCADCmd.exe"
ORODJE_FREECADCMD = {
    "name": "freecadcmd", "title": "FreeCADCmd (brez strežnika)",
    "description": "Izvede Python v ločenem procesu FreeCADCmd (nameščeni FreeCAD 1.1, brez okna in brez GUI), "
                   "neodvisno od spletnega FreeCAD-a: pretvorbe in preverjanja datotek (krog zapis-branje STEP, ki v "
                   "spletnem FreeCAD-u lahko sesuje proces), paketna obdelava, delo, ko strežnik ne teče. Dokumente "
                   "odpri sam (App.openDocument); spremembe se ne vidijo v brskalniku. Nastavi `rezultat`. Shranjevanje "
                   "in brisanje datotek le z dovoli_pisanje (izrecno dovoljenje uporabnika).",
    "inputSchema": {"type": "object", "additionalProperties": False, "properties": {
        "koda": {"type": "string", "description": "Python koda (App/FreeCAD, Part ... uvozi sam)"},
        "datoteka": {"type": "string", "description": "namesto kode izvedi skripto s to potjo (__file__ nastavljen)"},
        "dovoli_pisanje": {"type": "boolean", "description": "dovoli save/brisanje datotek (samo z dovoljenjem)"},
        "cakaj": {"type": "number", "description": "sekunde (privzeto 300)"}}},
    "annotations": {"title": "FreeCADCmd (brez strežnika)", "readOnlyHint": False, "destructiveHint": True,
                    "openWorldHint": False},
}
PREPOVEDANO_CMD = [(r"\.(save|saveAs|saveCopy)\s*\(", "shranjevanje dokumenta"),
                   (r"\bos\.(remove|unlink|rmdir|removedirs|replace|rename)\s*\(", "brisanje ali premikanje datotek"),
                   (r"\bshutil\.(rmtree|move)\s*\(", "brisanje ali premikanje map"), (r"\.unlink\s*\(", "brisanje datotek")]
OVOJ_CMD = r'''# -*- coding: utf-8 -*-
import contextlib, io, json, sys, traceback
_pot = %(pot)r
_ime = %(ime)r
with open(_pot, encoding="utf-8-sig") as _f:
    _koda = _f.read()
import FreeCAD
_ns = {"__name__": "__main__", "__file__": _ime if not _ime.startswith("<") else "", "App": FreeCAD, "FreeCAD": FreeCAD}
_napaka = ""
try:
    exec(compile(_koda, _ime, "exec"), _ns)
except BaseException:
    _napaka = traceback.format_exc()
sys.stdout.flush()
print("\n@@MCP-REZULTAT@@" + json.dumps({"rezultat": _ns.get("rezultat"), "napaka": _napaka}, ensure_ascii=False, default=str))
'''

_izhod = threading.Lock()
_stanje = {"seja": "mcp#%d" % os.getpid(), "katalog": None, "verzija": None, "tece": False, "seznam": False}


def log(besedilo: str) -> None:
    try:
        sys.stderr.write("[freecad-mcp] %s\n" % besedilo)
        sys.stderr.flush()
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------------------------------------------
# Povezava s spletnim FreeCAD-om

def povezava() -> dict | None:
    try:
        with open(POVEZAVA, encoding="utf-8") as f:
            p = json.load(f)
        return p if p.get("vrata") and p.get("zeton") else None
    except (OSError, ValueError):
        return None


def klic(metoda: str, pot: str, telo=None, cas: float = 30.0, ponovi: bool = True):
    """HTTP klic na strežnik. Vrne (status, bajti); dvigne ConnectionError, če strežnik ne teče."""
    p = povezava()
    if p is None:
        raise ConnectionError("ni povezave (%s)" % POVEZAVA)
    podatki = None
    glave = {"X-Zeton": p["zeton"], "X-Seja": _stanje["seja"]}
    if telo is not None:
        podatki = json.dumps(telo, ensure_ascii=False).encode("utf-8")
        glave["Content-Type"] = "application/json"
    zahteva = urllib.request.Request("http://127.0.0.1:%d%s" % (int(p["vrata"]), pot), data=podatki, headers=glave,
                                     method=metoda)
    try:
        with urllib.request.urlopen(zahteva, timeout=cas) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        if e.code == 403 and ponovi:   # strežnik je bil znova zagnan: nov žeton v povezava.json
            time.sleep(0.5)
            return klic(metoda, pot, telo, cas, ponovi=False)
        return e.code, e.read()
    except (urllib.error.URLError, ConnectionError, OSError) as e:
        raise ConnectionError(str(getattr(e, "reason", e)))


def tece() -> bool:
    try:
        status, _ = klic("GET", "/stanje", cas=3.0)
        return status == 200
    except ConnectionError:
        return False


def katalog(osvezi: bool = True) -> dict:
    """Katalog s strežnika (in zapis v predpomnilnik), sicer zadnji znani, sicer prazen."""
    if osvezi:
        try:
            status, telo = klic("GET", "/mcp/orodja", cas=10.0)
            if status == 200:
                k = json.loads(telo.decode("utf-8"))
                k["tece"] = True
                _stanje["katalog"] = k
                return k
        except (ConnectionError, ValueError):
            pass
    if _stanje["katalog"] is not None:
        k = dict(_stanje["katalog"])
    else:
        try:
            with open(KATALOG, encoding="utf-8") as f:
                k = json.load(f)
        except (OSError, ValueError):
            k = {"orodja": [], "viri": [], "predloge": [], "navodila": NAVODILA_REZERVA, "verzija": None}
    k["tece"] = False
    return k


def orodja(k: dict) -> list:
    sez = [dict(o) for o in k.get("orodja", []) if o.get("name") not in ("zazeni", "freecadcmd")]
    if not k.get("tece"):
        for o in sez:
            o["description"] = "(FreeCAD zdaj ne teče: najprej `zazeni`.) " + o.get("description", "")
    return [ORODJE_ZAZENI] + sez + [ORODJE_FREECADCMD]


def freecadcmd(argumenti: dict) -> tuple[str, bool]:
    """Python v ločenem procesu FreeCADCmd: koda gre v začasno datoteko, ovoj vrne izpis in `rezultat`."""
    import re
    koda = argumenti.get("koda") or ""
    ime = "<mcp>"
    if argumenti.get("datoteka"):
        ime = os.path.normpath(argumenti["datoteka"])
        try:
            with open(ime, encoding="utf-8-sig") as f:
                koda = f.read()
        except OSError as e:
            return "Skripte ni mogoče prebrati: %s" % e, True
    if not koda.strip():
        return "Ni kode (koda ali datoteka).", True
    if not argumenti.get("dovoli_pisanje"):
        for vzorec, razlog in PREPOVEDANO_CMD:
            if re.search(vzorec, koda):
                return ("Koda ni izvedena: %s. Če je uporabnik to izrecno dovolil, ponovi z dovoli_pisanje: true."
                        % razlog), True
    if not os.path.isfile(FREECADCMD):
        return "FreeCADCmd ni nameščen (%s; prepis FREECAD_MCP_FREECADCMD)." % FREECADCMD, True
    mapa = tempfile.mkdtemp(prefix="freecad-mcp-cmd-")
    pot_kode = os.path.join(mapa, "koda.py")
    pot_ovoja = os.path.join(mapa, "ovoj.py")
    with open(pot_kode, "w", encoding="utf-8") as f:
        f.write(koda)
    with open(pot_ovoja, "w", encoding="utf-8") as f:
        f.write(OVOJ_CMD % {"pot": pot_kode, "ime": ime})
    cakaj = float(argumenti.get("cakaj") or 300)
    zacetek = time.time()
    try:
        r = subprocess.run([FREECADCMD, pot_ovoja], cwd=os.path.dirname(ime) if ime != "<mcp>" else mapa,
                           stdin=subprocess.DEVNULL, capture_output=True, timeout=cakaj,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        return "FreeCADCmd ni končal v %d s (proces ustavljen)." % cakaj, True
    izpis = r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")
    rezultat, napaka = None, ""
    if "@@MCP-REZULTAT@@" in izpis:
        izpis, _, rep = izpis.rpartition("@@MCP-REZULTAT@@")
        try:
            podatki = json.loads(rep.strip().splitlines()[0])
            rezultat, napaka = podatki.get("rezultat"), podatki.get("napaka") or ""
        except (ValueError, IndexError):
            pass
    else:
        napaka = "FreeCADCmd se je končal brez rezultata (koda %s)." % r.returncode
    deli = ["FreeCADCmd: %.1f s." % (time.time() - zacetek)]
    izpis = izpis.strip()
    if izpis:
        deli.append("Izpis:\n" + (izpis[-30000:] if len(izpis) > 30000 else izpis))
    if rezultat is not None:
        deli.append("rezultat = " + json.dumps(rezultat, ensure_ascii=False, indent=1)[:20000])
    if napaka:
        deli.append("NAPAKA:\n" + "\n".join(napaka.strip().splitlines()[-14:]))
    return "\n".join(deli), bool(napaka)


def zazeni(argumenti: dict) -> tuple[str, bool]:
    if tece():
        return "Spletni FreeCAD že teče (http://127.0.0.1:%d/)." % povezava()["vrata"], False
    zagon = os.environ.get("FREECAD_MCP_ZAGON") or ZAZENI_BAT   # prepis za preizkusni primerek
    if not os.path.isfile(zagon):
        return "Ni zagonske skripte %s." % zagon, True
    okolje = dict(os.environ)
    if argumenti.get("brskalnik") is False:
        okolje["SPLET_BRSKALNIK"] = "0"
    zastavice = 0
    if os.name == "nt":
        zastavice = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    # stdin/stdout/stderr ne smejo podedovati kanala MCP
    subprocess.Popen(["cmd", "/c", zagon], cwd=REPO, env=okolje, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, creationflags=zastavice)
    rok = time.time() + float(argumenti.get("cakaj") or 240)
    while time.time() < rok:
        time.sleep(2.0)
        if tece():
            k = katalog()
            _poslji_spremembo_orodij(k)
            return "Spletni FreeCAD teče (http://127.0.0.1:%d/), orodij: %d." % (
                povezava()["vrata"], len(k.get("orodja", []))), False
    return ("FreeCAD se v %d s ni oglasil. Poglej build/splet-zagon.log in build/splet-zagon-napake.log v %s "
            "(morda čaka okno Obnova dokumentov v brskalniku)." % (float(argumenti.get("cakaj") or 240), REPO)), True


def poklici(ime: str, argumenti: dict) -> dict:
    """tools/call -> rezultat MCP {content, isError}."""
    if ime in ("zazeni", "freecadcmd"):
        besedilo, napaka = (zazeni if ime == "zazeni" else freecadcmd)(argumenti)
        return {"content": [{"type": "text", "text": besedilo}], "isError": napaka}
    try:
        cakaj = float(argumenti.get("cakaj") or 0)
    except (TypeError, ValueError):
        cakaj = 0
    cas = max(cakaj, 300.0) + 120.0
    try:
        status, telo = klic("POST", "/mcp/orodje", {"ime": ime, "argumenti": argumenti}, cas=cas)
    except ConnectionError as e:
        return {"content": [{"type": "text", "text": "Spletni FreeCAD ne teče ali ne odgovarja (%s). Zaženi ga z "
                                                      "orodjem `zazeni`." % e}], "isError": True}
    if status == 404:
        return {"content": [{"type": "text", "text": "Strežnik FreeCAD ne pozna orodij MCP (starejša različica): "
                                                      "ponovno zaženi spletni FreeCAD."}], "isError": True}
    try:
        odgovor = json.loads(telo.decode("utf-8"))
    except ValueError:
        return {"content": [{"type": "text", "text": "Neveljaven odgovor strežnika (%d): %s" % (
            status, telo[:500].decode("utf-8", "replace"))}], "isError": True}
    vsebina = []
    for v in odgovor.get("vsebina", []):
        if v.get("vrsta") == "slika":
            vsebina.append({"type": "image", "data": v["podatki"], "mimeType": v.get("mime", "image/png")})
        else:
            vsebina.append({"type": "text", "text": v.get("besedilo", "")})
    if not vsebina:
        vsebina.append({"type": "text", "text": "Opravljeno."})
    if odgovor.get("katalog") and _stanje["verzija"] and odgovor["katalog"] != _stanje["verzija"]:
        _poslji_spremembo_orodij(katalog())
    return {"content": vsebina, "isError": bool(odgovor.get("napaka"))}


def preberi_vir(uri: str) -> dict:
    try:
        status, telo = klic("GET", "/mcp/vir?uri=" + urllib.parse.quote(uri, safe=""), cas=30.0)
    except ConnectionError as e:
        raise ValueError("Spletni FreeCAD ne teče (%s); zaženi ga z orodjem zazeni." % e)
    if status != 200:
        raise ValueError("Vira %s ni." % uri)
    v = json.loads(telo.decode("utf-8"))
    return {"contents": [{"uri": uri, "mimeType": v.get("mimeType", "text/plain"), "text": v.get("text", "")}]}


def predloga(ime: str, argumenti: dict) -> dict:
    k = katalog()
    p = next((p for p in k.get("predloge", []) if p.get("name") == ime), None)
    if p is None:
        raise ValueError("Predloge %s ni." % ime)

    class Prazno(dict):
        def __missing__(self, kljuc):
            return ""
    besedilo = p.get("besedilo", "").format_map(Prazno({k2: str(v) for k2, v in (argumenti or {}).items()}))
    return {"description": p.get("description", ""),
            "messages": [{"role": "user", "content": {"type": "text", "text": besedilo}}]}


# ---------------------------------------------------------------------------------------------------------------
# JSON-RPC prek stdio

def _poslji(sporocilo: dict) -> None:
    vrstica = (json.dumps(sporocilo, ensure_ascii=False) + "\n").encode("utf-8")
    with _izhod:
        sys.stdout.buffer.write(vrstica)
        sys.stdout.buffer.flush()


def _poslji_spremembo_orodij(k: dict) -> None:
    """Claude Code znova prebere orodja, ko se katalog spremeni ali ko strežnik začne teči (opisi brez opombe)."""
    nova = k.get("verzija")
    if (nova and nova != _stanje["verzija"]) or bool(k.get("tece")) != bool(_stanje.get("tece")):
        log("katalog orodij spremenjen (%s -> %s, teče: %s)" % (_stanje["verzija"], nova, k.get("tece")))
        _stanje["verzija"] = nova or _stanje["verzija"]
        _stanje["tece"] = bool(k.get("tece"))
        if not _stanje.get("seznam"):
            return   # odjemalec orodij še ni prebral: ni česa osvežiti
        try:
            _poslji({"jsonrpc": "2.0", "method": "notifications/tools/list_changed"})
        except Exception:  # noqa: BLE001
            pass


def _odgovori(mid, rezultat=None, napaka=None):
    if mid is None:
        return
    if napaka is not None:
        _poslji({"jsonrpc": "2.0", "id": mid, "error": napaka})
    else:
        _poslji({"jsonrpc": "2.0", "id": mid, "result": rezultat})


def obdelaj(msg: dict) -> None:
    metoda = msg.get("method", "")
    mid = msg.get("id")
    params = msg.get("params") or {}
    try:
        if metoda == "initialize":
            info = params.get("clientInfo") or {}
            _stanje["seja"] = "%s#%d" % (info.get("name") or "mcp", os.getpid())
            k = katalog()
            _stanje["verzija"] = k.get("verzija")
            _stanje["tece"] = bool(k.get("tece"))
            _odgovori(mid, {
                "protocolVersion": params.get("protocolVersion") or PROTOKOL,
                "capabilities": {"tools": {"listChanged": True}, "resources": {}, "prompts": {}},
                "serverInfo": {"name": "freecad", "title": "Spletni FreeCAD", "version": VERZIJA},
                "instructions": k.get("navodila") or NAVODILA_REZERVA,
            })
        elif metoda == "ping":
            _odgovori(mid, {})
        elif metoda == "tools/list":
            k = katalog()
            _stanje["verzija"] = k.get("verzija") or _stanje["verzija"]
            _stanje["tece"] = bool(k.get("tece"))
            _stanje["seznam"] = True
            _odgovori(mid, {"tools": orodja(k)})
        elif metoda == "tools/call":
            # vsak klic v svoji niti: počasno orodje (render, python) ne zadrži ostalih
            def delo():
                try:
                    _odgovori(mid, poklici(params.get("name", ""), params.get("arguments") or {}))
                except Exception as e:  # noqa: BLE001
                    _odgovori(mid, {"content": [{"type": "text", "text": "Napaka mostu: %r" % e}], "isError": True})
            threading.Thread(target=delo, daemon=True).start()
        elif metoda == "resources/list":
            k = katalog()
            _odgovori(mid, {"resources": k.get("viri", [])})
        elif metoda == "resources/templates/list":
            _odgovori(mid, {"resourceTemplates": []})
        elif metoda == "resources/read":
            _odgovori(mid, preberi_vir(params.get("uri", "")))
        elif metoda == "prompts/list":
            k = katalog()
            _odgovori(mid, {"prompts": [{key: p[key] for key in ("name", "description", "arguments") if key in p}
                                        for p in k.get("predloge", [])]})
        elif metoda == "prompts/get":
            _odgovori(mid, predloga(params.get("name", ""), params.get("arguments") or {}))
        elif metoda.startswith("notifications/"):
            pass
        elif mid is not None:
            _odgovori(mid, napaka={"code": -32601, "message": "Metoda %s ni podprta" % metoda})
    except ValueError as e:
        _odgovori(mid, napaka={"code": -32602, "message": str(e)})
    except Exception as e:  # noqa: BLE001
        log("napaka pri %s: %r" % (metoda, e))
        _odgovori(mid, napaka={"code": -32603, "message": repr(e)})


def streznik() -> None:
    log("freecad-mcp %s, povezava %s" % (VERZIJA, POVEZAVA))
    vhod = sys.stdin.buffer
    while True:
        try:
            vrstica = vhod.readline()
        except (KeyboardInterrupt, OSError):
            break
        if not vrstica:
            break
        vrstica = vrstica.strip()
        if not vrstica:
            continue
        try:
            msg = json.loads(vrstica.decode("utf-8"))
        except ValueError:
            _poslji({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
            continue
        for m in (msg if isinstance(msg, list) else [msg]):
            if isinstance(m, dict):
                obdelaj(m)


# ---------------------------------------------------------------------------------------------------------------
# Ukazna vrstica

def _izpisi_rezultat(r: dict) -> None:
    mapa = None
    for c in r.get("content", []):
        if c.get("type") == "image":
            mapa = mapa or tempfile.mkdtemp(prefix="freecad-mcp-")
            koncnica = ".jpg" if "jpeg" in c.get("mimeType", "") else ".png"
            pot = os.path.join(mapa, "slika%d%s" % (len(os.listdir(mapa)) + 1, koncnica))
            with open(pot, "wb") as f:
                f.write(base64.b64decode(c["data"]))
            print("[slika] %s" % pot)
        else:
            print(c.get("text", ""))
    if r.get("isError"):
        print("(napaka)")


def main(argv: list[str]) -> int:
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    if not argv:
        streznik()
        return 0
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ukaz = argv[0]
    if ukaz in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    if ukaz == "test":
        p = povezava()
        print("Povezava:", POVEZAVA, "->", ("vrata %s" % p["vrata"]) if p else "MANJKA")
        print("Strežnik teče:", "da" if tece() else "NE")
        k = katalog()
        print("Katalog: verzija %s, orodij %d, virov %d, predlog %d (%s)" % (
            k.get("verzija"), len(k.get("orodja", [])), len(k.get("viri", [])), len(k.get("predloge", [])),
            "s strežnika" if k.get("tece") else "iz predpomnilnika"))
        if k.get("tece"):
            _izpisi_rezultat(poklici("stanje", {}))
        return 0 if k.get("tece") else 1
    if ukaz == "tools":
        for o in orodja(katalog()):
            print("%-12s %s" % (o["name"], " ".join(o.get("description", "").split())[:150]))
        return 0
    if ukaz == "call" and len(argv) >= 2:
        argumenti = json.loads(argv[2]) if len(argv) > 2 else {}
        r = poklici(argv[1], argumenti)
        _izpisi_rezultat(r)
        return 1 if r.get("isError") else 0
    if ukaz == "viri":
        for v in katalog().get("viri", []):
            print("%s  %s" % (v["uri"], v.get("name", "")))
        return 0
    if ukaz == "vir" and len(argv) >= 2:
        print(preberi_vir(argv[1])["contents"][0]["text"])
        return 0
    if ukaz == "predloge":
        for p in katalog().get("predloge", []):
            print("%-12s %s" % (p["name"], p.get("description", "")))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
