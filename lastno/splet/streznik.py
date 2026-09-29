# -*- coding: utf-8 -*-
"""Spletni pogled FreeCAD-a (dokaz koncepta): FreeCAD je motor, prikaz je v brskalniku.

Zagon (v oknu ali brez okna):
    FreeCAD.exe lastno/splet/streznik.py          (ali ZAZENI-SPLET.bat v tej mapi)
    FreeCADCmd.exe lastno/splet/streznik.py       (brez okna; ni izbire v 3D pogledu)
    v Python konzoli FreeCAD-a: exec(open(r"...\\lastno\\splet\\streznik.py", encoding="utf-8").read())
Nato v brskalniku: http://127.0.0.1:3020/

Zgradba:
  - HTTP strežnik teče v svoji niti in FreeCAD-ovega API-ja NIKOLI ne kliče sam. Bere le
    pripravljen posnetek geometrije (bajti JSON), zahteve iz brskalnika pa odloži v vrsto.
  - Glavna nit (časovnik v oknu ali zanka brez okna) obdela vrsto, ob spremembi dokumenta
    znova zgradi posnetek in odjemalcem pošlje dogodek (Server-Sent Events).
  - Izbira: klik v brskalniku -> POST /select -> Gui.Selection v FreeCAD-u -> opazovalec
    izbire -> dogodek "izbira" -> brskalnik obarva ploskev ali rob. Vir resnice je FreeCAD.
  - Ukazi: POST /python izvede Python na glavni niti (le z žetonom, ki ga pozna stran).

Oblika posnetka (/model): {"dokument", "verzija", "objekti": [ {"ime", "oznaka",
  "tocke": [x,y,z,...], "trikotniki": [i,j,k,...],
  "ploskve": [[zacetekTock, steviloTock, zacetekTrikotnikov, steviloTrikotnikov, r, g, b], ...],
  "robTocke": [x1,y1,z1,x2,y2,z2,...] (pari za odseke), "robovi": [[zacetekOdsekov, steviloOdsekov], ...] } ] }
Ploskev i ustreza FreeCAD-ovi oznaki "Face{i+1}", rob j oznaki "Edge{j+1}".
"""

import http.server
import json
import os
import queue
import secrets
import threading
import time
import traceback
import webbrowser

import FreeCAD as App

try:
    import FreeCADGui as Gui
    IMA_OKNO = hasattr(Gui, "getMainWindow") and Gui.getMainWindow() is not None
except Exception:  # noqa: BLE001
    Gui = None
    IMA_OKNO = False

VRATA = int(os.environ.get("SPLET_VRATA", "3020"))
TOLERANCA_PLOSKEV = 0.1   # mm, teselacija
ODMIK_ROBOV = 0.05        # mm, diskretizacija robov
ODPRI_BRSKALNIK = os.environ.get("SPLET_BRSKALNIK", "1") == "1"
try:
    MAPA = os.path.dirname(os.path.abspath(__file__))
except NameError:
    MAPA = os.path.join(App.getHomePath(), "lastno", "splet")
ZETON = secrets.token_hex(16)


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


def _vidni_objekti(doc):
    for obj in doc.Objects:
        if not hasattr(obj, "Shape"):
            continue
        if obj.isDerivedFrom("PartDesign::Body") or obj.isDerivedFrom("App::Part"):
            continue  # vsebnika prikazujemo prek njunih vidnih elementov
        try:
            if not obj.Visibility:
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


def _geometrija(obj):
    oblika = obj.Shape.copy()
    try:
        oblika.Placement = obj.getGlobalPlacement()
    except Exception:  # noqa: BLE001
        pass

    tocke, trikotniki, ploskve = [], [], []
    osnovna, po_ploskvah = _barve(obj, len(oblika.Faces))
    for i, ploskev in enumerate(oblika.Faces):
        try:
            v, t = ploskev.tessellate(TOLERANCA_PLOSKEV)
        except Exception:  # noqa: BLE001
            v, t = [], []
        zacetek_tock = len(tocke) // 3
        zacetek_trik = len(trikotniki) // 3
        for p in v:
            tocke.extend(_z3(p))
        for a, b, c in t:
            trikotniki.extend((a + zacetek_tock, b + zacetek_tock, c + zacetek_tock))
        barva = po_ploskvah[i] if po_ploskvah else osnovna
        ploskve.append([zacetek_tock, len(v), zacetek_trik, len(t),
                        round(barva[0], 3), round(barva[1], 3), round(barva[2], 3)])

    rob_tocke, robovi = [], []
    for rob in oblika.Edges:
        try:
            pts = rob.discretize(Deflection=ODMIK_ROBOV)
        except Exception:  # noqa: BLE001
            pts = [v.Point for v in rob.Vertexes]
        zacetek = len(rob_tocke) // 6
        for a, b in zip(pts, pts[1:]):
            rob_tocke.extend(_z3(a))
            rob_tocke.extend(_z3(b))
        robovi.append([zacetek, max(len(pts) - 1, 0)])

    return {
        "ime": obj.Name,
        "oznaka": obj.Label,
        "tocke": tocke,
        "trikotniki": trikotniki,
        "ploskve": ploskve,
        "robTocke": rob_tocke,
        "robovi": robovi,
    }


