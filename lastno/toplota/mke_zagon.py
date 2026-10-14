# -*- coding: utf-8 -*-
"""Zagon toplotne MKE (CalculiX) na modelu iz model_mke.py — ločen proces brez okna:

  TOPLOTA_MKE_MAPA=<mapa Toplota/mke> .pixi/envs/default/Library/bin/FreeCADCmd.exe lastno/toplota/mke_zagon.py

Odpre <mapa>/<ime>.FCStd (iz model.json), zmreži (stari Netgen), **sam zapiše vhodno datoteko CalculiX** (nabore
elementov določi po težiščih elementov iz okvirjev blokov v model.json — zapisovalnik FreeCAD-a nabore po telesih išče
prek vozlišč, kar je pri tej mreži počasno in nepopolno), požene ccx, prebere temperature iz .frd, izračuna temperature
po območjih (min/povprečje/max), nariše slike (matplotlib) in rezultate uvozi v dokument (za ogled v FreeCAD-u).
Enote kot pri FreeCAD-ovem zapisovalniku: mm, t, s, K -> moč mW, prevodnost mW/(mm K) (številsko = W/(m K)),
koeficient prestopa W/(m² K) = 1e-3 mW/(mm² K), gostota toka W/m² = 1e-3 mW/mm².
Izhod: <mapa>/rezultati.json, slika_*.png, dnevnik.txt, stanje.json (napredek), ccx/ (vhod in izhod ccx).
"""
import json
import os
import re
import subprocess
import sys
import time
import traceback

import FreeCAD as App

# FreeCADCmd brez PYTHONHOME najde sistemski Python 3.11 in ne pixi okolja: dodaj site-packages pixi okolja (numpy, matplotlib)
_SP = os.path.normpath(os.path.join(App.getHomePath(), "..", "Lib", "site-packages"))
if os.path.isdir(_SP) and _SP not in sys.path:
    sys.path.insert(0, _SP)

# mapo poda okoljska TOPLOTA_MKE_MAPA (FreeCADCmd vsak argument, ki ni skripta, poskusi odpreti kot datoteko)
MAPA = os.environ.get("TOPLOTA_MKE_MAPA") or (sys.argv[-1] if len(sys.argv) > 1 and os.path.isdir(sys.argv[-1]) else os.getcwd())
DNEVNIK = open(os.path.join(MAPA, "dnevnik.txt"), "w", encoding="utf-8")
STANJE = os.path.join(MAPA, "stanje.json")
SIGMA_MM = 5.670374419e-11   # mW/(mm² K⁴)


def log(s):
    print(s)
    DNEVNIK.write("%s %s\n" % (time.strftime("%H:%M:%S"), s))
    DNEVNIK.flush()


def stanje(faza, **ostalo):
    d = {"faza": faza, "cas": time.time()}
    d.update(ostalo)
    with open(STANJE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)


