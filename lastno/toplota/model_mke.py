# -*- coding: utf-8 -*-
"""Poenostavljena kopija sestava boxa za toplotno simulacijo (MKE, CalculiX) — korak 3 iz TOPLOTNA-ANALIZA-PLAN.md.

Iz odprtega sestava (npr. Slim A) prebere okvirje kosov, vrata zasuče v zaprto lego in zgradi nov dokument:
  Plašč (škatla z enakovredno debelino), Steklo in okna LED (spredaj), Zrak (notranjost brez naprav), naprave kot bloki
  (PC, TV, tiskalnik, Mikrotik, elektro plošče, LED, POS, kamera, zvočnik) in Klima kot blok (ponor toplote).
Vsi kosi gredo v Boolean Fragments (skupne ploskve za eno mrežo), nato analiza FEM: CalculiX »pure heat transfer«,
stacionarno; materiali, toplotni viri (W), konvekcija + sonce (DFlux) + sevanje na zunanjih ploskvah, mreža Netgen.

Teče na glavni niti FreeCAD-a (spletni strežnik, ukaz »toplota«) ali v FreeCADCmd. Vhod: nastavitve.json projekta
(razdelka naprave_W in mke), izhod: <Toplota>/mke/<ime> toplota.FCStd + model.json (seznam teles za mke_zagon.py).
"""
import json
import os

import FreeCAD as App
import Part
from FreeCAD import Vector

# kos v sestavu (začetek oznake) -> skupina v modelu; moč iz naprave_W po ključu skupine
SKUPINE = [
    ("ELEKTRO - PC", "PC"), ("Napajalnik za računalnik", "PC"), ("PRINT", "Tiskalnik"), ("Klima Basi ohišje", "Klima"),
    ("MIkrotik nosilec", "Mikrotik"), ("TV Basi", "TV"), ("DISPLAX", "TV"), ("Elektro TV - A", "Elektro TV"),
    ("Elektro levo zgoraj A", "Elektro levo"), ("LED RING", "LED"), ("NEXGO", "POS"), ("Canon M50", "Kamera"),
    ("Steklo basi A", "Steklo"), ("ZVOČNIK", "Zvočnik"),
]
MOC_KLJUC = {"PC": "PC + napajalnik", "TV": "TV", "Tiskalnik": "tiskalnik (povprečje)", "Mikrotik": "Mikrotik",
             "LED": "LED obroči", "POS": "POS in ostalo"}
# material po skupini: (prevodnost W/mK, gostota kg/m3, spec. toplota J/kgK)
MATERIALI = {"Plašč": (12.5, 7850, 480), "Steklo": (0.19, 1190, 1470), "Okno LED": (0.19, 1190, 1470),
             "Zrak": (0.5, 1.15, 1005), "Klima": (50.0, 2700, 900), "naprava": (1.0, 1500, 1000)}
VRATA = "Slim spredaj A"
TECAJ = "42-1-4349"


def _okvir(sh):
    b = sh.BoundBox
    return [b.XMin, b.YMin, b.ZMin, b.XMax, b.YMax, b.ZMax]


def _unija(a, b):
    return [min(a[0], b[0]), min(a[1], b[1]), min(a[2], b[2]), max(a[3], b[3]), max(a[4], b[4]), max(a[5], b[5])]


def _zasukan_okvir(o, os_x, os_y, kot_deg):
    """Okvir zasukan okoli navpične osi (os_x, os_y) — za vrata v zaprto lego."""
    import math
    c, s = math.cos(math.radians(kot_deg)), math.sin(math.radians(kot_deg))
    xs, ys = [], []
    for x in (o[0], o[3]):
        for y in (o[1], o[4]):
            dx, dy = x - os_x, y - os_y
            xs.append(os_x + c * dx - s * dy)
            ys.append(os_y + s * dx + c * dy)
    return [min(xs), min(ys), o[2], max(xs), max(ys), o[5]]


