# -*- coding: utf-8 -*-
"""Stenski zalogovnik za role folije (vinila), iz pločevine. Ena vrsta rol na polico.

Zagon (brez okna):  FreeCADCmd.exe lastno/modeli/police_folija.py
Izhod v mapi police-folija/ ob skripti: FCStd, STEP, DXF razvitih oblik, kosovnica.

Širina: najširše samolepilne folije pri IGEPA (PAKO Signparts, si.pakosignparts.com, pregled
2026-10-07) so 1620 mm (Guandong Ferro Film), običajne do 1600 mm; širši so le bannerji,
cerade in tekstil (2500/3200 mm), ki niso folije.

Sestav: 2 stranici, privijačeni v steno prek skrite zadnje prirobnice (tal se ne dotikajo),
5 polic z enim mehkim koritom in zavihanima robovoma, 10 skritih kotnikov pod policami.
Vse kovičeno s slepimi kovicami Ø4 (luknje Ø4,1): nosilec na stranico z glavo na zunanji strani
stranice, polica na nosilec z glavo v koritu. V steno gredo le sidra. Koordinate: z = 0 so tla,
y = D je stena.

Vsi kosi so upognjeni profili s stalnim prerezom: prerez je srednjica pločevine
(lomljena črta), vsak upogib ima svoj notranji polmer, razvita dolžina se računa s K-faktorjem.
"""
import math
import os

import FreeCAD as App
import Part
from FreeCAD import Vector as V

# ---------------------------------------------------------------- parametri (mm)
T_STRANICA = 3.0   # stranici (čista plošča, debelejša za tog prost sprednji rob)
T_OKVIR = 2.0      # nosilci (jeklo DC01)
T_POLICA = 1.5     # police
R = 2.0            # privzeti notranji polmer upogiba
K = 0.42           # K-faktor za razvito dolžino
W = 1700.0         # notranja širina med stranicama (najširša folija 1620 mm)
D = 260.0          # globina od stene (ena vrsta rol do Ø200)
H = 1600.0         # višina stranice
OD_TAL = 300.0     # spodnji rob stranic nad tlemi
STENA = 40.0       # zadnja prirobnica stranice (na steno, navznoter, skrita)
R_VOGAL = 80.0     # zaobljena sprednja vogala stranice
ODMIK = 6.0        # polica je od sprednjega roba stranice in od stene odmaknjena za toliko
# spodnja ploskev police nad spodnjim robom stranic; razmik 315 = rola Ø200 + dvig čez
# sprednji rob (60) + nosilec (40) + reža
POLICE = [50.0, 365.0, 680.0, 995.0, 1310.0]
SIDRA_Z = [20.0, 565.0, 1195.0, 1520.0]        # sidra v steno (na stranico), mimo zadnjih robov polic
DNO = 50.0         # ravno dno korita (vijak v nosilec)
GLOBINA = 50.0     # globina korita pod sprednjim robom
ROB_SPREDAJ = 10.0  # nizek sprednji rob nad koritom (rola gre čezenj brez dviga)
ROB_ZADAJ = 50.0   # zadnji rob nad koritom
ZAVIHEK = 14.0     # zavihek sprednjega in zadnjega roba nazaj
R_KORITO = 40.0    # polmer prehoda v dno korita (mehka oblika)
R_ROB = 10.0       # polmer prehoda rob-korito
ZRACNOST = 4.0     # reža med polico in stranico
NOSILEC = 40.0     # kraka kotnega nosilca
NET = 4.1          # luknja za slepo kovico Ø4
KOVICA_D = 4.0     # premer telesa kovice
KOVICA_GLAVA = (8.0, 1.2)   # premer in višina okrogle glave
KOVICA_ZAKLJUCEK = (5.6, 2.5)  # razširjeni slepi konec po kovičenju (premer, dolžina)
SIDRO = 10.5       # luknja za sidro v steno (M8 / Ø10)
GOSTOTA = 7.85e-6  # kg/mm3

IZHOD = os.environ.get("POLICE_IZHOD") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "police-folija")


