# -*- coding: utf-8 -*-
"""Gradnja projekta iz SolidWorksa v FreeCAD: vsak del in vsak sestav v isti zgradbi map kot v Dropboxu.
Splošna različica zgradi_darmar.py / zgradi_airpix.py (projekt izbere SW_PROJEKT = ključ iz prenos.json).

Vhod: <delovna>/<projekt>/podatki/struktura.json (sw_preberi.py: drevesa sestavov z legami, podatki modelov, meritve
delov) in STEP vsakega dela (skupna mapa STEP, ime = ključ sha1(pot|konfiguracija)).
Izhod (mapa projekta v Oblaku, ista zgradba kot v Dropboxu):
  <mapa>/<ime>.FCStd                 del: App::Part »Del« z uvoženo geometrijo (barve iz STEP), lastnosti SolidWorks,
                                     pri pločevini še skrita Razgrnitev
  <mapa>/<ime>.FCStd                 sestav: Assembly s povezavami (App::Link) na dele in podsestave, lege iz SolidWorksa
  <mapa>/<ime> (<konfiguracija>).FCStd   del ali sestav v konfiguraciji, ki ni dejavna v datoteki
  <mapa>/<ime> (sestav).FCStd        sestav, ki ima v isti mapi SolidWorks del z istim imenom
  .../Gibljivi podsestavi/<ime> (v <nadsestav>).FCStd   podsestav, ki ima v nadsestavu drugačne lege kosov
Dokument iz mape DRUGEGA projekta (npr. STANDARD BOX v photoboxu) dobi FCStd v mapi tistega projekta (prenos_cfg.ciljna_mapa);
če tam že obstaja, se le poveže. Zunanji deli/ le za poti zunaj PROJEKTI.
Navidezni deli (shranjeni v sestavu SolidWorks) dobijo svojo datoteko v mapi sestava.
Os Z navzgor: SolidWorks ima Y navzgor, zato je vsaka oblika zasukana za +90° okoli X (R), lega v sestavu pa je
R x L x R^-1 (L = lega iz SolidWorksa). Mate se ne prenašajo; vsak sestav ima en talni spoj, lege so točne.

Zagon: v primerku FreeCAD-a z oknom (barve iz STEP) – zagon_gradnje.py v ločenem skritem primerku lastne gradnje.
Gradnja nadaljuje, kjer je ostala (obstoječ FCStd se le odpre); SW_PREGRADI=1 zgradi vse znova.
Pomnilnik: dokumenti se po shranjevanju zapirajo (velike mape imajo tisoče dokumentov).
"""
import hashlib
import json
import os
import re
import sys
import time
import traceback

import FreeCAD as App

TU = os.path.dirname(os.path.abspath(__file__))
if TU not in sys.path:
    sys.path.insert(0, TU)
import prenos_cfg as cfg  # noqa: E402

KLJUC = os.environ.get("SW_PROJEKT") or ""
if not KLJUC:
    raise RuntimeError("SW_PROJEKT (ključ projekta iz prenos.json) ni nastavljen")
MAPA = cfg.cilj(KLJUC)
IZVOR = cfg.izvor(KLJUC)
PODATKI = cfg.podatki(KLJUC)
STEP = cfg.STEP
PREGRADI = os.environ.get("SW_PREGRADI") == "1"
PRIVZETE = {"default", "privzeto", "standard"}
TRANSP = True            # SolidWorks ArrayData: p' = p R + t -> stolpci FreeCAD = vrstice R
NAJVEC_ODPRTIH = 40      # čez to se po shranjevanju sestava zaprejo vsi dokumenti
PRAG_GB = float(os.environ.get("SW_PRAG_GB") or 4)   # zasebni pomnilnik procesa; čez prag se gradnja konča in zažene znova


class PomnilnikPoln(Exception):
    """Proces FreeCAD-a je prerasel prag: zagon_gradnje.py zapiše »pomnilnik«, prenos.py gradnjo nadaljuje v novem procesu."""


