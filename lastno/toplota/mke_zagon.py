# -*- coding: utf-8 -*-
"""Zagon toplotne MKE (CalculiX) na modelu iz model_mke.py — ločen proces brez okna:

  TOPLOTA_MKE_MAPA=<mapa Toplota/mke> .pixi/envs/default/Library/bin/FreeCADCmd.exe lastno/toplota/mke_zagon.py

Odpre <mapa>/<ime>.FCStd (iz model.json), zmreži Boolean Fragments z **Gmsh** (pip paket gmsh v pixi okolju; stari Netgen
pri pravih oblikah naprav ne da prostorninske mreže, novi Netgen 1.1 rabi zunanji Python), **sam zapiše vhod CalculiX**
(nabori elementov po težiščih: okna in naprave prek Shape.isInside, plašč zunaj notranjosti, sicer zrak; zunanje ploskve =
robni trikotniki mreže po straneh), požene ccx, prebere temperature iz .frd, izračuna temperature po območjih, nariše slike
(matplotlib), zapiše polje.json za 3D pregledovalnik in rezultat uvozi v dokument.
Enote kot pri FreeCAD-ovem zapisovalniku: mm, t, s, K -> moč mW, prevodnost mW/(mm K) (številsko = W/(m K)),
koeficient prestopa W/(m² K) = 1e-3 mW/(mm² K), gostota toka W/m² = 1e-3 mW/mm².
Izhod: <mapa>/rezultati.json, polje.json, slika_*.png, dnevnik.txt, stanje.json (napredek), ccx/ (vhod in izhod ccx).
"""
import json
import os
import re
import subprocess
import sys
import time
import traceback

import FreeCAD as App

# FreeCADCmd brez PYTHONHOME najde sistemski Python 3.11 in ne pixi okolja: dodaj site-packages pixi okolja (numpy, gmsh, matplotlib)
_SP = os.path.normpath(os.path.join(App.getHomePath(), "..", "Lib", "site-packages"))
if os.path.isdir(_SP) and _SP not in sys.path:
    sys.path.insert(0, _SP)

# mapo poda okoljska TOPLOTA_MKE_MAPA (FreeCADCmd vsak argument, ki ni skripta, poskusi odpreti kot datoteko)
MAPA = os.environ.get("TOPLOTA_MKE_MAPA") or (sys.argv[-1] if len(sys.argv) > 1 and os.path.isdir(sys.argv[-1]) else os.getcwd())
DNEVNIK = open(os.path.join(MAPA, "dnevnik.txt"), "w", encoding="utf-8")
STANJE = os.path.join(MAPA, "stanje.json")
SIGMA_MM = 5.670374419e-11   # mW/(mm² K⁴)
# lica tetraedra C3D4 v CalculiX-u: F1 = 1-2-3, F2 = 1-2-4, F3 = 2-3-4, F4 = 1-3-4 (indeksi vozlišč 0..3)
LICA_TET = [(0, 1, 2), (0, 1, 3), (1, 2, 3), (0, 2, 3)]


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
    """Prvi delujoči CalculiX: nastavitev FEM, pixi okolje, nameščeni FreeCAD, PATH (ccx -v izpiše »Version«, koda ni zanesljiva)."""
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
            if "Version" in (r.stdout + r.stderr):
                return k
        except Exception:  # noqa: BLE001
            pass
    return None


def _ascii(s):
    return re.sub(r"[^A-Za-z0-9_]", "_", s.replace("š", "s").replace("č", "c").replace("ž", "z").replace("Š", "S").replace("Č", "C"))


