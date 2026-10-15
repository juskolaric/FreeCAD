# -*- coding: utf-8 -*-
"""Kopija sestava boxa za toplotno simulacijo (MKE, CalculiX) — korak 3 iz TOPLOTNA-ANALIZA-PLAN.md.

Iz odprtega sestava (npr. Slim A) vzame kose po skupinah SKUPINE, vrata zasuče v zaprto lego (okoli tečaja TECAJ) in zgradi
nov dokument »<sestav> toplota«:
  - Plašč: obris zaprtega boxa iz prerezov pravih pločevinastih delov (konveksna ovojnica prerezov na treh višinah, zato
    so zaobljeni robovi in nos vrat v modelu), izvlečen po višini, enakovredna debelina (mke.debelina_plasca_mm);
  - Steklo in okni LED spredaj (izrezana iz plašča, sledita njegovi obliki);
  - naprave s **pravo obliko** (PC, napajalnik, tiskalnik, TV, LED obroča, POS, zvočnik, Mikrotik), kadar je kos veljavno
    telo z zmernim številom ploskev; sicer kot blok (elektro plošče, klima, kameri);
  - Zrak: notranjost brez naprav.
Vsi kosi gredo v Boolean Fragments (skupne ploskve za eno mrežo); dokument nosi analizo FEM z mrežo (stari Netgen).
Vhod CalculiX zapiše mke_zagon.py sam (nabori elementov po težiščih: okna, plašč, naprave prek Shape.isInside, sicer zrak).

Teče na glavni niti FreeCAD-a (spletni strežnik, ukaz »toplota«) ali v FreeCADCmd. Izhod: <Toplota>/mke/<ime> toplota.FCStd +
model.json (opis teles in blokov za mke_zagon.py in 3D pregledovalnik).
"""
import json
import math
import os
import re
import time

import FreeCAD as App
import Part
from FreeCAD import Vector

# kos v sestavu (začetek oznake) -> skupina v modelu; moč iz naprave_W po ključu skupine
SKUPINE = [
    ("ELEKTRO - PC", "PC"), ("Napajalnik za računalnik", "PC"), ("PRINT", "Tiskalnik"), ("Klima Basi ohišje", "Klima"),
    ("MIkrotik nosilec", "Mikrotik"), ("TV Basi", "TV"), ("DISPLAX", "TV"), ("Elektro TV - A", "Elektro TV"),
    ("Elektro levo zgoraj A", "Elektro levo"), ("LED RING", "LED"), ("NEXGO", "POS"), ("Canon M50", "Kamera"),
    ("Steklo basi A", "Steklo"), ("ZVOČNIK", "Zvočnik"),
]
MOC_KLJUC = {"PC": "PC + napajalnik", "TV": "TV", "Tiskalnik": "tiskalnik (povprečje)", "Mikrotik": "Mikrotik",
             "LED": "LED obroči", "POS": "POS in ostalo"}
# material po skupini: (prevodnost W/mK, gostota kg/m3, spec. toplota J/kgK)
MATERIALI = {"Plašč": (12.5, 7850, 480), "Steklo": (0.19, 1190, 1470), "Okno LED": (0.19, 1190, 1470),
             "Zrak": (1.0, 1.15, 1005), "Klima": (50.0, 2700, 900), "naprava": (10.0, 1500, 1000)}
# skupine, ki gredo v model s pravo obliko (če je kos veljaven in ne prevelik); ostale kot blok
# Prave oblike naprav: tiskalnik (STEP Sinfonia ima prekrivajoče se ploskve), PC (tanki deli) in LED obroč Gmsh-u podrejo mrežo
# (»overlapping facets«), TV in zvočnik imata preveč ploskev; zanesljivo gre le POS. Ostale naprave so bloki (okvirji), plašč
# pa ima pravi obris boxa (zaobljeni robovi, nos vrat).
REALNE = {"POS"}   # Mikrotik s pravo obliko (nosilec + SXT, 258 ploskev) Gmsh-u prav tako podre mrežo
NAJVEC_PLOSKEV = 300   # TV (656 ploskev) in zvočnik (551) kot blok: s pravo obliko Netgen ni dal prostorninske mreže (164k površinskih vozlišč, 0 teles)
VRATA = "Slim spredaj A"
TECAJ = "42-1-4349"
OBRIS_DELI = ("Slim zadaj A", "Slim spredaj A", "Kapa A")


