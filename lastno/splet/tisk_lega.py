"""Lega kosa za 3D tisk: analiza previsov in iskanje orientacije z najmanj podporami (od 2026-10-10).

Samo numpy, brez FreeCAD-a (strežnik da trikotniško mrežo, izračun teče na niti strežnika). Smer `gor` je smer
gradnje (normala mize) v koordinatah mreže; zasuk `rotacija` (3x3 po vrsticah) jo obrne v +Z, kot ga uporabi plošča
Tiskaj (pretvorba.py, orientacija »rocno«).

Ocena ene smeri:
- previs: ploskev, ki gleda navzdol in je od navpičnice nagnjena več kot `kot_previsa` (privzeto 45°), ni pa na mizi;
- podpore: hitra ocena = projicirana površina previsa x višina do mize (zgornja meja); za najboljše smeri natančneje
  z rastrom: podpora pade le do prve ploskve kosa pod previsom (»samopodpora« na kosu se šteje kot krajša podpora);
- stik z mizo: ploskve na dnu (oprijem; kos na robu ali oglišču se pri tisku prevrne ali odlepi);
- višina: čas tiska (majhna utež).
"""

import math

import numpy as np

KOT_PREVISA = 45.0      # stopinj od navpičnice; P2S zmore več, 45 je varna meja
NA_MIZI_MM = 0.3        # ploskev do te višine nad dnom leži na mizi
BREZ_PODPOR_CM3 = 0.02  # pod to prostornino podpor (cm³) šteje, da podpor ni


def _mreza(tocke, trikotniki):
    V = np.asarray(tocke, dtype=np.float64).reshape(-1, 3)
    F = np.asarray(trikotniki, dtype=np.int64).reshape(-1, 3)
    P0, P1, P2 = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    vek = np.cross(P1 - P0, P2 - P0)
    dvojna = np.linalg.norm(vek, axis=1)
    dobri = dvojna > 1e-12
    F, P0, P1, P2, vek, dvojna = F[dobri], P0[dobri], P1[dobri], P2[dobri], vek[dobri], dvojna[dobri]
    return {"V": V, "F": F, "P0": P0, "P1": P1, "P2": P2, "N": vek / dvojna[:, None], "A": dvojna / 2,
            "C": (P0 + P1 + P2) / 3}


def _fibonacci(n):
    i = np.arange(n) + 0.5
    z = 1 - 2 * i / n
    r = np.sqrt(1 - z * z)
    fi = i * math.pi * (3 - math.sqrt(5))
    return np.stack([r * np.cos(fi), r * np.sin(fi), z], axis=1)


def _smeri(m, n_krogla=400, n_ploskev=40):
    """Kandidatne smeri gor: enakomerno po krogli, osi in -normale največjih ravnih ploskev (ploskev na mizi)."""
    kljuc = np.round(m["N"], 3)
    enotne, inv = np.unique(kljuc, axis=0, return_inverse=True)
    povrsine = np.bincount(inv.ravel(), weights=m["A"])
    naj = np.argsort(-povrsine)[:n_ploskev]
    ploskve = -enotne[naj]
    osi = np.array([[0, 0, 1], [0, 0, -1], [1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0]], dtype=np.float64)
    vse = np.concatenate([osi, ploskve, _fibonacci(n_krogla)])
    vse /= np.linalg.norm(vse, axis=1)[:, None]
    # podvojene smeri (manj kot ~1,5°) ven, prve (osi, ploskve) imajo prednost
    izbrane = []
    for d in vse:
        if not izbrane or np.max(np.asarray(izbrane) @ d) < 0.9997:
            izbrane.append(d)
    return np.asarray(izbrane)


def _hitro(m, D, sin_prag):
    """Merila za več smeri hkrati (stolpci D); vrne slovar polj dolžine len(D)."""
    N, A, C, V = m["N"], m["A"], m["C"], m["V"]
    c = N @ D.T                       # (trikotniki, smeri): -1 = gleda naravnost navzdol
    dno = (V @ D.T).min(axis=0)
    vrh = (V @ D.T).max(axis=0)
    h = C @ D.T - dno
    na_mizi = (c < -0.995) & (h < NA_MIZI_MM)
    previs = (-c > sin_prag) & ~na_mizi
    Ap = A[:, None] * np.clip(-c, 0, None)
    return {
        "stik": (A[:, None] * na_mizi).sum(axis=0),
        "previsi": (A[:, None] * previs).sum(axis=0),
        "podpore_hitro": (Ap * h * previs).sum(axis=0),
        "visina": vrh - dno,
        "tezisce": (A[:, None] * h).sum(axis=0) / A.sum(),   # težišče površine (dovolj za oceno prevrnitve)
    }


