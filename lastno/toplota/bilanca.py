# -*- coding: utf-8 -*-
"""Bilančni toplotni model boxa na soncu (korak 1 iz TOPLOTNA-ANALIZA-PLAN.md).

Vozlišča: 5 zunanjih ploskev plašča (spredaj, zadaj, levo, desno, streha; dno adiabatno), notranji zrak, notranja masa
(naprave, police). Vreme: PVGIS TMY po urah (pvlib), sonce na vsako ploskev (pvlib), konvekcija in sevanje (ht).
Za vsako lokacijo in barvo plašča: prosto segrevanje (brez hlajenja), idealno hlajenje na cilj (potrebna moč) in po želji
delovanje vgrajene klime z omejeno močjo.

Uporaba: `izracun(mapa_toplota, nastavitve, obseg="teden"|"leto")` -> slovar z rezultati; piše POROCILO.md, urno/*.csv,
slike/*.png v mapo Toplota projekta. Knjižnice: numpy, scipy, pandas, pvlib, ht, matplotlib (pixi okolje FreeCAD-a;
numpy potrebuje .pixi/envs/default/Library/bin v PATH).
"""
import json
import math
import os
import time

import numpy as np
import pandas as pd
import pvlib
from ht.conv_free_immersed import Nu_vertical_plate_Churchill, Nu_horizontal_plate_McAdams
from scipy.integrate import solve_ivp

SIGMA = 5.670e-8
RHO_CP_ZRAK = 1.15 * 1005.0  # J/(m3 K) pri ~35 °C
NU_ZRAK, K_ZRAK, PR_ZRAK = 1.7e-5, 0.027, 0.71  # zrak pri ~40 °C
AZIMUT = {"S": 0.0, "V": 90.0, "J": 180.0, "Z": 270.0}
PLOSKVE = ["spredaj", "zadaj", "levo", "desno", "streha"]

PRIVZETE = {
    "box": {"sirina_mm": 400, "globina_mm": 565, "visina_mm": 1911, "plocevina_mm": 1.5},
    "steklo": {"povrsina_m2": 0.155, "prepustnost": 0.8, "absorptivnost": 0.1, "streha_okno_m2": 0.0},
    "plasc": {"emisivnost": 0.9, "barve": {"bela": 0.25, "svetlo siva": 0.5, "temna": 0.85}},
    "naprave_W": {"PC + napajalnik": 120, "TV": 80, "tiskalnik (povprečje)": 30, "Mikrotik": 10, "LED obroči": 30, "POS in ostalo": 10},
    "delez_v_zrak": 0.6,
    "notranja_masa": {"kg_jekla_ekvivalent": 40, "povrsina_m2": 2.5},
    "hlajenje": {"cilj_C": 35, "ventilacija_m3h": 0, "klima_W": 0},
    "orientacija_spredaj": "J",
    "lokacije": {"Biograd": {"lat": 43.937, "lon": 15.447}, "Opatija": {"lat": 45.336, "lon": 14.306}, "Zlatibor": {"lat": 43.730, "lon": 19.700}},
    "leto": 2023,
    "veter_najmanj_ms": 0.5,
    "albedo": 0.2,
}


def nalozi(mapa):
    """Nastavitve iz <mapa>/nastavitve.json, dopolnjene s privzetimi."""
    pot = os.path.join(mapa, "nastavitve.json")
    nast = json.loads(json.dumps(PRIVZETE))
    if os.path.isfile(pot):
        with open(pot, encoding="utf-8") as f:
            svoje = json.load(f)
        for k, v in svoje.items():
            if isinstance(v, dict) and isinstance(nast.get(k), dict) and k not in ("naprave_W", "lokacije"):
                nast[k].update(v)
            else:
                nast[k] = v
    return nast


def shrani(mapa, nast):
    os.makedirs(mapa, exist_ok=True)
    with open(os.path.join(mapa, "nastavitve.json"), "w", encoding="utf-8") as f:
        json.dump(nast, f, ensure_ascii=False, indent=2)


def moc_naprav(nast):
    return float(sum(v for k, v in nast["naprave_W"].items() if not k.startswith("_") and isinstance(v, (int, float))))


