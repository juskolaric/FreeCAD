# -*- coding: utf-8 -*-
"""Videz (material za prikaz) kosov za spletni pogled: barva + kovinskost, hrapavost in zrnatost (PBR).

FreeCAD videz hrani kot klasični material Coin (`ViewObject.ShapeAppearance`: DiffuseColor, SpecularColor,
Shininess ...), ki ga brskalnik (MeshStandardMaterial, PBR) ne more neposredno uporabiti. Zato:

1. Lastna prednastavitev: lastnost `Videz` (skupina »Videz«) na objektu kosa, npr. »pločevina«. Prednastavitev ob
   nastavitvi zapiše tudi ShapeAppearance, da je kos podoben tudi v FreeCAD-u; v brskalniku barva pride iz
   ShapeAppearance (uporabnik jo lahko spremeni), kovinskost/hrapavost/zrnatost iz prednastavitve.
2. Videz iz FreeCAD-ove knjižnice (Std_SetAppearance -> Steel, Chrome, Aluminum ...): prepozna se po vrednostih
   ShapeAppearance (knjižnica Materials/Appearance) in dobi ustrezne PBR vrednosti.
3. Sicer privzeti satenast videz (kovinskost 0,15, hrapavost 0,42) z barvo iz FreeCAD-a.

Sestav: povezava (App::Link) na podsestav je v posnetku en objekt, katerega oblika je sestav vseh kosov. Ploskve
sestava gredo po vrsti `getSubObjects()` (le vidni elementi), zato videz po ploskvah sestavimo po listih drevesa
(preverjeno: število ploskev in težišče prve ploskve vsakega lista se ujemata). Če se število ne ujema, ostane
ena barva za cel objekt (prejšnje vedenje).

Samo glavna nit (FreeCAD API)."""

import glob
import json
import os
import re

import FreeCAD as App

PRIVZETO = (0.15, 0.42, 0.0, 0)         # kovinskost, hrapavost, zrnatost, vzorec (brskalnik: satenast videz)
# vzorec: 0 = brez / brušenje (zrnatost), 1 = les (letnice in pore; brskalnik ga izriše iz koordinat modela)
LASTNOST = "Videz"

# Lastne prednastavitve. barva = barva, ki se zapiše v FreeCAD (ShapeAppearance) ob nastavitvi; None = ostane.
VIDEZI = {
    "pločevina": {"ime": "Pločevina (jeklo)", "barva": (0.66, 0.68, 0.70), "kov": 0.85, "hrap": 0.36, "zrn": 1.0},
    "nerjavna": {"ime": "Nerjaveča pločevina, brušena", "barva": (0.80, 0.81, 0.82), "kov": 0.95, "hrap": 0.26, "zrn": 1.0},
    "pocinkana": {"ime": "Pocinkana pločevina", "barva": (0.72, 0.75, 0.77), "kov": 0.8, "hrap": 0.45, "zrn": 1.6},
    "aluminij": {"ime": "Aluminij", "barva": (0.85, 0.86, 0.88), "kov": 0.9, "hrap": 0.32, "zrn": 0.6},
    "krom": {"ime": "Krom", "barva": (0.92, 0.92, 0.93), "kov": 1.0, "hrap": 0.07, "zrn": 0.0},
    "barvano-crno": {"ime": "Prašno barvano, črno", "barva": (0.09, 0.09, 0.10), "kov": 0.0, "hrap": 0.6, "zrn": 0.8},
    "barvano-belo": {"ime": "Prašno barvano, belo", "barva": (0.92, 0.92, 0.90), "kov": 0.0, "hrap": 0.55, "zrn": 0.8},
    "plastika": {"ime": "Plastika (barva ostane)", "barva": None, "kov": 0.0, "hrap": 0.48, "zrn": 0.0},
    "sijajna-plastika": {"ime": "Sijajna plastika (barva ostane)", "barva": None, "kov": 0.0, "hrap": 0.18, "zrn": 0.0},
    "guma": {"ime": "Guma", "barva": (0.08, 0.08, 0.08), "kov": 0.0, "hrap": 0.9, "zrn": 0.0},
    "3d-tisk-rumen": {"ime": "3D tisk (rumen PETG)", "barva": (0.98, 0.76, 0.08), "kov": 0.0, "hrap": 0.38, "zrn": 0.0},
    "folija": {"ime": "Folija (vinil, sijajna)", "barva": (0.10, 0.36, 0.78), "kov": 0.0, "hrap": 0.12, "zrn": 0.0},
    "les-hrast": {"ime": "Les, hrast", "barva": (0.72, 0.54, 0.34), "kov": 0.0, "hrap": 0.62, "zrn": 0.0, "vzorec": 1},
}