def pomnilnik_gb():
    try:
        import ctypes
        from ctypes import wintypes

        class PMC(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
                        ("PrivateUsage", ctypes.c_size_t)]
        pmc = PMC()
        pmc.cb = ctypes.sizeof(PMC)
        ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb)
        return pmc.PrivateUsage / 1e9
    except Exception:  # noqa: BLE001
        return 0.0


def preveri_pomnilnik(kje):
    gb = pomnilnik_gb()
    if gb > PRAG_GB:
        zapri_vse()
        log("POMNILNIK %.1f GB > prag %.1f GB po %s: gradnja se konča in nadaljuje v novem procesu" % (gb, PRAG_GB, kje))
        raise PomnilnikPoln("%.1f GB" % gb)

R = App.Matrix()
R.rotateX(1.5707963267948966)            # SolidWorks Y navzgor -> FreeCAD Z navzgor
R_INV = App.Matrix(R)
R_INV.transpose()                        # rotacija: inverz = transponirana

DNEVNIK = os.path.join(PODATKI, "gradnja.log")
ZADNJI = os.path.join(PODATKI, "zadnji.txt")          # kos, ki se gradi (ob sesutju FreeCAD-a pove, kateri je kriv)
PRESKOCI = os.path.join(PODATKI, "preskoci.json")     # ključ -> število sesutij FreeCAD-a pri tem kosu (piše prenos.py)


def log(*a):
    s = time.strftime("%H:%M:%S ") + " ".join(str(x) for x in a)
    App.Console.PrintMessage("[prenos %s] %s\n" % (KLJUC, s))
    with open(DNEVNIK, "a", encoding="utf-8") as f:
        f.write(s + "\n")


def kljuc(p, c):
    ime = re.sub(r'[<>:"/\\|?*^]', "_", os.path.splitext(os.path.basename(p))[0])
    return "%s__%s" % (ime[:60], hashlib.sha1((p.lower() + "|" + c).encode("utf-8")).hexdigest()[:8])


def cisto(s):
    return re.sub(r'[<>:"/\\|?*]', "_", s).strip(" .")


def ascii_ime(s):
    t = s.translate(str.maketrans("čćšžđČĆŠŽĐ", "ccszdCCSZD"))
    return (re.sub(r"[^A-Za-z0-9_]", "_", t)[:40] or "Dok").strip("_") or "Dok"


def matrika(a):
    t = [x * 1000.0 for x in a[9:12]]
    if TRANSP:
        return App.Matrix(a[0], a[3], a[6], t[0], a[1], a[4], a[7], t[1], a[2], a[5], a[8], t[2], 0, 0, 0, 1)
    return App.Matrix(a[0], a[1], a[2], t[0], a[3], a[4], a[5], t[1], a[6], a[7], a[8], t[2], 0, 0, 0, 1)


def v_z_gor(m):
    return R.multiply(m).multiply(R_INV)


def _nc(p):
    return os.path.normcase(os.path.normpath(p))


