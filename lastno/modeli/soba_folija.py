# -*- coding: utf-8 -*-
"""Sestav sobe za tisk: Roland TrueVIS VG3-640 na sredini, stenska zalogovnika folije ob dolgih stenah.

Zagon: v FreeCAD-u z oknom (barve se shranijo le takrat), npr. v spletnem strežniku prek POST /python:
    exec(open(r".../lastno/modeli/soba_folija.py", encoding="utf-8").read())
Pred tem mora obstajati police-folija/police-folija.FCStd (skripta police_folija.py).

Koordinate sobe: x vzdolž dolge stene (3000), y v globino (2600), z = 0 so tla.
Tiskalnik stoji vzdolž dolge stene (širši je od kratke stene); spredaj je proti steni y = 0.
Mere tiskalnika (s stojalom): 2886 x 748 x 1320 mm, 203 kg (Roland DG, podatkovni list VG3-640).
Tiskalnik je poenostavljen obris za razporeditev, ne natančen model.
"""
import os

import FreeCAD as App
import Part
from FreeCAD import Vector as V

SOBA_X, SOBA_Y, SOBA_Z = 3000.0, 2600.0, 2500.0   # višina sobe ni znana; le za prikaz
STENA_D = 100.0
TLA_D = 20.0
TISK_X, TISK_Y, TISK_Z = 2886.0, 748.0, 1320.0
REGAL_W, REGAL_D = 1700.0, 260.0                    # notranja širina in globina zalogovnika

MAPA = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else \
    r"C:\Users\Uporabnik\Desktop\Apps\FreeCAD\lastno\modeli"
REGAL = os.path.join(MAPA, "police-folija", "police-folija.FCStd")
IZHOD = os.path.join(MAPA, "police-folija")

ANTRACIT, BELA, ALU = (0.17, 0.18, 0.20), (0.93, 0.93, 0.92), (0.75, 0.76, 0.78)


def _barva(obj, b, prosojnost=0):
    try:
        obj.ViewObject.ShapeAppearance = [App.Material(DiffuseColor=b)]
        obj.ViewObject.Transparency = prosojnost
    except Exception:  # brez okna ni ViewObject
        pass


def _kos(doc, skupina, ime, oblika, barva, prosojnost=0):
    o = doc.addObject("Part::Feature", ime)
    o.Shape = oblika
    skupina.addObject(o)
    _barva(o, barva, prosojnost)
    return o


def soba(doc):
    s = doc.addObject("App::Part", "Soba")
    s.Label = "Soba 3,0 x 2,6 m"
    # tla so le znotraj sobe, stene stojijo ob njih (segajo do spodnjega roba tal), ne na njih
    tla = Part.makeBox(SOBA_X, SOBA_Y, TLA_D, V(0, 0, -TLA_D))
    _kos(doc, s, "Tla", tla, (0.55, 0.52, 0.48))
    zs, hs = -TLA_D, SOBA_Z + TLA_D
    # sprednja in leva stena sta skriti (pogled v sobo kot v prerezu)
    stene = [("Stena_spredaj", Part.makeBox(SOBA_X, STENA_D, hs, V(0, -STENA_D, zs))),
             ("Stena_zadaj", Part.makeBox(SOBA_X, STENA_D, hs, V(0, SOBA_Y, zs))),
             ("Stena_levo", Part.makeBox(STENA_D, SOBA_Y + 2 * STENA_D, hs, V(-STENA_D, -STENA_D, zs))),
             ("Stena_desno", Part.makeBox(STENA_D, SOBA_Y + 2 * STENA_D, hs, V(SOBA_X, -STENA_D, zs)))]
    for ime, oblika in stene:
        o = _kos(doc, s, ime, oblika, (0.86, 0.84, 0.80))
        if ime in ("Stena_spredaj", "Stena_levo"):
            o.Visibility = False
    return s