# FreeCAD-ova knjižnica videzov (Materials/Appearance/*.FCMat, klasične vrednosti Coin) -> PBR. barva None = barva
# iz FreeCAD-a (DiffuseColor); kovine imajo v Coinu črno ali temno difuzno barvo, zato dobijo svojo.
KNJIZNICA_PBR = {
    "Steel": ((0.56, 0.57, 0.58), 1.0, 0.35, 0.6),
    "Chrome": ((0.90, 0.90, 0.92), 1.0, 0.06, 0.0),
    "Aluminum": ((0.86, 0.87, 0.88), 1.0, 0.30, 0.4),
    "Brass": ((0.89, 0.74, 0.42), 1.0, 0.25, 0.0),
    "Bronze": ((0.71, 0.48, 0.25), 1.0, 0.35, 0.0),
    "Copper": ((0.93, 0.60, 0.45), 1.0, 0.25, 0.0),
    "Gold": ((1.00, 0.78, 0.34), 1.0, 0.20, 0.0),
    "Silver": ((0.95, 0.94, 0.92), 1.0, 0.15, 0.0),
    "Pewter": ((0.60, 0.60, 0.62), 0.9, 0.40, 0.4),
    "Metalized": ((0.70, 0.70, 0.72), 1.0, 0.25, 0.0),
    "Satin": ((0.62, 0.62, 0.64), 0.8, 0.45, 0.4),
    "Plastic": (None, 0.0, 0.50, 0.0),
    "Shiny Plastic": (None, 0.0, 0.18, 0.0),
    "Wood": ((0.66, 0.48, 0.30), 0.0, 0.6, 0.0, 1),
}

VSEBNIKI = ("App::Part", "App::DocumentObjectGroup", "App::LinkGroup")

_knjiznica = None


def _barva(niz):
    return tuple(float(x) for x in re.findall(r"[-\d.]+", niz)[:3])


def knjiznica():
    """[(ime, difuzna, zrcalna, sijaj)] iz FreeCAD-ove knjižnice videzov (enkrat prebrano)."""
    global _knjiznica
    if _knjiznica is not None:
        return _knjiznica
    _knjiznica = []
    mapa = os.path.join(App.getResourceDir(), "Mod", "Material", "Resources", "Materials", "Appearance")
    for pot in glob.glob(os.path.join(mapa, "*.FCMat")):
        try:
            with open(pot, encoding="utf-8") as f:
                besedilo = f.read()
            d = re.search(r'DiffuseColor:\s*"([^"]+)"', besedilo)
            s = re.search(r'SpecularColor:\s*"([^"]+)"', besedilo)
            h = re.search(r'Shininess:\s*"([^"]+)"', besedilo)
            if d and s and h:
                _knjiznica.append((os.path.splitext(os.path.basename(pot))[0], _barva(d.group(1)),
                                   _barva(s.group(1)), float(h.group(1))))
        except (OSError, ValueError):
            pass
    return _knjiznica


def _blizu(a, b, tol=0.006):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def ime_knjiznice(mat):
    """Ime videza iz knjižnice, ki ustreza materialu ShapeAppearance (App.Material), ali None."""
    try:
        d, s, h = tuple(mat.DiffuseColor[:3]), tuple(mat.SpecularColor[:3]), float(mat.Shininess)
    except Exception:  # noqa: BLE001
        return None
    for ime, kd, ks, kh in knjiznica():
        if _blizu(d, kd) and _blizu(s, ks) and abs(h - kh) <= 0.006:
            return ime
    return None