# ----------------------------------------------------------------------------- vreme in sonce
def vreme(mapa, ime, lok, leto):
    """Urno vreme PVGIS TMY (ghi, dni, dhi, temp_air, wind_speed), predpomnjeno v <mapa>/vreme/<ime>.csv."""
    os.makedirs(os.path.join(mapa, "vreme"), exist_ok=True)
    pot = os.path.join(mapa, "vreme", f"{ime}.csv")
    if os.path.isfile(pot):
        df = pd.read_csv(pot, index_col=0, parse_dates=True)
    else:
        df, _meta = pvlib.iotools.get_pvgis_tmy(lok["lat"], lok["lon"], map_variables=True, coerce_year=leto)
        df = df[["ghi", "dni", "dhi", "temp_air", "wind_speed"]]
        df.to_csv(pot)
    df.index = pd.DatetimeIndex(df.index)
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    return df.sort_index()


def sonce_na_ploskve(df, lok, azimut_spredaj, albedo):
    """POA sevanje (W/m2) po urah na ploskve spredaj, zadaj, levo, desno, streha."""
    loc = pvlib.location.Location(lok["lat"], lok["lon"], tz="UTC")
    pos = loc.get_solarposition(df.index)
    ploskve = {"spredaj": (90, azimut_spredaj), "zadaj": (90, (azimut_spredaj + 180) % 360),
               "levo": (90, (azimut_spredaj - 90) % 360), "desno": (90, (azimut_spredaj + 90) % 360), "streha": (0, 180)}
    out = {}
    for ime, (nagib, az) in ploskve.items():
        poa = pvlib.irradiance.get_total_irradiance(nagib, az, pos["apparent_zenith"], pos["azimuth"],
                                                    df["dni"], df["ghi"], df["dhi"], albedo=albedo)
        out[ime] = poa["poa_global"].fillna(0.0).clip(lower=0.0).to_numpy()
    return out


# ----------------------------------------------------------------------------- prenos toplote (ht)
def h_prosta_navpicna(dT, L):
    dT = max(abs(dT), 0.05)
    Gr = 9.81 * (1 / 313.0) * dT * L**3 / NU_ZRAK**2
    return Nu_vertical_plate_Churchill(PR_ZRAK, Gr) * K_ZRAK / L


def h_prosta_vodoravna(dT, L, topla_gor):
    dT = max(abs(dT), 0.05)
    Gr = 9.81 * (1 / 313.0) * dT * L**3 / NU_ZRAK**2
    return Nu_horizontal_plate_McAdams(PR_ZRAK, Gr, buoyancy=topla_gor) * K_ZRAK / L


def h_veter(v):
    return 5.7 + 3.8 * v  # McAdams, ravna plošča v vetru


def h_zunaj(dT, L, v, vodoravna=False, topla_gor=True):
    hn = h_prosta_vodoravna(dT, L, topla_gor) if vodoravna else h_prosta_navpicna(dT, L)
    return (hn**3 + h_veter(v) ** 3) ** (1 / 3)


def t_neba(T_amb_K):
    return 0.0552 * T_amb_K**1.5  # Swinbank, jasno nebo