# ----------------------------------------------------------------------------- mreža (Gmsh)
def zmrezi(frag, mke):
    """Tetraedrska mreža Boolean Fragments z Gmsh. Vrne (xyz N×3, tets M×4 z indeksi 0..N-1)."""
    import numpy as np
    import gmsh
    brep = os.path.join(MAPA, "ccx", "deli.brep")
    os.makedirs(os.path.dirname(brep), exist_ok=True)
    frag.Shape.exportBrep(brep)
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("General.NumThreads", max(1, (os.cpu_count() or 2) - 1))
        gmsh.model.add("box")
        gmsh.model.occ.importShapes(brep)
        gmsh.model.occ.synchronize()
        najvec = float(mke.get("velikost_elementa_mm", 100))
        gmsh.option.setNumber("Mesh.MeshSizeMax", najvec)
        gmsh.option.setNumber("Mesh.MeshSizeMin", float(mke.get("najmanjsi_element_mm", najvec / 25)))
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 0)
        gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 1)
        gmsh.option.setNumber("Mesh.Algorithm", 6)      # Frontal-Delaunay (2D)
        gmsh.option.setNumber("Mesh.Algorithm3D", 10)   # HXT
        gmsh.option.setNumber("Mesh.Optimize", 1)
        try:
            gmsh.model.mesh.generate(3)
        except Exception as e:  # noqa: BLE001
            log("HXT ni uspel (%s), poskus z Delaunay" % str(e).strip().splitlines()[-1][:120])
            gmsh.model.mesh.clear()
            gmsh.option.setNumber("Mesh.Algorithm3D", 1)
            gmsh.model.mesh.generate(3)
        tags, coords, _p = gmsh.model.mesh.getNodes()
        tags = np.asarray(tags, dtype=np.int64)
        xyz_vse = np.asarray(coords, dtype=float).reshape(-1, 3)
        preslikava = np.full(int(tags.max()) + 1, -1, dtype=np.int64)
        preslikava[tags] = np.arange(len(tags))
        tipi, elem_tags, node_tags = gmsh.model.mesh.getElements(3)
        tets = []
        for tip, nt in zip(tipi, node_tags):
            if tip == 4:   # 4-vozliščni tetraeder
                tets.append(preslikava[np.asarray(nt, dtype=np.int64).reshape(-1, 4)])
        if not tets:
            raise RuntimeError("Gmsh ni dal tetraedrov")
        tets = np.concatenate(tets)
        # samo uporabljena vozlišča, preštevilčena
        upor = np.unique(tets)
        nov = np.full(len(xyz_vse), -1, dtype=np.int64)
        nov[upor] = np.arange(len(upor))
        return xyz_vse[upor], nov[tets]
    finally:
        gmsh.finalize()


def _prostornine(xyz, tets):
    import numpy as np
    a, b, c, d = (xyz[tets[:, i]] for i in range(4))
    return np.abs(np.einsum("ij,ij->i", b - a, np.cross(c - a, d - a))) / 6.0


# ----------------------------------------------------------------------------- območja in lica
def _v_okvirju(c, o):
    return o[0] <= c[0] <= o[3] and o[1] <= c[1] <= o[4] and o[2] <= c[2] <= o[5]


def obmocja_elementov(xyz, tets, model, doc):
    """Ime območja za vsak tetraeder po težišču: okna, plašč (zunaj notranjosti), naprave (okvir + oblika prek Shape.isInside),
    sicer zrak. Vrne slovar ime -> seznam indeksov tetraedrov."""
    import numpy as np
    from FreeCAD import Vector
    notr = doc.getObject(model["objekt_notranjost"]).Shape.Solids
    okna = [(o["ime"], o["okvir"], doc.getObject(o["objekt"]).Shape.Solids) for o in model.get("okna", [])]
    bloki = [(b["ime"], b["okvir"], doc.getObject(b["objekt"]).Shape.Solids if b.get("realna") else None) for b in model["bloki"]]
    N = model["notranji_mm"]

    def v_telesu(c, solidi):
        return any(s.isInside(c, 0.01, True) for s in solidi)
    centri = xyz[tets].mean(axis=1)
    po_obmocjih = {}
    for i, c in enumerate(centri):
        c = c.tolist()
        cv = Vector(*c)
        ime = None
        for ime_o, o, sol in okna:
            if _v_okvirju(c, o) and v_telesu(cv, sol):
                ime = ime_o
                break
        if ime is None and (not _v_okvirju(c, N) or not v_telesu(cv, notr)):
            ime = "Plašč"
        if ime is None:
            for ime_b, o, sol in bloki:
                if _v_okvirju(c, o) and (sol is None or v_telesu(cv, sol)):
                    ime = ime_b
                    break
        po_obmocjih.setdefault(ime or "Zrak", []).append(i)
    return po_obmocjih


