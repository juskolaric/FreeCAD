# -*- coding: utf-8 -*-
"""Lastni parametrični elektro kosi za bazo standardnih delov: kabelski kanal z režami in letev DIN TS35.

Oba objekta sta ``Part::FeaturePython``: mere so lastnosti skupine »Kanal« oz. »Letev«, oblika se zgradi ob vsakem
preračunu iz čistih kvadrov (brez skic), zato se ob spremembi mer ne more pokvariti noben sklic na ploskev ali rob.

- ``Kanal``: kabelski kanal (perforiran, s prsti) in pokrov. Izhodišče je spodnji levi vogal: dolžina vzdolž +X,
  širina vzdolž +Y, višina vzdolž +Z (dno na Z = 0, kot pri kosih iz SolidWorksa ``ELEKTRO - Kanal``). Reže so v obeh
  stenah od vrha navzdol, v dnu so podolgovate montažne luknje s korakom. ``Visina`` je skupna višina s pokrovom.
- ``DinLetev``: letev DIN TS35 (EN 60715, 35 × 7,5 ali 35 × 15) z montažnimi režami v dnu. Koordinatni sistem je
  enak kot pri napajalnikih Mean Well v bazi: X vzdolž letve (od 0 do ``Dolzina``), Y čez širino (± 17,5),
  Z = 0 je vrh letve (ploskev, na katero sedejo kosi), telo letve je v -Z do -``Visina`` (montažna plošča).

Modul mora biti na poti Pythona, ko se odpre dokument: mapa ``lastno/elektro`` je z mapo uporabniških dodatkov
povezana kot ``%APPDATA%/FreeCAD/v1-1/Mod/lastna_elektro`` (stičišče, glej README.md). Brez modula se dokument odpre,
objekta pa obdržita zadnjo shranjeno obliko in se ne preračunata.
"""
import FreeCAD as App
import Part

V = App.Vector


def _lastnost(obj, tip, ime, skupina, opis, vrednost=None):
    if ime not in obj.PropertiesList:
        obj.addProperty(tip, ime, skupina, opis)
        if vrednost is not None:
            setattr(obj, ime, vrednost)


def _mm(x):
    return float(getattr(x, "Value", x))


def _kvader(x0, x1, y0, y1, z0, z1):
    return Part.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def _podolgovata(dolzina, sirina, globina, sredina, smer_z=V(0, 0, 1)):
    """Podolgovata luknja (stadion) z dolžino vzdolž X, pravokotno na XY, od sredina.z navzgor za globina."""
    r = sirina / 2.0
    d = max(dolzina - sirina, 0.0)
    if d < 1e-6:
        return Part.makeCylinder(r, globina, sredina, smer_z)
    a = sredina + V(-d / 2.0, 0, 0)
    b = sredina + V(d / 2.0, 0, 0)
    telo = _kvader(a.x, b.x, sredina.y - r, sredina.y + r, sredina.z, sredina.z + globina)
    return telo.fuse([Part.makeCylinder(r, globina, a, smer_z), Part.makeCylinder(r, globina, b, smer_z)])


