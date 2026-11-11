# -*- coding: utf-8 -*-
"""Zunanja oblika strojnega modela kot preprosta Blender datoteka v Oblikovanju, VEZANA na strojni sestav.

    python lastno/oblikovanje/zunanja_oblika.py "Space"             osveži, če se je zunanjost spremenila
    python lastno/oblikovanje/zunanja_oblika.py "Space" --preveri   samo pove, ali je Blender datoteka še enaka (koda 3 = ni)
    python lastno/oblikovanje/zunanja_oblika.py "Space" --vedno     zgradi novo različico v vsakem primeru
    python lastno/oblikovanje/zunanja_oblika.py "Malibu F" --recept=zunanja_oblika_1.5   recept Skripte/zunanja_oblika_1.5.json

Projekt je mapa v Oblak/3D modeliranje (ali polna pot); v njej je recept Skripte/zunanja_oblika.json:
    sestav                 glavni sestav (FCStd) v mapi projekta
    projekt_oblikovanja    projekt v Oblikovanju (Oblikovanje/Projekti/<ime>)
    ideja, opis            ideja, v katero gre vsaka osvežitev kot nova različica (kosi v scenah ji sledijo: posodobi_kos)
    izpusti                vrhnji kosi sestava, ki niso del zunanjosti (hitrost; skrito odpade tudi samo)
    najmanjsi_kos          telesa z manjšo diagonalo okvirja odpadejo (mm; vijaki, drobnarije)
    najmanjsa_luknja       luknje v ravnih ploskvah z manjšo diagonalo se zaprejo (mm; perforacija, izvrtine)
    najmanjsa_ploskev      ploskve z manjšo diagonalo odpadejo (mm; stene zaprtih lukenj)
    odstop                 odstop mreže od oblike (mm)
    prag_vidnosti          delež žarkov, ki mora s ploskve priti ven, da ploskev ostane (privzeto 0.01)
    materiali              {"*" | vrhnji kos | "vrhnji kos/kos podsestava": {ime, barva [r, g, b], kovinskost, hrapavost}};
                           velja najbolj natančen ključ; `ime` je ime materiala v Blenderju (isti ime = isti material)

Potek: FreeCADCmd (brez okna) odpre SHRANJEN sestav in izvozi grobo mrežo (zunanja_izvoz.py) -> odtis geometrije se
primerja z odtisom zadnje različice (vir.json v mapi ideje) -> ob razliki Blender brez okna obdrži le od zunaj vidne
ploskve in shrani novo različico ideje (zunanja_blender.py). Tekočega spletnega FreeCAD-a in Oblikovanja se ne dotakne;
bere z diska, zato sestav in spremenjene kose pred tem shrani.
"""
import glob
import hashlib
import json
import os
import subprocess
import sys
import tempfile

MAPA = os.path.dirname(os.path.abspath(__file__))
MODELI = os.path.join(os.path.expanduser("~"), "Oblak", "3D modeliranje")
FREECADCMD = os.environ.get("SPLET_FREECADCMD") or r"C:\Program Files\FreeCAD 1.1\bin\FreeCADCmd.exe"


def najdi_blender():
    pot = os.environ.get("SPLET_BLENDER")
    if pot and os.path.isfile(pot):
        return pot
    kandidati = []
    for koren in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                  os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")):
        kandidati += glob.glob(os.path.join(koren, "Blender Foundation", "Blender *", "blender.exe"))
    kandidati.sort(key=lambda p: [int(x) for x in os.path.basename(os.path.dirname(p)).split()[-1].split(".") if x.isdigit()])
    return kandidati[-1] if kandidati else None