def zunanje_ploskve(xyz, tets, model):
    """Robni trikotniki mreže (lice, ki pripada enemu tetraedru) = zunanja površina domene; po straneh glede na lego:
    streha, dno (preskoči), spredaj/zadaj/levo/desno (po smeri iz središča), okna spredaj. Vrne {stran: {lica: [(tet, F)], ...}}."""
    import numpy as np
    Z = model["zunanji_mm"]
    sc = model["scenarij"]
    T_amb = float(sc.get("T_zunaj_C", 35))
    T_sky = 0.0552 * (T_amb + 273.15) ** 1.5 - 273.15
    h = 5.7 + 3.8 * float(sc.get("veter_ms", 1.0))
    alpha, eps = float(model["alpha"]), float(model.get("eps", 0.9))
    T_bok = (T_sky + T_amb) / 2
    strani = {"streha": float(sc.get("G_streha", 0)), "spredaj": float(sc.get("G_spredaj", 0)), "zadaj": float(sc.get("G_zadaj", 0)),
              "levo": float(sc.get("G_bok", 0)), "desno": float(sc.get("G_bok", 0))}
    out = {k: {"lica": [], "G": g, "h": h, "T_sev": T_sky if k == "streha" else T_bok, "alpha": alpha, "eps": eps} for k, g in strani.items()}
    out["okna"] = {"lica": [], "G": strani["spredaj"], "h": h, "T_sev": T_bok, "alpha": float(model.get("alpha_steklo", 0.1)), "eps": 0.9}
    lica = np.concatenate([tets[:, list(l_)] for l_ in LICA_TET])            # 4M × 3
    kateri_tet = np.tile(np.arange(len(tets)), 4)
    katero_lice = np.repeat(np.arange(1, 5), len(tets))
    kljuci = np.sort(lica, axis=1)
    _u, prvi, stevci = np.unique(kljuci, axis=0, return_index=True, return_counts=True)
    rob = prvi[stevci == 1]
    okna = [o["okvir"] for o in model.get("okna", [])]
    cx, cy = (Z[0] + Z[3]) / 2, (Z[1] + Z[4]) / 2
    hw, hd = (Z[3] - Z[0]) / 2, (Z[4] - Z[1]) / 2
    centri = xyz[lica[rob]].mean(axis=1)
    for r, c in zip(rob, centri):
        par = (int(kateri_tet[r]) + 1, int(katero_lice[r]))
        if c[2] < Z[2] + 0.5:
            continue   # dno: adiabatno
        if c[2] > Z[5] - 0.5:
            out["streha"]["lica"].append(par)
        elif any(o[0] - 0.5 <= c[0] <= o[3] + 0.5 and o[2] - 0.5 <= c[2] <= o[5] + 0.5 and c[1] < cy for o in okna):
            out["okna"]["lica"].append(par)
        elif abs(c[1] - cy) / hd >= abs(c[0] - cx) / hw:
            out["spredaj" if c[1] < cy else "zadaj"]["lica"].append(par)
        else:
            out["levo" if c[0] < cx else "desno"]["lica"].append(par)
    return out