# ---------------------------------------------------------------- upognjen profil
class Profil:
    """Pločevinast kos s stalnim prerezom.

    tocke: srednjica prereza (u, v); dolzina: vzdolž osi w = u x v.
    polmeri: notranji polmer v vsakem notranjem oglišču (privzeto R).
    luknje: (segment, s, w, premer); s je razdalja od začetne točke segmenta po srednjici.
    os_u, os_v, izhodisce: kam v prostoru gre ravnina prereza.
    """

    def __init__(self, ime, tocke, dolzina, os_u, os_v, izhodisce, t,
                 luknje=(), polmeri=None, zaobli=0.0):
        self.ime = ime
        self.zaobli = zaobli   # polmer obeh vogalov na začetnem robu (prvi segment, w = 0 in w = dolzina)
        self.t = t
        self.p = [V(u, v, 0) for u, v in tocke]
        self.dolzina = dolzina
        self.os_u, self.os_v = os_u, os_v
        self.izhodisce = izhodisce
        self.luknje = list(luknje)
        n = len(self.p)
        self.r = [0.0] + list(polmeri or [R] * (n - 2)) + [0.0]
        self.smer = [(self.p[i + 1] - self.p[i]).normalize() for i in range(n - 1)]
        self.dol = [(self.p[i + 1] - self.p[i]).Length for i in range(n - 1)]
        self.kot = [0.0] * n   # predznačen kot zasuka v oglišču (levo +)
        self.tan = [0.0] * n   # razdalja od oglišča do začetka loka
        for i in range(1, n - 1):
            a, b = self.smer[i - 1], self.smer[i]
            self.kot[i] = math.atan2(a.x * b.y - a.y * b.x, a.x * b.x + a.y * b.y)
            self.tan[i] = self._rm(i) * math.tan(abs(self.kot[i]) / 2)
        for i in range(n - 1):
            if self.dol[i] < self.tan[i] + self.tan[i + 1] + 0.1:
                raise ValueError("%s: segment %d je prekratek za upogib" % (self.ime, i))

    def _rm(self, i):
        return self.r[i] + self.t / 2   # polmer srednjice upogiba

    @staticmethod
    def _levo(d):
        return V(-d.y, d.x, 0)

    def _odmik(self, h):
        """Robovi stranice, ki je za h odmaknjena levo od srednjice."""
        robovi, n = [], len(self.p)
        for i in range(n - 1):
            d, nl = self.smer[i], self._levo(self.smer[i])
            a = self.p[i] + d * self.tan[i] + nl * h
            b = self.p[i + 1] - d * self.tan[i + 1] + nl * h
            robovi.append(Part.LineSegment(a, b).toShape())
            if i + 1 < n - 1:
                j = i + 1
                rm = self._rm(j)
                sgn = 1.0 if self.kot[j] > 0 else -1.0
                zac = self.p[j] - d * self.tan[j]
                konec = self.p[j] + self.smer[j] * self.tan[j]
                c = zac + nl * rm * sgn
                sred = c + (self.p[j] - c).normalize() * (rm - sgn * h)
                robovi.append(Part.Arc(zac + nl * h, sred,
                                       konec + self._levo(self.smer[j]) * h).toShape())
        return robovi

    def oblika(self):
        h = self.t / 2
        levo, desno = self._odmik(h), self._odmik(-h)
        n0, n1 = self._levo(self.smer[0]), self._levo(self.smer[-1])
        robovi = levo + desno + [
            Part.LineSegment(self.p[0] + n0 * h, self.p[0] - n0 * h).toShape(),
            Part.LineSegment(self.p[-1] + n1 * h, self.p[-1] - n1 * h).toShape(),
        ]
        zica = Part.Wire(Part.__sortEdges__(robovi))
        telo = Part.Face(zica).extrude(V(0, 0, self.dolzina))
        for seg, s, w, premer in self.luknje:
            d, nl = self.smer[seg], self._levo(self.smer[seg])
            tocka = self.p[seg] + d * s + V(0, 0, w) - nl * (2 * self.t)
            telo = telo.cut(Part.makeCylinder(premer / 2, 4 * self.t, tocka, nl))
        if self.zaobli:
            rv, d, nl = self.zaobli, self.smer[0], self._levo(self.smer[0])
            for w0, e2 in ((0.0, V(0, 0, 1)), (self.dolzina, V(0, 0, -1))):
                a = self.p[0] + V(0, 0, w0) - nl * (2 * self.t)
                kot = Part.Face(Part.makePolygon([a - d - e2, a + d * rv - e2, a + d * rv + e2 * rv,
                                                  a - d + e2 * rv, a - d - e2]))
                krog = Part.Face(Part.Wire(Part.makeCircle(rv, a + d * rv + e2 * rv, nl)))
                telo = telo.cut(kot.cut(krog).extrude(nl * (4 * self.t)))
        os_w = self.os_u.cross(self.os_v)
        u, v, w, o = self.os_u, self.os_v, os_w, self.izhodisce
        m = App.Matrix(u.x, v.x, w.x, o.x,
                       u.y, v.y, w.y, o.y,
                       u.z, v.z, w.z, o.z,
                       0, 0, 0, 1)
        telo.Placement = App.Placement(m)
        return telo

    # ------------------------------------------------------------ razvita oblika
    def razvoj(self):
        """Vrne (dolžina razvoja, upogibi [(u, kot, polmer)], luknje [(u, w, premer)])."""
        u, zac_seg, upogibi = 0.0, [], []
        for i in range(len(self.dol)):
            zac_seg.append(u)
            u += self.dol[i] - self.tan[i] - self.tan[i + 1]
            j = i + 1
            if j < len(self.p) - 1:
                ba = abs(self.kot[j]) * (self.r[j] + K * self.t)
                upogibi.append((u + ba / 2, math.degrees(self.kot[j]), self.r[j]))
                u += ba
        luknje = [(zac_seg[seg] + s - self.tan[seg], w, premer)
                  for seg, s, w, premer in self.luknje]
        return u, upogibi, luknje


