# -*- coding: utf-8 -*-
"""Izvede Python kodo v FreeCAD-u, ki že teče s spletnim strežnikom (streznik.py), brez novega okna.

Namesto `FreeCAD.exe skripta.py` (odpre novo okno FreeCAD-a):
    python lastno/splet/izvedi.py skripta.py
    python lastno/splet/izvedi.py -c "print(App.ActiveDocument.Name)"
    ... | python lastno/splet/izvedi.py -

Koda teče na glavni niti FreeCAD-a z imeni App/FreeCAD in Gui/FreeCADGui. Izpis (print) in
spremenljivka `rezultat` se vrneta sem. Koda naj ne odpira pogovornih oken in naj ne kliče quit().
Vrata in žeton prebere iz %LOCALAPPDATA%/FreeCAD-splet/povezava.json (zapiše ga strežnik ob zagonu).
Python brez dodatnih knjižnic; deluje tudi s .pixi/envs/default/python.exe.
"""

import json
import os
import sys
import urllib.error
import urllib.request

DATOTEKA = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "FreeCAD-splet", "povezava.json")


def main(argumenti):
    if not argumenti or argumenti[0] in ("-h", "--help"):
        print(__doc__)
        return 2
    if argumenti[0] == "-c":
        koda = " ".join(argumenti[1:])
    elif argumenti[0] == "-":
        # bajti kot UTF-8: sys.stdin na Windows bere v kodni strani sistema (cp1252) in pokvari šumnike in pomišljaje
        koda = sys.stdin.buffer.read().decode("utf-8-sig")
    else:
        with open(argumenti[0], encoding="utf-8") as f:
            koda = f.read()
    try:
        with open(DATOTEKA, encoding="utf-8") as f:
            povezava = json.load(f)
    except (OSError, ValueError):
        print("Spletni strežnik FreeCAD-a ne teče (ni %s). Zaženi lastno/splet/ZAZENI-SPLET.bat "
              "ali za delo brez okna uporabi FreeCADCmd.exe." % DATOTEKA, file=sys.stderr)
        return 3
    zahteva = urllib.request.Request(
        "http://127.0.0.1:%d/python" % povezava["vrata"],
        data=json.dumps({"koda": koda, "cakaj": 600}).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Zeton": povezava["zeton"]},
        method="POST",
    )
    try:
        with urllib.request.urlopen(zahteva, timeout=620) as r:
            odgovor = json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, OSError) as e:
        print("Strežnik se ne odziva (%s). Je FreeCAD s spletnim strežnikom zaprt?" % e, file=sys.stderr)
        return 3
    if odgovor.get("izpis"):
        sys.stdout.write(odgovor["izpis"])
    if odgovor.get("rezultat") is not None:
        print(json.dumps(odgovor["rezultat"], ensure_ascii=False, indent=2))
    if not odgovor.get("koncano"):
        print("Koda se še izvaja (čas za odgovor je potekel).", file=sys.stderr)
        return 4
    if odgovor.get("napaka"):
        sys.stderr.write(odgovor["napaka"])
        return 1
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
