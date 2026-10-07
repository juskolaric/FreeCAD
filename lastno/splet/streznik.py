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
  - Varnost: vsak POST potrebuje žeton (glava X-Zeton), ki nastane ob zagonu in ga pozna le stran.

Dogodki SSE (GET /events): model {verzija}, izbira [...], aktivni {ime: bool}, okolje {delovnaMiza, urejanje},
skica {...}, obrazec {vrsta, kljuc, naslov, vrstice | datoteka} ali null.
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

    rob_tocke, robovi, rob_info = [], [], []
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
        rob_info.append(_rob_info(rob))

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


def _rob_info(rob):
    """Analitični podatki roba za pripenjanje v skici (kot v SolidWorksu): krajišči, razpolovišče,
    pri krogih središče, polmer in os. Vse v svetovnih koordinatah."""
    info = {"tip": type(rob.Curve).__name__}
    try:
        if rob.Vertexes:
            info["p1"] = _z3(rob.Vertexes[0].Point)
            info["p2"] = _z3(rob.Vertexes[-1].Point)
        info["sredina"] = _z3(rob.valueAt((rob.FirstParameter + rob.LastParameter) / 2.0))
        info["zaprt"] = bool(rob.isClosed())
        if info["tip"] == "Circle":
            info["sredisce"] = _z3(rob.Curve.Center)
            info["r"] = round(rob.Curve.Radius, 4)
            info["os"] = _z3(rob.Curve.Axis)
    except Exception:  # noqa: BLE001
        pass
    return info


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
        stolpcev = min(model.columnCount(), 4)

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
    kljuc = "%s:%x" % (_razred(koren), id(koren))
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
        "geometrija": geometrija, "zunanji": zunanji, "omejitve": omejitve, "resitev": resitev, "novi": novi or [],
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
        self.skrita_okna = []              # okna (pogovori), ki smo jih ob prikazu naredili nevidna
        self.obrazec = None                # JSON obrazca, ki je trenutno v brskalniku (ali None)
        self.obrazec_mapa = {}             # id -> (gradnik, dodatno) zadnjega zajema
        self.zadnji_obrazec = 0.0

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
        }

    # -- glavna nit --
    def obdelaj(self):
        while True:
            try:
                ukaz, podatki, odgovor = self.vrsta.get_nowait()
            except queue.Empty:
                break
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
            izbira.append({"objekt": s.ObjectName, "elementi": list(s.SubElementNames)})
        self.izbira = izbira
        self.oddaj("izbira", izbira)

    def _izvedi(self, ukaz, podatki, odgovor=None):
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
        elif ukaz == "obrazec":
            if IMA_OKNO and self.obrazec is not None and podatki.get("kljuc") == self.obrazec.get("kljuc"):
                _obrazec_dejanje(self.obrazec_mapa, podatki)
                self.zadnji_obrazec = 0.0  # novo stanje obrazca takoj nazaj v brskalnik
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
        elif pot in ("/ikona.svg", "/favicon.ico"):
            with open(os.path.join(MAPA, "ikona.svg"), "rb") as f:
                self._odgovor(f.read(), "image/svg+xml")
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
                "/izhod": "izhod", "/skica": "skica", "/znacilnost": "znacilnost", "/obrazec": "obrazec"}
        if pot == "/python":
            # Počaka na izvedbo na glavni niti in vrne izpis, napako in spremenljivko "rezultat".
            odgovor = {"konec": threading.Event(), "izpis": "", "napaka": "", "rezultat": None}
            STANJE.vrsta.put(("python", podatki, odgovor))
            koncano = odgovor["konec"].wait(float(podatki.get("cakaj", 120) or 120))
            telo = {"ok": koncano and not odgovor["napaka"], "koncano": koncano, "izpis": odgovor["izpis"],
                    "napaka": odgovor["napaka"], "rezultat": odgovor["rezultat"]}
            self._odgovor(json.dumps(telo, ensure_ascii=False, default=str).encode("utf-8"))
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