# ----------------------------------------------------------------------------- model
class Model:
    """nacin: 'prosto' (brez hlajenja), 'idealno' (zrak na cilju, meri potrebno moč), 'klima' (omejena moč klima_W)."""

    def __init__(self, nast, df, poa, absorptivnost, nacin="prosto"):
        b = nast["box"]
        W, D, H = b["sirina_mm"] / 1e3, b["globina_mm"] / 1e3, b["visina_mm"] / 1e3
        self.A = np.array([W * H, W * H, D * H, D * H, W * D])
        self.L = np.array([H, H, H, H, (W * D) / (2 * (W + D))])
        self.vodoravna = np.array([False, False, False, False, True])
        self.F_nebo = np.array([0.5, 0.5, 0.5, 0.5, 1.0])
        st = nast["steklo"]
        self.A_steklo = np.zeros(5)
        self.A_steklo[0] = st["povrsina_m2"]
        self.A_steklo[4] = st.get("streha_okno_m2", 0.0)
        self.tau, self.alpha_st = st["prepustnost"], st["absorptivnost"]
        self.alpha = np.full(5, absorptivnost)
        self.eps = nast["plasc"]["emisivnost"]
        self.A_neprosojna = self.A - self.A_steklo
        mat = nast["plasc"].get("material", {"gostota": 7850, "cp": 480})   # jeklo privzeto; aluminij 2700 / 900
        self.C_pl = float(mat["gostota"]) * b["plocevina_mm"] / 1e3 * float(mat["cp"]) * self.A
        self.V = W * D * H
        self.C_zrak = self.V * RHO_CP_ZRAK + 3000.0  # zrak + lahka vsebina
        m = nast["notranja_masa"]
        self.C_masa = m["kg_jekla_ekvivalent"] * 480.0
        self.A_masa = m["povrsina_m2"]
        self.P = moc_naprav(nast)
        self.delez_zrak = nast["delez_v_zrak"]
        hl = nast["hlajenje"]
        self.vent = hl["ventilacija_m3h"] / 3600.0 * RHO_CP_ZRAK
        self.nacin = nacin
        self.T_cilj = hl["cilj_C"] + 273.15
        self.P_klima = float(hl.get("klima_W", 0) or 0)
        self.K_reg = 2000.0
        self.t = np.arange(len(df)) * 3600.0
        self.t_index = df.index
        self.T_amb = df["temp_air"].to_numpy() + 273.15
        self.v = np.maximum(df["wind_speed"].to_numpy(), nast["veter_najmanj_ms"])
        self.G = np.column_stack([poa[i] for i in PLOSKVE])

    def vhod(self, t):
        T_amb = np.interp(t, self.t, self.T_amb)
        v = np.interp(t, self.t, self.v)
        G = np.array([np.interp(t, self.t, self.G[:, i]) for i in range(5)])
        return T_amb, v, G

    def tokovi(self, t, y):
        T_pl, T_zr, T_m = y[:5], y[5], y[6]
        T_amb, v, G = self.vhod(t)
        T_sky, T_tla = t_neba(T_amb), T_amb
        q = {"sonce": self.alpha * self.A_neprosojna * G + self.alpha_st * self.A_steklo * G,
             "sonce_skozi_steklo": float((self.tau * self.A_steklo * G).sum())}
        h_out = np.array([h_zunaj(T_pl[i] - T_amb, self.L[i], v, self.vodoravna[i], T_pl[i] > T_amb) for i in range(5)])
        q["konv_zunaj"] = h_out * self.A * (T_amb - T_pl)
        q["sev_zunaj"] = self.eps * SIGMA * self.A * (self.F_nebo * (T_sky**4 - T_pl**4) + (1 - self.F_nebo) * (T_tla**4 - T_pl**4))
        h_in = np.array([h_zunaj(T_pl[i] - T_zr, self.L[i], 0.0, self.vodoravna[i], T_pl[i] < T_zr) for i in range(5)])
        q["konv_znotraj"] = h_in * self.A * (T_zr - T_pl)
        eps_ef = 1 / (1 / 0.9 + 1 / 0.9 - 1)
        q["sev_znotraj"] = eps_ef * SIGMA * self.A * (T_m**4 - T_pl**4)
        h_m = h_prosta_navpicna(T_m - T_zr, 0.3)
        q["masa_zrak"] = h_m * self.A_masa * (T_m - T_zr)
        q["vent"] = self.vent * (T_amb - T_zr)
        if self.nacin == "prosto":
            q["hlajenje"] = 0.0
        else:
            x = (T_zr - self.T_cilj) / 0.2   # gladek regulator (softplus), da implicitni reševalnik ne obtiči
            P = self.K_reg * 0.2 * (x if x > 30 else math.log1p(math.exp(x)))
            q["hlajenje"] = min(P, self.P_klima) if self.nacin == "klima" else P
        return q

    def rhs(self, t, y):
        q = self.tokovi(t, y)
        dT_pl = (q["sonce"] + q["konv_zunaj"] + q["sev_zunaj"] + q["konv_znotraj"] + q["sev_znotraj"]) / self.C_pl
        dT_zr = (-q["konv_znotraj"].sum() + q["masa_zrak"] + self.P * self.delez_zrak + q["vent"] - q["hlajenje"]) / self.C_zrak
        dT_m = (-q["sev_znotraj"].sum() - q["masa_zrak"] + self.P * (1 - self.delez_zrak) + q["sonce_skozi_steklo"]) / self.C_masa
        return np.concatenate([dT_pl, [dT_zr, dT_m]])

    def simuliraj(self, t0=None, t1=None):
        t0 = 0.0 if t0 is None else t0
        t1 = self.t[-1] if t1 is None else t1
        y0 = np.full(7, np.interp(t0, self.t, self.T_amb))
        ure = np.arange(t0, t1 + 1, 3600.0)
        args = dict(t_eval=ure, max_step=900.0, rtol=1e-5, atol=1e-3)
        sol = solve_ivp(self.rhs, (t0, t1), y0, method="BDF", **args)
        if not sol.success:
            sol = solve_ivp(self.rhs, (t0, t1), y0, method="LSODA", **args)
        if not sol.success:
            raise RuntimeError(sol.message)
        P_hl = np.array([self.tokovi(t, sol.y[:, i])["hlajenje"] for i, t in enumerate(sol.t)])
        df = pd.DataFrame(sol.y.T - 273.15, columns=[f"T_{n}" for n in PLOSKVE] + ["T_zrak", "T_masa"])
        df["T_zunaj"] = np.interp(sol.t, self.t, self.T_amb) - 273.15
        df["G_spredaj"] = np.interp(sol.t, self.t, self.G[:, 0])
        df["G_streha"] = np.interp(sol.t, self.t, self.G[:, 4])
        df["P_hlajenje_W"] = P_hl
        df.index = self.t_index[0] + pd.to_timedelta(sol.t, unit="s")
        return df