# ---------------------------------------------------------------- DXF (R12, brez knjižnic)
def zapisi_dxf(pot, profil):
    dolg, upogibi, luknje = profil.razvoj()
    L = profil.dolzina
    e = []

    def crta(sloj, x1, y1, x2, y2):
        e.append("0\nLINE\n8\n%s\n10\n%.3f\n20\n%.3f\n30\n0\n11\n%.3f\n21\n%.3f\n31\n0"
                 % (sloj, x1, y1, x2, y2))

    rv = profil.zaobli
    for a, b in [((rv, 0), (dolg, 0)), ((dolg, 0), (dolg, L)), ((dolg, L), (rv, L)), ((0, L - rv), (0, rv))]:
        crta("OBRIS", a[0], a[1], b[0], b[1])
    if rv:
        for cy, k1, k2 in ((rv, 180, 270), (L - rv, 90, 180)):
            e.append("0\nARC\n8\nOBRIS\n10\n%.3f\n20\n%.3f\n30\n0\n40\n%.3f\n50\n%g\n51\n%g"
                     % (rv, cy, rv, k1, k2))
    for u, kot, r in upogibi:
        crta("UPOGIB", u, 0, u, L)
        e.append("0\nTEXT\n8\nOPIS\n10\n%.3f\n20\n%.3f\n30\n0\n40\n8\n1\n%s %.1f R%g\n50\n90"
                 % (u - 3, 10, "GOR" if kot > 0 else "DOL", abs(kot), r))
    for u, w, premer in luknje:
        e.append("0\nCIRCLE\n8\nOBRIS\n10\n%.3f\n20\n%.3f\n30\n0\n40\n%.3f" % (u, w, premer / 2))
    with open(pot, "w", encoding="ascii") as f:
        f.write("0\nSECTION\n2\nENTITIES\n" + "\n".join(e) + "\n0\nENDSEC\n0\nEOF\n")
    return dolg


# ---------------------------------------------------------------- kosi
X, Y, Z = V(1, 0, 0), V(0, 1, 0), V(0, 0, 1)
SREDINA = D / 2                       # sredina korita (globina)
NOS_Y = (SREDINA - 60.0, SREDINA + 60.0)  # kovici nosilec-stranica


def stranica():
    # tloris (ravnina XY), dolžina po višini: čista plošča z zaobljenima sprednjima vogaloma,
    # zadnja prirobnica na steno je obrnjena navznoter (od spredaj in s strani se ne vidi)
    t = T_STRANICA
    luknje = [(0, y, zs - NOSILEC / 2, NET) for zs in POLICE for y in NOS_Y]
    luknje += [(1, STENA / 2 + t / 2, z, SIDRO) for z in SIDRA_Z]
    tocke = [(-t / 2, 0), (-t / 2, D - t / 2), (STENA, D - t / 2)]
    return Profil("Stranica", tocke, H, X, Y, V(0, 0, 0), t, luknje, [R], zaobli=R_VOGAL)