def pozeni(ukaz, okolje, konec):
    """Požene ukaz, izpisuje samo naše vrstice (FreeCADCmd piše napredek odpiranja), vrne True, če je bil izpisan `konec`."""
    p = subprocess.run(ukaz, env=okolje, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    besedilo = p.stdout.decode("utf-8", "replace")
    uspeh = False
    for v in besedilo.replace("\r", "\n").split("\n"):
        v = v.strip()
        if not v or "%)" in v or v.startswith(("Importing", "Postprocessing", "Blender ", "Info:")):
            continue
        print("  " + v, flush=True)
        uspeh = uspeh or v.startswith(konec)
    return uspeh


def main():
    for tok in (sys.stdout, sys.stderr):      # konzola Windows (cp1250) ne zna vseh znakov
        try:
            tok.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    argv =[a for a in sys.argv[1:] if not a.startswith("--")]
    if not argv:
        print(__doc__)
        return 2
    projekt = argv[0] if os.path.isdir(argv[0]) else os.path.join(MODELI, argv[0])
    # --recept=<ime>: drug recept v Skripte/ (od 2026-11-11: Malibu F ima svojo obliko za vsako izdajo,
    # zunanja_oblika_1.5.json s »sestav« Izdaje/Izdaja 5 (...)/Malibu F.FCStd)
    ime_recepta = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--recept=")), "zunanja_oblika.json")
    if not ime_recepta.lower().endswith(".json"):
        ime_recepta += ".json"
    recept_pot = os.path.join(projekt, "Skripte", ime_recepta)
    if not os.path.isfile(recept_pot):
        print("Ni recepta: %s" % recept_pot)
        return 2
    with open(recept_pot, encoding="utf-8") as f:
        recept = json.load(f)
    delovna = os.path.join(tempfile.gettempdir(), "zunanja-oblika", os.path.basename(projekt), os.path.splitext(ime_recepta)[0])
    os.makedirs(delovna, exist_ok=True)
    mreza = os.path.join(delovna, "mreza.npz")
    okolje = dict(os.environ, ZO_RECEPT=recept_pot, ZO_IZHOD=mreza, ZO_VHOD=mreza, PYTHONIOENCODING="utf-8")
    with open(recept_pot, "rb") as f:        # tudi sprememba recepta (barve, pragovi) pomeni novo različico
        okolje["ZO_RECEPT_ODTIS"] = hashlib.sha1(f.read()).hexdigest()[:16]
    okolje.pop("PYTHONHOME", None)
    okolje.pop("PYTHONPATH", None)

    print("1/2 izvoz iz %s" % os.path.join(projekt, recept["sestav"]), flush=True)
    if not pozeni([FREECADCMD, os.path.join(MAPA, "zunanja_izvoz.py")], okolje, "KONEC"):
        print("Izvoz ni uspel.")
        return 1
    with open(os.path.join(delovna, "mreza.json"), encoding="utf-8") as f:
        meta = json.load(f)

    koren = os.environ.get("SPLET_OBLIKOVANJE_MAPA") or os.path.join(MODELI, "Oblikovanje")
    vir_pot = os.path.join(koren, "Projekti", recept["projekt_oblikovanja"], "Ideje", recept["ideja"], "vir.json")
    try:
        with open(vir_pot, encoding="utf-8") as f:
            vir = json.load(f)
    except (OSError, ValueError):
        vir = {}
    enako = vir.get("odtis") == meta["odtis"] and vir.get("recept_odtis") == okolje["ZO_RECEPT_ODTIS"]
    if enako and "--vedno" not in sys.argv:
        print("ENAKO: Blender datoteka (%s %s) ustreza strojnemu modelu, odtis %s." % (recept["ideja"], vir.get("razlicica", ""), meta["odtis"]))
        return 0
    if "--preveri" in sys.argv:
        print("RAZLIČNO: zunanjost strojnega modela se je spremenila (odtis %s, v Blenderju %s %s)."
              % (meta["odtis"], vir.get("razlicica", "ni različice"), vir.get("odtis", "")))
        return 3

    blender = najdi_blender()
    if not blender:
        print("Blender ni nameščen.")
        return 1
    print("2/2 Blender: %s" % recept["ideja"], flush=True)
    if not pozeni([blender, "-b", "--factory-startup", "--python", os.path.join(MAPA, "zunanja_blender.py")], okolje, "KONEC"):
        print("Gradnja v Blenderju ni uspela.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
