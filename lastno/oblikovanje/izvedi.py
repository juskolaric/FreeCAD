# Izvede Python v tekočem Oblikovanju (Blender v ozadju) in izpiše izpis, napako in `rezultat`.
#   python izvedi.py skripta.py
#   python izvedi.py -c "dodaj_obliko('krogla', 60); rezultat = len(D.objects)"
#   python izvedi.py - < skripta.py
# Vrata in žeton bere iz %LOCALAPPDATA%/FreeCAD-splet/oblikovanje.json (zapiše ga streznik_blender.py ob zagonu).
import json
import os
import sys
import urllib.request

POVEZAVA = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "FreeCAD-splet", "oblikovanje.json")


def main():
    if len(sys.argv) < 2:
        print(__doc__ or "uporaba: izvedi.py skripta.py | -c koda | -")
        return 2
    if sys.argv[1] == "-c":
        koda = sys.argv[2]
    elif sys.argv[1] == "-":
        koda = sys.stdin.buffer.read().decode("utf-8")
    else:
        with open(sys.argv[1], encoding="utf-8") as f:
            koda = f.read()
    try:
        with open(POVEZAVA, encoding="utf-8") as f:
            pov = json.load(f)
    except OSError:
        print("Oblikovanje ne teče (ni %s)." % POVEZAVA)
        return 1
    zahteva = urllib.request.Request("http://127.0.0.1:%d/python" % pov["vrata"],
                                     data=json.dumps({"koda": koda, "cakaj": 600}).encode("utf-8"),
                                     headers={"Content-Type": "application/json", "X-Zeton": pov["zeton"]})
    with urllib.request.urlopen(zahteva, timeout=620) as r:
        odg = json.loads(r.read().decode("utf-8"))
    if odg.get("izpis"):
        sys.stdout.write(odg["izpis"])
    if odg.get("napaka"):
        sys.stdout.write(odg["napaka"])
    if odg.get("rezultat") is not None:
        print("rezultat:", json.dumps(odg["rezultat"], ensure_ascii=False, default=str))
    return 0 if odg.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
