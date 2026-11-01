# -*- coding: utf-8 -*-
"""Ploščice (PBR teksture ambientCG) za videz in render: iskanje materialov, opis merila, preslikava UV v mm.

Material je mapa s slikami ambientCG (`*_Color.jpg`, `*_NormalGL.jpg`, `*_Roughness.jpg`, `*_Displacement.jpg`,
po želji `*_AmbientOcclusion.jpg`) in opisom `ploscica.json`. Mape so v knjižnici standardnih delov pod `_Ploscice`
(npr. `Standardni deli/Kopalnica/_Ploscice/Tiles036 - Bele ploscice kvadratne`); knjižnica mape s podčrtajem ne kaže.

ploscica.json (ambientCG fizične velikosti ne navaja, zato jo zapišemo sami):
    ploscic      [nx, ny]  koliko ploščic je na sliki vodoravno in navpično (pri vezavi in mozaiku nazivna ploščica;
                           pri nepravilnem vzorcu nazivni modul)
    privzeto_mm  [š, v]    privzeta velikost ene ploščice, ko je lastnost na kosu 0
    faza         [fu, fv]  kje na sliki je fuga (delež slike od spodnjega levega kota, kot UV): mreža ploščic se
                           začne s fugo v kotu ploskve
    barva        [r, g, b] povprečna barva (sRGB 0..1): FreeCAD in prikaz brez teksture
    hrapavost    povprečna hrapavost (prikaz brez teksture)
    vzorec, opis, vir      za ljudi
Zapiše ga ukaz `python ploscice.py zapisi <mapa> --ploscic NX NY --privzeto Š V` (faza in barva se izmerita iz slik,
potrebuje numpy in Pillow; sistemski Python). Štetje ploščic preveri na sliki (`--pregled slika.png`).

Kos dobi ploščico z lastnostmi v skupini Videz (videz.nastavi_ploscico):
    Ploscica          ime mape, njen začetek (npr. »Tiles036«) ali polna pot do mape
    PloscicaSirina    širina ene ploščice (mm; 0 = privzeto iz ploscica.json)
    PloscicaVisina    višina ene ploščice (mm; 0 = po razmerju privzete velikosti)
    PloscicaZasuk     zasuk vzorca v ravnini ploskve (°)
    PloscicaPloskve   po ploskvah (seznam vrstic »Face3: Tiles030 150x75 90«, »Face4: -« = brez ploščice); prepiše
                      zgornje za naštete ploskve

Preslikava (uv_ploskve): v ravnini ploskve, os v = navpična os kosa (njegov lokalni Z), os u = desno, gledano od
zunaj (normala proti gledalcu); na vodoravnih ploskvah u = lokalni X kosa. Ukrivljene ploskve dobijo škatlasto
preslikavo (prevladujoča os kosa). Izhodišče mreže je najmanjši u in v vseh ploskev iste smeri (in iste ploščice)
na objektu: ploščice se začnejo v spodnjem levem kotu stene in se nadaljujejo čez sosednje koplanarne ploskve.
1 enota UV = ena slika = ploscic × velikost ploščice v mm.

Brez FreeCAD-a in brez bpy (uporabljajo ga videz.py, streznik.py in ukazna vrstica)."""

import glob
import json
import math
import os
import re
import sys

KOREN = os.environ.get("SPLET_MODELIRANJE") or os.path.join(os.path.expanduser("~"), "Oblak", "3D modeliranje")
BAZA = os.environ.get("SPLET_BAZA") or os.path.join(KOREN, "Standardni deli")
OPIS = "ploscica.json"
SLIKE = {   # vloga -> konec imena datoteke ambientCG
    "barva": ("_Color",),
    "normala": ("_NormalGL", "_Normal"),
    "hrapavost": ("_Roughness",),
    "visina": ("_Displacement", "_Height"),
    "ao": ("_AmbientOcclusion",),
}
KONCNICE = (".jpg", ".jpeg", ".png")

_predpomnilnik = {}   # mapa -> (mtime opisa, opis)
_korenine = None