def tiskalnik(doc):
    """Poenostavljen Roland VG3-640: stojalo, ohišje, rola zadaj (dovod) in spredaj (navijalec)."""
    t = doc.addObject("App::Part", "Roland_VG3_640")
    t.Label = "Roland TrueVIS VG3-640"
    x0, y0 = (SOBA_X - TISK_X) / 2, (SOBA_Y - TISK_Y) / 2
    sivo, temno = (0.85, 0.86, 0.87), (0.25, 0.26, 0.28)
    noga_z = 820.0
    for x in (x0 + 60, x0 + TISK_X - 160):
        noga = Part.makeBox(100, 80, noga_z, V(x, y0 + TISK_Y / 2 - 40, 0))
        noga = noga.fuse(Part.makeBox(100, TISK_Y - 60, 40, V(x, y0 + 30, 0)))
        _kos(doc, t, "Noga_%d" % (1 if x < SOBA_X / 2 else 2), noga, temno)
    _kos(doc, t, "Precka_stojala", Part.makeBox(TISK_X - 320, 60, 60, V(x0 + 160, y0 + TISK_Y / 2 - 30, 300)), temno)
    # ohišje: stranska stolpa in vodilo z glavo
    ohisje = Part.makeBox(TISK_X, 520, 260, V(x0, y0 + 110, noga_z + 240))      # zgornji del z glavo
    ohisje = ohisje.fuse(Part.makeBox(TISK_X, 600, 240, V(x0, y0 + 70, noga_z)))  # plošča s tiskalno mizo
    ohisje = ohisje.cut(Part.makeBox(TISK_X - 2 * 330, 700, 120, V(x0 + 330, y0, noga_z + 180)))  # reža za medij
    for x in (x0, x0 + TISK_X - 330):
        ohisje = ohisje.fuse(Part.makeBox(330, 640, TISK_Z - noga_z, V(x, y0 + 50, noga_z)))
    o = _kos(doc, t, "Ohisje", ohisje.removeSplitter(), sivo)
    _kos(doc, t, "Zaslon", Part.makeBox(220, 20, 140, V(x0 + TISK_X - 290, y0 + 30, noga_z + 300)), temno)
    # role medija (1620 mm): dovod zadaj, navijalec spredaj
    dolzina = 1620.0
    xr = (SOBA_X - dolzina) / 2
    _kos(doc, t, "Rola_dovod", Part.makeCylinder(80, dolzina, V(xr, y0 + TISK_Y - 60, 560), V(1, 0, 0)), (0.15, 0.45, 0.75))
    _kos(doc, t, "Rola_navijalec", Part.makeCylinder(45, dolzina, V(xr, y0 + 60, 560), V(1, 0, 0)), (0.15, 0.45, 0.75))
    return t


def zalogovnik(doc, regal, ime, oznaka, placement):
    z = doc.addObject("App::Part", ime)
    z.Label = oznaka
    z.Placement = placement
    for o in regal.Objects:
        if hasattr(o, "Shape") and not o.Shape.isNull():
            barva = BELA if o.Name.startswith("Polica") else ALU if o.Name == "Kovice" else ANTRACIT
            _kos(doc, z, o.Name, o.Shape.copy(), barva)
    return z


def zgradi():
    pot = os.path.normcase(os.path.abspath(REGAL))
    regal = next((d for d in App.listDocuments().values()
                  if os.path.normcase(os.path.abspath(d.FileName or "")) == pot), None)
    odprl = regal is None
    if odprl:
        regal = App.openDocument(REGAL, hidden=True)
    for d in list(App.listDocuments().values()):
        if d.Name.startswith("SobaFolija"):
            App.closeDocument(d.Name)
    doc = App.newDocument("SobaFolija")
    doc.Label = "soba-folija"
    soba(doc)
    tiskalnik(doc)
    x0 = (SOBA_X - REGAL_W) / 2
    # zadnja stena (y = SOBA_Y): regal že gleda s hrbtom v +y
    zalogovnik(doc, regal, "Zalogovnik_zadaj", "Zalogovnik ob zadnji steni",
               App.Placement(V(x0, SOBA_Y - REGAL_D, 0), App.Rotation()))
    # sprednja stena (y = 0): zasukan za 180°
    zalogovnik(doc, regal, "Zalogovnik_spredaj", "Zalogovnik ob sprednji steni",
               App.Placement(V(x0 + REGAL_W, REGAL_D, 0), App.Rotation(V(0, 0, 1), 180)))
    if odprl:
        App.closeDocument(regal.Name)
    doc.recompute()

    # trki: zalogovnika s tiskalnikom in stenami
    def oblike(ime):
        rez = []
        for o in doc.getObject(ime).Group:
            s = o.Shape.copy()
            s.Placement = o.getGlobalPlacement()
            rez.append(s)
        return rez
    tisk = Part.makeCompound(oblike("Roland_VG3_640"))
    stene = Part.makeCompound(oblike("Soba"))
    porocilo = []
    for ime in ("Zalogovnik_zadaj", "Zalogovnik_spredaj"):
        reg = Part.makeCompound(oblike(ime))
        bb = reg.BoundBox
        porocilo.append("%s: x %.0f..%.0f, y %.0f..%.0f, z %.0f..%.0f, trk s tiskalnikom %.0f mm3, s stenami %.0f mm3"
                        % (ime, bb.XMin, bb.XMax, bb.YMin, bb.YMax, bb.ZMin, bb.ZMax,
                           reg.common(tisk).Volume, reg.common(stene).Volume))
    tb = tisk.BoundBox
    porocilo.append("Tiskalnik: x %.0f..%.0f, y %.0f..%.0f" % (tb.XMin, tb.XMax, tb.YMin, tb.YMax))
    porocilo.append("Prehod spredaj: %.0f mm, zadaj: %.0f mm, ob straneh tiskalnika: %.0f mm"
                    % (tb.YMin - REGAL_D, SOBA_Y - REGAL_D - tb.YMax, tb.XMin))

    doc.saveAs(os.path.join(IZHOD, "soba-folija.FCStd"))
    import Import
    Import.export([o for o in doc.Objects if o.TypeId == "App::Part"], os.path.join(IZHOD, "soba-folija.step"))
    with open(os.path.join(IZHOD, "soba-porocilo.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(porocilo) + "\n")
    print("\n".join(porocilo))
    return doc


zgradi()
