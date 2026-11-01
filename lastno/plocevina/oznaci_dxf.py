# -*- coding: utf-8 -*-
"""Laserska oznaka kosov v DXF razgrnitev (sloj GRAVURA).

Vsak kos iz pločevine dobi vgravirano kodo (in ime, če je prostor), da krivilec ve, kateri kos sodi h kateri
dokumentaciji. Oznaka je v sloju GRAVURA kot polilinije (potezna pisava), obris v sloju REZ ostane nedotaknjen.
Mesto: najgloblja točka razgrnitve (najdlje od robov in lukenj) — praviloma na osnovni ploskvi, ne na upogibu.

Uporaba (sistemski Python z ezdxf + shapely, ne pixi):
    python oznaci_dxf.py "<mapa z DXF po materialih>" [--izhod "<mapa>"] [--predpona SA] [--seznam "<Seznam kosov za razrez.csv>"]
Mapa: podmape = material ("Al 5754 2 mm", "Jeklo 3 mm" …), datoteke "<kos> xN.dxf". Izhod: ista zgradba v --izhod
(privzeto "<mapa> oznaceni") + "Oznake kosov.csv" (koda, kos, material, besedilo, velikost, lega).
Odločitev 2026-10-30 (Photobox Slim A).
"""
import argparse, csv, glob, math, os, re, sys, unicodedata

import ezdxf
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

SLOJ = "GRAVURA"
# Potezna (enočrtna) pisava Hershey Sans iz Inkscapea (SIL OFL): vsaka črka je nekaj črt, laser jo vgravira v enem prehodu.
PISAVA = r"C:\Program Files\Inkscape\share\inkscape\extensions\svg_fonts\HersheySans1.svg"
VISINA_VELIKIH = 662.0                           # višina velikih črk v enotah pisave (črka A sega od 0 do 662)
RAZMIK_CRK = 0.05                                # dodatni razmik med črkami (delež višine)
VELIKOSTI = (6.0, 5.0, 4.0, 3.0)                # višina črk v mm, po vrsti poskusov
ROB = 3.0                                        # najmanjša razdalja oznake do reza
TOL = 0.02