def korenine():
    """Mape `_Ploscice` v bazi standardnih delov (enkrat poiskane)."""
    global _korenine
    if _korenine is None:
        _korenine = sorted(glob.glob(os.path.join(BAZA, "*", "_Ploscice")) + glob.glob(os.path.join(BAZA, "_Ploscice")))
    return _korenine


def _je_material(mapa):
    return os.path.isdir(mapa) and bool(_slika(mapa, "barva"))


def _slika(mapa, vloga):
    try:
        imena = os.listdir(mapa)
    except OSError:
        return None
    for konec in SLIKE[vloga]:
        for ime in sorted(imena):
            osnova, konc = os.path.splitext(ime)
            if konc.lower() in KONCNICE and osnova.endswith(konec):
                return os.path.join(mapa, ime)
    return None


def najdi(ime):
    """Polna pot do mape materiala ali None. ime: polna pot, ime mape ali njen začetek (»Tiles036«)."""
    ime = (ime or "").strip().strip('"')
    if not ime or ime == "-":
        return None
    if os.path.isabs(ime):
        return os.path.normpath(ime) if _je_material(ime) else None
    for koren in korenine():
        pot = os.path.join(koren, ime)
        if _je_material(pot):
            return os.path.normpath(pot)
    nizko = ime.lower()
    for koren in korenine():
        try:
            mape = sorted(os.listdir(koren))
        except OSError:
            continue
        for m in mape:
            ml = m.lower()
            if ml == nizko or ml.startswith(nizko + " ") or ml.split(" - ")[0] == nizko:
                pot = os.path.join(koren, m)
                if _je_material(pot):
                    return os.path.normpath(pot)
    return None


def opis(mapa):
    """Opis materiala: slike (polne poti po vlogah), ploscic, privzeto_mm, faza, barva, hrapavost, ime, id, mapa."""
    try:
        mtime = os.path.getmtime(os.path.join(mapa, OPIS))
    except OSError:
        mtime = 0
    vnos = _predpomnilnik.get(mapa)
    if vnos is not None and vnos[0] == mtime:
        return vnos[1]
    podatki = {}
    if mtime:
        try:
            with open(os.path.join(mapa, OPIS), encoding="utf-8") as f:
                podatki = json.load(f)
        except (OSError, ValueError):
            podatki = {}
    ime = os.path.basename(mapa)
    o = {
        "mapa": mapa,
        "ime": ime,
        "id": ime.split(" - ")[0],
        "opis": podatki.get("opis") or (ime.split(" - ", 1)[1] if " - " in ime else ime),
        "ploscic": [max(1, int(x)) for x in (podatki.get("ploscic") or [1, 1])[:2]],
        "privzeto_mm": [float(x) for x in (podatki.get("privzeto_mm") or [300.0, 300.0])[:2]],
        "faza": [float(x) for x in (podatki.get("faza") or [0.0, 0.0])[:2]],
        "barva": [float(x) for x in (podatki.get("barva") or [0.8, 0.8, 0.8])[:3]],
        "hrapavost": float(podatki.get("hrapavost", 0.35)),
        "vzorec": podatki.get("vzorec", ""),
        "brez_opisa": not mtime,
        "slike": {v: _slika(mapa, v) for v in SLIKE},
    }
    _predpomnilnik[mapa] = (mtime, o)
    return o


def seznam():
    """Vsi materiali v knjižnici: [{ime, id, opis, mapa, privzeto_mm, barva, kategorija}]."""
    izhod = []
    for koren in korenine():
        kategorija = os.path.basename(os.path.dirname(koren))
        try:
            mape = sorted(os.listdir(koren))
        except OSError:
            continue
        for m in mape:
            pot = os.path.join(koren, m)
            if not _je_material(pot):
                continue
            o = opis(pot)
            izhod.append({"ime": o["ime"], "id": o["id"], "opis": o["opis"], "mapa": pot, "kategorija": kategorija,
                          "privzeto_mm": o["privzeto_mm"], "barva": o["barva"], "ploscic": o["ploscic"],
                          "brez_opisa": o["brez_opisa"]})
    return izhod