def _okvir(sh):
    b = sh.BoundBox
    return [b.XMin, b.YMin, b.ZMin, b.XMax, b.YMax, b.ZMax]


def _unija(a, b):
    return [min(a[0], b[0]), min(a[1], b[1]), min(a[2], b[2]), max(a[3], b[3]), max(a[4], b[4]), max(a[5], b[5])]


def _ovojnica(tocke):
    """Konveksna ovojnica točk (x, y) — monotona veriga."""
    pts = sorted(set((round(x, 2), round(y, 2)) for x, y in tocke))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    spodaj, zgoraj = [], []
    for p in pts:
        while len(spodaj) >= 2 and cross(spodaj[-2], spodaj[-1], p) <= 0:
            spodaj.pop()
        spodaj.append(p)
    for p in reversed(pts):
        while len(zgoraj) >= 2 and cross(zgoraj[-2], zgoraj[-1], p) <= 0:
            zgoraj.pop()
        zgoraj.append(p)
    return spodaj[:-1] + zgoraj[:-1]


def _poenostavi(poligon, najmanj_mm=4.0):
    """Izpusti oglišča, ki so bližje kot najmanj_mm (mreža sicer dobi drobne robove)."""
    out = []
    for p in poligon:
        if not out or math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) >= najmanj_mm:
            out.append(p)
    if len(out) > 2 and math.hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) < najmanj_mm:
        out.pop()
    return out


def preberi_sestav(doc, log=print):
    """Kosi sestava po skupinah (oblika v zaprti legi), obris zaprtega boxa in okvirji. Vrne slovar za gradnjo."""
    koreni = [o for o in doc.Objects if o.TypeId == "Assembly::AssemblyObject"]
    if not koreni:
        raise ValueError("Dokument ni sestav (ni Assembly::AssemblyObject).")
    koren = koreni[0]
    tecaj = None
    for o in doc.Objects:
        if o.Label.startswith(TECAJ):
            try:
                b = Part.getShape(o).BoundBox
                tecaj = ((b.XMin + b.XMax) / 2, (b.YMin + b.YMax) / 2)
                break
            except Exception:  # noqa: BLE001
                pass
    if tecaj is None:
        raise ValueError("V sestavu ne najdem tečaja »%s«." % TECAJ)

    def zapri(sh, je_vrata):
        if not je_vrata:
            return sh
        k = sh.copy()
        k.rotate(Vector(tecaj[0], tecaj[1], 0), Vector(0, 0, 1), 90)
        return k

    kosi, obrisi, z_obseg = {}, [], None
    for sub in koren.getSubObjects():
        try:
            otrok = koren.getSubObject(sub, retType=1)
            sh = Part.getShape(koren, sub, needSubElement=False)
        except Exception:  # noqa: BLE001
            continue
        if otrok is None or sh.isNull() or sh.Volume < 1:
            continue
        oznaka = otrok.Label
        # na vratih so tudi elektronika TV in tiskanina osvetlitve (v sestavu Slim A niso pod podsestavom vrat, a se vrtijo z njimi)
        je_vrata = oznaka.startswith(VRATA) or oznaka.startswith("Elektro TV - A") or oznaka.startswith("ELEKTRO - TV PCB")
        if any(oznaka.startswith(z) for z in OBRIS_DELI):
            obrisi.append(zapri(sh, je_vrata))
            if oznaka.startswith("Slim zadaj A"):
                z_obseg = [sh.BoundBox.ZMin, z_obseg[1] if z_obseg else sh.BoundBox.ZMax]
            if oznaka.startswith("Kapa A"):
                z_obseg = [z_obseg[0] if z_obseg else sh.BoundBox.ZMin, sh.BoundBox.ZMax]
        kandidati = [(oznaka, sub, sh)]
        if hasattr(otrok, "getSubObjects") and otrok.getSubObjects():
            for sub2 in otrok.getSubObjects():
                try:
                    c2 = koren.getSubObject(sub + sub2, retType=1)
                    sh2 = Part.getShape(koren, sub + sub2, needSubElement=False)
                except Exception:  # noqa: BLE001
                    continue
                if c2 is not None and not sh2.isNull() and sh2.Volume >= 1:
                    kandidati.append((c2.Label, sub + sub2, sh2))
        for lab, pot, sh_k in kandidati:
            for zacetek, skupina in SKUPINE:
                if lab.startswith(zacetek):
                    kljuc = (skupina, oznaka)
                    sh_z = zapri(sh_k, je_vrata)
                    if kljuc in kosi:
                        kosi[kljuc]["oblike"].append(sh_z)
                    else:
                        kosi[kljuc] = {"skupina": skupina, "kos": oznaka, "oblike": [sh_z]}
                    break
    if not obrisi or not z_obseg:
        raise ValueError("V sestavu ne najdem delov obrisa (%s)." % ", ".join(OBRIS_DELI))
    # obris zaprtega boxa: konveksna ovojnica prerezov pravih delov na treh višinah
    tocke = []
    for z in (z_obseg[0] + 0.2 * (z_obseg[1] - z_obseg[0]), (z_obseg[0] + z_obseg[1]) / 2, z_obseg[0] + 0.85 * (z_obseg[1] - z_obseg[0])):
        for sh in obrisi:
            try:
                for w in sh.slice(Vector(0, 0, 1), z):
                    tocke += [(v.X, v.Y) for v in w.Vertexes]
            except Exception:  # noqa: BLE001
                pass
    if len(tocke) < 3:
        raise ValueError("Prerezi delov obrisa niso dali točk.")
    obris = _poenostavi(_ovojnica(tocke))
    log("obris: %d točk ovojnice iz %d točk prerezov" % (len(obris), len(tocke)))
    bloki = []
    for (skupina, oznaka), k in kosi.items():
        solidi = [s for sh in k["oblike"] for s in sh.Solids]
        okv = None
        for sh in k["oblike"]:
            okv = _unija(okv, _okvir(sh)) if okv else _okvir(sh)
        realna = (skupina in REALNE and solidi and all(s.isValid() for s in solidi)
                  and sum(len(s.Faces) for s in solidi) <= NAJVEC_PLOSKEV and len(solidi) <= 20)
        bloki.append({"skupina": skupina, "kos": oznaka, "okvir": [round(v, 1) for v in okv], "realna": bool(realna),
                      "oblika": Part.makeCompound(solidi) if realna else None, "ploskev": sum(len(s.Faces) for s in solidi)})
    bloki.sort(key=lambda b: (b["skupina"], b["kos"]))
    xs, ys = [p[0] for p in obris], [p[1] for p in obris]
    zunanji = [min(xs), min(ys), z_obseg[0], max(xs), max(ys), z_obseg[1]]
    return {"zunanji": [round(v, 1) for v in zunanji], "obris": obris, "tecaj": tecaj, "bloki": bloki, "sestav": doc.Label}


