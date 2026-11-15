# -*- coding: utf-8 -*-
"""Delovni proces spletnega FreeCAD-a (FreeCADCmd brez okna; zažene ga delovni.py).

Poveže se na strežnik (SPLET_DELOVNI_NASLOV, SPLET_DELOVNI_KLJUC), nato v zanki sprejema posle:
  izmeri  {oblike: [(ime, pot_brep)], a: {...}}             -> {besedilo}
  python  {koda, oblike: {ime: pot}, datoteke: [FCStd], mapa} -> {izpis, rezultat, napaka, vrnjene: {ime: pot}}
  izvoz   {oblike: [(ime, pot)], cilj, natancnost}          -> {besedilo}
Odgovor je vedno slovar; napaka v poslu ne konča procesa (zrušitev OCC ga, strežnik zažene novega).
"""

import contextlib
import io
import json
import os
import sys
import time
import traceback

ZACETEK = time.time()
MAPA = os.environ.get("SPLET_DELOVNI_MAPA") or os.getcwd()
if MAPA not in sys.path:
    sys.path.insert(0, MAPA)

from multiprocessing.connection import Client  # noqa: E402

import FreeCAD as App  # noqa: E402
import Part  # noqa: E402

import mcp_orodja as M  # noqa: E402  (izmeri_oblike in pomožne funkcije meritev; Gui je tu None)


def _beri(pot):
    s = Part.Shape()
    s.read(pot)
    return s


def _json(v):
    return json.loads(json.dumps(v, ensure_ascii=False, default=M._json_vrednost))


def p_izmeri(p):
    oblike = [(ime, _beri(pot)) for ime, pot in p["oblike"]]
    return {"besedilo": M.izmeri_oblike(oblike, p.get("a") or {})}


def p_python(p):
    oblike = {ime: _beri(pot) for ime, pot in (p.get("oblike") or {}).items()}
    pred = set(App.listDocuments())
    dokumenti = []
    for pot in p.get("datoteke") or []:
        dokumenti.append(App.openDocument(pot))
    okolje = {"__name__": "__ozadje__", "App": App, "FreeCAD": App, "Part": Part, "Vector": App.Vector,
              "Placement": App.Placement, "Rotation": App.Rotation, "oblike": oblike, "dokumenti": dokumenti,
              "doc": dokumenti[0] if dokumenti else None, "mapa": p.get("mapa") or "", "vrni": {}}
    izpis = io.StringIO()
    napaka = ""
    zacetek = time.time()
    try:
        with contextlib.redirect_stdout(izpis), contextlib.redirect_stderr(izpis):
            exec(compile(p["koda"], "<ozadje>", "exec"), okolje)
    except BaseException as e:  # noqa: BLE001
        vrstice = traceback.format_exception(type(e), e, e.__traceback__)
        napaka = "".join(v for v in vrstice[-12:] if "delovni_proces.py" not in v)
    trajanje = time.time() - zacetek
    vrnjene = {}
    if not napaka:
        for i, (ime, oblika) in enumerate((okolje.get("vrni") or {}).items()):
            if isinstance(oblika, Part.Shape) and not oblika.isNull():
                pot = os.path.join(p["mapa"], "vrni%03d.brep" % i)
                oblika.exportBrep(pot)
                vrnjene[str(ime)] = pot
    rezultat = None
    if not napaka and okolje.get("rezultat") is not None:
        try:
            rezultat = _json(okolje["rezultat"])
        except Exception as e:  # noqa: BLE001
            rezultat = "(rezultat ni JSON: %s)" % e
    for ime in list(App.listDocuments()):
        if ime not in pred:
            try:
                App.closeDocument(ime)   # dokumenti posla (odprti z diska) ne ostanejo za naslednji posel
            except Exception:  # noqa: BLE001
                pass
    return {"izpis": izpis.getvalue(), "napaka": napaka, "rezultat": rezultat, "vrnjene": vrnjene,
            "trajanje": trajanje}


def p_izvoz(p):
    cilj = p["cilj"]
    oblike = [(ime, _beri(pot)) for ime, pot in p["oblike"]]
    konec = os.path.splitext(cilj)[1].lower()
    if konec in (".stl",):
        import MeshPart
        natancnost = float(p.get("natancnost") or 0.1)
        mreza = None
        for _, o in oblike:
            m = MeshPart.meshFromShape(Shape=o, LinearDeflection=natancnost, AngularDeflection=0.3, Relative=False)
            if mreza is None:
                mreza = m
            else:
                mreza.addMesh(m)
        mreza.write(cilj)
        return {"besedilo": "STL: %s (%d trikotnikov, odstopanje %s mm)" % (cilj, mreza.CountFacets, natancnost)}
    if konec in (".brep", ".brp"):
        Part.makeCompound([o for _, o in oblike]).exportBrep(cilj)
        return {"besedilo": "BREP: %s" % cilj}
    import Import
    doc = App.newDocument("Izvoz")
    try:
        objekti = []
        for ime, o in oblike:
            obj = doc.addObject("Part::Feature", "Kos")
            obj.Label = ime
            obj.Shape = o
            objekti.append(obj)
        doc.recompute()
        Import.export(objekti, cilj)
    finally:
        App.closeDocument(doc.Name)
    return {"besedilo": "STEP: %s (%d kosov)" % (cilj, len(oblike))}


POSLI = {"izmeri": p_izmeri, "python": p_python, "izvoz": p_izvoz}


def main():
    host, port = os.environ["SPLET_DELOVNI_NASLOV"].rsplit(":", 1)
    conn = Client((host, int(port)), authkey=bytes.fromhex(os.environ["SPLET_DELOVNI_KLJUC"]))
    conn.send({"pid": os.getpid(), "verzija": ".".join(App.Version()[:3]), "cas": time.time() - ZACETEK})
    while True:
        try:
            posel = conn.recv()
        except (EOFError, OSError):
            break   # strežnik se je končal ali je zaprl povezavo
        try:
            fn = POSLI.get(posel.get("vrsta"))
            if fn is None:
                izid = {"napaka": "neznan posel: %r" % posel.get("vrsta")}
            else:
                izid = fn(posel)
        except BaseException:  # noqa: BLE001
            izid = {"napaka": traceback.format_exc()}
        try:
            conn.send(izid)
        except (EOFError, OSError):
            break
        sys.stdout.flush()


main()