def dovoljena_slika(pot):
    """Ali sme spletni strežnik postreči to sliko (le slike materialov ploščic)."""
    try:
        pot = os.path.normpath(os.path.abspath(pot))
    except (TypeError, ValueError):
        return False
    if os.path.splitext(pot)[1].lower() not in KONCNICE or not os.path.isfile(pot):
        return False
    mapa = os.path.dirname(pot)
    if not _je_material(mapa):
        return False
    n = os.path.normcase(mapa)
    if any(n.startswith(os.path.normcase(os.path.normpath(k)) + os.sep) for k in korenine()):
        return True
    return mapa in _uporabljene


_uporabljene = set()   # mape s polno potjo, ki jih je uporabil kak kos (zunaj knjižnice)


# ---------------------------------------------------------------------------
# Nastavitev na kosu: (mapa, širina, višina, zasuk) iz lastnosti

def velikost(o, sirina=0.0, visina=0.0):
    """Velikost ene ploščice (mm) iz lastnosti kosa; 0 = privzeto, višina po razmerju privzete velikosti."""
    ps, pv = o["privzeto_mm"]
    sirina, visina = float(sirina or 0), float(visina or 0)
    if sirina <= 0 and visina <= 0:
        return ps, pv
    if sirina <= 0:
        return visina * ps / pv, visina
    if visina <= 0:
        return sirina, sirina * pv / ps
    return sirina, visina


def nastavitev(ime, sirina=0.0, visina=0.0, zasuk=0.0):
    """Ključ ploščice za videz ploskve: (mapa, š, v, zasuk) ali None, če materiala ni."""
    mapa = najdi(ime)
    if mapa is None:
        return None
    if os.path.isabs((ime or "").strip().strip('"')):
        _uporabljene.add(mapa)
    s, v = velikost(opis(mapa), sirina, visina)
    return (mapa, round(s, 3), round(v, 3), round(float(zasuk or 0) % 360.0, 3))


def odtis(ploscica):
    """Čas spremembe opisov materialov, ki jih ploščica kosa uporablja (za predpomnilnik posnetka)."""
    if not ploscica:
        return None
    privzeta, po = ploscica
    mape = sorted({k[0] for k in [privzeta] + [k for _, k in po] if k})
    izhod = []
    for m in mape:
        try:
            izhod.append(os.path.getmtime(os.path.join(m, OPIS)))
        except OSError:
            izhod.append(0)
    return tuple(izhod)


_VRSTICA = re.compile(r"^\s*((?:Face\d+[\s,;]*)+)\s*:\s*(\S+)"
                      r"(?:\s+(\d+(?:[.,]\d+)?)\s*[x×X*]\s*(\d+(?:[.,]\d+)?)(?:\s*mm)?)?"
                      r"(?:\s+(-?\d+(?:[.,]\d+)?)\s*°?)?\s*$")


def razcleni_ploskve(vrstice):
    """PloscicaPloskve -> {indeks ploskve (0..): ključ ali None (brez ploščice)}. Neveljavne vrstice preskoči."""
    izhod = {}
    for vrstica in vrstice or ():
        m = _VRSTICA.match(str(vrstica))
        if not m:
            continue
        stevilo = lambda x: float(x.replace(",", ".")) if x else 0.0  # noqa: E731
        ime = m.group(2)
        kljuc = None if ime in ("-", "brez", "nic", "nič") else nastavitev(ime, stevilo(m.group(3)), stevilo(m.group(4)),
                                                                          stevilo(m.group(5)))
        for f in re.findall(r"Face(\d+)", m.group(1)):
            izhod[int(f) - 1] = kljuc
    return izhod


