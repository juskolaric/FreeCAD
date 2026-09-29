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
    -> POST /ukaz -> Gui.runCommand na glavni niti; okna z nastavitvami ukaza se odprejo v FreeCAD-u.
  - Varnost: vsak POST potrebuje žeton (glava X-Zeton), ki nastane ob zagonu in ga pozna le stran.

Dogodki SSE (GET /events): model {verzija}, izbira [...], aktivni {ime: bool}, okolje {delovnaMiza, urejanje}.
Oblika posnetka geometrije (GET /model): glej _geometrija().
"""

import http.server
import json
import os
import queue
import secrets
import sys
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
# Okno FreeCAD-a: "skrito" (privzeto; pokaže se le, ko potrebuje vnos) ali "vidno".
OKNO_SKRITO = os.environ.get("SPLET_OKNO", "skrito") != "vidno"
try:
    MAPA = os.path.dirname(os.path.abspath(__file__))
except NameError:
    MAPA = os.path.join(App.getHomePath(), "lastno", "splet")
ZETON = secrets.token_hex(16)

# Delovna okolja, katerih ukazi so na voljo v brskalniku (ime, slovenski naslov, če ga FreeCAD nima).
DELOVNA_OKOLJA = [
    ("PartDesignWorkbench", "Snovanje delov"),
    ("SketcherWorkbench", "Skica"),
    ("PartWorkbench", "Del"),
]
# Splošne orodne vrstice (niso del zavihkov okolij).
SPLOSNE_ORODNE = {"File", "Edit", "Clipboard", "Workbench", "Macro", "View", "Individual Views", "Structure", "Help"}
# Vrstica hitrega dostopa (kot v SolidWorksu zgoraj levo).
HITRI_DOSTOP = ["Std_New", "Std_Open", "Std_Save", "Std_Undo", "Std_Redo", "Std_Refresh",
                "Std_ViewFitAll", "Std_ViewFitSelection", "Std_ViewIsometric"]


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


def _vidni_objekti(doc):
    v_urejanju = _objekt_v_urejanju(doc)
    for obj in doc.Objects:
        if not hasattr(obj, "Shape"):
            continue
        if STANJE.skica and obj.Name == STANJE.skica:
            continue  # skico, ki se ureja v brskalniku, brskalnik riše sam
        if obj.isDerivedFrom("PartDesign::Body") or obj.isDerivedFrom("App::Part"):
            continue  # vsebnika prikazujemo prek njunih vidnih elementov
        if _je_izhodisce(obj):
            continue  # osi in ravnine izhodišča (neskončne pomožne oblike)
        try:
            # Med urejanjem značilnosti (npr. Izboklina z odprtim oknom) je objekt v FreeCAD-u
            # viden kot predogled, čeprav je Visibility še False; pokažemo ga tudi tukaj.
            if not obj.Visibility and obj.Name != v_urejanju:
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
    """Posnetek enega objekta: teselirane ploskve (Face{i+1}) in diskretizirani robovi (Edge{j+1})."""
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
# Ukazi (samo glavna nit, samo z oknom)

_IKONE = {}


def _ikona_uri(ikona, kljuc):
    """QIcon -> PNG kot data URI (64 px), z medpomnilnikom po ključu."""
    if kljuc in _IKONE:
        return _IKONE[kljuc]
    uri = ""
    try:
        from PySide6 import QtCore
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
    try:
        for a in Gui.Command.get("Std_Workbench").getAction():
            if a.objectName() == ime or a.data() == ime:
                return _besedilo(a.text()) or privzeto
    except Exception:  # noqa: BLE001
        pass
    return privzeto


def zgradi_ukaze():
    """Seznam ukazov po delovnih okoljih in orodnih vrsticah (skupine ločene z ločili)."""
    from PySide6 import QtWidgets
    mw = Gui.getMainWindow()
    okolja = []
    imena_ukazov = []
    for ime, privzeti_naslov in DELOVNA_OKOLJA:
        if ime not in Gui.listWorkbenches():
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
        okolja.append({"ime": ime, "naslov": _naslov_okolja(ime, privzeti_naslov), "orodneVrstice": orodne})
    hitri = []
    for ime_ukaza in HITRI_DOSTOP:
        u = _ukaz(ime_ukaza, None)
        if u:
            hitri.append(u)
            imena_ukazov.append(ime_ukaza)
    return {"delovnaOkolja": okolja, "hitriDostop": hitri}, sorted(set(imena_ukazov))


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
    """Aktivira vsa potrebna delovna okolja, da nastanejo njihovi ukazi in orodne vrstice."""
    aktivno = Gui.activeWorkbench().name()
    for ime, _ in DELOVNA_OKOLJA:
        if ime in Gui.listWorkbenches():
            try:
                Gui.activateWorkbench(ime)
            except Exception:  # noqa: BLE001
                _log("okolja %s ni bilo mogoče naložiti: %s" % (ime, traceback.format_exc()))
    cilj = "PartDesignWorkbench" if "PartDesignWorkbench" in Gui.listWorkbenches() else aktivno
    try:
        Gui.activateWorkbench(cilj)
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# Skica v brskalniku: geometrijo in omejitve urejamo prek Python API-ja skice, reševalnik
# je FreeCAD-ov; FreeCAD-ov lastni način urejanja skice (okno) pri tem ni potreben.

def _v2(v):
    return [round(v.x, 4), round(v.y, 4)]


def _posnetek_skice(sk, novi=None):
    """Geometrija in omejitve skice v koordinatah skice ter lega skice v prostoru."""
    geometrija = []
    for i, g in enumerate(sk.Geometry):
        tip = type(g).__name__
        try:
            gradbena = bool(sk.getConstruction(i))
        except Exception:  # noqa: BLE001
            gradbena = bool(getattr(g, "Construction", False))
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
        geometrija.append(e)
    omejitve = []
    for i, c in enumerate(sk.Constraints):
        omejitve.append({
            "id": i, "tip": c.Type, "prvi": c.First, "prviPoz": c.FirstPos,
            "drugi": c.Second, "drugiPoz": c.SecondPos, "vrednost": round(c.Value, 4),
            "ime": c.Name, "gonilna": bool(c.Driving),
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
    return {
        "ime": sk.Name, "oznaka": sk.Label,
        "polozaj": {"osnova": [round(pl.Base.x, 4), round(pl.Base.y, 4), round(pl.Base.z, 4)],
                    "rotacija": [q[0], q[1], q[2], q[3]]},
        "geometrija": geometrija, "omejitve": omejitve, "resitev": resitev, "novi": novi or [],
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
            s = op.get(kljuc)
            if s:
                sk.addConstraint(Sketcher.Constraint("Coincident", i, poz, int(s[0]), int(s[1])))
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
        novi = ids
    elif vrsta == "krog":
        c, r = op["sredisce"], float(op["r"])
        if r <= 1e-6:
            raise ValueError("krog brez polmera")
        i = sk.addGeometry(Part.Circle(V(c[0], c[1], 0), V(0, 0, 1), r), gradbena)
        novi.append(i)
        s = op.get("spoji1")
        if s:
            sk.addConstraint(Sketcher.Constraint("Coincident", i, 3, int(s[0]), int(s[1])))
    elif vrsta == "tocka":
        p = op["p"]
        novi.append(sk.addGeometry(Part.Point(V(p[0], p[1], 0)), False))
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
                a, b = op["a"], op["b"]
                sk.addConstraint(Sketcher.Constraint("Coincident", int(a[0]), int(a[1]), int(b[0]), int(b[1])))
        elif vrsta == "gradbena":
            sk.toggleConstruction(int(op["id"]))
        elif vrsta == "izbrisiOmejitev":
            sk.delConstraint(int(op["id"]))
        else:
            raise ValueError("neznana vrsta: %s" % vrsta)
        doc.commitTransaction()
    except Exception:
        doc.abortTransaction()
        raise
    doc.recompute()
    return novi


# ---------------------------------------------------------------------------
# Stanje, deljeno med nitmi

class Stanje:
    def __init__(self):
        self.vrsta = queue.Queue()          # zahteve iz brskalnika -> glavna nit
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
        self.napaka = ""
        self.skica = ""                    # ime skice, ki se ureja v brskalniku
        self.samodejno_prikazano = False   # okno smo pokazali sami zaradi vnosa; po koncu ga spet skrijemo
        self.okno_na_zahtevo = False       # uporabnik je z gumbom zahteval vidno okno
        self.zapiranje_okna = False        # uporabnik je zaprl okno (X); ko ni več vprašanj, program konča

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
        zdaj = time.time()
        if self.umazano and zdaj - self.zadnja_gradnja > 0.3:
            self.zgradi()
        if IMA_OKNO and zdaj - self.zadnji_pregled > 0.5:
            self.zadnji_pregled = zdaj
            try:
                self.preveri_okolje()
            except Exception:  # noqa: BLE001
                self.napaka = traceback.format_exc()

    def zgradi(self):
        doc = App.ActiveDocument
        objekti = []
        if doc is not None:
            for obj in _vidni_objekti(doc):
                try:
                    objekti.append(_geometrija(obj))
                except Exception:  # noqa: BLE001
                    _log("objekt %s preskočen: %s" % (obj.Name, traceback.format_exc()))
        self.verzija += 1
        self._posnetek = json.dumps(
            {"dokument": doc.Label if doc else "", "verzija": self.verzija, "objekti": objekti},
            separators=(",", ":"),
        ).encode("utf-8")
        self.umazano = False
        self.zadnja_gradnja = time.time()
        self.oddaj("model", {"verzija": self.verzija})
        _log("posnetek %d: %d objektov, %.1f kB" % (self.verzija, len(objekti), len(self._posnetek) / 1024.0))

    def zgradi_ukaze(self):
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
        potrebuje_vnos = bool(pogovor) or opravilo
        if OKNO_SKRITO and not self.zapiranje_okna:
            # Skrito okno pokažemo, ko FreeCAD potrebuje vnos (izbira ravnine, nastavitve, urejanje skice),
            # in ga po koncu spet skrijemo. Če ga FreeCAD sam pokaže (npr. ob novem dokumentu), ga skrijemo,
            # razen če ga je uporabnik zahteval z gumbom.
            if potrebuje_vnos and not mw.isVisible():
                _pokazi_okno()
                self.samodejno_prikazano = True
            elif not potrebuje_vnos and mw.isVisible() and not self.okno_na_zahtevo:
                _skrij_okno()
                self.samodejno_prikazano = False
        if self.zapiranje_okna and not pogovor:
            if mw.isVisible():
                self.zapiranje_okna = False  # zapiranje preklicano (npr. pri vprašanju o shranjevanju)
            else:
                _log("okno zaprto, program se konča")
                QtWidgets.QApplication.instance().quit()
        try:
            spremenjeno = any(d.Modified for d in App.listDocuments().values())
        except Exception:  # noqa: BLE001
            spremenjeno = False
        okolje = {"delovnaMiza": Gui.activeWorkbench().name(), "urejanje": urejanje,
                  "pogovor": pogovor, "opravilo": opravilo, "oknoVidno": mw.isVisible(),
                  "spremenjeno": spremenjeno}
        if okolje != self.okolje:
            self.okolje = okolje
            self.oddaj("okolje", okolje)

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
                else:
                    _skrij_okno()
                self.zadnji_pregled = 0.0
        elif ukaz == "izhod":
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
        elif pot == "/ukazi":
            self._odgovor(STANJE.ukazi())
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
        poti = {"/select": "izbira", "/ukaz": "ukaz", "/okolje": "okolje", "/okno": "okno",
                "/izhod": "izhod", "/skica": "skica", "/znacilnost": "znacilnost", "/python": "python"}
        if pot in poti:
            STANJE.vrsta.put((poti[pot], podatki))
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
            STANJE.vrsta.put(("skica-posnetek", {}))
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


# ---------------------------------------------------------------------------
# Zagon

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

        # Skrito glavno okno ne sme pomeniti, da se program konča ob zaprtju zadnjega pogovornega okna.
        QtWidgets.QApplication.instance().setQuitOnLastWindowClosed(False)
        _FILTER = ZapiranjeOkna()
        mw.installEventFilter(_FILTER)
        if OKNO_SKRITO:
            _skrij_okno()
            _log("okno FreeCAD-a je skrito; pokaže se, ko potrebuje vnos, ali z gumbom v brskalniku")

    if App.ActiveDocument is None:
        _vzorcni_dokument()

    App.addDocumentObserver(OpazovalecDokumenta())
    if IMA_OKNO:
        Gui.addDocumentObserver(OpazovalecPogleda())
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
zazeni()