def _razpored(dolzina, korak, rob):
    """Sredine ponavljajočih se elementov vzdolž dolžine: simetrično okrog sredine, od robov vsaj ``rob``."""
    prosto = dolzina - 2.0 * rob
    if prosto < 0 or korak <= 0:
        return []
    n = int(prosto // korak) + 1
    zacetek = (dolzina - (n - 1) * korak) / 2.0
    return [zacetek + i * korak for i in range(n)]


# ---------------------------------------------------------------------------------------------------- kanal
class Kanal:
    def __init__(self, obj):
        obj.Proxy = self
        self._lastnosti(obj)

    def _lastnosti(self, obj):
        _lastnost(obj, "App::PropertyLength", "Dolzina", "Kanal", "Dolžina kanala (vzdolž X)", 200.0)
        _lastnost(obj, "App::PropertyLength", "Sirina", "Kanal", "Zunanja širina (vzdolž Y)", 25.0)
        _lastnost(obj, "App::PropertyLength", "Visina", "Kanal", "Skupna višina s pokrovom (vzdolž Z)", 40.0)
        _lastnost(obj, "App::PropertyLength", "DebelinaStene", "Kanal", "Debelina stranic in dna", 1.5)
        _lastnost(obj, "App::PropertyLength", "SirinaReze", "Kanal", "Širina reže med prsti", 4.0)
        _lastnost(obj, "App::PropertyLength", "KorakRez", "Kanal", "Korak rež (reža + prst)", 10.0)
        _lastnost(obj, "App::PropertyLength", "DnoReze", "Kanal", "Višina polne stene pod režami", 8.0)
        _lastnost(obj, "App::PropertyLength", "PremerLuknje", "Kanal", "Širina podolgovate montažne luknje v dnu", 6.0)
        _lastnost(obj, "App::PropertyLength", "DolzinaLuknje", "Kanal", "Dolžina podolgovate montažne luknje", 12.0)
        _lastnost(obj, "App::PropertyLength", "KorakLukenj", "Kanal", "Korak montažnih lukenj v dnu (0 = brez)", 25.0)
        _lastnost(obj, "App::PropertyBool", "Pokrov", "Kanal", "Nariši tudi pokrov", True)
        _lastnost(obj, "App::PropertyLength", "DebelinaPokrova", "Kanal", "Debelina plošče pokrova", 1.5)
        _lastnost(obj, "App::PropertyLength", "JezicekPokrova", "Kanal", "Višina jezička pokrova v kanalu", 5.0)

    def onDocumentRestored(self, obj):
        self._lastnosti(obj)

    def execute(self, obj):
        L, S, H = _mm(obj.Dolzina), _mm(obj.Sirina), _mm(obj.Visina)
        t = _mm(obj.DebelinaStene)
        tp = _mm(obj.DebelinaPokrova) if obj.Pokrov else 0.0
        hs = H - tp                                     # višina korita
        if min(L, S, H, t) <= 0 or hs <= t or S <= 2 * t:
            raise ValueError("Kanal: neveljavne mere")
        korito = _kvader(0, L, 0, S, 0, hs).cut(_kvader(0, L, t, S - t, t, hs + 1))
        rezi = []
        sr, kr, dr = _mm(obj.SirinaReze), _mm(obj.KorakRez), _mm(obj.DnoReze)
        if sr > 0 and kr > sr and dr < hs:
            for x in _razpored(L, kr, kr / 2.0 + sr / 2.0):
                rezi.append(_kvader(x - sr / 2.0, x + sr / 2.0, -1, t + 1, dr, hs + 1))
                rezi.append(_kvader(x - sr / 2.0, x + sr / 2.0, S - t - 1, S + 1, dr, hs + 1))
        pl, dl, kl = _mm(obj.PremerLuknje), _mm(obj.DolzinaLuknje), _mm(obj.KorakLukenj)
        if kl > 0 and pl > 0 and pl < S - 2 * t:
            for x in _razpored(L, kl, max(dl, pl) / 2.0 + 5.0):
                rezi.append(_podolgovata(max(dl, pl), pl, t + 2, V(x, S / 2.0, -1)))
        if rezi:
            korito = korito.cut(Part.makeCompound(rezi)) if len(rezi) > 1 else korito.cut(rezi[0])
        telesa = [korito.removeSplitter()]
        if obj.Pokrov and tp > 0:
            j = min(_mm(obj.JezicekPokrova), hs - dr)
            pokrov = _kvader(0, L, 0, S, hs, H)
            if j > 0:
                pokrov = pokrov.fuse([_kvader(0, L, t, 2 * t, hs - j, hs), _kvader(0, L, S - 2 * t, S - t, hs - j, hs)])
            telesa.append(pokrov.removeSplitter())
        obj.Shape = Part.makeCompound(telesa) if len(telesa) > 1 else telesa[0]


# ---------------------------------------------------------------------------------------------------- letev DIN
class DinLetev:
    def __init__(self, obj):
        obj.Proxy = self
        self._lastnosti(obj)

    def _lastnosti(self, obj):
        _lastnost(obj, "App::PropertyLength", "Dolzina", "Letev", "Dolžina letve (vzdolž X)", 200.0)
        _lastnost(obj, "App::PropertyLength", "Sirina", "Letev", "Širina letve (TS35 = 35)", 35.0)
        _lastnost(obj, "App::PropertyLength", "Visina", "Letev", "Globina profila (7,5 ali 15)", 7.5)
        _lastnost(obj, "App::PropertyLength", "SirinaDna", "Letev", "Zunanja širina dna (TS35 = 27)", 27.0)
        _lastnost(obj, "App::PropertyLength", "DebelinaPlocevine", "Letev", "Debelina pločevine", 1.0)
        _lastnost(obj, "App::PropertyBool", "Reze", "Letev", "Montažne reže v dnu (perforirana letev)", True)
        _lastnost(obj, "App::PropertyLength", "SirinaReze", "Letev", "Širina montažne reže", 6.2)
        _lastnost(obj, "App::PropertyLength", "DolzinaReze", "Letev", "Dolžina montažne reže", 18.0)
        _lastnost(obj, "App::PropertyLength", "KorakRez", "Letev", "Korak montažnih rež", 25.0)

    def onDocumentRestored(self, obj):
        self._lastnosti(obj)

    def execute(self, obj):
        L, S, H = _mm(obj.Dolzina), _mm(obj.Sirina), _mm(obj.Visina)
        sd, t = _mm(obj.SirinaDna), _mm(obj.DebelinaPlocevine)
        if min(L, S, H, sd, t) <= 0 or sd >= S or H <= t:
            raise ValueError("DinLetev: neveljavne mere")
        y = sd / 2.0
        deli = [
            _kvader(0, L, -y, y, -H, -H + t),                   # dno
            _kvader(0, L, -y, -y + t, -H, 0),                   # steni
            _kvader(0, L, y - t, y, -H, 0),
            _kvader(0, L, -S / 2.0, -y, -t, 0),                 # prirobnici (vrh letve na Z = 0)
            _kvader(0, L, y, S / 2.0, -t, 0),
        ]
        letev = deli[0].fuse(deli[1:])
        if obj.Reze:
            sr, dr, kr = _mm(obj.SirinaReze), _mm(obj.DolzinaReze), _mm(obj.KorakRez)
            if 0 < sr < sd - 2 * t and kr > 0:
                reze = [_podolgovata(max(dr, sr), sr, t + 2, V(x, 0, -H - 1)) for x in _razpored(L, kr, dr / 2.0 + 3.0)]
                if reze:
                    letev = letev.cut(Part.makeCompound(reze) if len(reze) > 1 else reze[0])
        obj.Shape = letev.removeSplitter()


def nov_kanal(doc, ime="Kanal"):
    obj = doc.addObject("Part::FeaturePython", ime)
    Kanal(obj)
    if App.GuiUp:
        obj.ViewObject.Proxy = 0
    return obj


def nova_letev(doc, ime="DinLetev"):
    obj = doc.addObject("Part::FeaturePython", ime)
    DinLetev(obj)
    if App.GuiUp:
        obj.ViewObject.Proxy = 0
    return obj
