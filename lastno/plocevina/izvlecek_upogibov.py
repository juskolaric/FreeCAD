# -*- coding: utf-8 -*-
"""Izvleček upogibov za dokumentacijo krivljenja (FreeCADCmd, brez okna).

Za vsak dokument v mapi z razgrnitvami (objekti `Razgrnitev` iz lastna_plocevina) vrne JSON s podatki, ki jih rabi
krivilec: obris razgrnitve, upogibne črte (lega v razgrnitvi, kot, smer gor/dol glede na osnovno ploskev, notranji
polmer, dolžina), globina v drevesu upogibov, dolžina kraka v razgrnitvi; zraven STL upognjenega kosa za sliko.

    FreeCADCmd.exe izvlecek_upogibov.py "<mapa z FCStd>" "<izhodna mapa>"
Izhod: <izhod>/upogibi.json in <izhod>/stl/<kos>.stl. Odločitev 2026-10-30 (Photobox Slim A).
"""
import glob, json, math, os, sys

import FreeCAD as App
import Part

MAPA = sys.argv[-2] if len(sys.argv) >= 3 else r"C:\Users\Uporabnik\Oblak\3D modeliranje\Photobox Slim A\Deli\Pločevina"
IZHOD = sys.argv[-1] if len(sys.argv) >= 3 else os.path.join(MAPA, "Razrez 2026-10-30", "Upogibi")
os.makedirs(os.path.join(IZHOD, "stl"), exist_ok=True)

sys.path.append(os.path.join(App.getUserAppDataDir(), "Mod", "lastna_plocevina"))
import lastna_plocevina as lp  # noqa: E402

lp._sheetmetal_na_poti()
from SheetMetalNewUnfolder import unfold, SketchExtraction  # noqa: E402


def poravnava(oblika, koren_ploskev):
    """Matrika, ki razgrnitev položi v XY (normala korena -> +Z) z izhodiščem v spodnjem levem kotu okvira."""
    return SketchExtraction.move_to_origin(oblika, koren_ploskev)


def zanke_iz_robov(robovi):
    """Robovi razgrnitve -> seznam zank točk (loki razdeljeni)."""
    zanke = []
    for w in Part.sortEdges(robovi):
        pts = []
        for e in w:
            n = max(1, int(e.Length / 2.0)) if e.Curve.__class__.__name__ != "Line" else 1
            pts += [e.valueAt(e.FirstParameter + (e.LastParameter - e.FirstParameter) * k / n) for k in range(n)]
        zanke.append([[round(p.x, 3), round(p.y, 3)] for p in pts])
    return zanke


def stran_kraka(zanke, x0, y0, x1, y1):
    """Katera stran upogibne črte je krak (manjša ploščina točk zunanjega obrisa) in kako daleč sega (mm)."""
    dx, dy = x1 - x0, y1 - y0
    L = math.hypot(dx, dy) or 1
    nx, ny = -dy / L, dx / L
    zun = max(zanke, key=lambda z: abs(sum(z[i][0] * z[(i + 1) % len(z)][1] - z[(i + 1) % len(z)][0] * z[i][1] for i in range(len(z)))))
    levo = [(p[0] - x0) * nx + (p[1] - y0) * ny for p in zun]
    # ploščina obrisa na vsaki strani: približek s številom točk (gosto vzorčen obris)
    nl = sum(1 for d in levo if d > 0); nd = sum(1 for d in levo if d < 0)
    stran = 1 if nl < nd else -1
    doseg = max([d * stran for d in levo if d * stran > 0] or [0])
    return stran, doseg