def _cilj(obj):
    try:
        cilj = obj.getLinkedObject(True)
        return cilj if cilj is not None else obj
    except Exception:  # noqa: BLE001
        return obj


def lastni_videz(obj):
    """Ključ lastne prednastavitve na objektu, na povezanem objektu ali na vsebniku (App::Part) v njegovem
    dokumentu; '' če ga ni."""
    for o in (obj, _cilj(obj)):
        v = getattr(o, LASTNOST, "") if LASTNOST in getattr(o, "PropertiesList", ()) else ""
        if v in VIDEZI:
            return v
    o = _cilj(obj)
    for _ in range(12):
        try:
            o = o.getParentGeoFeatureGroup()
        except Exception:  # noqa: BLE001
            return ""
        if o is None:
            return ""
        v = getattr(o, LASTNOST, "") if LASTNOST in o.PropertiesList else ""
        if v in VIDEZI:
            return v
    return ""


def _je_vsebnik(obj):
    if obj.TypeId == "Assembly::AssemblyLink":
        return True
    try:
        if obj.isDerivedFrom("App::Link") and int(getattr(obj, "ElementCount", 0) or 0) > 0:
            return True
    except Exception:  # noqa: BLE001
        pass
    cilj = _cilj(obj)
    return any(cilj.isDerivedFrom(t) for t in VSEBNIKI)


def _viden(obj, sub, otrok):
    try:
        v = obj.isElementVisible(sub.rstrip("."))
        if v >= 0:
            return bool(v)
    except Exception:  # noqa: BLE001
        pass
    return bool(getattr(otrok, "Visibility", True))


def listi(obj, podedovan="", globina=0):
    """[(list, ključ videza)] v vrstnem redu ploskev oblike objekta (glej opis modula)."""
    podedovan = lastni_videz(obj) or podedovan
    if globina < 12 and _je_vsebnik(obj):
        izhod = []
        for sub in obj.getSubObjects():
            try:
                otrok = obj.getSubObject(sub, retType=1)
            except Exception:  # noqa: BLE001
                otrok = None
            if otrok is None or not _viden(obj, sub, otrok):
                continue
            izhod.extend(listi(otrok, podedovan, globina + 1))
        return izhod
    if globina and not hasattr(obj, "Shape"):
        return []          # skupina spojev (JointGroup) ipd.: brez oblike, ne prispeva ploskev
    return [(obj, podedovan)]


def lastnosti(obj, kljuc):
    """(barva ali None, kovinskost, hrapavost, zrnatost, vzorec) lista `obj` s ključem videza; barva None = barva iz
    FreeCAD-a (po ploskvah)."""
    if kljuc in VIDEZI:
        p = VIDEZI[kljuc]
        return None, p["kov"], p["hrap"], p["zrn"], p.get("vzorec", 0)
    try:
        videz = list(_cilj(obj).ViewObject.ShapeAppearance)
        ime = ime_knjiznice(videz[0]) if videz else None
    except Exception:  # noqa: BLE001
        ime = None
    if ime in KNJIZNICA_PBR:
        return (KNJIZNICA_PBR[ime] + (0,))[:5]
    return (None,) + PRIVZETO


def _pbr(lastn, barva):
    return tuple(lastn[0] or barva[:3]) + tuple(lastn[1:])


def stevilo_ploskev_lista(lst):
    """Število ploskev lista; povezava ima toliko ploskev kot povezani objekt, katerega oblika je že izračunana
    (oblika povezave se ob vsakem branju zgradi znova, seznam Faces pa ustvari objekt za vsako ploskev)."""
    cilj = _cilj(lst)
    oblika = cilj.Shape if hasattr(cilj, "Shape") else lst.Shape
    return oblika.countElement("Face")


