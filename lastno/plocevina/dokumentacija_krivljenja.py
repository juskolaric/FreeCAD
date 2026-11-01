# -*- coding: utf-8 -*-
"""List za krivilca za vsak kos iz pločevine (PDF, A4 ležeče) + skupni PDF in CSV zaporedij.

Vhod: upogibi.json (izvlecek_upogibov.py, FreeCADCmd), mapa »DXF oznaceni« (oznaci_dxf.py: koda, gravura), seznam kosov (CSV).
List: glava (koda, ime, material, T, R, K, količina, razvita mera, mera upognjenega), razgrnitev z upogibnimi črtami U1…Un
(kot, smer gor/dol), slika upognjenega kosa (STL, lasten rasterizator), tabela upogibov in zaporedje korakov z orodjem,
prislonom in opozorili (pravila: raziskava/plocevina.md §3b).

Sistemski Python (numpy, matplotlib, PIL, ezdxf, shapely):
    python dokumentacija_krivljenja.py "<Razrez mapa>" [--izhod "<mapa>"]
Odločitev 2026-10-30 (Photobox Slim A).
"""
import argparse, csv, json, math, os, re, sys, unicodedata, datetime

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Polygon as MplPoly
from PIL import Image

TU = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TU); sys.path.insert(0, os.path.join(TU, ".."))
import plocevina_materiali as pm   # noqa: E402
import slika_stl                   # noqa: E402

plt.rcParams["font.family"] = "DejaVu Sans"; plt.rcParams["font.size"] = 8

# Amada AFH 2024: sila zračnega krivljenja kN/m (str. 74) za matrico V pri debelini T; jeklo; Al 5754 ≈ 0,5 ×, nerjavno ≈ 1,5 ×
SILA_KN_M = {(2, 12): 220, (1.5, 10): 150, (3, 18): 330, (3, 20): 300, (4, 32): 400, (8, 63): 800}