def obdelaj(doc, obj):
    kos = obj.Kos
    shp = kos.Shape.transformed(kos.Placement.toMatrix().inverse())
    t = lp.debelina_kosa(shp)
    bac = lp.racun_upogiba(obj.KFaktor, obj.Standard.lower(), getattr(obj, "KTabela", ""))
    koren_ime = obj.Proxy.korenska_ploskev(shp)
    kandidati = [koren_ime] + ["Face%d" % k for k, f in sorted(enumerate(shp.Faces, 1), key=lambda x: -x[1].Area)
                              if f.Surface.TypeId == "Part::GeomPlane" and "Face%d" % k != koren_ime][:6]
    napaka = None
    for koren_ime in kandidati:
        try:
            idx = shp.findSubShape(shp.getElement(koren_ime))[1] - 1
            crte, upogibi = unfold(shp, idx, bac); break
        except Exception as e:  # noqa: BLE001
            napaka = e
    else:
        raise napaka
    M = poravnava(Part.makeCompound(crte), shp.Faces[idx])
    crte = [e.transformed(M) for e in crte]
    zanke = zanke_iz_robov(crte)
    xs = [p[0] for z in zanke for p in z]; ys = [p[1] for z in zanke for p in z]
    up = []
    for i, b in enumerate(upogibi, 1):
        l = b.line.transformed(M); a, c = l.Vertexes[0].Point, l.Vertexes[-1].Point
        stran, doseg = stran_kraka(zanke, a.x, a.y, c.x, c.y)
        up.append(dict(st=i, x0=round(a.x, 2), y0=round(a.y, 2), x1=round(c.x, 2), y1=round(c.y, 2), dolzina=round(l.Length, 1),
                       kot=round(abs(b.angle), 1), smer="gor" if b.angle > 0 else "dol", polmer=round(b.radius, 2),
                       stran_kraka=stran, krak_razgrnjen=round(doseg, 1)))
    # globina: koliko drugih upogibov ima to črto na strani svojega kraka
    for u in up:
        mx, my = (u["x0"] + u["x1"]) / 2, (u["y0"] + u["y1"]) / 2; g = 0
        for v in up:
            if v is u: continue
            dx, dy = v["x1"] - v["x0"], v["y1"] - v["y0"]; L = math.hypot(dx, dy) or 1
            d = ((mx - v["x0"]) * (-dy / L) + (my - v["y0"]) * (dx / L)) * v["stran_kraka"]
            # tudi v stranskem dosegu črte
            s = ((mx - v["x0"]) * dx + (my - v["y0"]) * dy) / (L * L)
            if d > 0.5 and -0.05 <= s <= 1.05: g += 1
        u["globina"] = g
    ime = doc.Label.replace(" - parametrično", "").strip()
    stl = os.path.join(IZHOD, "stl", "%s.stl" % doc.Label.replace("/", "-"))
    shp.exportStl(stl)
    return dict(dokument=doc.Label, kos=kos.Label, ime=ime, material=getattr(obj, "Material", ""), T=round(t, 2), K=obj.KFaktor,
                KTabela=getattr(obj, "KTabela", ""), koren=koren_ime, okvir=[round(min(xs), 1), round(min(ys), 1), round(max(xs), 1), round(max(ys), 1)],
                zanke=zanke, upogibi=up, stl=stl, prostornina=round(shp.Volume), okvir3d=[round(shp.BoundBox.XLength, 1), round(shp.BoundBox.YLength, 1), round(shp.BoundBox.ZLength, 1)])


rez = []
vse = sorted(glob.glob(os.path.join(MAPA, "*.FCStd")))
# kos z »- parametrično« različico je na novo narisan: vzemi parametrično, izvirnega preskoči
param = {os.path.basename(f)[:-len(" - parametrično.FCStd")] for f in vse if f.endswith(" - parametrično.FCStd")}
for f in vse:
    if os.path.basename(f)[:-6] in param:
        continue
    try:
        doc = App.openDocument(f, hidden=True)
    except Exception as e:  # noqa: BLE001
        print("NAPAKA odpiranje", f, e); continue
    razg = [o for o in doc.Objects if getattr(o, "Proxy", None).__class__.__name__ == "Razgrnitev" and o.Kos is not None]
    for o in razg:
        try:
            r = obdelaj(doc, o); rez.append(r)
            print("OK", r["ime"], "| T", r["T"], "| upogibov", len(r["upogibi"]), "|", [(u["kot"], u["smer"], u["globina"]) for u in r["upogibi"]])
        except Exception as e:  # noqa: BLE001
            print("NAPAKA", doc.Label, o.Label, e); rez.append(dict(dokument=doc.Label, kos=o.Label, napaka=str(e)))
    if not razg:
        print("brez razgrnitve:", doc.Label)
    App.closeDocument(doc.Name)
json.dump(rez, open(os.path.join(IZHOD, "upogibi.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("konec:", len(rez), "->", IZHOD)