def _baza(d):
    """Pravokotna baza (e1, e2) ravnine pravokotno na d."""
    pomozna = np.array([1.0, 0, 0]) if abs(d[0]) < 0.9 else np.array([0, 1.0, 0])
    e1 = np.cross(d, pomozna)
    e1 /= np.linalg.norm(e1)
    return e1, np.cross(d, e1)


def _vzorci(m, maska, celica, gostota, nakljucno, najvec):
    """Enakomerni vzorci na izbranih trikotnikih (približno `gostota` na celico); vrne točke in utež (površino)."""
    A = m["A"][maska]
    if not len(A):
        return np.zeros((0, 3)), np.zeros(0), np.zeros(0, dtype=np.int64)
    n = np.maximum(1, np.ceil(A * gostota / (celica * celica))).astype(np.int64)
    if n.sum() > najvec:
        n = np.maximum(1, np.floor(n * najvec / n.sum())).astype(np.int64)
    idx = np.repeat(np.nonzero(maska)[0], n)
    u, v = nakljucno.random(len(idx)), nakljucno.random(len(idx))
    zunaj = u + v > 1
    u[zunaj], v[zunaj] = 1 - u[zunaj], 1 - v[zunaj]
    P0, P1, P2 = m["P0"][idx], m["P1"][idx], m["P2"][idx]
    tocke = P0 + (P1 - P0) * u[:, None] + (P2 - P0) * v[:, None]
    utez = np.repeat(A / n, n)
    return tocke, utez, idx


def podpore_natancno(m, d, sin_prag, celica=None):
    """Prostornina podpor (mm³) za smer d z rastrom: vsak vzorec previsa pade do prve ploskve kosa, ki gleda navzgor,
    pod njim v isti celici, sicer do mize."""
    V, N, C = m["V"], m["N"], m["C"]
    s = V @ d
    dno = s.min()
    if celica is None:
        e1, e2 = _baza(d)
        razpon = max(np.ptp(V @ e1), np.ptp(V @ e2), 1.0)
        celica = max(razpon / 250.0, 0.4)
    c = N @ d
    h = C @ d - dno
    previs = (-c > sin_prag) & ~((c < -0.995) & (h < NA_MIZI_MM))
    if not previs.any():
        return 0.0
    gor = c > 0.05
    nakljucno = np.random.default_rng(1)
    pt_p, ut_p, idx_p = _vzorci(m, previs, celica, 1.5, nakljucno, 400_000)
    pt_g, _, _ = _vzorci(m, gor, celica, 3.0, nakljucno, 1_500_000)
    e1, e2 = _baza(d)
    def celice(p):
        return (np.floor(p @ e1 / celica).astype(np.int64) * 1_000_003 + np.floor(p @ e2 / celica).astype(np.int64))
    hp = pt_p @ d - dno
    cp = celice(pt_p)
    visina = hp.copy()
    if len(pt_g):
        hg = pt_g @ d - dno
        cg = celice(pt_g)
        razpon = float(np.ptp(s)) + 10.0      # višina je vedno manjša: ključ celica*razpon + višina ohrani vrstni red
        red = np.lexsort((hg, cg))
        cg_s, hg_s = cg[red], hg[red]
        # za vsak vzorec previsa: najvišja ploskev navzgor v isti celici, ki je nižje od vzorca (vsaj pol celice)
        lev = np.searchsorted(cg_s, cp, side="left")
        des = np.searchsorted(cg_s, cp, side="right")
        ima = des > lev
        if ima.any():
            # binarno iskanje višine znotraj odseka celice: kombiniran ključ celica*razpon + višina
            kljuc_g = (cg_s - cg_s.min()).astype(np.float64) * razpon + hg_s
            kljuc_p = (cp - cg_s.min()).astype(np.float64) * razpon + (hp - max(celica * 0.5, 0.2))
            poz = np.searchsorted(kljuc_g, kljuc_p, side="right") - 1
            veljaven = ima & (poz >= lev) & (poz < des)
            pod = np.where(veljaven, hg_s[np.clip(poz, 0, len(hg_s) - 1)], 0.0)
            visina = np.where(veljaven, hp - pod, hp)
    Ap = ut_p * np.clip(-(N[idx_p] @ d), 0, None)
    return float((Ap * np.clip(visina, 0, None)).sum())


