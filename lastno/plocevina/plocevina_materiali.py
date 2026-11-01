# -*- coding: utf-8 -*-
"""Parametri upogiba pločevine po materialu in debelini: odprtina matrice V, notranji polmer R, K-faktor, najkrajši krak,
sila. Vir: Amada, katalog upogibnih orodij AFH 2024 (tabela za prosto krivljenje, str. 74; katalog v
``Oblak/3D modeliranje/Standardni deli/_Proizvajalci/Amada/``), The Fabricator in WILA za deleže V in pravila; K-faktorji iz
``lastno/raziskava/plocevina.md`` §1.1. Zavezujoče vrednosti da delavnica, ki kose krivi; tukajšnje so izhodišče za model.

Pravilo (Amada): V = 6 T do 3 mm, 8 T od 3 do 8 mm, 10 T od 8 do 12 mm, 12 T nad 12 mm. Pri prostem krivljenju notranji
polmer določa odprtina V (R ≈ delež · V po materialu), ne klin; klin je oster (R0,6–R0,8) do debeline ~3 mm, pri debelejši
pločevini R ≥ 0,63 T (klini R3, R5, R6 iz kataloga). Polmer v modelu je zaokrožen na pol milimetra in ni manjši od
najmanjšega dovoljenega za material.

Uporaba iz skript (prek ``izvedi.py`` ali orodja ``python``)::

    from plocevina_materiali import parametri, mere_plocevine
    p = parametri("Al 5754-H22", 2.0)      # {'V': 12, 'R': 2.0, 'K': 0.40, 'KTabela': '1:0.40; 3:0.50', ...}
    mere_plocevine(mere, "Al 5754-H22", 2.0)   # na objekt »Mere« vpiše Debelina, Polmer, KTabela, KFaktor, Material, V

Ključi materialov so v ``MATERIALI``; ``najdi("inox")`` poišče ključ po delu imena (tudi 1.4301, DC01, 5754 …).
"""
import math

# material: Rm [N/mm²], delež R/V, najmanjši R/T, K-tabela (R/T: K; največ dve vrstici zaradi napake interpolacije v
# SheetMetal V2), faktor sile proti jeklu 450, opis
MATERIALI = {
    "Jeklo S235 / DC01": dict(rm=450, delez_v=0.16, r_min_t=0.8, k=((1.0, 0.42), (3.0, 0.46)), sila=1.0,
                              opis="konstrukcijsko jeklo, hladno (DC01, EN 10131) ali toplo valjano (S235JR, EN 10051)",
                              iskanje=("jeklo", "s235", "dc01", "s355", "steel", "železo", "zelezo", "pocinkan", "dx51")),
    "Nerjavno 1.4301": dict(rm=700, delez_v=0.20, r_min_t=1.0, k=((1.0, 0.43), (3.0, 0.47)), sila=1.5,
                            opis="nerjavno jeklo 1.4301 (AISI 304) ali 1.4404 (316L), 2B",
                            iskanje=("nerjav", "inox", "1.4301", "1.4404", "304", "316", "stainless", "ainox")),
    "Al 5754-H22": dict(rm=220, delez_v=0.14, r_min_t=1.0, k=((1.0, 0.40), (3.0, 0.50)), sila=0.55,
                        opis="aluminij EN AW-5754 H22 (AlMg3), mehka zlitina za krivljenje; enako 5052-H32",
                        iskanje=("5754", "almg3", "5052", "aluminij", "alu", "al ", "al,", "aluminium", "aluminum")),
    "Al 6082-T6": dict(rm=310, delez_v=0.14, r_min_t=3.0, k=((1.0, 0.42), (3.0, 0.45)), sila=0.8,
                       opis="aluminij EN AW-6082 T6 (ali 6061-T6), trda zlitina: krivi se le z velikim polmerom",
                       iskanje=("6082", "6061", "t6", "almgsi")),
    "Baker / medenina": dict(rm=300, delez_v=0.16, r_min_t=1.0, k=((1.0, 0.36), (3.0, 0.42)), sila=0.7,
                             opis="baker (pol trd) ali medenina CuZn37 (pol trda)",
                             iskanje=("baker", "medenina", "cu", "ms63", "cuzn")),
}
PRIVZETI = "Jeklo S235 / DC01"