def nosilec(zs):
    # skrit kotnik pod polico: navpični krak navzdol ob stranici, vodoravni nosi dno korita
    t = T_OKVIR
    y0, dolg = SREDINA + 90.0, 180.0
    luknje = [(0, NOSILEC / 2, y0 - y, NET) for y in NOS_Y]
    luknje.append((1, NOSILEC / 2 - t / 2, y0 - SREDINA, NET))
    tocke = [(t / 2, zs - NOSILEC), (t / 2, zs - t / 2), (NOSILEC, zs - t / 2)]
    return Profil("Nosilec", tocke, dolg, X, Z, V(0, y0, 0), t, luknje)


def polica():
    t = T_POLICA
    a = SREDINA - DNO / 2
    y1, y2 = ODMIK, D - ODMIK
    vrh_s, vrh_z = GLOBINA + ROB_SPREDAJ, GLOBINA + ROB_ZADAJ
    tocke = [(y1 + ZAVIHEK, vrh_s), (y1, vrh_s), (y1, GLOBINA), (a, 0), (a + DNO, 0),
             (y2, GLOBINA), (y2, vrh_z), (y2 - ZAVIHEK, vrh_z)]
    polmeri = [R, R_ROB, R_KORITO, R_KORITO, R_ROB, R]
    dolg = W - 2 * ZRACNOST
    w1 = NOSILEC / 2 - ZRACNOST
    luknje = [(3, DNO / 2, w, NET) for w in (w1, dolg - w1)]
    return Profil("Polica", tocke, dolg, Y, Z, V(ZRACNOST, 0, 0), t, luknje, polmeri)


def kovica(p, n, oprijem):
    """Slepa kovica po kovičenju: okrogla glava na točki p (n kaže od pločevine proti glavi),
    telo skozi oprijem in razširjen slepi konec na drugi strani."""
    n = V(n).normalize()
    dg, hg = KOVICA_GLAVA
    rk = ((dg / 2) ** 2 + hg ** 2) / (2 * hg)          # polmer krogle, ki da kapico dg x hg
    glava = Part.makeSphere(rk, p - n * (rk - hg)).common(Part.makeCylinder(dg / 2, hg, p, n))
    telo = Part.makeCylinder(KOVICA_D / 2, oprijem, p, -n)
    dz, lz = KOVICA_ZAKLJUCEK
    konec = Part.makeCylinder(dz / 2, lz, p - n * oprijem, -n)
    return glava.fuse([telo, konec]).removeSplitter()


def kovice():
    """Vse kovice sestava: [(oznaka, oprijem, oblika)]; z = 0 je spodnji rob stranic."""
    rez = []
    op_s = T_STRANICA + T_OKVIR          # stranica + navpični krak nosilca
    op_p = T_POLICA + T_OKVIR            # dno police + vodoravni krak nosilca
    for zs in POLICE:
        for stran in (0, 1):
            zrcali = (lambda v: V(W - v.x, v.y, v.z)) if stran else (lambda v: v)
            smer = V(1, 0, 0) if stran else V(-1, 0, 0)
            for y in NOS_Y:   # glava na zunanji strani stranice
                rez.append(("Kovica_stranica", op_s,
                            kovica(zrcali(V(-T_STRANICA, y, zs - NOSILEC / 2)), smer, op_s)))
            # glava v koritu police, slepi konec pod nosilcem
            rez.append(("Kovica_polica", op_p,
                        kovica(zrcali(V(NOSILEC / 2, SREDINA, zs + T_POLICA)), V(0, 0, 1), op_p)))
    return rez