# ----------------------------------------------------------------------------- vhod in izhod CalculiX
def zapisi_inp(pot, xyz, tets, model, po_obmocjih, ploskve):
    sc = model["scenarij"]
    T_amb = float(sc.get("T_zunaj_C", 35)) + 273.15
    mat = model["materiali"]
    moci = {b["ime"]: b.get("W", 0) for b in model["bloki"]}
    V = _prostornine(xyz, tets)
    viri = []
    with open(pot, "w", encoding="ascii", errors="replace") as f:
        f.write("** Toplotna MKE boxa (lastno/toplota/mke_zagon.py, mreža Gmsh); enote mm, t, s, K, mW\n*NODE, NSET=Nall\n")
        for i, p in enumerate(xyz):
            f.write("%d, %.3f, %.3f, %.3f\n" % (i + 1, p[0], p[1], p[2]))
        f.write("*ELEMENT, TYPE=C3D4, ELSET=Eall\n")
        for i, t in enumerate(tets):
            f.write("%d, %d, %d, %d, %d\n" % (i + 1, t[0] + 1, t[1] + 1, t[2] + 1, t[3] + 1))
        for ime, els in po_obmocjih.items():
            f.write("*ELSET, ELSET=E_%s\n" % _ascii(ime))
            for i in range(0, len(els), 16):
                f.write(", ".join(str(e + 1) for e in els[i:i + 16]) + ",\n")
        f.write("*PHYSICAL CONSTANTS, ABSOLUTE ZERO=0, STEFAN BOLTZMANN=%g\n" % SIGMA_MM)
        for ime in po_obmocjih:
            m = mat.get(ime) or mat.get(model["skupina_obmocja"].get(ime, ""), {"k": 1.0})
            f.write("*MATERIAL, NAME=M_%s\n*CONDUCTIVITY\n%g\n*DENSITY\n%g\n*SPECIFIC HEAT\n%g\n" % (
                _ascii(ime), float(m["k"]), float(m.get("rho", 1000)) * 1e-12, float(m.get("cp", 1000)) * 1e6))
            f.write("*SOLID SECTION, ELSET=E_%s, MATERIAL=M_%s\n" % (_ascii(ime), _ascii(ime)))
        f.write("*INITIAL CONDITIONS, TYPE=TEMPERATURE\nNall, %g\n" % T_amb)
        f.write("*STEP\n*HEAT TRANSFER, STEADY STATE\n*DFLUX\n")
        for ime, els in po_obmocjih.items():
            P = float(moci.get(ime, 0) or 0)
            if P <= 0:
                continue   # klima (negativna moč) je spodaj kot konvektivni ponor, ne kot telesni ponor (ta ohladi blok pod ničlo)
            Vo = float(V[els].sum())
            if Vo <= 0:
                continue
            bf = P * 1000.0 / Vo
            viri.append((ime, P, Vo))
            for e in els:
                f.write("%d, BF, %g\n" % (e + 1, bf))
        for p in ploskve.values():
            if p["G"] > 0:
                for e, lice in p["lica"]:
                    f.write("%d, S%d, %g\n" % (e, lice, p["alpha"] * p["G"] * 1e-3))
        f.write("*FILM\n")
        for p in ploskve.values():
            for e, lice in p["lica"]:
                f.write("%d, F%d, %g, %g\n" % (e, lice, T_amb, p["h"] * 1e-3))
        # klima kot toplotni izmenjevalnik: na mejnih licih bloka klime konvekcija proti temperaturi izpiha; h tak, da pri ΔT 30 K
        # odvede nazivno moč (odvedena toplota se tako sama omeji, blok ne pade pod temperaturo izpiha)
        T_izpih = float(model.get("mke", {}).get("klima_izpih_C", 18)) + 273.15
        for ime, els in po_obmocjih.items():
            P = float(moci.get(ime, 0) or 0)
            if P >= 0:
                continue
            lica_k = _mejna_lica(tets, els)
            A = sum(_ploscina(xyz, tets[e - 1], lice) for e, lice in lica_k)   # mm²
            if A <= 0:
                continue
            h = -P / (A * 1e-6) / 30.0   # W/(m² K)
            viri.append((ime + " (izmenjevalnik h %.0f W/m2K, izpih %.0f C)" % (h, T_izpih - 273.15), P, A))
            for e, lice in lica_k:
                f.write("%d, F%d, %g, %g\n" % (e, lice, T_izpih, h * 1e-3))
        f.write("*RADIATE\n")
        for p in ploskve.values():
            for e, lice in p["lica"]:
                f.write("%d, R%d, %g, %g\n" % (e, lice, p["T_sev"] + 273.15, p["eps"]))
        f.write("*NODE FILE\nNT\n*END STEP\n")
    return viri


def _mejna_lica(tets, els):
    """(element 1..M, lice 1..4) na meji območja els (lice, ki ga ima en sam tetraeder območja)."""
    import numpy as np
    tet = tets[els]
    lica = np.concatenate([tet[:, list(l_)] for l_ in LICA_TET])
    kateri = np.tile(np.asarray(els), 4)
    katero = np.repeat(np.arange(1, 5), len(tet))
    kljuci = np.sort(lica, axis=1)
    _u, prvi, stevci = np.unique(kljuci, axis=0, return_index=True, return_counts=True)
    rob = prvi[stevci == 1]
    return [(int(kateri[r]) + 1, int(katero[r])) for r in rob]