# ---------------------------------------------------------------------------
# Stanje, deljeno med nitmi

class Stanje:
    def __init__(self):
        self.vrsta = queue.Queue()          # zahteve iz brskalnika -> glavna nit
        self.odjemalci = []                 # vrste SSE odjemalcev
        self.kljuc = threading.Lock()
        self._posnetek = b'{"dokument":"","verzija":0,"objekti":[]}'
        self.verzija = 0
        self.izbira = []
        self.umazano = True
        self.zadnja_gradnja = 0.0
        self.napaka = ""

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

    def stanje(self):
        return {
            "verzija": self.verzija,
            "izbira": self.izbira,
            "vrata": VRATA,
            "okno": IMA_OKNO,
            "odjemalcev": len(self.odjemalci),
            "napaka": self.napaka,
        }

    # -- glavna nit --
    def obdelaj(self):
        while True:
            try:
                ukaz, podatki = self.vrsta.get_nowait()
            except queue.Empty:
                break
            try:
                self._izvedi(ukaz, podatki)
            except Exception:  # noqa: BLE001
                self.napaka = traceback.format_exc()
                _log("napaka pri ukazu %s: %s" % (ukaz, self.napaka))
        if self.umazano and time.time() - self.zadnja_gradnja > 0.3:
            self.zgradi()

    def zgradi(self):
        doc = App.ActiveDocument
        objekti = []
        if doc is not None:
            for obj in _vidni_objekti(doc):
                try:
                    objekti.append(_geometrija(obj))
                except Exception:  # noqa: BLE001
                    _log("objekt %s preskocen: %s" % (obj.Name, traceback.format_exc()))
        self.verzija += 1
        self._posnetek = json.dumps(
            {"dokument": doc.Label if doc else "", "verzija": self.verzija, "objekti": objekti},
            separators=(",", ":"),
        ).encode("utf-8")
        self.umazano = False
        self.zadnja_gradnja = time.time()
        self.oddaj("model", {"verzija": self.verzija})
        _log("posnetek %d: %d objektov, %.1f kB" % (self.verzija, len(objekti), len(self._posnetek) / 1024.0))

    def posodobi_izbiro(self):
        if not IMA_OKNO:
            return
        izbira = []
        for s in Gui.Selection.getSelectionEx():
            izbira.append({"objekt": s.ObjectName, "elementi": list(s.SubElementNames)})
        self.izbira = izbira
        self.oddaj("izbira", izbira)

    def _izvedi(self, ukaz, podatki):
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
        elif ukaz == "python":
            exec(podatki.get("koda", ""), {"App": App, "FreeCAD": App, "Gui": Gui, "FreeCADGui": Gui})
            self.umazano = True


STANJE = Stanje()


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

    def slotActivateDocument(self, doc):
        STANJE.umazano = True

    def slotCreatedDocument(self, doc):
        STANJE.umazano = True

    def slotDeletedDocument(self, doc):
        STANJE.umazano = True


class OpazovalecPogleda:
    def slotChangedObject(self, vobj, prop):
        if prop in ("ShapeAppearance", "ShapeColor", "DiffuseColor", "Visibility", "Transparency"):
            STANJE.umazano = True


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
    allow_reuse_address = True


class Zahteva(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # tiho
        pass

    def _odgovor(self, telo, vrsta="application/json; charset=utf-8", koda=200):
        self.send_response(koda)
        self.send_header("Content-Type", vrsta)
        self.send_header("Content-Length", str(len(telo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(telo)

    def do_GET(self):
        pot = self.path.split("?")[0]
        if pot == "/":
            with open(os.path.join(MAPA, "index.html"), "rb") as f:
                stran = f.read().replace(b"__ZETON__", ZETON.encode("ascii"))
            self._odgovor(stran, "text/html; charset=utf-8")
        elif pot == "/model":
            self._odgovor(STANJE.posnetek())
        elif pot == "/stanje":
            self._odgovor(json.dumps(STANJE.stanje(), ensure_ascii=False).encode("utf-8"))
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
        if pot == "/select":
            STANJE.vrsta.put(("izbira", podatki))
            self._odgovor(b'{"ok":true}')
        elif pot == "/python":
            STANJE.vrsta.put(("python", podatki))
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
            self._poslji_sse("model", {"verzija": STANJE.verzija})
            self._poslji_sse("izbira", STANJE.izbira)
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
        try:
            Gui.SendMsgToActiveView("ViewFit")
        except Exception:  # noqa: BLE001
            pass
    return doc


# ---------------------------------------------------------------------------
# Zagon

def zazeni():
    if App.ActiveDocument is None:
        _vzorcni_dokument()

    App.addDocumentObserver(OpazovalecDokumenta())
    if IMA_OKNO:
        Gui.addDocumentObserver(OpazovalecPogleda())
        Gui.Selection.addObserver(OpazovalecIzbire())

    streznik = Streznik(("127.0.0.1", VRATA), Zahteva)
    nit = threading.Thread(target=streznik.serve_forever, name="splet-streznik", daemon=True)
    nit.start()
    naslov = "http://127.0.0.1:%d/" % VRATA
    _log("strežnik teče na %s (okno: %s)" % (naslov, "da" if IMA_OKNO else "ne"))

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
zazeni()
