# -*- coding: utf-8 -*-
"""Kontrola prenosa projekta (brez okna, FreeCADCmd; projekt = SW_PROJEKT):
- del: okvir v FreeCAD-u proti okvirju iz SolidWorksa (GetPartBox, zasukan pokonci), ±1 mm;
- sestav: vsako telo vsakega vidnega dela na legi iz SolidWorksa (Transform2 x telo dela) mora imeti v sestavu telo
  z enakim težiščem (±0,5 mm) in prostornino (±1 %); okvir sestava proti GetBox iz SolidWorksa.
Zapiše <podatki>/kontrola.json in izpiše povzetek.
Zagon: pixi run -- .pixi/envs/default/Library/bin/FreeCADCmd.exe preveri.py"""
import json
import os
import sys

import FreeCAD as App
import Part

try:
    TU = os.path.dirname(os.path.abspath(__file__))
except NameError:
    TU = os.path.join(os.path.expanduser("~"), "Desktop", "GitHub", "CAD in 3D", "FreeCAD", "lastno", "solidworks")
if TU not in sys.path:
    sys.path.insert(0, TU)
import zgradi as zd  # noqa: E402

PODATKI = zd.PODATKI
S = json.load(open(os.path.join(PODATKI, "struktura.json"), encoding="utf-8"))
REZ = json.load(open(os.path.join(PODATKI, "rezultat.json"), encoding="utf-8"))
R = zd.R
izid = {"deli": {}, "sestavi": {}}


def okvir_pokonci(b):
    a, c = R.multVec(App.Vector(*b[:3])), R.multVec(App.Vector(*b[3:]))
    return [min(a.x, c.x), min(a.y, c.y), min(a.z, c.z), max(a.x, c.x), max(a.y, c.y), max(a.z, c.z)]


def zapri_vse():
    for d in list(App.listDocuments().values()):
        App.closeDocument(d.Name)


# ---------------------------------------------------------------- deli
telesa_dela = {}
slabi_deli = []
for k, z in sorted(REZ.items()):
    if z["vrsta"] != "del" or not os.path.exists(z["datoteka"]):
        continue
    try:
        doc = App.openDocument(z["datoteka"], True)
        obl = Part.getShape(zd.tarca_dela(doc), "", needSubElement=False, refine=False, transform=True)
    except Exception as e:  # noqa: BLE001
        slabi_deli.append((os.path.relpath(z["datoteka"], zd.cfg.CILJ_KOREN), "ni odprl", str(e)[:80]))
        continue
    telesa_dela[k] = [(t.CenterOfMass, abs(t.Volume)) for t in obl.Solids if abs(t.Volume) > 1e-6]
    bb = obl.BoundBox
    r = {"teles": len(obl.Solids), "V": sum(v for _, v in telesa_dela[k]),
         "okvir": [bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax]}
    sw = S["deli"].get(k, {})
    if sw.get("okvir") and obl.Solids:
        r["d_okvir"] = max(abs(u - w) for u, w in zip(r["okvir"], okvir_pokonci(sw["okvir"])))
        if r["d_okvir"] > 1.0:
            slabi_deli.append((os.path.relpath(z["datoteka"], zd.cfg.CILJ_KOREN), "okvir", round(r["d_okvir"], 2)))
    if not obl.Solids:
        slabi_deli.append((os.path.relpath(z["datoteka"], zd.cfg.CILJ_KOREN), "brez teles", len(obl.Faces)))
    izid["deli"][k] = r
    App.closeDocument(doc.Name)

# ---------------------------------------------------------------- sestavi
slabi_sestavi = []
for p, s in sorted(S["sestavi"].items()):
    if "drevo" not in s:
        continue
    z = REZ.get(zd.kljuc(s["pot"], s["cfg"]))
    if not z or not os.path.exists(z["datoteka"]):
        continue
    pricakovano = []

    def obhod(vozli, skrito):
        for x in vozli:
            if x["zatrto"] or not x["lega"]:
                continue
            sk = skrito or x["skrito"]
            if x["vrsta"] == "DEL" and not sk and x["kljuc"] in telesa_dela:
                g = zd.v_z_gor(zd.matrika(x["lega"]))
                for c, vol in telesa_dela[x["kljuc"]]:
                    pricakovano.append((g.multVec(c), vol, x["ime"]))
            obhod(x.get("otroci", []), sk)

    obhod(s["drevo"], False)
    try:
        doc = App.openDocument(z["datoteka"], True)
        obl = Part.getShape(zd.tarca_sestava(doc), "", needSubElement=False, refine=False, transform=True)
    except Exception as e:  # noqa: BLE001
        slabi_sestavi.append((os.path.relpath(z["datoteka"], zd.cfg.CILJ_KOREN), 0, 0, ["ni odprl: " + str(e)[:80]]))
        zapri_vse()
        continue
    telesa = [(t.CenterOfMass, abs(t.Volume)) for t in obl.Solids if abs(t.Volume) > 1e-6]
    brez = [ime for c, vol, ime in pricakovano
            if vol >= 1 and not any((c - c2).Length < 0.5 and abs(vol - v2) <= 0.01 * vol for c2, v2 in telesa)]
    bb = obl.BoundBox
    r = {"teles_pricakovanih": len(pricakovano), "teles_fc": len(telesa), "brez_para": brez,
         "okvir_fc": [bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax] if telesa else None}
    if s.get("okvir") and telesa:
        r["okvir_sw"] = okvir_pokonci(s["okvir"])
        r["d_okvir"] = max(abs(u - w) for u, w in zip(r["okvir_fc"], r["okvir_sw"]))
    izid["sestavi"][z["datoteka"]] = r
    if brez:
        slabi_sestavi.append((os.path.relpath(z["datoteka"], zd.cfg.CILJ_KOREN), len(pricakovano), len(brez), brez[:4]))
    zapri_vse()

povzetek = {
    "deli_preverjenih": len(izid["deli"]), "deli_odstopa": len(slabi_deli),
    "sestavi_preverjenih": len(izid["sestavi"]),
    "teles_na_legi": sum(r["teles_pricakovanih"] - len(r["brez_para"]) for r in izid["sestavi"].values()),
    "teles_pricakovanih": sum(r["teles_pricakovanih"] for r in izid["sestavi"].values()),
    "sestavi_z_odstopanji": len(slabi_sestavi),
    "slabi_deli": slabi_deli, "slabi_sestavi": [list(x) for x in slabi_sestavi],
}
izid["povzetek"] = povzetek
json.dump(izid, open(os.path.join(PODATKI, "kontrola.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("DELI: preverjenih %d, odstopa %d" % (len(izid["deli"]), len(slabi_deli)))
for x in slabi_deli[:40]:
    print("   ", x)
print("SESTAVI: preverjenih %d, teles na legi %d od %d, sestavov z odstopanji %d" % (
    len(izid["sestavi"]), povzetek["teles_na_legi"], povzetek["teles_pricakovanih"], len(slabi_sestavi)))
for x in slabi_sestavi[:40]:
    print("   ", x)
with open(os.path.join(PODATKI, "kontrola.konec"), "w", encoding="utf-8") as f:
    f.write("ok\n")