# Amada: V po debelini (tabela sil pri prostem krivljenju), standardne odprtine matric iz iste tabele
ODPRTINE_V = (4, 6, 7, 8, 10, 12, 14, 16, 18, 20, 25, 32, 40, 50, 63, 80, 100, 125, 160, 200, 250)


def najdi(ime):
    """Ključ v ``MATERIALI`` po delu imena (»inox«, »Al EN AW-5754 H22«, »DC01 2 mm«); None, če ni ujemanja."""
    if not ime:
        return None
    s = ime.lower()
    if ime in MATERIALI:
        return ime
    for kljuc, m in MATERIALI.items():
        if kljuc.lower() == s:
            return kljuc
    for kljuc, m in MATERIALI.items():   # trde zlitine pred mehkimi, da »6082« ne zadene »al«
        if any(x in s for x in m["iskanje"] if x not in ("al ", "al,", "alu", "aluminij", "aluminium", "aluminum", "cu")):
            return kljuc
    for kljuc, m in MATERIALI.items():
        if any(x in s for x in m["iskanje"]):
            return kljuc
    return None


def odprtina_v(t):
    """Priporočena odprtina matrice V (Amada: 6 T do 3 mm, 8 T do 8 mm, 10 T do 12 mm, sicer 12 T), zaokrožena na
    najbližjo standardno odprtino."""
    k = 6 if t <= 3 else 8 if t <= 8 else 10 if t <= 12 else 12
    v = k * t
    return min(ODPRTINE_V, key=lambda x: (abs(x - v), -x))


def polmer(material, t, v=None):
    """Notranji polmer upogiba v modelu: delež odprtine V po materialu, zaokrožen na 0,5 mm navzgor, najmanj najmanjši
    polmer materiala (r_min_t · T) in najmanj 0,5 mm."""
    m = MATERIALI[najdi(material) or PRIVZETI]
    v = v or odprtina_v(t)
    r = max(m["delez_v"] * v, m["r_min_t"] * t, 0.5)
    return math.ceil(r * 2 - 1e-9) / 2


def k_faktor(material, t, r):
    """K (ANSI) pri razmerju R/T iz dvovrstične tabele materiala (pod prvo vrstico prva vrednost, nad zadnjo zadnja)."""
    m = MATERIALI[najdi(material) or PRIVZETI]
    (rt1, k1), (rt2, k2) = m["k"]
    rt = r / t
    if rt <= rt1:
        return k1
    if rt >= rt2:
        return k2
    return round(k1 + (k2 - k1) * (rt - rt1) / (rt2 - rt1), 3)


def k_tabela(material):
    """Niz za lastnost ``KTabela`` objekta Razgrnitev (»1:0.40; 3:0.50«)."""
    m = MATERIALI[najdi(material) or PRIVZETI]
    return "; ".join("%g:%.2f" % (rt, k) for rt, k in m["k"])


def najkrajsi_krak(v):
    """Najkrajši krak (prirobnica) pri odprtini V: ≈ 0,7 V (Amada: 2,8 pri V4 … 5,5 pri V8, 7 pri V10, 11 pri V16, 14 pri V20)."""
    return round(0.7 * v, 1)


def sila(material, t, v, dolzina_m=1.0):
    """Sila upogiba [kN] za dolžino ``dolzina_m`` metrov: P = 650 · T² · L / V za jeklo 450, pomnoženo s faktorjem materiala."""
    m = MATERIALI[najdi(material) or PRIVZETI]
    return round(650 * t * t * dolzina_m / v * m["sila"], 1)