# ----------------------------------------------------------------------------- izračun in poročilo
def najhujsi_teden(df):
    ocena = (df["temp_air"] + df["ghi"] / 40.0).rolling(24, center=True).mean().fillna(0)
    i = int(ocena.to_numpy().argmax())
    return max(0, i - 4 * 24), min(len(df) - 1, i + 3 * 24)


def slika(df, naslov, pot, cilj):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(2, 1, figsize=(10, 6.4), sharex=True)
    for col, lab in [("T_zunaj", "zunaj"), ("T_streha", "streha"), ("T_spredaj", "plašč spredaj"),
                     ("T_zrak", "zrak v boxu"), ("T_masa", "naprave / masa")]:
        ax[0].plot(df.index, df[col], label=lab)
    ax[0].axhline(cilj, color="k", ls="--", lw=0.8, label=f"cilj {cilj} °C")
    ax[0].set_ylabel("°C"); ax[0].legend(ncol=3, fontsize=8); ax[0].set_title(naslov, fontsize=11); ax[0].grid(alpha=0.3)
    ax[1].plot(df.index, df["G_streha"], label="sonce na streho W/m²", color="orange")
    ax[1].plot(df.index, df["G_spredaj"], label="sonce spredaj W/m²", color="gold")
    ax[1].plot(df.index, df["P_hlajenje_W"], label="hlajenje W", color="tab:blue")
    ax[1].legend(fontsize=8); ax[1].grid(alpha=0.3); ax[1].set_ylabel("W, W/m²")
    fig.autofmt_xdate(); fig.tight_layout(); fig.savefig(pot, dpi=100); plt.close(fig)


def md_tabela(vrstice):
    if not vrstice:
        return "(ni rezultatov)"
    stolpci = list(vrstice[0].keys())
    out = ["| " + " | ".join(stolpci) + " |", "|" + "|".join("---" for _ in stolpci) + "|"]
    out += ["| " + " | ".join(str(v.get(s, "")) for s in stolpci) + " |" for v in vrstice]
    return "\n".join(out)