def preberi_sestav(doc):
    """Okvirji kosov sestava (globalno, mm) po skupinah; vrata zasukana v zaprto lego. Vrne slovar za gradnjo."""
    koreni = [o for o in doc.Objects if o.TypeId == "Assembly::AssemblyObject"]
    if not koreni:
        raise ValueError("Dokument ni sestav (ni Assembly::AssemblyObject).")
    koren = koreni[0]
    tecaj = None
    for o in doc.Objects:
        if o.Label.startswith(TECAJ):
            try:
                b = Part.getShape(o).BoundBox
                tecaj = ((b.XMin + b.XMax) / 2, (b.YMin + b.YMax) / 2)
                break
            except Exception:  # noqa: BLE001
                pass
    skupine, vrata_okvir, zadaj_okvir, kapa_okvir = {}, None, None, None
    for sub in koren.getSubObjects():
        try:
            otrok = koren.getSubObject(sub, retType=1)
            sh = Part.getShape(koren, sub, needSubElement=False)
        except Exception:  # noqa: BLE001
            continue
        if otrok is None or sh.isNull() or sh.Volume < 1:
            continue
        oznaka = otrok.Label
        o = _okvir(sh)
        je_vrata = oznaka.startswith(VRATA)
        if je_vrata:
            vrata_okvir = o
        if oznaka.startswith("Slim zadaj A"):
            zadaj_okvir = o
        if oznaka.startswith("Kapa A"):
            kapa_okvir = o
        # kosi na vratih in v podsestavih: vsak podkos posebej
        podkosi = [(oznaka, o)]
        if hasattr(otrok, "getSubObjects") and otrok.getSubObjects():
            podkosi = []
            for sub2 in otrok.getSubObjects():
                try:
                    c2 = koren.getSubObject(sub + sub2, retType=1)
                    sh2 = Part.getShape(koren, sub + sub2, needSubElement=False)
                except Exception:  # noqa: BLE001
                    continue
                if c2 is None or sh2.isNull() or sh2.Volume < 1:
                    continue
                podkosi.append((c2.Label, _okvir(sh2)))
            podkosi.append((oznaka, o))
        for lab, ok in podkosi:
            for zacetek, skupina in SKUPINE:
                if lab.startswith(zacetek):
                    if je_vrata and tecaj:
                        ok = _zasukan_okvir(ok, tecaj[0], tecaj[1], 90)
                    kljuc = (skupina, oznaka)   # ista skupina v drugem podsestavu = drug blok (dve kameri)
                    skupine[kljuc] = _unija(skupine[kljuc], ok) if kljuc in skupine else list(ok)
                    break
    if vrata_okvir is None or zadaj_okvir is None:
        raise ValueError("V sestavu ne najdem »%s« ali »Slim zadaj A«." % VRATA)
    vrata_zaprta = _zasukan_okvir(vrata_okvir, tecaj[0], tecaj[1], 90) if tecaj else vrata_okvir
    kapa = kapa_okvir or zadaj_okvir
    zunanji = [kapa[0], min(vrata_zaprta[1], zadaj_okvir[1]), zadaj_okvir[2],
               kapa[3], max(vrata_zaprta[4], zadaj_okvir[4]), kapa[5]]
    bloki = [{"skupina": k[0], "kos": k[1], "okvir": [round(v, 1) for v in o]} for k, o in skupine.items()]
    bloki.sort(key=lambda b: (b["skupina"], b["kos"]))
    return {"zunanji": [round(v, 1) for v in zunanji], "tecaj": tecaj, "bloki": bloki, "sestav": doc.Label}


def _skatla(o):
    return Part.makeBox(o[3] - o[0], o[4] - o[1], o[5] - o[2], Vector(o[0], o[1], o[2]))


def _presek(a, b):
    return [max(a[0], b[0]), max(a[1], b[1]), max(a[2], b[2]), min(a[3], b[3]), min(a[4], b[4]), min(a[5], b[5])]


def _veljaven(o, najmanj=5.0):
    return o[3] - o[0] >= najmanj and o[4] - o[1] >= najmanj and o[5] - o[2] >= najmanj