def _skatla(o):
    return Part.makeBox(o[3] - o[0], o[4] - o[1], o[5] - o[2], Vector(o[0], o[1], o[2]))


def _presek(a, b):
    return [max(a[0], b[0]), max(a[1], b[1]), max(a[2], b[2]), min(a[3], b[3]), min(a[4], b[4]), min(a[5], b[5])]


def _veljaven(o, najmanj=5.0):
    return o[3] - o[0] >= najmanj and o[4] - o[1] >= najmanj and o[5] - o[2] >= najmanj


def _prizma(poligon, z0, z1):
    pts = [Vector(x, y, z0) for x, y in poligon] + [Vector(poligon[0][0], poligon[0][1], z0)]
    return Part.Face(Part.makePolygon(pts)).extrude(Vector(0, 0, z1 - z0))


def _notranji_obris(poligon, t):
    pts = [Vector(x, y, 0) for x, y in poligon] + [Vector(poligon[0][0], poligon[0][1], 0)]
    notranji = Part.Face(Part.makePolygon(pts)).makeOffset2D(-t, 2, False, False, False)
    return [(v.X, v.Y) for v in notranji.OuterWire.OrderedVertexes]


BARVE = {"Plašč": (0.82, 0.84, 0.87), "Steklo": (0.55, 0.75, 0.95), "Okno LED": (0.55, 0.75, 0.95), "PC": (0.85, 0.35, 0.3),
         "TV": (0.2, 0.25, 0.3), "Tiskalnik": (0.5, 0.5, 0.55), "Klima": (0.3, 0.6, 0.9), "Mikrotik": (0.9, 0.6, 0.2), "LED": (0.95, 0.85, 0.3),
         "POS": (0.3, 0.3, 0.35), "Kamera": (0.25, 0.25, 0.25), "Elektro levo": (0.4, 0.7, 0.4), "Elektro TV": (0.4, 0.7, 0.4), "Zvočnik": (0.45, 0.4, 0.4)}