def rotacija_na_z(d):
    """Najmanjši zasuk (3x3 po vrsticah), ki smer d obrne v +Z."""
    d = np.asarray(d, dtype=np.float64)
    d = d / np.linalg.norm(d)
    z = np.array([0.0, 0.0, 1.0])
    os_ = np.cross(d, z)
    s, c = np.linalg.norm(os_), float(d @ z)
    if s < 1e-9:
        return np.eye(3) if c > 0 else np.diag([1.0, -1.0, -1.0])
    k = os_ / s
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    kot = math.atan2(s, c)
    return np.eye(3) + math.sin(kot) * K + (1 - math.cos(kot)) * (K @ K)


def _ocena(merila, i, podpore_mm3, min_stik_mm2):
    """Manjša je boljša; enota je približno cm³ podpor.
    - kos brez ravne ploskve na mizi (stoji na robu ali oglišču) se med tiskom odlepi ali prevrne: kazen 10 pomeni, da se
      poševna lega splača le, če prihrani več kot ~10 cm³ podpor;
    - visoko težišče nad majhnim stikom (vitek kos pokonci) se med tiskom maje: kazen raste s kvadratom razmerja
      višina težišča / velikost stika nad 2;
    - višina (število slojev, čas, tveganje) 1 cm³ na 100 mm."""
    stik, tezisce = float(merila["stik"][i]), float(merila["tezisce"][i])
    kazen_stika = 10.0 * max(0.0, 1.0 - stik / min_stik_mm2) if min_stik_mm2 > 0 else 0.0
    razmerje = tezisce / max(math.sqrt(stik), 1.0)
    kazen_vitkosti = min(10.0, 0.5 * max(0.0, razmerje - 2.0) ** 2)
    return (podpore_mm3 / 1000.0 + 0.1 * float(merila["previsi"][i]) / 100.0 + 0.01 * float(merila["visina"][i])
            + kazen_stika + kazen_vitkosti)


def analiziraj(tocke, trikotniki, kot_previsa=KOT_PREVISA, kandidatov=5):
    """Najboljše lege kosa. Vrne slovar s `kandidati` (urejeni po oceni; prvi je predlog) in `kot_je` (lega, kot je
    kos v modelu: gor = +Z mreže)."""
    m = _mreza(tocke, trikotniki)
    if not len(m["A"]):
        return {"ok": False, "sporocilo": "Kos nima ploskev."}
    sin_prag = math.sin(math.radians(kot_previsa))
    D = _smeri(m)
    merila = {k: [] for k in ("stik", "previsi", "podpore_hitro", "visina", "tezisce")}
    for i in range(0, len(D), 24):
        r = _hitro(m, D[i:i + 24], sin_prag)
        for k in merila:
            merila[k].append(r[k])
    merila = {k: np.concatenate(v) for k, v in merila.items()}
    # najmanjši sprejemljiv stik: 1 cm², pri majhnih kosih pol največje ravne ploskve
    min_stik = min(100.0, 0.5 * float(merila["stik"].max())) if merila["stik"].max() > 0 else 0.0
    hitre = np.array([_ocena(merila, i, merila["podpore_hitro"][i], min_stik) for i in range(len(D))])
    # natančno le najboljše in med sabo različne smeri (vsaj ~20° narazen)
    izbrane = []
    for i in np.argsort(hitre):
        if all(D[i] @ D[j] < 0.94 for j in izbrane):
            izbrane.append(int(i))
        if len(izbrane) >= max(kandidatov * 2, 8):
            break

    def opis(i, podpore):
        d = D[i]
        return {
            "gor": [round(float(x), 6) for x in d],
            "rotacija": [round(float(x), 9) for x in rotacija_na_z(d).ravel()],
            "podpore_cm3": round(podpore / 1000.0, 3),
            "previsi_cm2": round(float(merila["previsi"][i]) / 100.0, 2),
            "stik_cm2": round(float(merila["stik"][i]) / 100.0, 2),
            "visina_mm": round(float(merila["visina"][i]), 1),
            "brez_podpor": podpore / 1000.0 < BREZ_PODPOR_CM3,
            "stabilna": bool(merila["stik"][i] >= min_stik * 0.999),
            "ocena": round(_ocena(merila, i, podpore, min_stik), 3),
        }

    kandidati = [opis(i, podpore_natancno(m, D[i], sin_prag)) for i in izbrane]
    kandidati.sort(key=lambda k: k["ocena"])
    kandidati = kandidati[:kandidatov]
    kot_je = opis(0, podpore_natancno(m, D[0], sin_prag))   # D[0] = +Z
    return {"ok": True, "kandidati": kandidati, "kot_je": kot_je, "kot_previsa": kot_previsa,
            "trikotnikov": int(len(m["A"])), "smeri": int(len(D))}