def _ploscina(xyz, tet, lice):
    import numpy as np
    a, b, c = (xyz[tet[i]] for i in LICA_TET[lice - 1])
    return float(np.linalg.norm(np.cross(b - a, c - a)) / 2.0)


def preberi_frd(pot):
    """Temperature vozlišč iz .frd (blok NDTEMP) -> slovar id -> K."""
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


# ----------------------------------------------------------------------------- slike in polje
def slike(xyz, Tc, model, najvec):
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    Z = model["zunanji_mm"]
    out = []
    fig, ax = plt.subplots(1, 3, figsize=(13, 5.2))
    pogledi = [("spredaj (Y min)", xyz[:, 1] < Z[1] + 0.5, 0, 2, "X", "Z"), ("desno (X max)", xyz[:, 0] > Z[3] - 0.5, 1, 2, "Y", "Z"),
               ("streha (Z max)", xyz[:, 2] > Z[5] - 0.5, 0, 1, "X", "Y")]
    vmin, vmax = float(np.percentile(Tc, 1)), float(Tc.max())
    for a, (naslov, m, i, j, lx, ly) in zip(ax, pogledi):
        if not m.any():
            continue
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
    m = np.abs(xyz[:, 0] - xs) < max(10.0, najvec / 2)
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


def izvozi_polje(xyz, Tc, tets, model, po_obmocjih):
    """polje.json: vozlišča, temperature, po območjih tetraedri in robni trikotniki (three.js v brskalniku)."""
    import numpy as np
    obmocja = []
    for ime, els in sorted(po_obmocjih.items()):
        tet = tets[els]
        lica = np.concatenate([tet[:, list(l_)] for l_ in LICA_TET])
        kljuci = np.sort(lica, axis=1)
        _u, prvi, stevci = np.unique(kljuci, axis=0, return_index=True, return_counts=True)
        rob = lica[prvi[stevci == 1]]
        obmocja.append({"ime": ime, "skupina": model["skupina_obmocja"].get(ime, ime), "tetre": tet.ravel().tolist(),
                        "trikotniki": rob.ravel().tolist(), "W": next((b["W"] for b in model["bloki"] if b["ime"] == ime), 0)})
    polje = {"vozlisca": np.round(xyz, 1).ravel().tolist(), "T": np.round(Tc, 2).tolist(), "obmocja": obmocja,
             "zunanji_mm": model["zunanji_mm"], "scenarij": model["scenarij"], "cas": time.strftime("%Y-%m-%d %H:%M")}
    with open(os.path.join(MAPA, "polje.json"), "w", encoding="utf-8") as f:
        json.dump(polje, f, ensure_ascii=False, separators=(",", ":"))


