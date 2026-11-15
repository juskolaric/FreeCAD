# -*- coding: utf-8 -*-
"""Delovni procesi za težke izračune (od 2026-11-15).

FreeCAD App ni varen za več niti, zato vse delo z dokumenti teče na glavni niti spletnega FreeCAD-a. Dolg klic OCC
(common, distToShape na uvoženem sestavu s 192 lupinami) med izvajanjem drži GIL: zamrzne glavno nit in tudi niti
HTTP strežnika (brskalnik visi na »Čakam na FreeCAD«, nove povezave so zavrnjene). Zato gre težko delo v ločen
proces FreeCADCmd iste gradnje:

- glavna nit naredi le hiter posnetek oblik (BREP z globalno lego, `posnemi`) v začasno mapo posla;
- delovni proces (`delovni_proces.py`, bazen do SPLET_DELOVNI procesov, privzeto 2) prebere posnetek, izračuna in
  vrne rezultat po lokalni povezavi (multiprocessing.connection, naključen ključ);
- posel, ki preseže rok, se ustavi s koncem procesa (glavne niti FreeCAD-a ni mogoče prekiniti, procesa pa).

Kliče se iz niti strežnika (orodja MCP z nit="streznik"), nikoli z glavne niti (ta bi čakala sama nase).
"""

import os
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
import traceback
import uuid
from multiprocessing.connection import Listener

import FreeCAD as App

MAPA = os.path.dirname(os.path.abspath(__file__))
SKRIPTA = os.path.join(MAPA, "delovni_proces.py")
MAPA_POSLOV = os.path.join(tempfile.gettempdir(), "freecad-splet-posli")
KOREN = os.path.normpath(os.path.join(MAPA, "..", ".."))
DNEVNIK = os.path.join(KOREN, "build", "splet-delovni.log")


def _najvec():
    try:
        return max(1, min(int(os.environ.get("SPLET_DELOVNI", "2")), 4))
    except ValueError:
        return 2


NAJVEC = _najvec()
ZAGON_ROK = 120.0          # s za zagon FreeCADCmd in povezavo (prvi uvoz Part v velikem okolju zna trajati)
NAJDLJE = 3600.0           # trdi rok posla (s); potem se proces ustavi

_kljuc = threading.Condition()
_delavci = []              # Delavec
_log = [None]              # funkcija dnevnika strežnika (nastavi povezi)


def _dnevnik(besedilo):
    fn = _log[0]
    if fn is not None:
        try:
            fn("delovni: " + besedilo)
        except Exception:  # noqa: BLE001
            pass


def freecadcmd():
    pot = os.environ.get("SPLET_FREECADCMD")
    if pot:
        return pot
    try:
        dom = App.getHomePath()
    except Exception:  # noqa: BLE001
        dom = ""
    for kandidat in (os.path.join(dom, "bin", "FreeCADCmd.exe"), os.path.join(os.path.dirname(os.sys.executable),
                                                                               "FreeCADCmd.exe")):
        if kandidat and os.path.isfile(kandidat):
            return os.path.normpath(kandidat)
    return ""


