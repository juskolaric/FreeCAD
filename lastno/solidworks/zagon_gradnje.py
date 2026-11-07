# -*- coding: utf-8 -*-
"""Samostojen zagon gradnje (zgradi.py) v ločenem primerku lastne gradnje FreeCAD-a (okno takoj skrito, na koncu se
zapre). Uporabnikov spletni FreeCAD se med gradnjo ne obremeni.

Zagon (prenos.py to naredi sam; iz mape repozitorija FreeCAD, z ločenim user.cfg in TEMP):
  SW_PROJEKT=<ključ iz prenos.json>  TEMP=TMP=<začasna mapa>
  pixi run -q --no-progress -- .pixi/envs/default/Library/bin/FreeCAD.exe --user-cfg <kopija user.cfg> zagon_gradnje.py
Konec: <podatki>/gradnja.konec vsebuje »ok« ali sled napake. VEDNO prek pixi, sicer manjka PySide6 (past 6. 11. 2026).
"""
import os
import sys
import traceback

import FreeCAD as App
import FreeCADGui as Gui

TU = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else \
    os.path.join(os.path.expanduser("~"), "Desktop", "GitHub", "CAD in 3D", "FreeCAD", "lastno", "solidworks")
if TU not in sys.path:
    sys.path.insert(0, TU)
import prenos_cfg as cfg  # noqa: E402

KONEC = os.path.join(cfg.podatki(os.environ["SW_PROJEKT"]), "gradnja.konec")

try:
    Gui.getMainWindow().hide()
except Exception:  # noqa: BLE001
    pass


def teci():
    try:
        Gui.getMainWindow().hide()
        App.ParamGet("User parameter:BaseApp/Preferences/Document").SetBool("CreateBackupFiles", False)
        import zgradi
        try:
            zgradi.zgradi()
            izid = "ok"
        except zgradi.PomnilnikPoln as e:
            izid = "pomnilnik %s" % e        # prenos.py gradnjo nadaljuje v novem procesu
    except Exception:  # noqa: BLE001
        izid = traceback.format_exc()
    with open(KONEC, "w", encoding="utf-8") as f:
        f.write(izid)
    os._exit(0)


from PySide import QtCore  # noqa: E402

QtCore.QTimer.singleShot(3000, teci)