def brez_ploskev(vrstice, ploskve):
    """Vrstice PloscicaPloskve brez naštetih ploskev (vrstica, ki ostane brez ploskev, odpade)."""
    izhod, ploskve = [], set(ploskve)
    for vrstica in vrstice or ():
        glava, locilo, rep = str(vrstica).partition(":")
        imena = re.findall(r"Face\d+", glava)
        if not locilo or not imena or not set(imena) & ploskve:
            izhod.append(vrstica)
            continue
        ostale = [f for f in imena if f not in ploskve]
        if ostale:
            izhod.append(" ".join(ostale) + ":" + rep)
    return izhod


def vrstica_ploskev(ploskve, ime, sirina=0.0, visina=0.0, zasuk=0.0):
    """Vrstica za PloscicaPloskve (»Face3 Face4: Tiles030 150x75 90«)."""
    besedilo = " ".join(ploskve) + ": " + (ime or "-")
    if ime and ime != "-" and (sirina or visina):
        besedilo += " %gx%g" % (float(sirina or 0), float(visina or 0))
    if ime and ime != "-" and zasuk:
        besedilo += " %g" % float(zasuk)
    return besedilo


# ---------------------------------------------------------------------------
# UV v merilu realnega sveta (čisti Python; kliče ga glavna nit ob gradnji posnetka)

def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a):
    d = math.sqrt(_dot(a, a))
    return (a[0] / d, a[1] / d, a[2] / d) if d > 1e-12 else (0.0, 0.0, 0.0)


def _baza(n, os_x, os_z):
    """(u, v) v ravnini z normalo n: v = navpičnica kosa, u = v × n (desno, gledano od zunaj); vodoravna ploskev: u = X."""
    if abs(_dot(n, os_z)) < 0.999:
        v = _norm(_sub(os_z, tuple(_dot(os_z, n) * c for c in n)))
        u = _cross(v, n)
    else:
        u = _norm(_sub(os_x, tuple(_dot(os_x, n) * c for c in n)))
        v = _cross(n, u)
    return u, v