def izracun(mapa, nast, obseg="teden", lokacije=None, barve=None, orientacije=True, napredek=None):
    """Celoten izračun: za vsako lokacijo in barvo prosto, idealno hlajenje (in klima, če klima_W > 0).
    obseg: 'teden' = najhujši teden, 'leto' = cel TMY. napredek(besedilo) sporoča potek."""
    os.makedirs(os.path.join(mapa, "urno"), exist_ok=True)
    os.makedirs(os.path.join(mapa, "slike"), exist_ok=True)
    jav = napredek or (lambda s: None)
    az = AZIMUT.get(nast.get("orientacija_spredaj", "J"), 180.0)
    lokacije = lokacije or list(nast["lokacije"].keys())
    barve = barve or list(nast["plasc"]["barve"].keys())
    cilj = nast["hlajenje"]["cilj_C"]
    klima_W = float(nast["hlajenje"].get("klima_W", 0) or 0)
    vrstice, slike, zacetek = [], {}, time.time()
    for ime_lok in lokacije:
        lok = nast["lokacije"][ime_lok]
        jav(f"vreme {ime_lok}")
        df = vreme(mapa, ime_lok, lok, nast["leto"])
        poa = sonce_na_ploskve(df, lok, az, nast["albedo"])
        i0, i1 = najhujsi_teden(df)
        t0, t1 = (i0 * 3600.0, i1 * 3600.0) if obseg == "teden" else (None, None)
        for barva in barve:
            alpha = nast["plasc"]["barve"][barva]
            jav(f"{ime_lok}, plašč {barva} ({time.time() - zacetek:.0f} s)")
            prosto = Model(nast, df, poa, alpha, "prosto").simuliraj(t0, t1)
            hlaj = Model(nast, df, poa, alpha, "idealno").simuliraj(t0, t1)
            klima = Model(nast, df, poa, alpha, "klima").simuliraj(t0, t1) if klima_W > 0 else None
            oznaka = f"{ime_lok}_{barva.replace(' ', '-')}"
            prosto.to_csv(os.path.join(mapa, "urno", f"{oznaka}_prosto.csv"), float_format="%.2f")
            hlaj.to_csv(os.path.join(mapa, "urno", f"{oznaka}_hlajenje.csv"), float_format="%.2f")
            prosto = prosto.iloc[24:] if len(prosto) > 72 else prosto
            if klima is not None and len(klima) > 72:
                klima = klima.iloc[24:]
            dan = prosto["T_zrak"].idxmax()
            okno = slice(dan.normalize() - pd.Timedelta(days=1), dan.normalize() + pd.Timedelta(days=2))
            s_pr, s_hl = f"slike/{oznaka}_prosto.png", f"slike/{oznaka}_hlajenje.png"
            slika(prosto.loc[okno], f"{ime_lok}, plašč {barva} — brez hlajenja", os.path.join(mapa, s_pr), cilj)
            slika(hlaj.loc[okno], f"{ime_lok}, plašč {barva} — idealno hlajenje na {cilj} °C", os.path.join(mapa, s_hl), cilj)
            slike[oznaka] = {"prosto": s_pr, "hlajenje": s_hl}
            if klima is not None:
                s_kl = f"slike/{oznaka}_klima.png"
                slika(klima.loc[okno], f"{ime_lok}, plašč {barva} — klima {klima_W:.0f} W", os.path.join(mapa, s_kl), cilj)
                slike[oznaka]["klima"] = s_kl
            # prvih 24 h je ogrevanje iz začetnega stanja (vse pri zunanji temperaturi): vrh in energijo oceni brez njih
            hlaj = hlaj.iloc[24:] if len(hlaj) > 72 else hlaj
            vrh = hlaj["P_hlajenje_W"].idxmax()
            dan_hl = hlaj.loc[vrh.normalize():vrh.normalize() + pd.Timedelta(days=1)]
            v = {"lokacija": ime_lok, "plašč": barva, "α": alpha,
                 "T_zrak max °C": round(float(prosto["T_zrak"].max()), 1),
                 "T_masa max °C": round(float(prosto["T_masa"].max()), 1),
                 "T_streha max °C": round(float(prosto["T_streha"].max()), 1),
                 "T_zunaj ob tem °C": round(float(prosto.loc[dan, "T_zunaj"]), 1),
                 "kdaj": dan.strftime("%d.%m. %H:%M UTC"),
                 "ur > 35 °C": int((prosto["T_zrak"] > 35).sum()), "ur > 40 °C": int((prosto["T_zrak"] > 40).sum()),
                 "hlajenje vrh W": int(round(float(hlaj["P_hlajenje_W"].max()), -1)),
                 "hlajenje najhujši dan kWh": round(float(dan_hl["P_hlajenje_W"].sum()) / 1000, 1),
                 "hlajenje skupaj kWh": round(float(hlaj["P_hlajenje_W"].sum()) / 1000, 1)}
            if klima is not None:
                v[f"T_zrak max s klimo {klima_W:.0f} W"] = round(float(klima["T_zrak"].max()), 1)
                v[f"ur > {cilj} °C s klimo"] = int((klima["T_zrak"] > cilj + 0.5).sum())
            vrstice.append(v)
    orient = []
    if orientacije and vrstice:
        naj = max(vrstice, key=lambda r: r["T_zrak max °C"])["lokacija"]
        df = vreme(mapa, naj, nast["lokacije"][naj], nast["leto"])
        i0, i1 = najhujsi_teden(df)
        alpha = nast["plasc"]["barve"][barve[0]]
        for smer, az2 in AZIMUT.items():
            jav(f"orientacija {smer}")
            poa = sonce_na_ploskve(df, nast["lokacije"][naj], az2, nast["albedo"])
            prosto = Model(nast, df, poa, alpha, "prosto").simuliraj(i0 * 3600.0, i1 * 3600.0)
            hlaj = Model(nast, df, poa, alpha, "idealno").simuliraj(i0 * 3600.0, i1 * 3600.0)
            orient.append({"lokacija": naj, "spredaj proti": smer, "plašč": barve[0],
                           "T_zrak max °C": round(float(prosto["T_zrak"].max()), 1),
                           "T_masa max °C": round(float(prosto["T_masa"].max()), 1),
                           "hlajenje vrh W": int(round(float(hlaj["P_hlajenje_W"].max()), -1))})
    rez = {"obseg": obseg, "cas": time.strftime("%Y-%m-%d %H:%M"), "trajanje_s": round(time.time() - zacetek),
           "tabela": vrstice, "orientacije": orient, "slike": slike, "naprave_W": moc_naprav(nast),
           "orientacija_spredaj": nast.get("orientacija_spredaj", "J"), "cilj_C": cilj, "klima_W": klima_W}
    with open(os.path.join(mapa, "rezultati.json"), "w", encoding="utf-8") as f:
        json.dump(rez, f, ensure_ascii=False, indent=1)
    porocilo(mapa, nast, rez)
    return rez