def ploskve_videza(obj, stevilo_ploskev, barve):
    """Videz po ploskvah objekta posnetka: (osnovna, po_ploskvah ali None), vsak vnos (r, g, b, kov, hrap, zrn,
    vzorec).
    `barve(obj, n)` je strežnikova funkcija (osnovna barva, barve po ploskvah ali None)."""
    vsi = listi(obj)
    if len(vsi) > 1:
        try:
            po_ploskvah = []
            for lst, kljuc in vsi:
                n = stevilo_ploskev_lista(lst)
                osnovna, posamezne = barve(lst, n)
                lastn = lastnosti(lst, kljuc)
                if posamezne:
                    po_ploskvah.extend(_pbr(lastn, b) for b in posamezne)
                else:
                    po_ploskvah.extend([_pbr(lastn, osnovna)] * n)
            if po_ploskvah and len(po_ploskvah) == stevilo_ploskev:
                return po_ploskvah[0], po_ploskvah
        except Exception:  # noqa: BLE001
            pass
    kljuc = vsi[0][1] if vsi else lastni_videz(obj)
    osnovna, posamezne = barve(obj, stevilo_ploskev)
    lastn = lastnosti(obj, kljuc)
    return _pbr(lastn, osnovna), ([_pbr(lastn, b) for b in posamezne] if posamezne else None)


def kljuc_videza(obj, barve):
    """Odtis videza za predpomnilnik posnetka (brez branja oblik listov: le ključi, barve, vidnost)."""
    odtis = []
    for lst, kljuc in listi(obj):
        try:
            cilj = _cilj(lst)
            videz = tuple((tuple(m.DiffuseColor[:3]), tuple(m.SpecularColor[:3]), round(m.Shininess, 4))
                          for m in cilj.ViewObject.ShapeAppearance) if getattr(cilj, "ViewObject", None) else ()
        except Exception:  # noqa: BLE001
            videz = ()
        odtis.append((lst.FullName if hasattr(lst, "FullName") else lst.Name, kljuc, videz,
                      bool(getattr(getattr(lst, "ViewObject", None), "OverrideMaterial", False))))
    return tuple(odtis)


# ---------------------------------------------------------------------------
# Nastavljanje videza (iz brskalnika ali skripte)

def _material(barva, p):
    """App.Material za FreeCAD-ov prikaz (Coin) iz prednastavitve: kovine dobijo močnejši odsev."""
    m = App.Material()
    m.DiffuseColor = tuple(barva) + (1.0,)
    m.AmbientColor = tuple(0.3 * c for c in barva) + (1.0,)
    s = 0.25 + 0.5 * p["kov"]
    m.SpecularColor = (s, s, s, 1.0)
    m.EmissiveColor = (0.0, 0.0, 0.0, 1.0)
    m.Shininess = max(0.05, 0.6 * (1.0 - p["hrap"]))
    m.Transparency = 0.0
    return m


def kosi_z_obliko(cilj):
    """Objekti z vidno obliko pod `cilj` v njegovem dokumentu (cilj sam, če ni vsebnik). Razgrnitev, DXF in
    izhodišča izpusti."""
    if not any(cilj.isDerivedFrom(t) for t in VSEBNIKI):
        return [cilj]
    izhod, vrsta = [], list(getattr(cilj, "Group", []))
    while vrsta:
        o = vrsta.pop(0)
        if o.Name.startswith(("Razgrnitev", "DXF")) or "Origin" in o.TypeId:
            continue
        if any(o.isDerivedFrom(t) for t in VSEBNIKI):
            vrsta.extend(getattr(o, "Group", []))
        elif hasattr(o, "Shape") and getattr(o, "ViewObject", None) is not None:
            izhod.append(o)
    return izhod


IZVIRNI = "VidezIzvirni"   # ShapeAppearance pred prvo prednastavitvijo (JSON), da ga »privzeto« vrne
_POLJA = ("DiffuseColor", "AmbientColor", "SpecularColor", "EmissiveColor", "Shininess", "Transparency")


