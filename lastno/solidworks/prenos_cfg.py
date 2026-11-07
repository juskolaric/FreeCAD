# -*- coding: utf-8 -*-
"""Skupne nastavitve prenosa iz SolidWorksa (prenos.json): projekti, poti, razvrstitev dokumentov v mape Oblaka.

Deluje v sistemskem Pythonu in v FreeCAD-u (brez odvisnosti)."""
import json
import os
import re

TU = os.path.dirname(os.path.abspath(__file__))
PRENOS = json.load(open(os.path.join(TU, "prenos.json"), encoding="utf-8"))
IZVOR_KOREN = os.path.normpath(PRENOS["izvor_koren"])
CILJ_KOREN = os.path.normpath(PRENOS["cilj_koren"])
DELOVNA = os.path.normpath(PRENOS["delovna"])
STEP = os.path.normpath(PRENOS["step"])


def _nc(p):
    return os.path.normcase(os.path.normpath(p))


# vse mape PROJEKTI, ki imajo svoj projekt v Oblaku: ključ (pot pod PROJEKTI, »/«) -> ime mape v Oblaku
PRESLIKAVA = dict(PRENOS.get("ze_preneseni", {}))
for _p in PRENOS["projekti"]:
    PRESLIKAVA[_p["kljuc"]] = _p["cilj"]
_PO_DOLZINI = sorted(PRESLIKAVA.items(), key=lambda t: -len(t[0]))


def projekt(kljuc):
    for p in PRENOS["projekti"]:
        if p["kljuc"] == kljuc:
            return p
    raise KeyError("projekt %r ni v prenos.json" % kljuc)


def izvor(kljuc):
    return os.path.join(IZVOR_KOREN, kljuc.replace("/", os.sep))


def cilj(kljuc):
    return os.path.join(CILJ_KOREN, PRESLIKAVA[kljuc].replace("/", os.sep))


def podatki(kljuc):
    return os.path.join(DELOVNA, PRESLIKAVA[kljuc].replace("/", " - "), "podatki")


def pripada(pot):
    """Kateri projekt (ključ) pokriva pot SolidWorks; None, če nobeden (zunaj PROJEKTI ali nenašteta mapa)."""
    n = _nc(pot)
    for k, _ in _PO_DOLZINI:
        osnova = _nc(izvor(k)) + os.sep
        if n.startswith(osnova):
            return k
    return None


def ciljna_mapa(pot, kljuc_projekta):
    """Mapa v Oblaku za dokument SolidWorks `pot`, ko gradimo projekt `kljuc_projekta`:
    - dokument iz mape kakšnega projekta (tudi drugega) -> ta projekt, ista zgradba podmap;
    - sicer -> <ta projekt>/Zunanji deli/<pot pod PROJEKTI ali brez pogona>."""
    k = pripada(pot)
    if k is not None:
        rel = os.path.relpath(os.path.dirname(os.path.normpath(pot)), izvor(k))
        return os.path.normpath(os.path.join(cilj(k), "" if rel == "." else rel)), k
    n = os.path.normpath(pot)
    m = re.search(r"[\\/]PROJEKTI[\\/](.+)$", n, re.I)
    rel = m.group(1) if m else n.replace(":", "")
    return os.path.normpath(os.path.join(cilj(kljuc_projekta), "Zunanji deli", os.path.dirname(rel))), None


def vse_strukture():
    """Vse struktura.json že prebranih projektov (za dejavne konfiguracije dokumentov iz drugih map)."""
    sez = []
    if not os.path.isdir(DELOVNA):
        return sez
    for ime in sorted(os.listdir(DELOVNA)):
        p = os.path.join(DELOVNA, ime, "podatki", "struktura.json")
        if os.path.exists(p):
            sez.append(p)
    return sez