def klin(t, r):
    """Priporočen klin Amada: ostri R0,6 (R0,8 pri jeklu 1,5–3 mm), pri debelejši pločevini R ≥ 0,63 T (R3, R5, R6)."""
    if t <= 1.5:
        return "86°/88° R0,6"
    if t <= 3:
        return "86°/88° R0,6 ali R0,8"
    if t <= 4.5:
        return "86° R3 (standardni 804/904, raven, 1000 kN/m)"
    return "60° R5 ali R6 (ravni 803/603, 1000 kN/m; labodji vrat ne zdrži)"


def parametri(material, t, v=None, r=None):
    """Vsi parametri upogiba za material in debelino: V, R, K, KTabela, najkrajši krak, sila na meter, klin, opis.
    ``v`` ali ``r`` podata vrednost delavnice (potrjena matrica ali polmer), ostalo se preračuna iz njiju."""
    kljuc = najdi(material) or PRIVZETI
    m = MATERIALI[kljuc]
    v = v or odprtina_v(t)
    r = r or polmer(kljuc, t, v)
    k = k_faktor(kljuc, t, r)
    return {
        "material": kljuc, "opis": m["opis"], "T": t, "V": v, "R": r, "K": k, "KTabela": k_tabela(kljuc),
        "krak": najkrajsi_krak(v), "sila_kN_m": sila(kljuc, t, v), "klin": klin(t, r),
        "luknja_do_upogiba": round(2 * t + r, 1), "razbremenitev": round(r + t + 0.5, 1),
    }


def opis(material, t, v=None, r=None):
    """Kratek izpis parametrov za pogovor ali PREBERI.txt."""
    p = parametri(material, t, v, r)
    return ("%s, T %g mm: V%g, notranji R %g (R/T %.2f), K %.2f (tabela %s), najkrajši krak %g mm, sila ≈ %g kN/m "
            "(%.1f t/m), klin %s; luknja ≥ %g mm od upogiba, razbremenitev %g mm."
            % (p["material"], t, p["V"], p["R"], p["R"] / t, p["K"], p["KTabela"], p["krak"], p["sila_kN_m"],
               p["sila_kN_m"] / 9.81, p["klin"], p["luknja_do_upogiba"], p["razbremenitev"]))


def mere_plocevine(mere, material, t, v=None, r=None, skupina="Mere"):
    """Na objekt »Mere« kosa vpiše lastnosti pločevine (ustvari manjkajoče): Debelina, Polmer, KFaktor, KTabela, Material,
    OdprtinaV, Klin. Vrne slovar ``parametri``. Skripte kosov naj polmer in K berejo od tod, ne iz števil v kodi."""
    p = parametri(material, t, v, r)

    def lastnost(tip, ime, vrednost, opis_):
        if ime not in mere.PropertiesList:
            mere.addProperty(tip, ime, skupina, opis_)
        setattr(mere, ime, vrednost)
    lastnost("App::PropertyLength", "Debelina", p["T"], "Debelina pločevine")
    lastnost("App::PropertyLength", "Polmer", p["R"], "Notranji polmer upogibov (iz V in materiala)")
    lastnost("App::PropertyFloat", "KFaktor", p["K"], "K-faktor (ANSI) pri tem R/T")
    lastnost("App::PropertyString", "KTabela", p["KTabela"], "K po R/T za razgrnitev")
    lastnost("App::PropertyString", "Material", p["material"], "Material in stanje")
    lastnost("App::PropertyLength", "OdprtinaV", p["V"], "Odprtina matrice V (Amada)")
    lastnost("App::PropertyString", "Klin", p["klin"], "Priporočen klin (Amada)")
    return p


if __name__ == "__main__":
    for mat, t in (("Al 5754-H22", 2.0), ("inox", 1.4), ("inox", 4.0), ("inox", 5.0), ("inox", 6.0), ("DC01", 1.5),
                   ("DC01", 2.0), ("S235", 3.0), ("6082", 2.0)):
        print(opis(mat, t))