# ----------------------------------------------------------------------------- glavni potek
def main():
    import numpy as np
    zacetek = time.time()
    with open(os.path.join(MAPA, "model.json"), encoding="utf-8") as f:
        model = json.load(f)
    mke = model.get("mke", {})
    stanje("odpiram")
    doc = App.openDocument(model["pot"])
    frag = doc.getObject("Deli")
    stanje("mreza")
    log("mreženje z Gmsh (največ %g mm) ..." % float(mke.get("velikost_elementa_mm", 100)))
    xyz, tets = zmrezi(frag, mke)
    log("mreža: %d vozlišč, %d tetraedrov (%.0f s)" % (len(xyz), len(tets), time.time() - zacetek))
    stanje("vhod", vozlisc=len(xyz))
    po_obmocjih = obmocja_elementov(xyz, tets, model, doc)
    log("območja: " + ", ".join("%s %d" % (k, len(v)) for k, v in sorted(po_obmocjih.items())))
    ploskve = zunanje_ploskve(xyz, tets, model)
    log("lica: " + ", ".join("%s %d" % (k, len(v["lica"])) for k, v in ploskve.items()))
    mapa_ccx = os.path.join(MAPA, "ccx")
    for ime in os.listdir(mapa_ccx):
        if ime.startswith("box."):
            try:
                os.remove(os.path.join(mapa_ccx, ime))
            except OSError:
                pass
    inp = os.path.join(mapa_ccx, "box.inp")
    viri = zapisi_inp(inp, xyz, tets, model, po_obmocjih, ploskve)
    log("viri: " + ", ".join("%s %.0f W (%.1f %s)" % (i, P, Vo / 1e6 if P > 0 else Vo / 1e4, "l" if P > 0 else "dm2") for i, P, Vo in viri))
    ccx = _najdi_ccx()
    if not ccx:
        raise RuntimeError("CalculiX (ccx.exe) ni najden: nastavi ga v nastavitvah FEM ali namesti FreeCAD 1.1.")
    log("inp zapisan (%.0f s), ccx: %s" % (time.time() - zacetek, ccx))
    stanje("ccx", vozlisc=len(xyz))
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
    Tc = np.array([T.get(i + 1, 0.0) for i in range(len(xyz))]) - 273.15
    po_telesih = []
    for ime, els in sorted(po_obmocjih.items()):
        vals = Tc[np.unique(tets[els])]
        po_telesih.append({"telo": ime, "skupina": model["skupina_obmocja"].get(ime, ime), "min": round(float(vals.min()), 1),
                           "povp": round(float(vals.mean()), 1), "max": round(float(vals.max()), 1), "elementov": len(els)})
    po_skupinah = {}
    for p in po_telesih:
        g = po_skupinah.setdefault(p["skupina"], {"skupina": p["skupina"], "min": 1e9, "max": -1e9, "povp": []})
        g["min"] = min(g["min"], p["min"]); g["max"] = max(g["max"], p["max"]); g["povp"].append(p["povp"])
    for g in po_skupinah.values():
        g["povp"] = round(sum(g["povp"]) / len(g["povp"]), 1)
    try:
        seznam_slik = slike(xyz, Tc, model, float(mke.get("velikost_elementa_mm", 100)))
    except Exception:  # noqa: BLE001
        seznam_slik = []
        log("slika ni uspela: " + traceback.format_exc())
    izhod = {"cas": time.strftime("%Y-%m-%d %H:%M"), "trajanje_s": round(time.time() - zacetek), "vozlisc": len(xyz), "elementov": len(tets),
             "T_min_C": round(float(Tc.min()), 1), "T_max_C": round(float(Tc.max()), 1), "po_skupinah": list(po_skupinah.values()),
             "po_telesih": po_telesih, "slike": seznam_slik, "scenarij": model["scenarij"], "viri_W": model["viri_W"], "ccx": ccx, "mreza": "gmsh"}
    with open(os.path.join(MAPA, "rezultati.json"), "w", encoding="utf-8") as f:
        json.dump(izhod, f, ensure_ascii=False, indent=1)
    try:
        izvozi_polje(xyz, Tc, tets, model, po_obmocjih)
        log("polje.json za 3D pregledovalnik zapisano")
    except Exception:  # noqa: BLE001
        log("polje.json ni uspelo: " + traceback.format_exc().strip().splitlines()[-1])
    try:
        from feminout import importCcxFrdResults
        analiza = [o for o in doc.Objects if o.TypeId == "Fem::FemAnalysis"][0]
        for o in list(doc.Objects):
            if o.TypeId == "Fem::FemResultObjectPython":
                doc.removeObject(o.Name)
        importCcxFrdResults.importFrd(frd, analiza, "CalculiX_")
        doc.save()
    except Exception:  # noqa: BLE001
        log("uvoz rezultata v dokument ni uspel: " + traceback.format_exc().strip().splitlines()[-1])
    stanje("koncano", trajanje_s=izhod["trajanje_s"])
    log("končano: T %.1f … %.1f °C, %d s" % (izhod["T_min_C"], izhod["T_max_C"], izhod["trajanje_s"]))


# FreeCADCmd skripto izvede z __name__ != "__main__", zato brez varovala
try:
    main()
except Exception:  # noqa: BLE001
    log(traceback.format_exc())
    stanje("napaka", napaka=traceback.format_exc().strip().splitlines()[-1])
    sys.exit(1)