def ascii_velike(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().upper()


def material_iz_mape(mapa):
    m = mapa.lower()
    if m.startswith("al"):
        return "Al 5754-H22"
    if "inox" in m or "nerj" in m:
        return "Nerjavno 1.4301"
    return "Jeklo S235 / DC01"


def orodje(material, T, upogibi, kos):
    """Klin, matrica, sila/m za kos (vsi upogibi so enaki kot/R, zato eno orodje)."""
    p = pm.parametri(material, T)
    V = p["V"]
    povratni = any(u["globina"] > 0 for u in upogibi)
    globok = max([u["krak_razgrnjen"] for u in upogibi] or [0]) > 100
    if T <= 3.0:
        klin = "88° R0,6 · Amada 804 (standard, H120)"
    elif T <= 4.5:
        klin = "88° R3 · Amada 804 R3 (H120)"
    else:
        klin = "60° R5 · Amada 803/603 (1000 kN/m)"
    if povratni:
        klin = klin.replace("804 (standard, H120)", "847 labodji vrat (H120, 500 kN/m)").replace("804 R3", "847 R3 labodji vrat")
    if globok:
        klin += " — krak > 100 mm: klin H160 ali ozka matrica, preveri doseg"
    veliki = sorted(set(u["polmer"] for u in upogibi if u["polmer"] > 3 * T))
    if veliki:
        klin += "; upogibi z velikim R " + ", ".join(f"{r:g}" for r in veliki) + ": zaokrožitveni vložek R ali stopenjsko krivljenje"
    jeklo = material.startswith("Jeklo")
    kn_m = SILA_KN_M.get((T, V))
    if kn_m is None:
        kn_m = 650 * T * T / V * 1.33 * 10   # približek
    if material.startswith("Al"):
        kn_m *= 0.5
    elif material.startswith("Nerj"):
        kn_m *= 1.5
    return dict(V=V, klin=klin, kn_m=round(kn_m), R=p["R"], krak_min=p["krak"], p=p)


def zaporedje(upogibi):
    """Vrstni red: najgloblji (povratni) kraki prej, krajši kraki prej, upogibi iste smeri skupaj."""
    def kljuc(u):
        return (-u["globina"], u["krak_razgrnjen"], 0 if u["smer"] == "dol" else 1, u["dolzina"])
    return sorted(upogibi, key=kljuc)


def zunanja_mera(u, T, K, kot):
    """Zunanja mera kraka po krivljenju za 90°: razgrnjen krak − BA/2 + R + T (BA = kot·(R + K·T))."""
    R = u["polmer"]; ba = math.radians(kot) * (R + K * T)
    return u["krak_razgrnjen"] - ba / 2 + R + T if abs(kot - 90) < 1 else None


def poravnaj_dxf(dxf_pot, zanke):
    """Gravura iz DXF (sloj GRAVURA) prenesena v okvir razgrnitve: ujemanje po okviru (premik, po potrebi zrcaljenje)."""
    try:
        import ezdxf
    except ImportError:
        return [], None
    if not os.path.exists(dxf_pot):
        return [], None
    doc = ezdxf.readfile(dxf_pot); msp = doc.modelspace()
    xs = []; ys = []
    for e in msp:
        if e.dxf.layer == "GRAVURA":
            continue
        t = e.dxftype()
        if t == "LINE":
            xs += [e.dxf.start.x, e.dxf.end.x]; ys += [e.dxf.start.y, e.dxf.end.y]
        elif t == "CIRCLE" or t == "ARC":
            c, r = e.dxf.center, e.dxf.radius; xs += [c.x - r, c.x + r]; ys += [c.y - r, c.y + r]
    if not xs:
        return [], None
    zx = [p[0] for z in zanke for p in z]; zy = [p[1] for z in zanke for p in z]
    dx, dy = min(zx) - min(xs), min(zy) - min(ys)
    crte = []
    for e in msp.query("POLYLINE[layer=='GRAVURA']"):
        crte.append([(v.dxf.location.x + dx, v.dxf.location.y + dy) for v in e.vertices])
    return crte, (round(max(xs) - min(xs), 1), round(max(ys) - min(ys), 1))


def slika_kosa(stl, png):
    if os.path.exists(png):
        return png
    tri = slika_stl.beri_stl(stl)
    slika_stl.izrisi(tri, png, ((1, -1.2, 0.9), (0, 0, 1)), velikost=700)
    return png


def list_kosa(pdf, k, meta, izhod_slik):
    koda, kolicina, dxf_oznacen, mapa_mat = meta["koda"], meta["kolicina"], meta["dxf"], meta["mapa"]
    material = k.get("material") or material_iz_mape(mapa_mat)
    T = k["T"]; K = k["K"]; up = k["upogibi"]
    o = orodje(material, T, up, k)
    zap = zaporedje(up)
    fig = plt.figure(figsize=(11.69, 8.27))
    fig.text(0.03, 0.965, f"{koda}  ·  {k['ime']}", fontsize=15, weight="bold")
    fig.text(0.03, 0.935, f"Photobox Slim A — list za krivilca   |   {material}, T = {T:g} mm   |   notranji R = {o['R']:g} mm (upogibi: "
             f"{', '.join(sorted(set('R%g' % u['polmer'] for u in up))) or '—'})   |   K = {K:g} ({k.get('KTabela') or 'ena vrednost'})   |   "
             f"količina na avtomat: {kolicina}   |   {datetime.date.today():%d. %m. %Y}", fontsize=8)
    ok = k["okvir"]; ok3 = k["okvir3d"]
    fig.text(0.03, 0.912, f"Razvita mera {ok[2]-ok[0]:.1f} × {ok[3]-ok[1]:.1f} mm   ·   upognjen kos {ok3[0]:g} × {ok3[1]:g} × {ok3[2]:g} mm   ·   "
             f"laserska oznaka: »{meta['oznaka'] or 'brez (premajhen kos)'}«  (sloj GRAVURA, {meta['vis'] or '—'} mm)", fontsize=8)
    # --- razgrnitev ---
    fig.text(0.03, 0.885, "Razgrnitev — pogled s strani gravure (rdeče); »gor« = krak proti gledalcu, »dol« = stran od njega. "
             "Črte: modra gor, oranžna dol; U-oznake so številke upogibov, koraki so spodaj.", fontsize=7.2, color="#333")
    ax = fig.add_axes([0.03, 0.36, 0.55, 0.51]); ax.set_aspect("equal"); ax.axis("off")
    zanke = k["zanke"]
    for i, z in enumerate(zanke):
        ax.add_patch(MplPoly(z, closed=True, fill=(i == 0), facecolor="#dde8f3" if i == 0 else "white", edgecolor="#123", lw=0.8))
    for z in zanke[1:]:
        ax.add_patch(MplPoly(z, closed=True, fill=True, facecolor="white", edgecolor="#123", lw=0.6))
    grav, dxf_okvir = poravnaj_dxf(dxf_oznacen, zanke)
    for c in grav:
        ax.plot([p[0] for p in c], [p[1] for p in c], color="#c00", lw=0.7)
    for u in up:
        st = next(i for i, z in enumerate(zap, 1) if z is u)
        ax.plot([u["x0"], u["x1"]], [u["y0"], u["y1"]], color="#06c" if u["smer"] == "gor" else "#d60", lw=1.1, ls=(0, (6, 3)))
        f = 0.25 + 0.5 * ((u["st"] % 3) / 2)   # oznake izmenično vzdolž črte, da se ne prekrivajo
        mx, my = u["x0"] + (u["x1"] - u["x0"]) * f, u["y0"] + (u["y1"] - u["y0"]) * f
        ax.annotate(f"U{u['st']} {u['kot']:g}° {u['smer']}" + (f" R{u['polmer']:g}" if u["polmer"] > 3 * T else ""), (mx, my), fontsize=6.5,
                    color="#06c" if u["smer"] == "gor" else "#d60", ha="center", va="bottom",
                    bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.85))
    W, H = ok[2] - ok[0], ok[3] - ok[1]
    ax.annotate("", (ok[0], ok[1] - 0.06 * H - 2), (ok[2], ok[1] - 0.06 * H - 2), arrowprops=dict(arrowstyle="<->", lw=0.6))
    ax.text((ok[0] + ok[2]) / 2, ok[1] - 0.06 * H - 4, f"{W:.1f}", ha="center", va="top", fontsize=7)
    ax.annotate("", (ok[0] - 0.05 * W - 2, ok[1]), (ok[0] - 0.05 * W - 2, ok[3]), arrowprops=dict(arrowstyle="<->", lw=0.6))
    ax.text(ok[0] - 0.05 * W - 4, (ok[1] + ok[3]) / 2, f"{H:.1f}", ha="right", va="center", fontsize=7, rotation=90)
    ax.set_xlim(ok[0] - 0.12 * W - 8, ok[2] + 0.04 * W + 2); ax.set_ylim(ok[1] - 0.14 * H - 8, ok[3] + 0.06 * H + 2)
    # --- slika upognjenega kosa ---
    ax2 = fig.add_axes([0.60, 0.50, 0.38, 0.40]); ax2.axis("off")
    try:
        png = slika_kosa(k["stl"], os.path.join(izhod_slik, f"{koda}.png"))
        ax2.imshow(Image.open(png)); ax2.text(0.01, 0.99, "upognjen kos (izometrija)", transform=ax2.transAxes, fontsize=7, va="top", color="#555")
    except Exception as e:  # noqa: BLE001
        ax2.text(0.5, 0.5, f"slika ni na voljo\n{e}", ha="center", va="center", fontsize=7)
    # --- tabela upogibov ---
    ax3 = fig.add_axes([0.60, 0.30, 0.39, 0.195]); ax3.axis("off")
    if up:
        vrst = [[f"U{u['st']}", f"{u['kot']:g}°", u["smer"], f"R{u['polmer']:g}", f"{u['dolzina']:.0f}", f"{u['krak_razgrnjen']:.1f}",
                 (f"{zunanja_mera(u, T, K, u['kot']):.1f}" if zunanja_mera(u, T, K, u["kot"]) else "—"), str(u["globina"])] for u in up]
        tab = ax3.table(cellText=vrst, colLabels=["upogib", "kot med\nkraki", "smer", "R not.", "dolžina", "krak\nrazgrnjen", "zun. mera\nkraka", "glob."],
                        loc="upper center", cellLoc="center", colWidths=[0.1, 0.11, 0.09, 0.1, 0.12, 0.16, 0.16, 0.08])
        tab.auto_set_font_size(False); tab.set_fontsize(6); tab.scale(1, 0.9)
        for (r_, c_), cel in tab.get_celld().items():
            if r_ == 0: cel.set_height(cel.get_height() * 1.6)
    else:
        ax3.text(0, 0.9, "Kos je raven — brez upogibov (samo laserski razrez).", fontsize=8, va="top")
    # --- zaporedje ---
    vrstice = [f"ORODJE:  klin {o['klin']};  matrica 1V, V = {o['V']:g} mm;  sila ≈ {o['kn_m']} kN/m "
               f"(najdaljši upogib {max([u['dolzina'] for u in up] or [0]):.0f} mm → ≈ {o['kn_m'] * max([u['dolzina'] for u in up] or [0]) / 1000:.0f} kN);  "
               f"najkrajši dovoljen krak 0,7 V = {o['krak_min']:g} mm;  zračno krivljenje, kot z globino (vzmetenje Al 1–2°, nerjavno 2–4°)."]
    if up:
        vrstice.append("ZAPOREDJE (od znotraj navzven, krajši kraki prej, menjava smeri = obrat kosa):")
        prej = None
        for i, u in enumerate(zap, 1):
            obrat = "" if prej is None or prej == u["smer"] else "  ⟲ obrni kos (druga smer)"
            opoz = []
            if u["krak_razgrnjen"] < o["krak_min"]:
                opoz.append(f"⚠ krak {u['krak_razgrnjen']:.1f} < 0,7 V — ožja matrica ali podpora")
            if u["krak_razgrnjen"] > 100:
                opoz.append("⚠ visok krak — preveri doseg klina / trk z orodjem")
            if u["globina"] > 0:
                opoz.append("povratni krak: upogni pred zunanjim (U z globino 0), zunanji nato z labodjim vratom")
            if u["kot"] < 1:
                opoz.append("⚠ zvit del (velik R, kot 0) — valjanje ali stopenjsko krivljenje, ne en gib")
            elif u["kot"] < 89:
                opoz.append(f"oster kot {u['kot']:g}° — klin 30°/60°, po potrebi dva giba")
            elif u["kot"] > 91:
                opoz.append(f"odprt kot {u['kot']:g}° — isti klin, manjša globina giba")
            if u["polmer"] > 3 * T:
                opoz.append(f"⚠ velik notranji R{u['polmer']:g} — zaokrožitveni klin/vložek R{u['polmer']:.0f} (Amada R7–R50) ali stopenjsko krivljenje (bump), ne V12")
            zm = zunanja_mera(u, T, K, u["kot"])
            vrstice.append(f"  {i}. U{u['st']}: {u['kot']:g}° {u['smer']}, dolžina {u['dolzina']:.0f} mm, prislon {u['krak_razgrnjen']:.1f} mm od upogibne črte "
                           f"(zun. mera kraka {zm:.1f} mm){obrat}" + ("   " + "; ".join(opoz) if opoz else "") if zm else
                           f"  {i}. U{u['st']}: {u['kot']:g}° {u['smer']}, dolžina {u['dolzina']:.0f} mm, prislon {u['krak_razgrnjen']:.1f} mm{obrat}" + ("   " + "; ".join(opoz) if opoz else ""))
            prej = u["smer"]
        vrstice.append("Prvi kos: izmeri kot in zunanjo mero, popravi globino giba, nato serija. Prislon vedno na raven dolg rob, nikoli na že upognjen krak.")
    import textwrap
    crte = []
    for v in vrstice:
        crte += textwrap.wrap(v, 175, subsequent_indent="      ") + [None]
    y = 0.33 - max(0, len(up) - 4) * 0.017
    noga = "Lastna dokumentacija (FreeCAD + lastna_plocevina). Zaporedje in orodje sta predlog po pravilih Amada AFH 2024 / raziskava plocevina.md §3b — krivilec ga potrdi ali prilagodi svojemu stroju. Tolerance ISO 2768-mK, kot ±1°."
    stran = 1
    for v in crte:
        if v is None:
            y -= 0.004; continue
        if y < 0.06:   # nadaljevanje na novi strani
            fig.text(0.03, 0.02, noga, fontsize=6.5, color="#555"); pdf.savefig(fig)
            if meta.get("png") and stran == 1: fig.savefig(meta["png"], dpi=110)
            plt.close(fig); stran += 1
            fig = plt.figure(figsize=(11.69, 8.27))
            fig.text(0.03, 0.965, f"{koda}  ·  {k['ime']}  —  nadaljevanje (stran {stran})", fontsize=13, weight="bold"); y = 0.92
        fig.text(0.03, y, v, fontsize=7.3, va="top"); y -= 0.024
    fig.text(0.03, 0.02, noga, fontsize=6.5, color="#555")
    pdf.savefig(fig)
    if meta.get("png") and stran == 1:
        fig.savefig(meta["png"], dpi=110)
    plt.close(fig)
    return dict(koda=koda, ime=k["ime"], material=material, T=T, upogibov=len(up), V=o["V"], klin=o["klin"],
                zaporedje=" → ".join(f"U{u['st']}({u['kot']:g}°{'↑' if u['smer']=='gor' else '↓'}, {u['krak_razgrnjen']:.0f})" for u in zap))