# ---------------------------------------------------------------- razvrstitev in imena
def dejavne_konfiguracije(S):
    """pot (mala) -> dejavna konfiguracija: iz vseh že prebranih projektov (del, odprt kjerkoli, ali sestav kot koren)."""
    d = {}
    for p in cfg.vse_strukture():
        try:
            T = json.load(open(p, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for pot, z in T.get("dejavne", {}).items():
            if z.get("dejavna"):
                d[pot] = z["dejavna"]
        for pot, z in T.get("sestavi", {}).items():
            if "cfg" in z:
                d[pot] = z["cfg"]
    for pot, z in S.get("dejavne", {}).items():          # ta projekt ima prednost
        if z.get("dejavna"):
            d[pot] = z["dejavna"]
    for pot, z in S["sestavi"].items():
        if "cfg" in z:
            d[pot] = z["cfg"]
    return d


def ima_soimenjaka(pot):
    """SLDASM, ki ima v isti mapi SolidWorks SLDPRT z istim imenom -> sestav dobi pripono »(sestav)«."""
    if not pot.lower().endswith(".sldasm"):
        return False
    return os.path.exists(os.path.splitext(pot)[0] + ".SLDPRT") or os.path.exists(os.path.splitext(pot)[0] + ".sldprt")


def razvrsti(S):
    """ključ -> zapis (vrsta, pot, cfg, mapa, ime, model, meritve). Vse, kar je v mapi, in vse, kar sestavi rabijo."""
    dejavne = dejavne_konfiguracije(S)
    vse = {}

    def dodaj(k, pot, c, vrsta, navidezno=False, oce=None, ime_dat=None):
        if k in vse:
            return vse[k]
        if navidezno:
            mapa, proj = cfg.ciljna_mapa(oce, KLJUC)
            osnova = ime_dat or os.path.splitext(os.path.basename(pot))[0]
            if "^" in osnova:                                   # Part1^Sestav -> Part1 (Sestav)
                a, b = osnova.split("^", 1)
                osnova = "%s (%s)" % (a, b)
            if c.lower() not in PRIVZETE:
                osnova += " [%s]" % c
        else:
            mapa, proj = cfg.ciljna_mapa(pot, KLJUC)
            osnova = os.path.splitext(os.path.basename(pot))[0]
            dej = dejavne.get(pot.lower())
            if c != dej and not (dej is None and c.lower() in PRIVZETE):
                osnova = "%s (%s)" % (osnova, c)
            if vrsta == "sestav" and ima_soimenjaka(pot):
                osnova += " (sestav)"
        vse[k] = {"kljuc": k, "pot": pot, "cfg": c, "vrsta": vrsta, "navidezno": navidezno, "mapa": mapa,
                  "projekt": proj, "osnova": cisto(osnova), "model": S["modeli"].get(k, {}),
                  "meritve": S["deli"].get(k, {}), "primerkov": 0}
        return vse[k]

    for k, z in S["deli"].items():
        if z.get("navidezno"):
            m = S["modeli"].get(k, {})
            dodaj(k, z["pot"], z["cfg"], "del", True, m.get("oce"), m.get("ime_dat"))
        else:
            dodaj(k, z["pot"], z["cfg"], "del")

    def obhod(vozli):
        for x in vozli:
            if x["zatrto"]:
                continue
            m = S["modeli"].get(x["kljuc"], {})
            z = dodaj(x["kljuc"], x["pot"], x["cfg"], "sestav" if x["vrsta"] == "SESTAV" else "del",
                      x["navidezno"], m.get("oce"), m.get("ime_dat"))
            z["primerkov"] += 1
            obhod(x.get("otroci", []))

    for p, s in S["sestavi"].items():
        if "drevo" in s:
            dodaj(kljuc(s["pot"], s["cfg"]), s["pot"], s["cfg"], "sestav")
            obhod(s["drevo"])
    # enolična imena v mapi; obstoječa datoteka (iz prejšnje gradnje tega ali drugega projekta) obdrži ime
    zasedena = set()
    for k, z in sorted(vse.items(), key=lambda t: (t[1]["navidezno"], t[1]["vrsta"] != "del", t[0])):
        ime, n = z["osnova"], 2
        if z["vrsta"] == "sestav" and not ime.endswith(" (sestav)"):
            if os.path.exists(os.path.join(z["mapa"], ime + " (sestav).FCStd")) and \
                    not os.path.exists(os.path.join(z["mapa"], ime + ".FCStd")):
                ime = z["osnova"] = ime + " (sestav)"              # prejšnja gradnja (DJ DarMar, Airpix) je tako imenovala
            elif (z["mapa"].lower(), ime.lower()) in zasedena:
                ime = z["osnova"] = ime + " (sestav)"
        while (z["mapa"].lower(), ime.lower()) in zasedena:
            ime, n = "%s %d" % (z["osnova"], n), n + 1
        zasedena.add((z["mapa"].lower(), ime.lower()))
        z["ime"] = ime
        z["datoteka"] = os.path.join(z["mapa"], ime + ".FCStd")
    return vse


def definicije_sestavov(S, vse):
    """ključ sestava -> seznam (vozel, lokalna lega SolidWorks) neposrednih otrok.

    Osnovna definicija sestava je njegovo drevo, ko je odprt kot koren (sicer prva pojavitev v drugem sestavu).
    Gibljiv podsestav (vzmet, pant, vodilo, zložljiva polica) ima v nadsestavu lahko drugačne lege otrok kot sam
    zase: taka pojavitev dobi svojo različico »<ime> (v <nadsestav>)« z legami iz te pojavitve. Vozel dobi
    `kljuc_var` = ključ, na katerega naj kaže povezava (osnovni ali različica)."""
    defi = {}
    for p, s in S["sestavi"].items():                       # sestav, odprt kot koren: lege otrok so že lokalne
        if "drevo" in s:
            defi[kljuc(s["pot"], s["cfg"])] = [(x, matrika(x["lega"])) for x in s["drevo"] if x["lega"]]
    # podsestav iz drugega projekta, ki je tam že zgrajen: osnova je njegovo drevo kot koren (iz struktura.json tistega
    # projekta), da pojavitev z drugačno lego kosov (pant, plinska vzmet) dobi različico in ne obvelja za osnovo
    tuji = 0
    for pot_s in cfg.vse_strukture():
        if _nc(pot_s) == _nc(os.path.join(PODATKI, "struktura.json")):
            continue
        try:
            T = json.load(open(pot_s, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for s in T.get("sestavi", {}).values():
            if "drevo" not in s:
                continue
            k = kljuc(s["pot"], s["cfg"])
            if k in defi or k not in vse or not os.path.exists(vse[k]["datoteka"]):
                continue
            defi[k] = [(x, matrika(x["lega"])) for x in s["drevo"] if x["lega"]]
            tuji += 1
    if tuji:
        log("osnovne definicije %d podsestavov iz drugih projektov (datoteke že obstajajo)" % tuji)

    def lokalne(x):
        g_inv = matrika(x["lega"]).inverse()
        return [(o, g_inv.multiply(matrika(o["lega"]))) for o in x.get("otroci", []) if o["lega"]]

    def prve(vozli):
        for x in vozli:
            if x["zatrto"]:
                continue
            if x["vrsta"] == "SESTAV" and x["kljuc"] not in defi and x["lega"]:
                defi[x["kljuc"]] = lokalne(x)
            prve(x.get("otroci", []))

    for s in S["sestavi"].values():
        prve(s.get("drevo", []))

    razlicice = {}
    po_osnovi = {}

    def enako(sa, sb):
        """Ali sta poddrevesi enaki (ista imena, zatrtost, ključi, lokalne lege v toleranci, rekurzivno)."""
        a = {o["ime"].split("/")[-1]: (o, M) for o, M in sa}
        b = {o["ime"].split("/")[-1]: (o, M) for o, M in sb}
        if a.keys() != b.keys():
            return False
        for ime, (oa, ma) in a.items():
            ob, mb = b[ime]
            if bool(oa["zatrto"]) != bool(ob["zatrto"]) or oa["kljuc"] != ob["kljuc"]:
                return False
            if oa["zatrto"]:
                continue
            if max(abs(ma.A[i] - mb.A[i]) for i in (3, 7, 11)) > 0.01:
                return False
            if max(abs(ma.A[i] - mb.A[i]) for i in (0, 1, 2, 4, 5, 6, 8, 9, 10)) > 1e-5:
                return False
            if oa["vrsta"] == "SESTAV" and not enako(lokalne(oa), lokalne(ob)):
                return False
        return True

    def nadrejeni(vozli, nad):
        for x in vozli:
            x["_nad"] = nad
            nadrejeni(x.get("otroci", []), vse.get(x["kljuc"], {}).get("osnova", nad)
                      if x["vrsta"] == "SESTAV" else nad)

    for s in S["sestavi"].values():
        if "drevo" in s:
            nadrejeni(s["drevo"], vse.get(kljuc(s["pot"], s["cfg"]), {}).get("osnova"))

    def ucinkovit(o):
        if o["vrsta"] != "SESTAV" or o["zatrto"] or not o["lega"]:
            return o["kljuc"]
        if "kljuc_var" not in o:
            k = o["kljuc"]
            sez = lokalne(o)
            if k not in defi or enako(sez, defi[k]):
                o["kljuc_var"] = k
            else:
                for vk in po_osnovi.get(k, []):
                    if enako(sez, defi[vk]):
                        o["kljuc_var"] = vk
                        break
                else:
                    vk = "%s~%d" % (k, len(po_osnovi.get(k, [])) + 1)
                    po_osnovi.setdefault(k, []).append(vk)
                    defi[vk] = sez
                    razlicice[vk] = (k, sez, o.get("_nad"))
                    o["kljuc_var"] = vk
        return o["kljuc_var"]

    def vsi(vozli):
        for x in vozli:
            ucinkovit(x)
            vsi(x.get("otroci", []))

    for s in S["sestavi"].values():
        vsi(s.get("drevo", []))
    # različice: zapis za gradnjo v podmapi »Gibljivi podsestavi« ob osnovnem sestavu, enolično ime
    zasedena = set()
    for vk, (osnovni, sez, nad) in sorted(razlicice.items(), key=lambda t: (t[1][0], int(t[0].rsplit("~", 1)[1]))):
        b = vse[osnovni]
        mapa = os.path.join(b["mapa"], "Gibljivi podsestavi")
        osnova = cisto("%s (v %s)" % (b["osnova"], nad or "drugem sestavu"))
        ime, n = osnova, 2
        while (mapa.lower(), ime.lower()) in zasedena:
            ime, n = "%s %d" % (osnova, n), n + 1
        zasedena.add((mapa.lower(), ime.lower()))
        z = dict(b, kljuc=vk, osnova=osnova, ime=ime, mapa=mapa, razlicica_od=b["ime"], primerkov=0,
                 datoteka=os.path.join(mapa, ime + ".FCStd"))
        for odv in ("dok", "objekt", "opombe", "manjka", "zatrto_izpusceno"):
            z.pop(odv, None)
        vse[vk] = z
    return defi


# ---------------------------------------------------------------- dokumenti
def odprt_dok(pot):
    for d in App.listDocuments().values():
        if d.FileName and _nc(d.FileName) == _nc(pot):
            return d
    return None


def odpri(pot):
    return odprt_dok(pot) or App.openDocument(pot, True)


def zapri_vse():
    for d in list(App.listDocuments().values()):
        try:
            App.closeDocument(d.Name)
        except Exception:  # noqa: BLE001
            pass


def nov_dok(ime):
    doc = App.newDocument(ascii_ime(ime))
    doc.Label = ime
    return doc


def shrani(doc, pot):
    """Shrani; odjemalec oblaka nove datoteke med nalaganjem za hip zaklene (FreeCAD potem zavrne shranjevanje)."""
    os.makedirs(os.path.dirname(pot), exist_ok=True)
    for poskus in range(20):
        try:
            doc.saveAs(pot)
            break
        except OSError:
            if poskus == 19:
                raise
            time.sleep(1.5)
    if App.GuiUp:
        import FreeCADGui
        FreeCADGui.getDocument(doc.Name).Modified = False


def oznaci(obj, z):
    m = z["model"]
    vrsta = "sestav" if z["vrsta"] == "sestav" else ("pločevina" if "FlatPattern" in m.get("tipi", []) else "del")
    if z["navidezno"]:
        vrsta += " (navidezni v SolidWorksu)"
    for ime, vrednost in (("Izvor", z["pot"] if not z["navidezno"] else "%s v %s" % (z["osnova"], m.get("oce", ""))),
                          ("Konfiguracija", z["cfg"]), ("MaterialSW", m.get("material") or ""), ("Vrsta", vrsta)):
        if ime not in obj.PropertiesList:
            obj.addProperty("App::PropertyString", ime, "SolidWorks", "Podatek iz SolidWorksa")
        setattr(obj, ime, vrednost)
    pl = m.get("plocevina")
    if pl and "T" in pl:
        for ime, vrednost, opis in (("Debelina", pl["T"], "debelina pločevine"),
                                    ("Polmer", pl["R"], "notranji polmer upogiba")):
            if ime not in obj.PropertiesList:
                obj.addProperty("App::PropertyLength", ime, "SolidWorks", opis)
            setattr(obj, ime, vrednost)
        if "KFaktor" not in obj.PropertiesList:
            obj.addProperty("App::PropertyFloat", "KFaktor", "SolidWorks", "K-faktor iz SolidWorksa")
        obj.KFaktor = pl["K"]
    lastn = {a: b for a, b in (m.get("lastnosti") or {}).items() if b}
    if lastn:
        if "LastnostiSW" not in obj.PropertiesList:
            obj.addProperty("App::PropertyMap", "LastnostiSW", "SolidWorks", "lastnosti po meri iz SolidWorksa")
        obj.LastnostiSW = {str(a): str(b) for a, b in lastn.items()}


def tarca_dela(doc):
    o = doc.getObject("Del")
    if o is not None:
        return o
    for o in doc.Objects:
        if "Izvor" in o.PropertiesList:
            return o
    return doc.RootObjects[0]


def tarca_sestava(doc):
    for o in doc.Objects:
        if o.TypeId == "Assembly::AssemblyObject":
            return o
    return doc.getObject("Assembly")


def zgradi_del(z):
    import ImportGui
    pot = z["datoteka"]
    if os.path.exists(pot) and not (PREGRADI and z.get("projekt") == KLJUC):
        doc = odpri(pot)
        z["dok"], z["objekt"] = doc.Name, tarca_dela(doc).Name
        z["obstojec"] = True
        return doc
    step = os.path.join(STEP, z["kljuc"] + ".step")
    if not os.path.exists(step):
        raise RuntimeError("ni STEP (%s)" % (z["meritve"].get("napaka") or z["meritve"].get("koda")))
    doc = nov_dok(z["ime"])
    ImportGui.insert(step, doc.Name)
    doc.recompute()
    koreni = [o for o in doc.RootObjects if not o.TypeId.startswith("App::Origin")]
    if not koreni:
        raise RuntimeError("STEP je prazen")
    # uvoz STEP naredi App::Part z imenom izdelka (šumniki, ključ) in v njem telesa: telesa se prestavijo v »Del«
    # (z isto globalno lego, zasukano pokonci), uvoženi vsebnik se odstrani
    tarca = doc.addObject("App::Part", "Del")
    telesa = []
    for o in koreni:
        if o.TypeId == "App::Part":
            m0 = o.Placement.toMatrix()
            otroci = [c for c in o.Group if not c.TypeId.startswith("App::Origin")]
            for c in otroci:
                o.removeObject(c)
                c.Placement = App.Placement(R.multiply(m0).multiply(c.Placement.toMatrix()))
                telesa.append(c)
            doc.removeObject(o.Name)
        else:
            o.Placement = App.Placement(R.multiply(o.Placement.toMatrix()))
            telesa.append(o)
    for i, c in enumerate(telesa):
        tarca.addObject(c)
        c.Label = "Telo" if len(telesa) == 1 else "Telo %d" % (i + 1)
    tarca.Label = z["ime"]
    oznaci(tarca, z)
    doc.recompute()
    if z.get("brez_razgrnitve"):
        z.setdefault("opombe", []).append("razgrnitev izpuščena: FreeCAD se je pri njej sesul")
    elif "FlatPattern" in z["model"].get("tipi", []):
        try:
            import lastna_plocevina as lp
            kos = max((o for o in doc.Objects if o.isDerivedFrom("Part::Feature") and o.Shape.Solids),
                      key=lambda o: o.Shape.Volume)
            razg = doc.addObject("Part::FeaturePython", "Razgrnitev")
            lp.Razgrnitev(razg, kos)
            if App.GuiUp:
                lp.PogledRazgrnitve(razg.ViewObject)
            razg.KFaktor = float((z["model"].get("plocevina") or {}).get("K", 0.44))
            razg.Label = z["ime"] + " – razgrnitev"
            razg.Visibility = False
            doc.recompute()
            if "Invalid" in razg.State or razg.Shape.isNull():
                raise RuntimeError(razg.getStatusString() or "razgrnitev ni uspela")
            bb = razg.Shape.BoundBox
            z["razgrnitev"] = [round(bb.XLength, 1), round(bb.YLength, 1)]
        except Exception as e:  # noqa: BLE001
            z.setdefault("opombe", []).append("razgrnitev ni uspela: %s" % str(e).splitlines()[0][:120])
            for o in list(doc.Objects):
                if o.Name.startswith("Razgrnitev"):
                    doc.removeObject(o.Name)
    shrani(doc, pot)
    z["dok"], z["objekt"] = doc.Name, tarca.Name
    return doc


def talni_spoj(asm, obj):
    try:
        import JointObject
        sk = [o for o in asm.Group if o.TypeId == "Assembly::JointGroup"][0]
        g = sk.newObject("App::FeaturePython", "GroundedJoint")
        JointObject.GroundedJoint(g, obj)
        if App.GuiUp:
            JointObject.ViewProviderGroundedJoint(g.ViewObject)
    except Exception as e:  # noqa: BLE001
        log("talni spoj ni uspel:", e)


def zgradi_sestav(z, otroci, vse):
    pot = z["datoteka"]
    lasten = z.get("projekt") == KLJUC or bool(z.get("razlicica_od"))
    if os.path.exists(pot) and not (lasten and (PREGRADI or os.environ.get("SW_PREGRADI_SESTAVE") == "1")):
        doc = odpri(pot)                 # sestav drugega projekta se nikoli ne gradi znova (njegova osnova je tam)
        z["dok"], z["objekt"] = doc.Name, tarca_sestava(doc).Name
        z["obstojec"] = True
        return doc
    doc = nov_dok(z["ime"])
    asm = doc.addObject("Assembly::AssemblyObject", "Assembly")
    asm.Type = "Assembly"
    asm.newObject("Assembly::JointGroup", "Joints")
    asm.Label = z["ime"]
    oznaci(asm, z)
    shrani(doc, pot)                    # povezava na drug dokument potrebuje pot (relativni sklic)
    prvi = None
    for x, lokalna in otroci:
        c = vse.get(x.get("kljuc_var") or x["kljuc"])
        if c is None or not os.path.exists(c.get("datoteka", "")):
            # zatrta komponenta, ki je ni v mapi projekta, se ne prenese (v SolidWorksu ni naložena)
            z.setdefault("zatrto_izpusceno" if x["zatrto"] else "manjka", []).append(x["ime"])
            continue
        cd = odpri(c["datoteka"])
        tarca = (tarca_sestava(cd) if c["vrsta"] == "sestav" else tarca_dela(cd))
        link = asm.newObject("App::Link", "Link")
        link.LinkedObject = tarca
        link.Label = x["ime"].split("/")[-1] + (" (zatrto)" if x["zatrto"] else "")
        link.Placement = App.Placement(v_z_gor(lokalna))
        link.Visibility = not (x["skrito"] or x["zatrto"])   # zatrto v SolidWorksu = skrito v FreeCAD-u
        if x["zatrto"]:
            link.addProperty("App::PropertyBool", "ZatrtoSW", "SolidWorks", "komponenta je v SolidWorksu zatrta")
            link.ZatrtoSW = True
        elif prvi is None:
            prvi = link
    if prvi is not None:
        talni_spoj(asm, prvi)
    doc.recompute()
    shrani(doc, pot)
    z["dok"], z["objekt"] = doc.Name, asm.Name
    return doc


def zadnji(z=None):
    with open(ZADNJI, "w", encoding="utf-8") as f:
        if z is not None:
            json.dump({"kljuc": z["kljuc"], "ime": z["ime"], "vrsta": z["vrsta"], "datoteka": z["datoteka"]}, f, ensure_ascii=False)


def preskoceni():
    try:
        return dict(json.load(open(PRESKOCI, encoding="utf-8")))
    except Exception:  # noqa: BLE001
        return {}


def zgradi():
    for p in (os.path.join(App.getUserAppDataDir(), "Mod", "lastna_plocevina"),
              os.path.join(App.getUserAppDataDir(), "Mod", "sheetmetal")):
        if p not in sys.path:
            sys.path.append(p)
    S = json.load(open(os.path.join(PODATKI, "struktura.json"), encoding="utf-8"))
    vse = razvrsti(S)
    defi = definicije_sestavov(S, vse)
    deli = [z for z in vse.values() if z["vrsta"] == "del"]
    log("projekt %s -> %s: delov %d, sestavov %d (definicij %d)" % (KLJUC, MAPA, len(deli), len(vse) - len(deli), len(defi)))
    samo_deli = os.environ.get("SW_SAMO_DELI") == "1"         # preizkus: le deli, ki že imajo STEP
    omeji = int(os.environ.get("SW_OMEJI") or 0)
    narejenih = 0
    presk = preskoceni()
    for i, z in enumerate(sorted(deli, key=lambda z: z["datoteka"])):
        if samo_deli and not os.path.exists(os.path.join(STEP, z["kljuc"] + ".step")):
            continue
        if omeji and narejenih >= omeji:
            break
        sesutij = presk.get(z["kljuc"], 0)
        if sesutij >= 2 and not os.path.exists(z["datoteka"]):
            z.setdefault("opombe", []).append("preskočeno: FreeCAD se je pri uvozu tega kosa sesul (%d-krat)" % sesutij)
            log("PRESKOČEN del (sesutje)", z["ime"])
            continue
        if sesutij == 1:
            z["brez_razgrnitve"] = True
        narejenih += 1
        t0 = time.time()
        try:
            zadnji(z)
            doc = zgradi_del(z)
            zadnji()
            if not z.get("obstojec"):
                log("del %d/%d %s (%.1f s)" % (i + 1, len(deli), os.path.relpath(z["datoteka"], cfg.CILJ_KOREN),
                                               time.time() - t0))
            App.closeDocument(doc.Name)
            if i % 25 == 0:
                preveri_pomnilnik("delu %d" % (i + 1))
        except PomnilnikPoln:
            raise
        except Exception:  # noqa: BLE001
            z.setdefault("opombe", []).append("uvoz ni uspel: " + traceback.format_exc().splitlines()[-1])
            log("NAPAKA del", z["ime"], z["opombe"][-1])
    zapri_vse()

    if samo_deli:
        log("KONEC preizkusa (samo deli: %d)" % narejenih)
        return

    def globina(k, pot=()):
        if k in pot:
            return 0
        return 1 + max([globina(x.get("kljuc_var") or x["kljuc"], pot + (k,)) for x, _ in defi.get(k, [])
                        if x["vrsta"] == "SESTAV"] or [0])

    sestavi = sorted((z for z in vse.values() if z["vrsta"] == "sestav"), key=lambda z: globina(z["kljuc"]))
    for z in sestavi:
        if z["kljuc"] not in defi:
            z.setdefault("opombe", []).append("drevo sestava ni prebrano")
            log("PRESKOČEN sestav brez drevesa", z["ime"])
            continue
        if presk.get(z["kljuc"], 0) >= 1 and not os.path.exists(z["datoteka"]):
            z.setdefault("opombe", []).append("preskočeno: FreeCAD se je pri gradnji tega sestava sesul")
            log("PRESKOČEN sestav (sesutje)", z["ime"])
            continue
        try:
            zadnji(z)
            zgradi_sestav(z, defi[z["kljuc"]], vse)
            zadnji()
            if not z.get("obstojec"):
                log("sestav %s%s" % (os.path.relpath(z["datoteka"], cfg.CILJ_KOREN),
                                     (" (manjka: %s)" % ", ".join(z["manjka"])) if z.get("manjka") else ""))
        except PomnilnikPoln:
            raise
        except Exception:  # noqa: BLE001
            z.setdefault("opombe", []).append("gradnja ni uspela: " + traceback.format_exc().splitlines()[-1])
            log("NAPAKA sestav", z["ime"], z["opombe"][-1])
        if len(App.listDocuments()) > NAJVEC_ODPRTIH:
            zapri_vse()
        preveri_pomnilnik("sestavu %s" % z["ime"])
    zapri_vse()
    rez = {k: {kk: vv for kk, vv in z.items() if kk not in ("model",)} for k, z in vse.items()}
    json.dump(rez, open(os.path.join(PODATKI, "rezultat.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    log("KONEC gradnje")


if __name__ == "__main__":
    zgradi()