def uredi_prikaz(doc, deli, Z):
    """Prikaz modela v pogledu: naprave in okna obarvani po skupinah, zrak in pomožni objekti skriti, plašč za prikaz prerezan po
    sredini (leva polovica), ker spletni pogled prosojnosti ne riše; pravi Plašč ostane skrit (uporablja ga mreža)."""
    polovica = Part.makeBox(Z[3] - Z[0] + 20, Z[4] - Z[1] + 20, Z[5] - Z[2] + 20, Vector((Z[0] + Z[3]) / 2, Z[1] - 10, Z[2] - 10))
    for o in doc.Objects:
        if o.TypeId != "Part::Feature":
            continue
        lab = o.Label
        skupina = next((k for k in sorted(BARVE, key=len, reverse=True) if lab.startswith(k)), None)
        if lab == "Plašč":
            o.Visibility = False
            pr = doc.addObject("Part::Feature", "Prikaz_plasca")
            pr.Label = "Plašč (prikaz, prerezan)"
            pr.Shape = o.Shape.cut(polovica)
            if pr.ViewObject is not None:
                pr.ViewObject.ShapeColor = BARVE["Plašč"]
            continue
        if skupina is None or lab.startswith("Zrak") or lab.startswith("Notranjost"):
            o.Visibility = False
            continue
        o.Visibility = True
        if o.ViewObject is not None:
            o.ViewObject.ShapeColor = BARVE[skupina]


def _ascii(s):
    s = s.replace("š", "s").replace("č", "c").replace("ž", "z").replace("Š", "S").replace("Č", "C").replace("Ž", "Z")
    return re.sub(r"[^A-Za-z0-9_]", "_", s)