def uvod(pdf):
    fig = plt.figure(figsize=(11.69, 8.27))
    fig.text(0.03, 0.95, "Photobox Slim A — dokumentacija krivljenja pločevine", fontsize=16, weight="bold")
    bes = open(os.path.join(TU, "navodila_krivilcu.md"), encoding="utf-8").read() if os.path.exists(os.path.join(TU, "navodila_krivilcu.md")) else ""
    y = 0.90
    for v in bes.splitlines():
        if v.startswith("#"):
            fig.text(0.03, y, v.lstrip("# "), fontsize=9.5, weight="bold", va="top"); y -= 0.03
        elif v.strip():
            fig.text(0.03, y, v, fontsize=7.6, va="top"); y -= 0.023
        else:
            y -= 0.008
    pdf.savefig(fig); plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("razrez"); ap.add_argument("--izhod")
    a = ap.parse_args()
    izhod = a.izhod or os.path.join(a.razrez, "Dokumentacija krivljenja")
    os.makedirs(os.path.join(izhod, "slike"), exist_ok=True)
    kosi = json.load(open(os.path.join(a.razrez, "Upogibi", "upogibi.json"), encoding="utf-8"))
    kosi = [k for k in kosi if "upogibi" in k]
    oznake = {}
    with open(os.path.join(a.razrez, "DXF oznaceni", "Oznake kosov.csv"), encoding="utf-8-sig") as f:
        for r in csv.DictReader(f, delimiter=";"):
            oznake[r["Kos"]] = r
    kolicine = {}
    with open(os.path.join(a.razrez, "Seznam kosov za razrez.csv"), encoding="utf-8-sig") as f:
        for r in csv.DictReader(f, delimiter=";"):
            kolicine[r["Kos"]] = r
    povzetek = []; dodatna = [max([int(v["Koda"].split("-")[1]) for v in oznake.values()] or [0])]
    with PdfPages(os.path.join(izhod, "Slim A - krivljenje - vsi kosi.pdf")) as skupni:
        uvod(skupni)
        for k in sorted(kosi, key=lambda k: (oznake.get(k["ime"], {}).get("Koda", "ZZ"))):
            ime = k["ime"]
            oz = oznake.get(ime)
            if oz is None:   # dokument z več kosi (»… - del 1«) ali daljše ime: najdaljše skupno ime
                kand = [(len(os.path.commonprefix([n, ime])), v) for n, v in oznake.items() if n.startswith(ime) or ime.startswith(n)]
                oz = max(kand, key=lambda t: t[0])[1] if kand else None
            if oz is None:
                dodatna[0] += 1; koda = f"SA-{dodatna[0]:02d}"; mapa = ""; dxf = ""; bes = ""; vis = ""
                print(f"  ? {ime}: ni v seznamu razreza, dobi kodo {koda}")
            else:
                koda, mapa, bes, vis = oz["Koda"], oz["Material (mapa)"], oz["Besedilo oznake"], oz["Višina mm"]
                dxf = os.path.join(a.razrez, "DXF oznaceni", mapa, f"{oz['Kos']} x{kolicine.get(oz['Kos'], {}).get('Količina', '1')}.dxf")
            meta = dict(koda=koda, kolicina=kolicine.get(oz["Kos"] if oz else ime, {}).get("Količina", "?"), dxf=dxf, mapa=mapa, oznaka=bes, vis=vis)
            meta["png"] = os.path.join(izhod, "slike", f"list {koda}.png")
            with PdfPages(os.path.join(izhod, f"{koda} {ime}.pdf")) as posamezni:
                r = list_kosa(posamezni, k, meta, os.path.join(izhod, "slike"))
            meta["png"] = None
            list_kosa(skupni, k, meta, os.path.join(izhod, "slike"))
            povzetek.append(r); print(f"  {koda} {ime}: {r['upogibov']} upogibov, V{r['V']:g}, {r['zaporedje'] or 'ravno'}")
    with open(os.path.join(izhod, "Zaporedja krivljenja.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(povzetek[0].keys()), delimiter=";"); w.writeheader(); w.writerows(povzetek)
    print(f"\n{len(povzetek)} listov -> {izhod}")


if __name__ == "__main__":
    main()