def _shrani_izvirni(o):
    if IZVIRNI in o.PropertiesList:
        return
    zapis = [{p: (list(getattr(m, p)) if p.endswith("Color") else float(getattr(m, p))) for p in _POLJA}
             for m in o.ViewObject.ShapeAppearance]
    o.addProperty("App::PropertyString", IZVIRNI, "Videz", "Videz (ShapeAppearance) pred prednastavitvijo")
    o.setEditorMode(IZVIRNI, 2)   # skrita v urejevalniku lastnosti
    setattr(o, IZVIRNI, json.dumps(zapis))


def _vrni_izvirni(o):
    if IZVIRNI not in o.PropertiesList:
        return
    try:
        materiali = []
        for z in json.loads(getattr(o, IZVIRNI)):
            m = App.Material()
            for p in _POLJA:
                setattr(m, p, tuple(z[p]) if p.endswith("Color") else z[p])
            materiali.append(m)
        if materiali:
            o.ViewObject.ShapeAppearance = tuple(materiali)
    except Exception:  # noqa: BLE001
        pass
    o.removeProperty(IZVIRNI)


def nastavi_videz(obj, kljuc):
    """Kosu (povezava -> povezani objekt v svojem dokumentu) nastavi prednastavitev `kljuc` ali jo odstrani
    (kljuc '' ali 'privzeto': vrne videz izpred prve prednastavitve). Vrne (cilj, spremenjeni objekti)."""
    cilj = _cilj(obj)
    if kljuc and kljuc != "privzeto" and kljuc not in VIDEZI:
        raise ValueError("neznan videz: %s" % kljuc)
    if not kljuc or kljuc == "privzeto":
        for o in [cilj] + kosi_z_obliko(cilj):
            if LASTNOST in o.PropertiesList:
                o.removeProperty(LASTNOST)
            if getattr(o, "ViewObject", None) is not None:
                _vrni_izvirni(o)
        return cilj, []
    if LASTNOST not in cilj.PropertiesList:
        cilj.addProperty("App::PropertyString", LASTNOST, "Videz",
                         "Videz kosa v spletnem pogledu (prednastavitev: %s)" % ", ".join(VIDEZI))
    setattr(cilj, LASTNOST, kljuc)
    p = VIDEZI[kljuc]
    spremenjeni = []
    for o in kosi_z_obliko(cilj):
        vo = o.ViewObject
        try:
            _shrani_izvirni(o)
            barva = p["barva"] or tuple(vo.ShapeAppearance[0].DiffuseColor[:3])
            vo.ShapeAppearance = (_material(barva, p),)
            spremenjeni.append(o)
        except Exception:  # noqa: BLE001
            pass
    return cilj, spremenjeni


def je_plocevina(obj):
    """Kos iz pločevine: lastnost Vrsta = »pločevina« (prenos iz SolidWorksa) ali debelina pločevine
    (Debelina iz SolidWorksa, SheetMetal), razen folij."""
    cilj = _cilj(obj)
    vrsta = str(getattr(cilj, "Vrsta", "") or "").lower()
    if "pločevina" in vrsta:
        return True
    if "folij" in vrsta or "foil" in vrsta:
        return False
    if "Debelina" in cilj.PropertiesList:
        return True
    modul = type(getattr(cilj, "Proxy", None)).__module__ or ""
    return modul.startswith(("SheetMetal", "SM")) or modul == "lastna_plocevina"


def videz_plocevine(obj):
    """Prednastavitev za kos iz pločevine po materialu iz SolidWorksa (MaterialSW): nerjavno jeklo, aluminij,
    sicer jeklena pločevina."""
    mat = str(getattr(_cilj(obj), "MaterialSW", "") or "").lower()
    if "stainless" in mat or "nerjav" in mat or "inox" in mat:
        return "nerjavna"
    if "alumin" in mat or "1060" in mat or "6061" in mat or "5754" in mat:
        return "aluminij"
    return "pločevina"


def seznam_videzov():
    return [{"kljuc": k, "ime": v["ime"], "barva": v["barva"], "kov": v["kov"], "hrap": v["hrap"]} for k, v in VIDEZI.items()]