def zgradi(doc_sestava, nast, mapa_mke, log=print):
    """Zgradi dokument »<sestav> toplota« z deli, analizo FEM in mrežo; shrani v mapa_mke. Vrne opis (slovar)."""
    os.makedirs(mapa_mke, exist_ok=True)
    pod = preberi_sestav(doc_sestava)
    mke = nast.get("mke", {})
    t = float(mke.get("debelina_plasca_mm", 6))
    sc = mke.get("scenarij", {})
    Z = pod["zunanji"]
    N = [Z[0] + t, Z[1] + t, Z[2] + t, Z[3] - t, Z[4] - t, Z[5] - t]   # notranjost
    N2 = [N[0] + 2, N[1] + 2, N[2] + 2, N[3] - 2, N[4] - 2, N[5] - 2]
    ime = pod["sestav"] + " toplota"
    doc = App.newDocument(ime.replace(" ", "_"))
    doc.Label = ime
    deli = []   # (ime, skupina, oblika)

    # plašč in okna spredaj (Y = Z[1])
    plasc = _skatla(Z).cut(_skatla(N))
    okna = []
    for b in pod["bloki"]:
        o = b["okvir"]
        if b["skupina"] == "Steklo":
            okna.append(("Steklo", "Steklo", [o[0], Z[1], o[2], o[3], Z[1] + t, o[5]]))
        elif b["skupina"] == "LED":
            cx, cz = (o[0] + o[3]) / 2, (o[2] + o[5]) / 2
            okna.append(("Okno LED", "Okno LED", [cx - 50, Z[1], cz - 50, cx + 50, Z[1] + t, cz + 50]))
    for ime_okna, skupina, o in okna:
        o = _presek(o, [Z[0] + t, Z[1], Z[2] + t, Z[3] - t, Z[4], Z[5] - t])
        if not _veljaven(o):
            continue
        sk = _skatla(o)
        plasc = plasc.cut(sk)
        deli.append((ime_okna, skupina, sk))
    deli.insert(0, ("Plašč", "Plašč", plasc))

    # naprave in klima kot bloki v notranjosti
    zrak = _skatla(N)
    moci = nast.get("naprave_W", {})
    stevci = {}
    bloki_opis = []
    for b in pod["bloki"]:
        if b["skupina"] in ("Steklo",):
            continue
        o = _presek(b["okvir"], N2)
        if not _veljaven(o, 8.0):
            continue
        sk = _skatla(o)
        stevci[b["skupina"]] = stevci.get(b["skupina"], 0) + 1
        ime_bloka = b["skupina"] if stevci[b["skupina"]] == 1 else "%s %d" % (b["skupina"], stevci[b["skupina"]])
        deli.append((ime_bloka, b["skupina"], sk))
        bloki_opis.append({"ime": ime_bloka, "skupina": b["skupina"], "kos": b["kos"], "okvir": [round(v, 1) for v in o],
                           "prostornina_l": round(sk.Volume / 1e6, 2)})
        zrak = zrak.cut(sk)
    # preimenuj drugi primerek iste skupine (PC in napajalnik -> oba PC): moč se deli po prostornini
    deli.append(("Zrak", "Zrak", zrak))

    # objekti Part + Boolean Fragments
    objekti = []
    for ime_dela, skupina, sh in deli:
        o = doc.addObject("Part::Feature", ime_dela.replace(" ", "_").replace("š", "s").replace("č", "c"))
        o.Label = ime_dela
        o.Shape = sh
        objekti.append(o)
    import BOPTools.SplitFeatures as SF
    frag = SF.makeBooleanFragments(name="Deli")
    frag.Label = "Deli (Boolean Fragments)"
    frag.Objects = objekti
    frag.Mode = "Standard"
    for o in objekti:
        o.Visibility = False
    doc.recompute()
    sh = frag.Shape
    # telesa fragmentov -> skupine (po težišču)
    telesa = []
    for i, s in enumerate(sh.Solids):
        c = s.CenterOfMass
        zadetek = None
        for ime_dela, skupina, sh0 in deli:
            if ime_dela == "Zrak":
                continue
            if sh0.isInside(c, 0.01, True):
                zadetek = (ime_dela, skupina)
                break
        if zadetek is None:
            zadetek = ("Zrak", "Zrak")
        telesa.append({"indeks": i + 1, "ime": zadetek[0], "skupina": zadetek[1], "prostornina_l": round(s.Volume / 1e6, 3)})
    log("Boolean Fragments: %d teles, %d ploskev" % (len(sh.Solids), len(sh.Faces)))

    # FEM
    import ObjectsFem
    analiza = ObjectsFem.makeAnalysis(doc, "Analiza")
    analiza.Label = "Toplotna analiza"
    solver = ObjectsFem.makeSolverCalculiXCcxTools(doc, "CalculiX")
    solver.AnalysisType = "thermomech"
    solver.ThermoMechType = "pure heat transfer"
    solver.ThermoMechSteadyState = True
    analiza.addObject(solver)
    # materiali: eden na skupino (reference = vsa telesa skupine)
    po_skupinah = {}
    for tel in telesa:
        po_skupinah.setdefault(tel["skupina"], []).append(tel)
    # materiali: naprave en material (zapisovalnik FreeCAD-a za vsak material dela nabore elementov v Pythonu — vsak nabor
    # pri 300k elementih traja minute), toplotni viri ostanejo po telesih
    po_materialih = {}
    for skupina, tels in po_skupinah.items():
        ime_m = skupina if skupina in MATERIALI else "Naprave"
        po_materialih.setdefault(ime_m, []).extend(tels)
    for skupina, tels in po_materialih.items():
        k, rho, cp = MATERIALI.get(skupina, MATERIALI["naprava"])
        if skupina == "Plašč":
            k = float(mke.get("prevodnost_plasca", k))
        mat = ObjectsFem.makeMaterialSolid(doc, "Material_" + skupina.replace(" ", "_"))
        mat.Label = "Material " + skupina
        mat.Material = {"Name": skupina, "Density": "%g kg/m^3" % rho, "ThermalConductivity": "%g W/m/K" % k,
                        "SpecificHeat": "%g J/kg/K" % cp, "YoungsModulus": "1000 MPa", "PoissonRatio": "0.3",
                        "ThermalExpansionCoefficient": "12 um/m/K"}   # mehanske vrednosti zahteva preverjanje, čisti prenos toplote jih ne uporabi
        mat.References = [(frag, "Solid%d" % t_["indeks"]) for t_ in tels]
        analiza.addObject(mat)
    zac = ObjectsFem.makeConstraintInitialTemperature(doc, "Zacetna_temperatura")
    zac.Label = "Začetna temperatura"
    zac.initialTemperature = "%g K" % (float(sc.get("T_zunaj_C", 35)) + 273.15)
    analiza.addObject(zac)
    # toplotni viri: moč skupine deljena po prostornini blokov
    A_steklo = sum((o[3] - o[0]) * (o[5] - o[2]) for _, s_, o in okna if s_ == "Steklo") / 1e6
    tau = float(nast.get("steklo", {}).get("prepustnost", 0.8))
    skozi_steklo = tau * A_steklo * float(sc.get("G_spredaj", 0))
    viri = []
    for skupina, tels in po_skupinah.items():
        P = float(moci.get(MOC_KLJUC.get(skupina, ""), 0) or 0)
        if skupina == "TV":
            P += skozi_steklo
        if skupina == "Klima":
            P = -float(nast.get("hlajenje", {}).get("klima_W", 0) or 0)
        if P == 0:
            continue
        V = sum(t_["prostornina_l"] for t_ in tels) or 1.0
        for t_ in tels:
            vir = ObjectsFem.makeConstraintBodyHeatSource(doc, "Vir_" + t_["ime"].replace(" ", "_"))
            vir.Label = "Vir %s" % t_["ime"]
            vir.Mode = "Total Power"
            vir.TotalPower = "%g W" % (P * t_["prostornina_l"] / V)
            vir.References = [(frag, "Solid%d" % t_["indeks"])]
            analiza.addObject(vir)
            viri.append({"telo": t_["ime"], "W": round(P * t_["prostornina_l"] / V, 1)})
    # zunanje ploskve: konvekcija + sonce + sevanje po straneh
    T_amb = float(sc.get("T_zunaj_C", 35))
    v = float(sc.get("veter_ms", 1.0))
    h = 5.7 + 3.8 * v
    alpha = float(nast.get("plasc", {}).get("barve", {}).get(mke.get("barva", "bela"), 0.25))
    alpha_st = float(nast.get("steklo", {}).get("absorptivnost", 0.1))
    T_sky = 0.0552 * (T_amb + 273.15) ** 1.5 - 273.15
    strani = {"streha": ("z", Z[5], sc.get("G_streha", 0), T_sky),
              "spredaj": ("y", Z[1], sc.get("G_spredaj", 0), (T_sky + T_amb) / 2),
              "zadaj": ("y", Z[4], sc.get("G_zadaj", 0), (T_sky + T_amb) / 2),
              "levo": ("x", Z[0], sc.get("G_bok", 0), (T_sky + T_amb) / 2),
              "desno": ("x", Z[3], sc.get("G_bok", 0), (T_sky + T_amb) / 2)}
    ploskve_strani = {k: [] for k in strani}
    okna_ploskve = []
    for i, f in enumerate(sh.Faces):
        c = f.CenterOfMass
        for ime_s, (os_, vred, _g, _ts) in strani.items():
            if abs(getattr(c, os_) - vred) < 0.01:
                # okno spredaj (steklo) loči po okvirju
                if ime_s == "spredaj" and any(o[0] - 0.1 <= c.x <= o[3] + 0.1 and o[2] - 0.1 <= c.z <= o[5] + 0.1 for _, _, o in okna):
                    okna_ploskve.append("Face%d" % (i + 1))
                else:
                    ploskve_strani[ime_s].append("Face%d" % (i + 1))
                break
    for ime_s, (os_, vred, G, T_s) in strani.items():
        ref = [(frag, f) for f in ploskve_strani[ime_s]]
        if not ref:
            continue
        kon = ObjectsFem.makeConstraintHeatflux(doc, "Konvekcija_" + ime_s)
        kon.Label = "Konvekcija " + ime_s
        kon.ConstraintType = "Convection"
        kon.AmbientTemp = "%g K" % (T_amb + 273.15)
        kon.FilmCoef = "%g W/m^2/K" % h
        kon.References = ref
        analiza.addObject(kon)
        if float(G) > 0:
            son = ObjectsFem.makeConstraintHeatflux(doc, "Sonce_" + ime_s)
            son.Label = "Sonce " + ime_s
            son.ConstraintType = "DFlux"
            son.DFlux = "%g W/m^2" % (alpha * float(G))
            son.References = ref
            analiza.addObject(son)
        sev = ObjectsFem.makeConstraintHeatflux(doc, "Sevanje_" + ime_s)
        sev.Label = "Sevanje " + ime_s
        sev.ConstraintType = "Radiation"
        sev.AmbientTemp = "%g K" % (T_s + 273.15)
        sev.Emissivity = float(nast.get("plasc", {}).get("emisivnost", 0.9))
        sev.References = ref
        analiza.addObject(sev)
    if okna_ploskve:
        ref = [(frag, f) for f in okna_ploskve]
        kon = ObjectsFem.makeConstraintHeatflux(doc, "Konvekcija_okna")
        kon.Label = "Konvekcija okna"
        kon.ConstraintType = "Convection"
        kon.AmbientTemp = "%g K" % (T_amb + 273.15)
        kon.FilmCoef = "%g W/m^2/K" % h
        kon.References = ref
        analiza.addObject(kon)
        if float(sc.get("G_spredaj", 0)) > 0:
            son = ObjectsFem.makeConstraintHeatflux(doc, "Sonce_okna")
            son.Label = "Sonce okna (vpito v steklu)"
            son.ConstraintType = "DFlux"
            son.DFlux = "%g W/m^2" % (alpha_st * float(sc.get("G_spredaj", 0)))
            son.References = ref
            analiza.addObject(son)
    # mreža (izračuna se šele ob zagonu MKE, ne tu)
    # stari (vgrajeni) Netgen: zmreži se ob preračunu v istem procesu, tudi v FreeCADCmd (novi Netgen 1.1 požene zunanji
    # Python z netgen vezavami prek QProcess, ki jih pixi okolje nima)
    mreza = ObjectsFem.makeMeshNetgenLegacy(doc, "Mreza")
    mreza.Label = "Mreža Netgen"
    mreza.Shape = frag
    mreza.MaxSize = float(mke.get("velikost_elementa_mm", 40))
    mreza.SecondOrder = False
    mreza.Fineness = str(mke.get("finost", "VeryCoarse"))   # VeryCoarse … VeryFine; nabori elementov po telesih (getNodesBySolid) rastejo z vozlišči
    analiza.addObject(mreza)
    for o in doc.Objects:
        if o.TypeId.startswith("Fem::") and o is not analiza:
            o.purgeTouched()
    mreza.purgeTouched()
    # moč po blokih (za lastni zapisovalnik v mke_zagon.py): moč skupine deljena po prostornini blokov skupine
    for b_ in bloki_opis:
        P = float(moci.get(MOC_KLJUC.get(b_["skupina"], ""), 0) or 0)
        if b_["skupina"] == "TV":
            P += skozi_steklo
        if b_["skupina"] == "Klima":
            P = -float(nast.get("hlajenje", {}).get("klima_W", 0) or 0)
        V = sum(x["prostornina_l"] for x in bloki_opis if x["skupina"] == b_["skupina"]) or 1.0
        b_["W"] = round(P * b_["prostornina_l"] / V, 1)
    okna_opis = [{"ime": ime_o, "skupina": sk_o, "okvir": [round(v, 1) for v in o]} for ime_o, sk_o, o in okna]
    skupina_obmocja = {b_["ime"]: b_["skupina"] for b_ in bloki_opis}
    skupina_obmocja.update({o_["ime"]: o_["skupina"] for o_ in okna_opis})
    skupina_obmocja.update({"Plašč": "Plašč", "Zrak": "Zrak"})
    materiali = {}
    for ime_o, sk in skupina_obmocja.items():
        k, rho, cp = MATERIALI.get(sk, MATERIALI["naprava"])
        if sk == "Plašč":
            k = float(mke.get("prevodnost_plasca", k))
        elif sk == "Zrak":
            k = float(mke.get("prevodnost_zraka", k))        # efektivna (naravna konvekcija), umeritveni parameter
        elif sk not in MATERIALI:
            k = float(mke.get("prevodnost_naprav", k))       # kovinska ohišja naprav razlivajo toploto po površini
        materiali[ime_o] = {"k": k, "rho": rho, "cp": cp}
    opis = {"sestav": pod["sestav"], "zunanji_mm": Z, "notranji_mm": N, "debelina_mm": t, "tecaj": pod["tecaj"], "bloki": bloki_opis,
            "okna": okna_opis, "skupina_obmocja": skupina_obmocja, "materiali": materiali, "eps": float(nast.get("plasc", {}).get("emisivnost", 0.9)),
            "alpha_steklo": alpha_st, "mke": mke,
            "telesa": telesa, "viri_W": viri, "scenarij": sc, "alpha": alpha, "h": round(h, 2), "T_sky_C": round(T_sky, 1),
            "A_steklo_m2": round(A_steklo, 3), "sonce_skozi_steklo_W": round(skozi_steklo, 1),
            "ploskve": {k: len(v) for k, v in ploskve_strani.items()}, "okna_ploskev": len(okna_ploskve)}
    pot = os.path.join(mapa_mke, ime + ".FCStd")
    doc.saveAs(pot)
    opis["pot"] = pot
    with open(os.path.join(mapa_mke, "model.json"), "w", encoding="utf-8") as f:
        json.dump(opis, f, ensure_ascii=False, indent=1)
    log("model shranjen: %s" % pot)
    return opis, doc