# ---------- branje DXF: obris in luknje ----------
def _segmenti(msp):
    seg, krogi = [], []
    for e in msp:
        t = e.dxftype()
        if t == "LINE":
            a, b = e.dxf.start, e.dxf.end
            seg.append(((a.x, a.y), (b.x, b.y), None))
        elif t == "ARC":
            c, r = e.dxf.center, e.dxf.radius
            a0, a1 = math.radians(e.dxf.start_angle), math.radians(e.dxf.end_angle)
            while a1 <= a0:
                a1 += 2 * math.pi
            seg.append(((c.x + r * math.cos(a0), c.y + r * math.sin(a0)), (c.x + r * math.cos(a1), c.y + r * math.sin(a1)), (r, (c.x, c.y), a0, a1)))
        elif t == "CIRCLE":
            krogi.append(((e.dxf.center.x, e.dxf.center.y), e.dxf.radius))
        elif t in ("LWPOLYLINE", "POLYLINE"):
            pts = [(p[0], p[1]) for p in e.get_points("xy")] if t == "LWPOLYLINE" else [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
            for i in range(len(pts) - 1):
                seg.append((pts[i], pts[i + 1], None))
            if e.closed or e.is_closed if hasattr(e, "is_closed") else e.closed:
                seg.append((pts[-1], pts[0], None))
    return seg, krogi


def _zanke(seg):
    ostali = list(seg); zan = []
    while ostali:
        s = ostali.pop(); pot = [(s, False)]; zac, kon = s[0], s[1]
        while math.dist(zac, kon) > TOL:
            for i, o in enumerate(ostali):
                if math.dist(o[0], kon) <= TOL:
                    pot.append((o, False)); kon = o[1]; ostali.pop(i); break
                if math.dist(o[1], kon) <= TOL:
                    pot.append((o, True)); kon = o[0]; ostali.pop(i); break
            else:
                break
        zan.append(pot)
    return zan


def _tocke(pot):
    pts = []
    for s, obr in pot:
        p0, p1, info = s
        if info is None:
            pts.append(p1 if obr else p0)
        else:
            r, c, a0, a1 = info
            n = max(2, int((a1 - a0) / 0.1))
            koti = [a0 + (a1 - a0) * k / n for k in range(n + 1)]
            if obr:
                koti.reverse()
            pts += [(c[0] + r * math.cos(a), c[1] + r * math.sin(a)) for a in koti[:-1]]
    return pts


def razgrnitev(doc):
    """Shapely Polygon razgrnitve (obris z luknjami) iz modelnega prostora."""
    seg, krogi = _segmenti(doc.modelspace())
    zanke = [_tocke(z) for z in _zanke(seg)]
    zanke = [z for z in zanke if len(z) >= 3]
    for (cx, cy), r in krogi:
        n = max(12, int(2 * math.pi * r / 1.0))
        zanke.append([(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)])
    poly = [Polygon(z).buffer(0) for z in zanke]
    poly.sort(key=lambda p: -p.area)
    if not poly:
        return None
    return Polygon(poly[0].exterior.coords, [p.exterior.coords for p in poly[1:] if poly[0].contains(p.representative_point())])


# ---------- besedilo (potezna pisava) ----------
_GLIFI = None


def _pisava():
    """Glifi iz SVG pisave: znak -> (širina, [polilinije v enotah pisave])."""
    global _GLIFI
    if _GLIFI is None:
        _GLIFI = {}
        vsebina = open(PISAVA, encoding="utf-8").read()
        for m in re.finditer(r'<glyph([^>]*)/?>', vsebina):
            atr = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
            if "unicode" not in atr:
                continue
            ch = atr["unicode"]
            if ch.startswith("&#"):
                ch = chr(int(ch[3:-1], 16)) if ch[2] in "xX" else chr(int(ch[2:-1]))
            adv = float(atr.get("horiz-adv-x", 378))
            crte, tren = [], []
            for uk, x, y in re.findall(r"([ML])\s*([-\d.]+)[\s,]+([-\d.]+)", atr.get("d", "")):
                if uk == "M":
                    if len(tren) > 1:
                        crte.append(tren)
                    tren = [(float(x), float(y))]
                else:
                    tren.append((float(x), float(y)))
            if len(tren) > 1:
                crte.append(tren)
            _GLIFI[ch] = (adv, crte)
    return _GLIFI


def ascii_velike(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().upper()


def poti_besedila(besedilo, velikost):
    """Polilinije (mm) za besedilo z višino velikih črk = velikost."""
    g = _pisava(); k = velikost / VISINA_VELIKIH; x = 0.0; poti = []
    for ch in besedilo:
        adv, crte = g.get(ch, g.get("?", (378.0, [])))
        for c in crte:
            poti.append([(x + px * k, py * k) for px, py in c])
        x += adv * k + RAZMIK_CRK * velikost
    return poti


def okvir_poti(poti):
    xs = [p[0] for c in poti for p in c]; ys = [p[1] for c in poti for p in c]
    return min(xs), min(ys), max(xs), max(ys)


# ---------- lega ----------
def najdi_lego(poly, sirina, visina):
    """Vrne (x, y, kot) središča oznake: najgloblja točka razgrnitve, kjer okvir oznake še leži znotraj roba."""
    dovoljeno = poly.buffer(-ROB)
    if dovoljeno.is_empty:
        return None
    for d in (80, 60, 45, 35, 25, 18, 12, 8, 5, 3, 0):
        jedro = poly.buffer(-(ROB + d))
        if jedro.is_empty:
            continue
        deli = list(jedro.geoms) if hasattr(jedro, "geoms") else [jedro]
        deli.sort(key=lambda g: -g.area)
        for g in deli[:4]:
            c = g.representative_point()
            for kot in (0, 90):
                w, h = (sirina, visina) if kot == 0 else (visina, sirina)
                for dx, dy in ((0, 0), (w / 4, 0), (-w / 4, 0), (0, h), (0, -h)):
                    b = box(c.x + dx - w / 2, c.y + dy - h / 2, c.x + dx + w / 2, c.y + dy + h / 2)
                    if dovoljeno.contains(b):
                        return (c.x + dx, c.y + dy, kot)
    return None


def oznaci(pot_dxf, besedila, izhod):
    """Doda oznako v kopijo DXF. besedila: seznam poskusov (daljše prej). Vrne (besedilo, velikost, x, y, kot) ali None."""
    doc = ezdxf.readfile(pot_dxf)
    poly = razgrnitev(doc)
    if poly is None or poly.is_empty:
        return None
    izbira = None
    for velikost in VELIKOSTI:
        for b in besedila:
            poti = poti_besedila(b, velikost)
            x0, y0, x1, y1 = okvir_poti(poti)
            lega = najdi_lego(poly, x1 - x0 + 2, y1 - y0 + 2)
            if lega:
                izbira = (b, velikost, poti, (x0, y0, x1, y1), lega); break
        if izbira:
            break
    if not izbira:
        return None
    b, velikost, poti, (x0, y0, x1, y1), (cx, cy, kot) = izbira
    if SLOJ not in doc.layers:
        doc.layers.add(SLOJ, color=1)
    msp = doc.modelspace()
    sx, sy = (x0 + x1) / 2, (y0 + y1) / 2
    ca, sa = math.cos(math.radians(kot)), math.sin(math.radians(kot))
    for c in poti:
        tocke = [(cx + (x - sx) * ca - (y - sy) * sa, cy + (x - sx) * sa + (y - sy) * ca) for x, y in c]
        msp.add_polyline2d(tocke, dxfattribs={"layer": SLOJ})   # odprta POLYLINE (potezna črka), dela tudi v DXF R12
    os.makedirs(os.path.dirname(izhod), exist_ok=True)
    doc.saveas(izhod)
    return (b, velikost, round(cx, 1), round(cy, 1), kot)


def kratki_material(ime_mape):
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*mm", ime_mape)
    deb = m.group(1).replace(",", ".") if m else "?"
    deb = deb[:-2] if deb.endswith(".0") else deb
    if ime_mape.lower().startswith("al"):
        return f"AL{deb}"
    if "inox" in ime_mape.lower() or "nerj" in ime_mape.lower():
        return f"INOX{deb}"
    return f"FE{deb}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mapa")
    ap.add_argument("--izhod")
    ap.add_argument("--predpona", default="SA")
    ap.add_argument("--seznam", help="CSV s stolpcem Kos (vrstni red kod); sicer abecedno")
    a = ap.parse_args()
    izhod = a.izhod or (a.mapa.rstrip("\\/") + " oznaceni")
    datoteke = sorted(glob.glob(os.path.join(a.mapa, "*", "*.dxf")))
    vrstni_red = []
    if a.seznam and os.path.exists(a.seznam):
        with open(a.seznam, encoding="utf-8-sig") as f:
            vrstni_red = [r["Kos"] for r in csv.DictReader(f, delimiter=";")]
    def kljuc(f):
        ime = re.sub(r" x\d+$", "", os.path.basename(f)[:-4])
        return (vrstni_red.index(ime) if ime in vrstni_red else len(vrstni_red), ime)
    datoteke.sort(key=kljuc)
    vrstice = []
    for i, f in enumerate(datoteke, 1):
        mapa = os.path.basename(os.path.dirname(f)); ime = re.sub(r" x\d+$", "", os.path.basename(f)[:-4])
        koda = f"{a.predpona}-{i:02d}"; mat = kratki_material(mapa)
        besedila = [f"{koda} {ascii_velike(ime)} {mat}", f"{koda} {ascii_velike(ime)[:18]}", f"{koda} {mat}", koda]
        cilj = os.path.join(izhod, mapa, os.path.basename(f))
        r = oznaci(f, besedila, cilj)
        if r is None:
            # premajhen kos: kopija brez oznake
            os.makedirs(os.path.dirname(cilj), exist_ok=True)
            ezdxf.readfile(f).saveas(cilj)
            vrstice.append([koda, ime, mapa, "", "", "", "", "BREZ OZNAKE (premajhen kos)"])
            print(f"  ! {koda} {ime}: ni prostora za oznako")
        else:
            b, vel, x, y, kot = r
            vrstice.append([koda, ime, mapa, b, vel, x, y, f"{kot}°"])
            print(f"  {koda} {ime}: \"{b}\" {vel} mm @ ({x}, {y}) {kot}°")
    with open(os.path.join(izhod, "Oznake kosov.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Koda", "Kos", "Material (mapa)", "Besedilo oznake", "Višina mm", "X mm", "Y mm", "Opomba"])
        w.writerows(vrstice)
    print(f"\n{len(vrstice)} kosov -> {izhod}  (sloj {SLOJ}, Oznake kosov.csv)")


if __name__ == "__main__":
    main()
