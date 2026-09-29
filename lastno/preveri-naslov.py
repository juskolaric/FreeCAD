# Preizkus zanke: FreeCAD ob zagonu zapiše naslov glavnega okna in verzijo v build/naslov-okna.txt in se zapre.
# Zagon: pixi run -- .pixi/envs/default/Library/bin/FreeCAD.exe lastno/preveri-naslov.py
import os
import FreeCAD
import FreeCADGui
from PySide6 import QtCore, QtWidgets

try:
    MAPA = os.path.dirname(os.path.abspath(__file__))
except NameError:
    MAPA = os.getcwd()
IZHOD = os.path.normpath(os.path.join(MAPA, "..", "build", "naslov-okna.txt"))

def _zapisi():
    try:
        os.makedirs(os.path.dirname(IZHOD), exist_ok=True)
        mw = FreeCADGui.getMainWindow()
        v = FreeCAD.Version()
        with open(IZHOD, "w", encoding="utf-8") as f:
            f.write("NASLOV: " + mw.windowTitle() + "\n")
            f.write("VERZIJA: " + ".".join(str(x) for x in v[0:3]) + " " + str(v[3]) + "\n")
    except Exception as e:
        with open(IZHOD, "w", encoding="utf-8") as f:
            f.write("NAPAKA: " + repr(e) + "\n")
    QtWidgets.QApplication.instance().quit()

QtCore.QTimer.singleShot(3000, _zapisi)