def _najdi_ccx():
    """Prvi delujoči CalculiX: nastavitev FEM, pixi okolje (ccx.exe tam brez libarpack.dll pade s kodo 127), nameščeni FreeCAD, PATH."""
    import glob
    import shutil
    kandidati = [App.ParamGet("User parameter:BaseApp/Preferences/Mod/Fem/Ccx").GetString("ccxBinaryPath", ""),
                 os.path.join(App.getHomePath(), "bin", "ccx.exe")]
    kandidati += sorted(glob.glob(os.path.join("C:\\", "Program Files", "FreeCAD*", "bin", "ccx.exe")), reverse=True)
    kandidati.append(shutil.which("ccx") or "")
    for k in kandidati:
        if not k or not os.path.isfile(k):
            continue
        try:
            r = subprocess.run([k, "-v"], capture_output=True, text=True, timeout=20, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if "Version" in (r.stdout + r.stderr):   # ccx -v vrne izpis različice, izhodna koda ni zanesljiva
                return k
        except Exception:  # noqa: BLE001
            pass
    return None


def _v_okvirju(c, o):
    return o[0] <= c[0] <= o[3] and o[1] <= c[1] <= o[4] and o[2] <= c[2] <= o[5]


def obmocja_elementov(fm, model):
    """Ime območja za vsak prostorninski element po težišču: okna, bloki, plašč (zunaj notranjosti), sicer zrak."""
    N = model["notranji_mm"]
    okna = [(o["ime"], o["okvir"]) for o in model.get("okna", [])]
    bloki = [(b["ime"], b["okvir"]) for b in model["bloki"]]
    vozl = fm.Nodes
    po_obmocjih = {}
    for e in fm.Volumes:
        ns = fm.getElementNodes(e)
        c = [sum(vozl[n].x for n in ns) / len(ns), sum(vozl[n].y for n in ns) / len(ns), sum(vozl[n].z for n in ns) / len(ns)]
        ime = None
        for ime_o, o in okna:
            if _v_okvirju(c, o):
                ime = ime_o
                break
        if ime is None and not _v_okvirju(c, N):
            ime = "Plašč"
        if ime is None:
            for ime_b, o in bloki:
                if _v_okvirju(c, o):
                    ime = ime_b
                    break
        po_obmocjih.setdefault(ime or "Zrak", []).append(e)
    return po_obmocjih


def _ascii(s):
    return re.sub(r"[^A-Za-z0-9_]", "_", s.replace("š", "s").replace("č", "c").replace("ž", "z").replace("Š", "S").replace("Č", "C"))


def _prostornina(fm, vozl, e):
    ns = fm.getElementNodes(e)
    if len(ns) < 4:
        return 0.0
    a, b, c, d = (vozl[n] for n in ns[:4])
    return abs((b - a).dot((c - a).cross(d - a))) / 6.0


def zapisi_inp(pot, fm, model, po_obmocjih, ploskve):
    """Vhod CalculiX: mreža (*INCLUDE), nabori po območjih, materiali, viri, sonce, konvekcija, sevanje; stacionarni prenos toplote."""
    sc = model["scenarij"]
    T_amb = float(sc.get("T_zunaj_C", 35)) + 273.15
    mat = model["materiali"]
    moci = {b["ime"]: b.get("W", 0) for b in model["bloki"]}   # moč po blokih (model_mke: moč skupine po prostornini)
    mesh_pot = os.path.join(os.path.dirname(pot), "mreza_vozlisca.inp")
    fm.writeABAQUS(mesh_pot, 1, False)
    vozl = fm.Nodes
    with open(pot, "w", encoding="ascii", errors="replace") as f:
        f.write("** Toplotna MKE boxa (lastno/toplota/mke_zagon.py); enote mm, t, s, K, mW\n")
        f.write("*INCLUDE, INPUT=%s\n" % os.path.basename(mesh_pot))
        for ime, els in po_obmocjih.items():
            f.write("*ELSET, ELSET=E_%s\n" % _ascii(ime))
            for i in range(0, len(els), 16):
                f.write(", ".join(str(e) for e in els[i:i + 16]) + ",\n")
        f.write("*PHYSICAL CONSTANTS, ABSOLUTE ZERO=0, STEFAN BOLTZMANN=%g\n" % SIGMA_MM)
        for ime in po_obmocjih:
            m = mat.get(ime) or mat.get(model["skupina_obmocja"].get(ime, ""), {"k": 1.0})
            f.write("*MATERIAL, NAME=M_%s\n*CONDUCTIVITY\n%g\n*DENSITY\n%g\n*SPECIFIC HEAT\n%g\n" % (
                _ascii(ime), float(m["k"]), float(m.get("rho", 1000)) * 1e-12, float(m.get("cp", 1000)) * 1e6))
            f.write("*SOLID SECTION, ELSET=E_%s, MATERIAL=M_%s\n" % (_ascii(ime), _ascii(ime)))
        f.write("*INITIAL CONDITIONS, TYPE=TEMPERATURE\nNall, %g\n" % T_amb)
        f.write("*STEP\n*HEAT TRANSFER, STEADY STATE\n*DFLUX\n")
        viri = []
        for ime, els in po_obmocjih.items():
            P = float(moci.get(ime, 0) or 0)
            if P == 0:
                continue
            V = sum(_prostornina(fm, vozl, e) for e in els)
            if V <= 0:
                continue
            bf = P * 1000.0 / V   # mW / mm³
            viri.append((ime, P, V))
            for e in els:
                f.write("%d, BF, %g\n" % (e, bf))
        for p in ploskve.values():
            if p["G"] > 0:
                for e, lice in p["lica"]:
                    f.write("%d, S%d, %g\n" % (e, lice, p["alpha"] * p["G"] * 1e-3))
        f.write("*FILM\n")
        for p in ploskve.values():
            for e, lice in p["lica"]:
                f.write("%d, F%d, %g, %g\n" % (e, lice, T_amb, p["h"] * 1e-3))
        f.write("*RADIATE\n")
        for p in ploskve.values():
            for e, lice in p["lica"]:
                f.write("%d, R%d, %g, %g\n" % (e, lice, p["T_sev"] + 273.15, p["eps"]))
        f.write("*NODE FILE\nNT\n*END STEP\n")
    return viri


def zunanje_ploskve(fm, frag, model):
    """Elementi in lica na zunanjih ploskvah po straneh (streha, spredaj, zadaj, levo, desno) + okna spredaj."""
    Z = model["zunanji_mm"]
    sc = model["scenarij"]
    T_amb = float(sc.get("T_zunaj_C", 35))
    T_sky = 0.0552 * (T_amb + 273.15) ** 1.5 - 273.15
    h = 5.7 + 3.8 * float(sc.get("veter_ms", 1.0))
    alpha, eps = float(model["alpha"]), float(model.get("eps", 0.9))
    T_bok = (T_sky + T_amb) / 2
    strani = {"streha": ("z", Z[5], float(sc.get("G_streha", 0)), T_sky), "spredaj": ("y", Z[1], float(sc.get("G_spredaj", 0)), T_bok),
              "zadaj": ("y", Z[4], float(sc.get("G_zadaj", 0)), T_bok), "levo": ("x", Z[0], float(sc.get("G_bok", 0)), T_bok),
              "desno": ("x", Z[3], float(sc.get("G_bok", 0)), T_bok)}
    okna = [o["okvir"] for o in model.get("okna", [])]
    out = {k: {"lica": [], "G": v[2], "h": h, "T_sev": v[3], "alpha": alpha, "eps": eps} for k, v in strani.items()}
    out["okna"] = {"lica": [], "G": float(sc.get("G_spredaj", 0)), "h": h, "T_sev": T_bok, "alpha": float(model.get("alpha_steklo", 0.1)), "eps": 0.9}
    for face in frag.Shape.Faces:
        c = face.CenterOfMass
        for ime_s, (os_, vred, _g, _t) in strani.items():
            if abs(getattr(c, os_) - vred) < 0.01:
                lica = list(fm.getccxVolumesByFace(face))
                if ime_s == "spredaj" and any(o[0] - 0.1 <= c.x <= o[3] + 0.1 and o[2] - 0.1 <= c.z <= o[5] + 0.1 for o in okna):
                    out["okna"]["lica"] += lica
                else:
                    out[ime_s]["lica"] += lica
                break
    return out


def preberi_frd(pot):
    """Temperature vozlišč iz .frd (blok NDTEMP)."""
    T = {}
    v_bloku = False
    with open(pot, encoding="ascii", errors="replace") as f:
        for vrstica in f:
            if vrstica.startswith(" -4") and "NDTEMP" in vrstica:
                v_bloku = True
                continue
            if v_bloku:
                if vrstica.startswith(" -3"):
                    break
                if vrstica.startswith(" -1"):
                    T[int(vrstica[3:13])] = float(vrstica[13:25])
    return T


def slike(fm, T, model, mreza):
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    vozl = fm.Nodes
    ids = list(T)
    xyz = np.array([[vozl[n].x, vozl[n].y, vozl[n].z] for n in ids])
    Tc = np.array([T[n] for n in ids]) - 273.15
    Z = model["zunanji_mm"]
    out = []
    fig, ax = plt.subplots(1, 3, figsize=(13, 5.2))
    pogledi = [("spredaj (Y min)", xyz[:, 1] < Z[1] + 0.5, 0, 2, "X", "Z"), ("desno (X max)", xyz[:, 0] > Z[3] - 0.5, 1, 2, "Y", "Z"),
               ("streha (Z max)", xyz[:, 2] > Z[5] - 0.5, 0, 1, "X", "Y")]
    vmin, vmax = float(np.percentile(Tc, 1)), float(Tc.max())
    for a, (naslov, m, i, j, lx, ly) in zip(ax, pogledi):
        sc = a.scatter(xyz[m, i], xyz[m, j], c=Tc[m], s=9, cmap="inferno", vmin=vmin, vmax=vmax)
        a.set_title("%s: %.1f–%.1f °C" % (naslov, Tc[m].min(), Tc[m].max()), fontsize=10)
        a.set_aspect("equal"); a.set_xlabel(lx); a.set_ylabel(ly)
    fig.colorbar(sc, ax=ax, label="°C", shrink=0.8)
    fig.suptitle("Plašč, stacionarno — zunaj %.1f °C, sonce streha %g W/m², spredaj %g W/m²" % (
        model["scenarij"].get("T_zunaj_C", 0), model["scenarij"].get("G_streha", 0), model["scenarij"].get("G_spredaj", 0)))
    pot = os.path.join(MAPA, "slika_plasc.png")
    fig.savefig(pot, dpi=100); plt.close(fig)
    out.append(os.path.basename(pot))
    xs = (Z[0] + Z[3]) / 2
    m = np.abs(xyz[:, 0] - xs) < max(10.0, mreza.MaxSize / 2)
    fig, a = plt.subplots(figsize=(6, 9))
    sc = a.scatter(xyz[m, 1], xyz[m, 2], c=Tc[m], s=12, cmap="inferno")
    a.set_aspect("equal"); a.set_xlabel("Y"); a.set_ylabel("Z"); a.set_title("prerez na sredini X: %.1f–%.1f °C" % (Tc[m].min(), Tc[m].max()))
    for b in model["bloki"]:
        o = b["okvir"]
        a.add_patch(plt.Rectangle((o[1], o[2]), o[4] - o[1], o[5] - o[2], fill=False, ec="#4aa3ff", lw=0.8))
        a.text(o[1], o[5], b["ime"], fontsize=6, color="#4aa3ff", va="bottom")
    fig.colorbar(sc, label="°C")
    pot = os.path.join(MAPA, "slika_prerez.png")
    fig.tight_layout(); fig.savefig(pot, dpi=100); plt.close(fig)
    out.append(os.path.basename(pot))
    return out


def main():
    import numpy as np
    zacetek = time.time()
    with open(os.path.join(MAPA, "model.json"), encoding="utf-8") as f:
        model = json.load(f)
    stanje("odpiram")
    doc = App.openDocument(model["pot"])
    frag = doc.getObject("Deli")
    mreza = [o for o in doc.Objects if o.TypeId in ("Fem::FemMeshShapeNetgenObject", "Fem::FemMeshShapeBaseObjectPython")][0]
    stanje("mreza")
    log("mreženje (MaxSize %g mm, %s) ..." % (mreza.MaxSize, mreza.Fineness))
    mreza.touch()
    doc.recompute()
    fm = mreza.FemMesh
    log("mreža: %d vozlišč, %d prostorninskih elementov (%.0f s)" % (fm.NodeCount, fm.VolumeCount, time.time() - zacetek))
    stanje("vhod", vozlisc=fm.NodeCount)
    po_obmocjih = obmocja_elementov(fm, model)
    log("območja: " + ", ".join("%s %d" % (k, len(v)) for k, v in sorted(po_obmocjih.items())))
    ploskve = zunanje_ploskve(fm, frag, model)
    log("lica: " + ", ".join("%s %d" % (k, len(v["lica"])) for k, v in ploskve.items()))
    mapa_ccx = os.path.join(MAPA, "ccx")
    os.makedirs(mapa_ccx, exist_ok=True)
    for ime in os.listdir(mapa_ccx):
        try:
            os.remove(os.path.join(mapa_ccx, ime))
        except OSError:
            pass
    inp = os.path.join(mapa_ccx, "box.inp")
    viri = zapisi_inp(inp, fm, model, po_obmocjih, ploskve)
    log("viri: " + ", ".join("%s %.0f W v %.1f l" % (i, P, V / 1e6) for i, P, V in viri))
    ccx = _najdi_ccx()
    if not ccx:
        raise RuntimeError("CalculiX (ccx.exe) ni najden: nastavi ga v nastavitvah FEM ali namesti FreeCAD 1.1.")
    log("inp zapisan (%.0f s), ccx: %s" % (time.time() - zacetek, ccx))
    stanje("ccx", vozlisc=fm.NodeCount)
    t0 = time.time()
    okolje = dict(os.environ)
    okolje.setdefault("OMP_NUM_THREADS", str(max(1, (os.cpu_count() or 2) - 1)))
    r = subprocess.run([ccx, "-i", "box"], cwd=mapa_ccx, capture_output=True, text=True, env=okolje, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    with open(os.path.join(mapa_ccx, "ccx_izpis.txt"), "w", encoding="utf-8") as f:
        f.write(r.stdout + "\n" + r.stderr)
    log("ccx končan (%.0f s, koda %d)" % (time.time() - t0, r.returncode))
    frd = os.path.join(mapa_ccx, "box.frd")
    if not os.path.isfile(frd):
        napake = [v.strip() for v in r.stdout.splitlines() if "ERROR" in v][:3]
        raise RuntimeError("ccx ni dal rezultatov: " + ("; ".join(napake) or "glej ccx/ccx_izpis.txt"))
    stanje("rezultati")
    T = preberi_frd(frd)
    if not T:
        raise RuntimeError("v .frd ni temperatur (NDTEMP)")
    po_telesih = []
    for ime, els in sorted(po_obmocjih.items()):
        ns = set()
        for e in els:
            ns.update(fm.getElementNodes(e))
        vals = np.array([T[n] for n in ns if n in T]) - 273.15
        if len(vals):
            po_telesih.append({"telo": ime, "skupina": model["skupina_obmocja"].get(ime, ime), "min": round(float(vals.min()), 1),
                               "povp": round(float(vals.mean()), 1), "max": round(float(vals.max()), 1), "elementov": len(els)})
    po_skupinah = {}
    for p in po_telesih:
        g = po_skupinah.setdefault(p["skupina"], {"skupina": p["skupina"], "min": 1e9, "max": -1e9, "povp": []})
        g["min"] = min(g["min"], p["min"]); g["max"] = max(g["max"], p["max"]); g["povp"].append(p["povp"])
    for g in po_skupinah.values():
        g["povp"] = round(sum(g["povp"]) / len(g["povp"]), 1)
    try:
        seznam_slik = slike(fm, T, model, mreza)
    except Exception:  # noqa: BLE001
        seznam_slik = []
        log("slika ni uspela: " + traceback.format_exc())
    Tv = np.array(list(T.values())) - 273.15
    izhod = {"cas": time.strftime("%Y-%m-%d %H:%M"), "trajanje_s": round(time.time() - zacetek), "vozlisc": fm.NodeCount,
             "elementov": fm.VolumeCount, "T_min_C": round(float(Tv.min()), 1), "T_max_C": round(float(Tv.max()), 1),
             "po_skupinah": list(po_skupinah.values()), "po_telesih": po_telesih, "slike": seznam_slik, "scenarij": model["scenarij"],
             "viri_W": model["viri_W"], "ccx": ccx}
    with open(os.path.join(MAPA, "rezultati.json"), "w", encoding="utf-8") as f:
        json.dump(izhod, f, ensure_ascii=False, indent=1)
    # rezultat v dokument (ogled v FreeCAD-u: objekt CalculiX_Results s temperaturo)
    try:
        from feminout import importCcxFrdResults
        analiza = [o for o in doc.Objects if o.TypeId == "Fem::FemAnalysis"][0]
        for o in list(doc.Objects):
            if o.TypeId == "Fem::FemResultObjectPython":
                doc.removeObject(o.Name)
        importCcxFrdResults.importFrd(frd, analiza, "CalculiX_")
    except Exception:  # noqa: BLE001
        log("uvoz rezultata v dokument ni uspel: " + traceback.format_exc().strip().splitlines()[-1])
    doc.save()
    stanje("koncano", trajanje_s=izhod["trajanje_s"])
    log("končano: T %.1f … %.1f °C, %d s" % (izhod["T_min_C"], izhod["T_max_C"], izhod["trajanje_s"]))


# FreeCADCmd skripto izvede z __name__ != "__main__", zato brez varovala
try:
    main()
except Exception:  # noqa: BLE001
    log(traceback.format_exc())
    stanje("napaka", napaka=traceback.format_exc().strip().splitlines()[-1])
    sys.exit(1)