class Delavec:
    def __init__(self, st):
        self.st = st
        self.proc = None
        self.conn = None
        self.zaseden = None      # opis posla ali None
        self.zacetek = 0.0
        self.poslov = 0

    def zivi(self):
        return self.proc is not None and self.proc.poll() is None and self.conn is not None

    def zazeni(self):
        cmd = freecadcmd()
        if not cmd:
            raise RuntimeError("FreeCADCmd.exe ni najden ob tej gradnji (prepis SPLET_FREECADCMD)")
        kljuc = secrets.token_bytes(24)
        poslusalec = Listener(("127.0.0.1", 0), authkey=kljuc)
        naslov = poslusalec.address
        okolje = dict(os.environ)
        okolje.update({"SPLET_DELOVNI_NASLOV": "%s:%d" % naslov, "SPLET_DELOVNI_KLJUC": kljuc.hex(),
                       "SPLET_DELOVNI_MAPA": MAPA})
        os.makedirs(os.path.dirname(DNEVNIK), exist_ok=True)
        izpis = open(DNEVNIK, "a", encoding="utf-8", errors="replace")
        izpis.write("\n--- delavec %d, %s ---\n" % (self.st, time.strftime("%Y-%m-%d %H:%M:%S")))
        izpis.flush()
        self.proc = subprocess.Popen([cmd, SKRIPTA], env=okolje, stdin=subprocess.DEVNULL, stdout=izpis,
                                     stderr=subprocess.STDOUT, cwd=MAPA,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        izpis.close()
        sprejeto = {}

        def sprejmi():
            try:
                sprejeto["c"] = poslusalec.accept()
            except Exception as e:  # noqa: BLE001
                sprejeto["e"] = e

        nit = threading.Thread(target=sprejmi, name="delovni-sprejem", daemon=True)
        nit.start()
        rok = time.time() + ZAGON_ROK
        while nit.is_alive() and time.time() < rok and self.proc.poll() is None:
            nit.join(0.2)
        if "c" not in sprejeto:
            try:
                poslusalec.close()
            except Exception:  # noqa: BLE001
                pass
            self.ustavi()
            raise RuntimeError("delovni proces se ni povezal (%s); dnevnik %s" % (
                sprejeto.get("e") or ("končal s kodo %s" % self.proc.returncode if self.proc and
                                      self.proc.returncode is not None else "rok"), DNEVNIK))
        poslusalec.close()
        self.conn = sprejeto["c"]
        pozdrav = self.conn.recv()   # {"pid", "verzija", "cas"}
        _dnevnik("delavec %d pripravljen (PID %s, zagon %.1f s)" % (self.st, pozdrav.get("pid"), pozdrav.get("cas", 0)))

    def ustavi(self):
        try:
            if self.conn is not None:
                self.conn.close()
        except Exception:  # noqa: BLE001
            pass
        self.conn = None
        if self.proc is not None and self.proc.poll() is None:
            try:
                self.proc.kill()
                self.proc.wait(10)
            except Exception:  # noqa: BLE001
                pass
        self.proc = None


def _vzemi_delavca(rok):
    """Prost (ali nov) delavec; zasede ga. Čaka do roka, če so vsi zasedeni."""
    with _kljuc:
        while True:
            for d in _delavci:
                if d.zaseden is None:
                    d.zaseden = "zagon"
                    return d
            if len(_delavci) < NAJVEC:
                d = Delavec(len(_delavci) + 1)
                d.zaseden = "zagon"
                _delavci.append(d)
                return d
            ostane = rok - time.time()
            if ostane <= 0:
                return None
            _kljuc.wait(min(ostane, 1.0))


def _sprosti(d):
    with _kljuc:
        d.zaseden = None
        _kljuc.notify_all()


def nova_mapa():
    """Začasna mapa posla (posnetki BREP, vrnjene oblike); pobriše jo pospravi()."""
    pot = os.path.join(MAPA_POSLOV, time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6])
    os.makedirs(pot, exist_ok=True)
    return pot


def pospravi(mapa):
    if mapa and os.path.normpath(mapa).startswith(os.path.normpath(MAPA_POSLOV) + os.sep):
        shutil.rmtree(mapa, ignore_errors=True)