def porocilo(mapa, nast, rez):
    b = nast["box"]
    obseg = "najhujši teden" if rez["obseg"] == "teden" else "celo leto (TMY)"
    md = [f"# Toplotna bilanca boxa na soncu — korak 1 ({rez['cas']})", "",
          f"Model: `lastno/toplota/bilanca.py` (repo FreeCAD), vhod `Toplota/nastavitve.json`. Obseg: {obseg}, urno vreme PVGIS TMY, ",
          f"box {b['sirina_mm']} × {b['globina_mm']} × {b['visina_mm']} mm (zaprta vrata), sprednja stena proti {rez['orientacija_spredaj']}, ",
          f"naprave skupaj **{rez['naprave_W']:.0f} W**, ventilacija {nast['hlajenje']['ventilacija_m3h']} m³/h, cilj hlajenja {rez['cilj_C']} °C"
          + (f", klima {rez['klima_W']:.0f} W." if rez["klima_W"] else "."), "",
          f"Vozlišča: plašč po ploskvah ({nast['plasc'].get('material', {}).get('ime', 'jeklo')} {b['plocevina_mm']} mm), notranji zrak, notranja masa (naprave, police). Sonce iz pvlib na vsako ",
          "ploskev, konvekcija (ht: Churchill-Chu, McAdams) + veter, sevanje v nebo in tla, sevanje plašč–masa. Dno adiabatno.", "",
          "## Rezultati", "", md_tabela(rez["tabela"]), ""]
    if rez["orientacije"]:
        md += ["## Vpliv orientacije sprednje stene (najhujši teden)", "", md_tabela(rez["orientacije"]), ""]
    md += ["- *T_zrak max* je najvišja temperatura zraka v boxu brez hlajenja; *hlajenje vrh* je toplota, ki jo mora klima odvajati ",
           "  v najhujši uri, da zrak ostane pod ciljem (odvedena toplota, ne električna moč klime).",
           "- Slike najhujšega dne: `Toplota/slike/`, urni podatki: `Toplota/urno/`.", "",
           "## Kaj je ocena in kaj potrjeno",
           "- Mere boxa in okna so iz modela (zaprta vrata); barva plašča, moči naprav, prepustnost pleksija in notranja masa so ocene ",
           "  v `nastavitve.json` — po potrditvi popravi vrednosti in poženi znova.",
           "- Brez meritve iz pravega boxa je negotovost ± 5 °C. Sevanje tal je pri temperaturi zraka (asfalt na soncu je toplejši)."]
    with open(os.path.join(mapa, "POROCILO.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md))
