# -*- coding: utf-8 -*-
"""Lastni parametrični objekti za pločevino nad dodatkom SheetMetal (shaise), odporni na preimenovanje topologije.

SheetMetal objekti hranijo izbrane ploskve in robove po imenih (``Face4``, ``Edge14``). Ko se mera osnovnega
telesa spremeni (npr. višina izbokline pod posnetim robom), FreeCAD 1.x teh imen pogosto ne zna več preslikati
(»missing element reference … ?Edge14«) in kos se pokvari. Objekta tukaj imen ne hranita: ob vsakem preračunu
geometrijsko poiščeta, kar potrebujeta, in pokličeta jedro dodatka SheetMetal.

- ``TeloVPlocevino``: telo -> pločevina (SheetMetal »Solid to Sheet Metal«). Odstrani ravne ploskve na dnu
  (najnižji Z, normala navzdol) in razreže vse nevodoravne robove (navpični vogali, diagonale posnetih robov);
  vodoravni robovi postanejo upogibi. Primerno za škatle, korita, podstavke, odprte spodaj.
- ``Razgrnitev``: razgrnitev kosa (SheetMetal V2) z največje ravne ploskve z normalo navzgor (+Z).

Modul mora biti na poti Pythona, ko se odpre dokument: mapa ``lastno/plocevina`` je z mapo uporabniških dodatkov
povezana kot ``%APPDATA%/FreeCAD/v1-1/Mod/lastna_plocevina`` (stičišče, glej README.md v tej mapi).
Brez modula se dokument odpre, objekta pa obdržita zadnjo shranjeno obliko in se ne preračunata.
"""
import os
import sys

import FreeCAD as App
import Part


def _sheetmetal_na_poti():
    """FreeCAD, zagnan pred namestitvijo dodatka SheetMetal, mape dodatka še nima v sys.path."""
    try:
        import SheetMetalFromSolid  # noqa: F401
    except ImportError:
        sys.path.append(os.path.join(App.getUserAppDataDir(), "Mod", "sheetmetal"))
        dodatni = os.path.join(App.getUserAppDataDir(), "AdditionalPythonPackages", "py%d%d" % sys.version_info[:2])
        if os.path.isdir(dodatni) and dodatni not in sys.path:
            sys.path.append(dodatni)


def _lastnost(obj, tip, ime, skupina, opis, vrednost=None):
    if ime not in obj.PropertiesList:
        obj.addProperty(tip, ime, skupina, opis)
        if vrednost is not None:
            setattr(obj, ime, vrednost)


TOL = 1e-6


def izbira_za_skatlo(oblika):
    """Imena ploskev in robov za »Solid to Sheet Metal«: ravne ploskve na dnu (odstranijo se) in vsi
    nevodoravni robovi (razrežejo se)."""
    zmin = oblika.BoundBox.ZMin
    dno = ["Face%d" % k for k, f in enumerate(oblika.Faces, 1)
           if f.Surface.TypeId == "Part::GeomPlane" and abs(f.BoundBox.ZMax - zmin) < TOL]
    rezi = ["Edge%d" % k for k, e in enumerate(oblika.Edges, 1)
            if abs(e.BoundBox.ZMax - e.BoundBox.ZMin) > TOL]
    return dno + rezi


class TeloVPlocevino:
    def __init__(self, obj, osnova=None):
        obj.Proxy = self
        self._lastnosti(obj)
        if osnova is not None:
            obj.Osnova = osnova

    def _lastnosti(self, obj):
        _lastnost(obj, "App::PropertyLink", "Osnova", "Pločevina", "Telo, ki se pretvori v pločevino")
        _lastnost(obj, "App::PropertyLength", "Debelina", "Pločevina", "Debelina pločevine", 1.0)
        _lastnost(obj, "App::PropertyLength", "Polmer", "Pločevina", "Notranji polmer upogiba", 1.0)
        _lastnost(obj, "App::PropertyBool", "Navznoter", "Pločevina",
                  "Material navznoter od ploskev telesa (privzeto navzven)", False)

    def onDocumentRestored(self, obj):
        self._lastnosti(obj)

    def execute(self, obj):
        if obj.Osnova is None or obj.Osnova.Shape.isNull():
            return
        _sheetmetal_na_poti()
        import SheetMetalFromSolid
        oblika = obj.Osnova.Shape
        izbira = izbira_za_skatlo(oblika)
        obj.Shape = SheetMetalFromSolid.smMakeSheetMetalFromSolid(
            oblika, izbira, obj.Polmer.Value, obj.Debelina.Value, 0.1, obj.Navznoter)

    def dumps(self):
        return None

    def loads(self, stanje):
        return None


class Razgrnitev:
    def __init__(self, obj, kos=None):
        obj.Proxy = self
        self._lastnosti(obj)
        if kos is not None:
            obj.Kos = kos

    def _lastnosti(self, obj):
        _lastnost(obj, "App::PropertyLink", "Kos", "Razgrnitev", "Kos iz pločevine, ki se razgrne")
        _lastnost(obj, "App::PropertyFloat", "KFaktor", "Razgrnitev", "K-faktor (lega nevtralne osi)", 0.44)
        _lastnost(obj, "App::PropertyEnumeration", "Standard", "Razgrnitev", "ANSI: K glede na debelino; DIN: glede na polovico")
        if not obj.Standard:
            obj.Standard = ["ANSI", "DIN"]
            obj.Standard = "ANSI"

    def onDocumentRestored(self, obj):
        self._lastnosti(obj)

    @staticmethod
    def korenska_ploskev(oblika):
        kandidati = [(k, f) for k, f in enumerate(oblika.Faces, 1)
                     if f.Surface.TypeId == "Part::GeomPlane" and f.normalAt(0, 0).z > 0.99]
        if not kandidati:
            kandidati = [(k, f) for k, f in enumerate(oblika.Faces, 1) if f.Surface.TypeId == "Part::GeomPlane"]
        return "Face%d" % max(kandidati, key=lambda t: t[1].Area)[0]

    def execute(self, obj):
        if obj.Kos is None or obj.Kos.Shape.isNull():
            return
        _sheetmetal_na_poti()
        from SheetMetalNewUnfolder import BendAllowanceCalculator, getUnfold
        bac = BendAllowanceCalculator.from_single_value(obj.KFaktor, obj.Standard.lower())
        _koren, ravno, _pregibi, _normala, _info = getUnfold(bac, obj.Kos, self.korenska_ploskev(obj.Kos.Shape))
        obj.Shape = ravno

    def dumps(self):
        return None

    def loads(self, stanje):
        return None


def obris_za_laser(razgrnitev_oblika):
    """Zanke (zunanji obris in izrezi) zgornje ploskve razgrnitve, poravnane na XY in v izhodišče — za DXF."""
    ploskev = max(razgrnitev_oblika.Faces, key=lambda f: f.Area)
    n = ploskev.normalAt(0, 0)
    pl = App.Placement(App.Vector(), App.Rotation(n, App.Vector(0, 0, 1)))
    oblika = Part.Compound(ploskev.Wires).transformed(pl.toMatrix())
    b = oblika.BoundBox
    oblika.translate(App.Vector(-b.XMin, -b.YMin, -b.ZMin))
    return oblika