def posel(vrsta, podatki, opis="", najdlje=NAJDLJE):
    """Zažene posel v delovnem procesu in takoj vrne slovar odgovora {konec: Event, napaka, rezultat} (ista oblika
    kot pri glavni niti, zato ga orodje `opravilo` zna počakati). Rezultat je slovar, ki ga vrne delovni proces."""
    odgovor = {"konec": threading.Event(), "izpis": "", "napaka": "", "rezultat": None, "delovni": True}

    def tek():
        d = _vzemi_delavca(time.time() + najdlje)
        if d is None:
            odgovor["napaka"] = "Vsi delovni procesi so zasedeni."
            odgovor["konec"].set()
            return
        try:
            if not d.zivi():
                d.ustavi()
                d.zazeni()
            d.zaseden = opis or vrsta
            d.zacetek = time.time()
            d.poslov += 1
            d.conn.send({"vrsta": vrsta, **podatki})
            rok = d.zacetek + najdlje
            while True:
                if d.conn.poll(0.5):
                    odgovor["rezultat"] = d.conn.recv()
                    break
                if d.proc is None or d.proc.poll() is not None:
                    odgovor["napaka"] = "Delovni proces se je med poslom končal (koda %s; morda zrušitev OCC). " \
                                        "Dnevnik: %s" % (d.proc.returncode if d.proc else "?", DNEVNIK)
                    d.ustavi()
                    break
                if odgovor.get("ustavi") or time.time() > rok:
                    odgovor["napaka"] = ("Posel je ustavljen na zahtevo." if odgovor.get("ustavi") else
                                         "Posel je presegel %d s; delovni proces je ustavljen." % najdlje)
                    d.ustavi()
                    break
        except (EOFError, OSError) as e:
            odgovor["napaka"] = "Povezava z delovnim procesom je prekinjena (%s). Dnevnik: %s" % (e, DNEVNIK)
            d.ustavi()
        except Exception:  # noqa: BLE001
            odgovor["napaka"] = traceback.format_exc()
            d.ustavi()
        finally:
            trajanje = time.time() - d.zacetek if d.zacetek else 0.0
            _dnevnik("posel %s (delavec %d): %.1f s%s" % (opis or vrsta, d.st, trajanje,
                                                         " NAPAKA" if odgovor["napaka"] else ""))
            d.zacetek = 0.0
            _sprosti(d)
            odgovor["konec"].set()

    threading.Thread(target=tek, name="delovni-posel", daemon=True).start()
    return odgovor


def stanje():
    """Seznam delavcev za orodje `stanje` in /stanje."""
    with _kljuc:
        return [{"st": d.st, "pid": d.proc.pid if d.proc is not None and d.proc.poll() is None else None,
                 "zaseden": d.zaseden, "s": round(time.time() - d.zacetek, 1) if d.zacetek else 0.0,
                 "poslov": d.poslov} for d in _delavci]


def povzetek():
    s = stanje()
    if not s:
        return "Delovni procesi (FreeCADCmd za težke izračune): še niso zagnani (do %d, zaženejo se ob prvem poslu)." % NAJVEC
    return "Delovni procesi: " + "; ".join(
        "%d: %s" % (x["st"], ("dela »%s« %d s" % (x["zaseden"], x["s"])) if x["zaseden"] and x["s"] else
                    ("zaganja se" if x["zaseden"] else ("prost" if x["pid"] else "ustavljen")))
        for x in s)


def ogrej(zamik=20.0):
    """Zažene enega delavca v ozadju (prvi posel nato ne čaka na zagon FreeCADCmd)."""
    def tek():
        time.sleep(zamik)
        d = _vzemi_delavca(time.time() + 1)
        if d is None:
            return
        try:
            if not d.zivi():
                d.zazeni()
        except Exception as e:  # noqa: BLE001
            _dnevnik("ogrevanje: %s" % e)
        finally:
            _sprosti(d)
    threading.Thread(target=tek, name="delovni-ogrevanje", daemon=True).start()


def ustavi_vse():
    with _kljuc:
        for d in _delavci:
            d.ustavi()


# ---------------------------------------------------------------------------------------------------------------
# Posnetek oblik (glavna nit): BREP z globalno lego v mapo posla

def posnemi(oblike, mapa):
    """`oblike`: [(ime, Part.Shape)] -> [(ime, pot_brep)]. Hitro (zapis BREP), zato sme na glavno nit."""
    izid = []
    for i, (ime, oblika) in enumerate(oblike):
        pot = os.path.join(mapa, "o%03d.brep" % i)
        oblika.exportBrep(pot)
        izid.append((ime, pot))
    return izid