# ---------------------------------------------------------------- sestav
def zgradi():
    os.makedirs(IZHOD, exist_ok=True)
    doc = App.newDocument("PoliceFolija")
    kosi = []  # (ime objekta, profil, oblika)

    s = stranica()
    o = s.oblika()
    kosi.append(("Stranica_L", s, o))
    kosi.append(("Stranica_D", s, o.mirror(V(W / 2, 0, 0), X)))
    for i, zs in enumerate(POLICE, 1):
        n = nosilec(zs)
        o = n.oblika()
        kosi.append(("Nosilec_%d_L" % i, n, o))
        kosi.append(("Nosilec_%d_D" % i, n, o.mirror(V(W / 2, 0, 0), X)))
        p = polica()
        o = p.oblika()
        o.translate(V(0, 0, zs - o.BoundBox.ZMin))
        kosi.append(("Polica_%d" % i, p, o))

    objekti = []
    for ime, _, oblika in kosi:
        oblika.translate(V(0, 0, OD_TAL))   # z = 0 so tla
        obj = doc.addObject("Part::Feature", ime)
        obj.Shape = oblika
        objekti.append(obj)
    net = kovice()
    for _, _, oblika in net:
        oblika.translate(V(0, 0, OD_TAL))
    obj = doc.addObject("Part::Feature", "Kovice")
    obj.Label = "Kovice Ø4 (%d)" % len(net)
    obj.Shape = Part.makeCompound([k[2] for k in net])
    objekti.append(obj)
    doc.recompute()

    # trki med kosi (dotik je dovoljen, prekrivanje ne)
    trki = []
    for i in range(len(kosi)):
        for j in range(i + 1, len(kosi)):
            a, b = kosi[i][2], kosi[j][2]
            if not a.BoundBox.intersect(b.BoundBox):
                continue
            vol = a.common(b).Volume
            if vol > 1.0:
                trki.append("%s x %s: %.0f mm3" % (kosi[i][0], kosi[j][0], vol))
    # kovica mora iti skozi luknje brez prekrivanja s pločevino
    for oznaka, _, oblika in net:
        for ime, _, kos in kosi:
            if oblika.BoundBox.intersect(kos.BoundBox):
                vol = oblika.common(kos).Volume
                if vol > 0.5:
                    trki.append("%s x %s: %.1f mm3" % (oznaka, ime, vol))

    # razvite oblike in kosovnica (enaki kosi samo enkrat)
    videni = {}
    for ime, prof, oblika in kosi:
        oznaka = prof.ime
        if oznaka in videni:
            videni[oznaka][1] += 1
            continue
        dolg = zapisi_dxf(os.path.join(IZHOD, "razvoj-%s.dxf" % oznaka.lower()), prof)
        videni[oznaka] = [oznaka, 1, prof.t, dolg, prof.dolzina, len(prof.razvoj()[1]),
                          len(prof.luknje), oblika.Volume * GOSTOTA]
    skupaj = 0.0
    with open(os.path.join(IZHOD, "kosovnica.csv"), "w", encoding="utf-8") as f:
        f.write("kos;kolicina;debelina_mm;razvoj_mm;dolzina_mm;upogibi;luknje;masa_kos_kg\n")
        for oznaka, kol, t, dolg, L, upog, luk, masa in videni.values():
            f.write("%s;%d;%.1f;%.1f;%.1f;%d;%d;%.2f\n" % (oznaka, kol, t, dolg, L, upog, luk, masa))
            skupaj += kol * masa
        for oznaka in ("Kovica_stranica", "Kovica_polica"):
            izbor = [k for k in net if k[0] == oznaka]
            f.write("%s (slepa Ø%g, luknja Ø%g, oprijem %.1f mm);%d;;;;;;\n"
                    % (oznaka, KOVICA_D, NET, izbor[0][1], len(izbor)))

    doc.saveAs(os.path.join(IZHOD, "police-folija.FCStd"))
    import Import
    Import.export(objekti, os.path.join(IZHOD, "police-folija.step"))

    bb = Part.makeCompound([k[2] for k in kosi]).BoundBox
    print("KOSOV: %d" % len(kosi))
    print("MERE: %.0f x %.0f x %.0f mm" % (bb.XLength, bb.YLength, bb.ZLength))
    print("MASA: %.1f kg" % skupaj)
    print("KOVIC: %d" % len(net))
    print("TRKI: " + ("; ".join(trki) if trki else "ni"))
    for v in videni.values():
        print("  %s x%d  t%.1f  razvoj %.1f x %.1f mm, %d upogibov, %.2f kg" %
              (v[0], v[1], v[2], v[3], v[4], v[5], v[7]))
    return doc


zgradi()