def zgradi(doc_sestava, nast, mapa_mke, log=print):
    """Zgradi dokument »<sestav> toplota« (kosi, Boolean Fragments, analiza z mrežo), shrani v mapa_mke. Vrne (opis, dokument)."""
    t_zac = time.time()
    os.makedirs(mapa_mke, exist_ok=True)
    pod = preberi_sestav(doc_sestava, log)
    mke = nast.get("mke", {})
    t = float(mke.get("debelina_plasca_mm", 12))
    sc = mke.get("scenarij", {})
    Z = pod["zunanji"]
    obris = pod["obris"]
    obris_n = _notranji_obris(obris, t)
    zunanji_solid = _prizma(obris, Z[2], Z[5])
    notranjost = _prizma(obris_n, Z[2] + t, Z[5] - t)
    N = _okvir(notranjost)
    N2 = [N[0] + 2, N[1] + 2, N[2] + 2, N[3] - 2, N[4] - 2, N[5] - 2]
    notranjost2 = _prizma(_notranji_obris(obris, t + 2), Z[2] + t + 2, Z[5] - t - 2)   # naprave segajo le do tu
    ime = pod["sestav"] + " toplota"
    doc = App.newDocument(ime.replace(" ", "_"))
    doc.Label = ime
    deli = []   # (ime, skupina, oblika, opis)

    plasc = zunanji_solid.cut(notranjost)
    # okna spredaj (Y min): škatla skozi (tudi zaobljen) sprednji del plašča; okno = presek s plaščem
    okna = []
    for b in pod["bloki"]:
        o = b["okvir"]
        if b["skupina"] == "Steklo":
            okna.append(("Steklo", "Steklo", [o[0], Z[1] - 5, o[2], o[3], Z[1] + t + 60, o[5]]))
        elif b["skupina"] == "LED":
            cx, cz = (o[0] + o[3]) / 2, (o[2] + o[5]) / 2
            okna.append(("Okno LED", "Okno LED", [cx - 50, Z[1] - 5, cz - 50, cx + 50, Z[1] + t + 60, cz + 50]))
    stevci = {}
    for ime_okna, skupina, o in okna:
        sk = _skatla(o)
        okno = plasc.common(sk)
        if okno.isNull() or okno.Volume < 1000:
            continue
        plasc = plasc.cut(sk)
        stevci[ime_okna] = stevci.get(ime_okna, 0) + 1
        ime_o = ime_okna if stevci[ime_okna] == 1 else "%s %d" % (ime_okna, stevci[ime_okna])
        deli.append((ime_o, skupina, okno, {"okvir": [round(v, 1) for v in _okvir(okno)]}))
    deli.insert(0, ("Plašč", "Plašč", plasc, {}))

    # naprave: prava oblika ali blok
    bloki_opis, naprave = [], []
    zasedeno = []   # naprave se ne smejo prekrivati (zvočnik je v okvirju tiskalnika ...): vsaka nova odšteje prejšnje
    for b in pod["bloki"]:
        if b["skupina"] == "Steklo":
            continue
        sh = None
        if b["realna"]:
            try:
                sh = b["oblika"].common(notranjost2).removeSplitter()
            except Exception:  # noqa: BLE001
                sh = None
            if sh is None or sh.isNull() or sh.Volume < 1000:
                b["realna"] = False
        if not b["realna"]:
            o = _presek(b["okvir"], N2)
            if not _veljaven(o, 8.0):
                continue
            sh = _skatla(o).common(notranjost2)
            if sh.isNull() or sh.Volume < 1000:
                continue
        if zasedeno:
            try:
                sh2 = sh.cut(Part.makeCompound(zasedeno))
                if not sh2.isNull() and sh2.Volume > 500:
                    sh = sh2.removeSplitter() if b["realna"] else sh2
                else:
                    continue
            except Exception:  # noqa: BLE001
                pass
        stevci[b["skupina"]] = stevci.get(b["skupina"], 0) + 1
        ime_bloka = b["skupina"] if stevci[b["skupina"]] == 1 else "%s %d" % (b["skupina"], stevci[b["skupina"]])
        deli.append((ime_bloka, b["skupina"], sh, {}))
        if b["realna"]:
            # zrak vidi škatlo okoli prave oblike; reža med škatlo in obliko je ločeno (majhno) telo zraka. Veliko telo zraka z
            # drobnimi ploskvami pravih oblik Netgen sicer ne zmreži (površina da, prostornine ne).
            ob = _okvir(sh)
            H = _skatla(_presek([ob[0] - 3, ob[1] - 3, ob[2] - 3, ob[3] + 3, ob[4] + 3, ob[5] + 3], N2)).common(notranjost2)
            if zasedeno:
                H = H.cut(Part.makeCompound(zasedeno))
            reza = H.cut(sh)
            if not reza.isNull() and reza.Volume > 100:
                deli.append(("Zrak ob " + ime_bloka, "Zrak", reza, {}))
            naprave.append(H)
            zasedeno.append(H)
        else:
            naprave.append(sh)
            zasedeno.append(sh)
        bloki_opis.append({"ime": ime_bloka, "skupina": b["skupina"], "kos": b["kos"], "okvir": [round(v, 1) for v in _okvir(sh)],
                           "prostornina_l": round(sh.Volume / 1e6, 2), "realna": b["realna"], "ploskev": len(sh.Faces)})
    log("kosi: " + ", ".join("%s%s" % (b["ime"], "" if b["realna"] else " (blok)") for b in bloki_opis))
    zrak = notranjost.cut(Part.makeCompound(naprave)) if naprave else notranjost
    deli.append(("Zrak", "Zrak", zrak, {}))

    # objekti Part + Boolean Fragments
    objekti, imena_objektov = [], {}
    for ime_dela, skupina, sh, _o in deli:
        o = doc.addObject("Part::Feature", _ascii(ime_dela))
        o.Label = ime_dela
        o.Shape = sh
        objekti.append(o)
        imena_objektov[ime_dela] = o.Name
    o_not = doc.addObject("Part::Feature", "Notranjost")
    o_not.Label = "Notranjost (pomožno)"
    o_not.Shape = notranjost
    o_not.Visibility = False
    import BOPTools.SplitFeatures as SF
    frag = SF.makeBooleanFragments(name="Deli")
    frag.Label = "Deli (Boolean Fragments)"
    frag.Objects = objekti
    frag.Mode = "Standard"
    for o in objekti:
        o.Visibility = False
    doc.recompute()
    sh = frag.Shape
    log("Boolean Fragments: %d teles, %d ploskev (%.0f s)" % (len(sh.Solids), len(sh.Faces), time.time() - t_zac))

    # analiza FEM: mreža (izračuna se ob zagonu MKE); vhod CalculiX zapiše mke_zagon.py sam
    import ObjectsFem
    analiza = ObjectsFem.makeAnalysis(doc, "Analiza")
    analiza.Label = "Toplotna analiza"
    solver = ObjectsFem.makeSolverCalculiXCcxTools(doc, "CalculiX")
    solver.AnalysisType = "thermomech"
    solver.ThermoMechType = "pure heat transfer"
    solver.ThermoMechSteadyState = True
    analiza.addObject(solver)
    mreza = ObjectsFem.makeMeshNetgenLegacy(doc, "Mreza")
    mreza.Label = "Mreža Netgen"
    mreza.Shape = frag
    mreza.MaxSize = float(mke.get("velikost_elementa_mm", 100))
    mreza.SecondOrder = False
    mreza.Fineness = str(mke.get("finost", "VeryCoarse"))
    analiza.addObject(mreza)
    for o in doc.Objects:
        if o.TypeId.startswith("Fem::") and o is not analiza:
            o.purgeTouched()

    # moči, materiali, opis
    moci = nast.get("naprave_W", {})
    tau = float(nast.get("steklo", {}).get("prepustnost", 0.8))
    A_steklo = sum((d[3]["okvir"][3] - d[3]["okvir"][0]) * (d[3]["okvir"][5] - d[3]["okvir"][2]) for d in deli if d[1] == "Steklo") / 1e6
    skozi_steklo = tau * A_steklo * float(sc.get("G_spredaj", 0))
    for b_ in bloki_opis:
        P = float(moci.get(MOC_KLJUC.get(b_["skupina"], ""), 0) or 0)
        if b_["skupina"] == "TV":
            P += skozi_steklo
        if b_["skupina"] == "Klima":
            P = -float(nast.get("hlajenje", {}).get("klima_W", 0) or 0)
        V = sum(x["prostornina_l"] for x in bloki_opis if x["skupina"] == b_["skupina"]) or 1.0
        b_["W"] = round(P * b_["prostornina_l"] / V, 1)
        b_["objekt"] = imena_objektov[b_["ime"]]
    okna_opis = [{"ime": d[0], "skupina": d[1], "okvir": d[3]["okvir"], "objekt": imena_objektov[d[0]]} for d in deli if d[1] in ("Steklo", "Okno LED")]
    skupina_obmocja = {b_["ime"]: b_["skupina"] for b_ in bloki_opis}
    skupina_obmocja.update({o_["ime"]: o_["skupina"] for o_ in okna_opis})
    skupina_obmocja.update({"Plašč": "Plašč", "Zrak": "Zrak"})
    materiali = {}
    for ime_o, sk in skupina_obmocja.items():
        k, rho, cp = MATERIALI.get(sk, MATERIALI["naprava"])
        if sk == "Plašč":
            k = float(mke.get("prevodnost_plasca", k))
        elif sk == "Zrak":
            k = float(mke.get("prevodnost_zraka", k))
        elif sk not in MATERIALI:
            k = float(mke.get("prevodnost_naprav", k))
        materiali[ime_o] = {"k": k, "rho": rho, "cp": cp}
    T_amb = float(sc.get("T_zunaj_C", 35))
    opis = {"sestav": pod["sestav"], "zunanji_mm": Z, "notranji_mm": [round(v, 1) for v in N], "obris": obris, "obris_notranji": obris_n,
            "debelina_mm": t, "tecaj": pod["tecaj"], "bloki": bloki_opis, "okna": okna_opis, "skupina_obmocja": skupina_obmocja,
            "materiali": materiali, "eps": float(nast.get("plasc", {}).get("emisivnost", 0.9)),
            "alpha": float(nast.get("plasc", {}).get("barve", {}).get(mke.get("barva", "bela"), 0.25)),
            "alpha_steklo": float(nast.get("steklo", {}).get("absorptivnost", 0.1)), "mke": mke, "scenarij": sc,
            "h": round(5.7 + 3.8 * float(sc.get("veter_ms", 1.0)), 2), "T_sky_C": round(0.0552 * (T_amb + 273.15) ** 1.5 - 273.15, 1),
            "A_steklo_m2": round(A_steklo, 3), "sonce_skozi_steklo_W": round(skozi_steklo, 1),
            "viri_W": [{"telo": b_["ime"], "W": b_["W"]} for b_ in bloki_opis if b_["W"]], "teles": len(sh.Solids), "ploskev": len(sh.Faces),
            "objekt_notranjost": o_not.Name, "cas_gradnje_s": round(time.time() - t_zac)}
    uredi_prikaz(doc, deli, Z)
    pot = os.path.join(mapa_mke, ime + ".FCStd")
    doc.saveAs(pot)
    opis["pot"] = pot
    with open(os.path.join(mapa_mke, "model.json"), "w", encoding="utf-8") as f:
        json.dump(opis, f, ensure_ascii=False, indent=1)
    log("model shranjen: %s (%.0f s)" % (pot, time.time() - t_zac))
    return opis, doc