def uv_objekta(tocke, trikotniki, ploskve, kljuci, os_x=(1.0, 0.0, 0.0), os_z=(0.0, 0.0, 1.0)):
    """UV vseh točk objekta posnetka (seznam 2 × število točk, 0 pri ploskvah brez ploščice).

    tocke, trikotniki: ploski seznami posnetka; ploskve: [začetek točk, št. točk, začetek trikotnikov, št. trikotnikov,
    ...]; kljuci[i]: ključ ploščice ploskve i (mapa, š, v, zasuk) ali None; os_x, os_z: lokalni X in Z kosa v svetu."""
    n_tock = len(tocke) // 3
    uv = [0.0] * (2 * n_tock)
    P = lambda i: (tocke[3 * i], tocke[3 * i + 1], tocke[3 * i + 2])  # noqa: E731
    os_x, os_z = _norm(os_x), _norm(os_z)
    os_y = _cross(os_z, os_x)
    osi = [os_x, os_y, os_z, tuple(-c for c in os_x), tuple(-c for c in os_y), tuple(-c for c in os_z)]
    skupine = {}    # (ključ, smer) -> [(točka, (u, v))...] za izhodišče
    dodelitve = []  # (točka, ključ, smer, u, v)
    for i, p in enumerate(ploskve):
        kljuc = kljuci[i] if i < len(kljuci) else None
        if not kljuc:
            continue
        t0, nt = int(p[2]), int(p[3])
        v0, nv = int(p[0]), int(p[1])
        normale = {}   # točka -> vsota normal (utežena s ploščino)
        skupna = (0.0, 0.0, 0.0)
        ravna = True
        prva = None
        for t in range(t0, t0 + nt):
            a, b, c = trikotniki[3 * t], trikotniki[3 * t + 1], trikotniki[3 * t + 2]
            nn = _cross(_sub(P(b), P(a)), _sub(P(c), P(a)))
            dol = math.sqrt(_dot(nn, nn))
            if dol < 1e-12:
                continue
            enota = (nn[0] / dol, nn[1] / dol, nn[2] / dol)
            if prva is None:
                prva = enota
            elif _dot(prva, enota) < 0.9998:   # ~1,1°
                ravna = False
            skupna = (skupna[0] + nn[0], skupna[1] + nn[1], skupna[2] + nn[2])
            for k in (a, b, c):
                s = normale.get(k, (0.0, 0.0, 0.0))
                normale[k] = (s[0] + nn[0], s[1] + nn[1], s[2] + nn[2])
        if prva is None:
            continue
        if ravna:
            n = _norm(skupna)
            smer = ("R",) + tuple(round(c, 3) for c in n)
            u, v = _baza(n, os_x, os_z)
            for k in range(v0, v0 + nv):
                dodelitve.append((k, kljuc, smer, u, v))
        else:
            # ukrivljena ploskev: škatlasta preslikava po prevladujoči osi kosa (normala v točki)
            for k in range(v0, v0 + nv):
                nk = _norm(normale.get(k, skupna))
                ai = max(range(6), key=lambda j: _dot(nk, osi[j]))
                u, v = _baza(osi[ai], os_x, os_z)
                dodelitve.append((k, kljuc, ("O", ai), u, v))
    izhodisca = {}
    for k, kljuc, smer, u, v in dodelitve:
        p = P(k)
        du, dv = _dot(p, u), _dot(p, v)
        g = (kljuc, smer)
        m = izhodisca.get(g)
        izhodisca[g] = (du, dv) if m is None else (min(m[0], du), min(m[1], dv))
    opisi = {}
    for k, kljuc, smer, u, v in dodelitve:
        o = opisi.get(kljuc[0]) or opisi.setdefault(kljuc[0], opis(kljuc[0]))
        mapa, s, h, zasuk = kljuc
        W, H = s * o["ploscic"][0], h * o["ploscic"][1]
        u0, v0_ = izhodisca[(kljuc, smer)]
        p = P(k)
        du, dv = _dot(p, u) - u0, _dot(p, v) - v0_
        if zasuk:
            c, sn = math.cos(math.radians(zasuk)), math.sin(math.radians(zasuk))
            du, dv = du * c + dv * sn, -du * sn + dv * c
        uv[2 * k] = round(du / W + o["faza"][0], 5)
        uv[2 * k + 1] = round(dv / H + o["faza"][1], 5)
    return uv


# ---------------------------------------------------------------------------
# Ukazna vrstica: zapis ploscica.json (sistemski Python z numpy in Pillow)

def _izmeri(mapa, nx, ny):
    """Faza fug (delež, od spodnjega levega kota) in povprečna barva ter hrapavost iz slik materiala."""
    import numpy as np
    from PIL import Image
    N = 1024
    o = opis(mapa)
    barva = np.asarray(Image.open(o["slike"]["barva"]).convert("RGB").resize((256, 256)), dtype=np.float64) / 255
    hrap = 0.35
    if o["slike"]["hrapavost"]:
        hrap = float(np.asarray(Image.open(o["slike"]["hrapavost"]).convert("L").resize((256, 256)), dtype=np.float64).mean() / 255)
    vir = o["slike"]["visina"] or o["slike"]["barva"]
    a = np.asarray(Image.open(vir).convert("L").resize((N, N)), dtype=np.float64)[::-1]   # vrstica 0 = spodaj (UV)
    fu = fv = 0.0
    if nx > 1 or ny > 1:
        def zlozi(profil, n):
            """Profil, zložen na eno ploščico (n ploščic na sliki): povprečje po legi znotraj ploščice."""
            perioda = len(profil) / n
            k = ((np.arange(len(profil)) % perioda) / perioda * int(round(perioda))).astype(int)
            k = np.minimum(k, int(round(perioda)) - 1)
            vsota = np.bincount(k, weights=profil, minlength=int(round(perioda)))
            return vsota / np.maximum(np.bincount(k, minlength=int(round(perioda))), 1), perioda / int(round(perioda))
        fy = 0.0
        if ny > 1:
            z, f = zlozi(a.mean(axis=1), ny)
            fy = float(np.argmin(z)) * f
        Py = N / ny
        sredina = int(fy + Py / 2) % N
        pas = a[max(0, sredina - int(Py / 4)): sredina + int(Py / 4) + 1].mean(axis=0)
        fx = 0.0
        if nx > 1:
            z, f = zlozi(pas, nx)
            fx = float(np.argmin(z)) * f
        fu, fv = fx / N, fy / N
    return [round(fu, 4), round(fv, 4)], [round(float(c), 3) for c in barva.reshape(-1, 3).mean(axis=0)], round(hrap, 3)


def zapisi(mapa, ploscic, privzeto, vzorec="", opis_=None, vir=None):
    faza, barva, hrap = _izmeri(mapa, ploscic[0], ploscic[1])
    ime = os.path.basename(mapa)
    podatki = {
        "ploscic": [int(ploscic[0]), int(ploscic[1])],
        "privzeto_mm": [float(privzeto[0]), float(privzeto[1])],
        "faza": faza,
        "barva": barva,
        "hrapavost": hrap,
        "vzorec": vzorec,
        "opis": opis_ or (ime.split(" - ", 1)[1] if " - " in ime else ime),
        "vir": vir or "ambientCG %s (CC0), https://ambientcg.com/view?id=%s" % (ime.split(" - ")[0], ime.split(" - ")[0]),
    }
    with open(os.path.join(mapa, OPIS), "w", encoding="utf-8") as f:
        json.dump(podatki, f, ensure_ascii=False, indent=1)
    _predpomnilnik.pop(mapa, None)
    return podatki


def pregled(mapa, izhod, velikost_px=640):
    """Slika barve z vrisano mrežo ploščic in fazo (preverjanje štetja)."""
    from PIL import Image, ImageDraw
    o = opis(mapa)
    nx, ny = o["ploscic"]
    fu, fv = o["faza"]
    im = Image.open(o["slike"]["barva"]).convert("RGB").resize((velikost_px, velikost_px))
    d = ImageDraw.Draw(im)
    for i in range(nx + 1):
        x = (fu + i / nx) % 1 * velikost_px
        d.line([(x, 0), (x, velikost_px)], fill=(255, 0, 0), width=1)
    for j in range(ny + 1):
        y = velikost_px - (fv + j / ny) % 1 * velikost_px
        d.line([(0, y), (velikost_px, y)], fill=(255, 0, 0), width=1)
    im.save(izhod)


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(description="Opis ploščic (ploscica.json) za render spletnega FreeCAD-a")
    pod = ap.add_subparsers(dest="ukaz", required=True)
    z = pod.add_parser("zapisi", help="zapiši ploscica.json (faza in barva se izmerita)")
    z.add_argument("mapa")
    z.add_argument("--ploscic", nargs=2, type=int, required=True, metavar=("NX", "NY"))
    z.add_argument("--privzeto", nargs=2, type=float, required=True, metavar=("SIRINA", "VISINA"))
    z.add_argument("--vzorec", default="")
    z.add_argument("--opis")
    z.add_argument("--pregled", help="shrani še sliko z vrisano mrežo")
    s = pod.add_parser("seznam", help="materiali v knjižnici")
    s.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.ukaz == "zapisi":
        mapa = najdi(a.mapa)
        if not mapa:
            ap.error("materiala ni: %s" % a.mapa)
        print(json.dumps(zapisi(mapa, a.ploscic, a.privzeto, a.vzorec, a.opis), ensure_ascii=False))
        if a.pregled:
            pregled(mapa, a.pregled)
    else:
        sez = seznam()
        if a.json:
            print(json.dumps(sez, ensure_ascii=False, indent=1))
        else:
            for m in sez:
                print("%-12s %-40s %s x %s mm, %d x %d na sliki%s" % (
                    m["id"], m["opis"], *("%g" % x for x in m["privzeto_mm"]), *m["ploscic"],
                    "  (brez ploscica.json)" if m["brez_opisa"] else ""))


if __name__ == "__main__":
    main(sys.argv[1:])
