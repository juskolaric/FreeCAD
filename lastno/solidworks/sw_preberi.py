# -*- coding: utf-8 -*-
"""Branje cele mape SolidWorks (samo branje; izvorne datoteke se ne spreminjajo) za prenos v naš FreeCAD.
Splošna različica skript sw_darmar.py / sw_airpix.py (DJ DarMar 16. 10., Airpix 6.–7. 11. 2026).

1) sestavi: vsak SLDASM v mapi se odpre kot koren; zapiše se celo drevo komponent (ime, pot, konfiguracija, lega
   glede na koren, zatrto, skrito, navidezno), podatki modelov (pločevina, material, lastnosti po meri) in število mat.
   Navidezni deli (shranjeni v sestavu) se izvozijo v STEP kar iz sestava.
2) deli: vsak SLDPRT v mapi (dejavna konfiguracija) in vsak del iz dreves (tudi zunaj mape, v uporabljeni
   konfiguraciji) -> STEP (AP214 z barvami), prostornina, težišče in okvir (kontrola uvoza v FreeCAD).
3) risbe: SLDDRW brez PDF-ja z istim imenom -> PDF.
Nadaljuje, kjer je ostal (stanje v <podatki>/struktura.json se shrani po vsakem dokumentu).
SolidWorks teče brez okna in se vsakih NA_ZAGON dokumentov zažene znova (pomnilnik).
STEP vseh projektov gre v ENO mapo (ime = ključ sha1(pot|konfiguracija)), zato se isti kos iz več projektov izvozi enkrat.

Uporaba: python sw_preberi.py <mapa SolidWorks (izvor)> <mapa podatkov> <mapa STEP>
Okolje: SW_SESTAVI_ZNOVA=1 prebere drevesa sestavov znova (deli in risbe ostanejo); SW_NA_ZAGON=N;
SW_BREZ_PODMAP=podmapa;podmapa (relativno na izvor) se izpustijo (so svoj projekt). Konec = <podatki>/preberi.konec.
"""
import hashlib
import json
import os
import re
import sys
import time
import traceback
import types

import pythoncom
from win32com.client import VARIANT, dynamic

IZVOR, PODATKI, STEP = (os.path.abspath(a) for a in sys.argv[1:4])   # SolidWorks relativne poti razreši po svoje
if not os.path.isdir(IZVOR):
    raise SystemExit("izvorna mapa ne obstaja: " + IZVOR)
STANJE = os.path.join(PODATKI, "struktura.json")
NA_ZAGON = int(os.environ.get("SW_NA_ZAGON") or 40)

os.makedirs(PODATKI, exist_ok=True)
os.makedirs(STEP, exist_ok=True)


def log(*a):
    s = time.strftime("%Y-%m-%d %H:%M:%S ") + " ".join(str(x) for x in a)
    print(s, flush=True)
    with open(os.path.join(PODATKI, "sw.log"), "a", encoding="utf-8") as f:
        f.write(s + "\n")


def v(obj, ime):
    """Lastnost ali metoda brez argumentov (pozna vezava COM ju ne loči vedno)."""
    a = getattr(obj, ime)
    return a() if isinstance(a, (types.MethodType, types.FunctionType)) else a


def kljuc(p, cfg):
    ime = re.sub(r'[<>:"/\\|?*^]', "_", os.path.splitext(os.path.basename(p))[0])
    return "%s__%s" % (ime[:60], hashlib.sha1((p.lower() + "|" + cfg).encode("utf-8")).hexdigest()[:8])


def kljuc_navideznega(oce, pot, cfg):
    """Navidezna komponenta ima začasno pot, ki se ob vsakem odprtju spremeni: ključ = sestav + ime datoteke."""
    return kljuc("navidezni:" + oce.lower() + "|" + os.path.basename(pot), cfg)


if os.path.exists(STANJE):
    S = json.load(open(STANJE, encoding="utf-8"))
    if os.environ.get("SW_SESTAVI_ZNOVA") == "1":      # drevesa sestavov znova (deli in risbe ostanejo)
        S["sestavi"] = {}
else:
    S = {"izvor": IZVOR, "sestavi": {}, "modeli": {}, "deli": {}, "risbe": {}, "napake": []}


def shrani_stanje():
    tmp = STANJE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(S, f, ensure_ascii=False, indent=1)
    for poskus in range(20):                 # odjemalec oblaka datoteko med nalaganjem za hip zaklene
        try:
            os.replace(tmp, STANJE)
            return
        except PermissionError:
            if poskus == 19:
                raise
            time.sleep(1.5)


# ---------------------------------------------------------------- SolidWorks
sw = None
odprtih = 0


def zazeni():
    global sw, odprtih
    pythoncom.CoInitialize()
    sw = dynamic.Dispatch("SldWorks.Application")
    sw.Visible = False
    try:
        sw.UserControl = False
    except Exception:  # noqa: BLE001
        pass
    odprtih = 0
    log("SolidWorks", v(sw, "RevisionNumber"))
    step_z_barvami()


# SolidWorks privzeto izvaža STEP AP203 brez barv: med izvozom AP214 z barvami ploskev, na koncu se vrne prejšnje.
SW_STEP_AP, SW_STEP_BARVE = 75, 397          # swStepAP, swStepExportFaceEdgeProps
prej = {}


def step_z_barvami():
    if not prej:
        prej["ap"] = sw.GetUserPreferenceIntegerValue(SW_STEP_AP)
        prej["barve"] = sw.GetUserPreferenceToggle(SW_STEP_BARVE)
        S["nastavitve_sw_prej"] = dict(prej)
    sw.SetUserPreferenceIntegerValue(SW_STEP_AP, 214)
    sw.SetUserPreferenceToggle(SW_STEP_BARVE, True)


def vrni_nastavitve():
    if prej and sw is not None:
        try:
            sw.SetUserPreferenceIntegerValue(SW_STEP_AP, prej["ap"])
            sw.SetUserPreferenceToggle(SW_STEP_BARVE, prej["barve"])
            log("nastavitve STEP vrnjene:", prej)
        except Exception as e:  # noqa: BLE001
            log("nastavitev STEP ni bilo mogoče vrniti:", e, prej)


def ponovno():
    global sw
    try:
        sw.CloseAllDocuments(True)
        sw.ExitApp()
    except Exception:  # noqa: BLE001
        pass
    sw = None
    time.sleep(5)
    zazeni()


def odpri(pot, vrsta):
    global odprtih
    if odprtih >= NA_ZAGON:
        ponovno()
    odprtih += 1
    spec = sw.GetOpenDocSpec(pot)
    spec.DocumentType = vrsta
    spec.ReadOnly = True
    spec.Silent = True
    spec.LightWeight = False
    m = sw.OpenDoc7(spec)
    if m is None:
        raise RuntimeError("ni se odprl (napaka %s, opozorilo %s)" % (spec.Error, spec.Warning))
    return m


def zapri(m):
    try:
        sw.CloseDoc(v(m, "GetTitle"))
    except Exception:  # noqa: BLE001
        pass


def pregled_modela(m):
    tipi, smd = [], None
    ft = v(m, "FirstFeature")
    while ft is not None:
        t = v(ft, "GetTypeName2")
        if t not in tipi:
            tipi.append(t)
        if t == "SheetMetal" and smd is None:
            try:
                d = v(ft, "GetDefinition")
                smd = {"T": d.Thickness * 1000, "R": d.BendRadius * 1000, "K": d.KFactor}
            except Exception as e:  # noqa: BLE001
                smd = {"napaka": str(e)}
        ft = v(ft, "GetNextFeature")
    r = {"tipi": tipi, "plocevina": smd}
    for ime, f in (("toolbox", lambda: m.Extension.ToolboxPartType), ("material", lambda: m.MaterialIdName)):
        try:
            r[ime] = f()
        except Exception:  # noqa: BLE001
            r[ime] = None
    try:
        cpm = m.Extension.CustomPropertyManager("")
        imena = v(cpm, "GetNames") or []
        r["lastnosti"] = {n: cpm.Get(n) for n in imena}
    except Exception:  # noqa: BLE001
        pass
    return r


def stevilo_mat(m):
    n = 0
    ft = v(m, "FirstFeature")
    while ft is not None:
        if v(ft, "GetTypeName2") == "MateGroup":
            s = v(ft, "GetFirstSubFeature")
            while s is not None:
                n += 1
                s = v(s, "GetNextSubFeature")
        ft = v(ft, "GetNextFeature")
    return n


def meritve(m):
    r = {}
    try:
        mp = m.Extension.CreateMassProperty()
        mp.UseSystemUnits = True
        r["prostornina"] = mp.Volume * 1e9                      # mm3
        r["tezisce"] = [x * 1000 for x in mp.CenterOfMass]      # mm
    except Exception as e:  # noqa: BLE001
        r["napaka_mase"] = str(e)
    try:
        b = m.GetPartBox(True)
        r["okvir"] = [x * 1000 for x in b]
    except Exception:  # noqa: BLE001
        pass
    try:
        r["teles"] = len(m.GetBodies2(0, True) or ())
    except Exception:  # noqa: BLE001
        pass
    return r


def izvozi_step(m, cfg, k):
    if cfg:
        try:
            m.ShowConfiguration2(cfg)
        except Exception:  # noqa: BLE001
            pass
    cilj = os.path.join(STEP, k + ".step")
    if os.path.exists(cilj):
        os.remove(cilj)
    koda = m.SaveAs3(cilj, 0, 1)
    ok = os.path.exists(cilj) and os.path.getsize(cilj) > 0
    return ok, koda


def izvozi_pdf(m, cilj):
    """Risba -> PDF z ExportPdfData in ViewPdfAfterSaving = False: navaden SaveAs3 upošteva uporabnikovo možnost
    »View PDF after saving« in odpre Foxit, ki uporabniku krade fokus (7. 11. 2026). Errors/Warnings sta byref."""
    pdf = sw.GetExportFileData(1)                      # swExportPdfData
    pdf.ViewPdfAfterSaving = False
    try:
        pdf.SetSheets(1, None)                         # swExportData_ExportAllSheets
    except Exception:  # noqa: BLE001
        pass
    err = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    warn = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    try:
        ok = m.Extension.SaveAs(cilj, 0, 1, pdf, err, warn)          # SaveAs3 z None za AdvancedSaveAsOptions: Type mismatch
    except Exception:  # noqa: BLE001
        ok = m.Extension.SaveAs3(cilj, 0, 1, pdf, None, err, warn)
    return "%s/%s/%s" % (ok, err.value, warn.value)


# ---------------------------------------------------------------- 1) sestavi
def obhod(comp, oce_pot, globina):
    vozli = []
    for c in v(comp, "GetChildren") or ():
        c = dynamic.Dispatch(c)
        pp = v(c, "GetPathName")
        cfg = c.ReferencedConfiguration
        # uvožena komponenta (STEP, vstavljen neposredno v sestav, npr. Person Sample) živi le v začasni mapi
        # ...\swxNNN\IC~~\ dokler je sestav odprt: kot navidezno se izvozi iz sestava, ne odpira se sama
        navidezno = bool(c.IsVirtual) or "\\ic~~\\" in pp.lower()
        vrsta = "SESTAV" if pp.lower().endswith(".sldasm") else "DEL"
        k = kljuc_navideznega(oce_pot, pp, cfg) if navidezno else kljuc(pp, cfg)
        vozel = {"ime": c.Name2, "pot": pp, "cfg": cfg, "kljuc": k, "vrsta": vrsta,
                 "zatrto": False, "skrito": bool(c.IsHidden(False)),
                 "navidezno": navidezno, "fiksno": bool(v(c, "IsFixed")), "globina": globina,
                 "obstaja": navidezno or os.path.exists(pp)}
        # IsSuppressed je True tudi za »lahke« (lightweight) komponente, ki jih SolidWorks v načinu za velike sestave
        # ne naloži; zatrta je le komponenta s stanjem 0 (swComponentSuppressed), 1/4 = lahka, 2/3 = naložena
        try:
            stanje = v(c, "GetSuppression2")
        except Exception:  # noqa: BLE001
            stanje = 0 if v(c, "IsSuppressed") else 2
        vozel["zatrto"] = stanje == 0
        vozel["lahko"] = stanje in (1, 4)
        try:
            vozel["lega"] = list(c.Transform2.ArrayData)
        except Exception:  # noqa: BLE001
            vozel["lega"] = None
        m = None
        if not vozel["zatrto"]:
            try:
                m = v(c, "GetModelDoc2")
            except Exception:  # noqa: BLE001
                m = None
            vozel["nalozeno"] = m is not None
        if m is not None and k not in S["modeli"]:
            try:
                z = dict(pot=pp, cfg=cfg, vrsta=vrsta, navidezno=navidezno, **pregled_modela(m))
                if vrsta == "SESTAV":
                    z["mat"] = stevilo_mat(m)
                if navidezno:
                    z["oce"] = oce_pot
                    z["ime_dat"] = os.path.splitext(os.path.basename(pp))[0]
                S["modeli"][k] = z
            except Exception as e:  # noqa: BLE001
                S["modeli"][k] = {"pot": pp, "cfg": cfg, "vrsta": vrsta, "napaka": str(e)}
        if m is not None and navidezno and vrsta == "DEL" and k not in S["deli"]:
            try:
                ok, koda = izvozi_step(m, cfg, k)
                S["deli"][k] = dict(pot=pp, cfg=cfg, navidezno=True, step=ok, koda=koda, **meritve(m))
                log("  navidezni del", c.Name2, "STEP" if ok else "NAPAKA %s" % koda)
            except Exception as e:  # noqa: BLE001
                S["deli"][k] = {"pot": pp, "cfg": cfg, "navidezno": True, "step": False, "napaka": str(e)}
        vozel["otroci"] = obhod(c, pp if (vrsta == "SESTAV" and not navidezno) else oce_pot, globina + 1)
        vozli.append(vozel)
    return vozli


def preberi_sestav(pot):
    m = odpri(pot, 2)
    try:
        try:
            m.ResolveAllLightWeightComponents(False)
        except Exception:  # noqa: BLE001
            pass
        cfg = v(m.ConfigurationManager.ActiveConfiguration, "Name")
        koren = m.ConfigurationManager.ActiveConfiguration.GetRootComponent3(True)
        drevo = obhod(koren, pot, 1)
        z = {"pot": pot, "cfg": cfg, "drevo": drevo, "mat": stevilo_mat(m),
             "konfiguracije": list(v(m, "GetConfigurationNames") or ())}
        try:
            z["okvir"] = [x * 1000 for x in m.GetBox(0)]
        except Exception:  # noqa: BLE001
            pass
        k = kljuc(pot, cfg)
        if k not in S["modeli"]:
            S["modeli"][k] = dict(pot=pot, cfg=cfg, vrsta="SESTAV", navidezno=False, mat=z["mat"], tipi=[])
        return z
    finally:
        zapri(m)


# ---------------------------------------------------------------- 2) deli
def preberi_del(pot, potrebne):
    """Odpre del, zapiše dejavno konfiguracijo in izvozi vse potrebne konfiguracije (None = dejavna)."""
    m = odpri(pot, 1)
    try:
        dejavna = v(m.ConfigurationManager.ActiveConfiguration, "Name")
        imena = list(v(m, "GetConfigurationNames") or ())
        S.setdefault("dejavne", {})[pot.lower()] = {"dejavna": dejavna, "konfiguracije": imena}
        for cfg in sorted({c or dejavna for c in potrebne}, key=lambda c: c != dejavna):
            k = kljuc(pot, cfg)
            if k in S["deli"] and S["deli"][k].get("step"):
                continue
            ok, koda = izvozi_step(m, cfg, k)
            z = dict(pot=pot, cfg=cfg, navidezno=False, step=ok, koda=koda, dejavna=(cfg == dejavna), **meritve(m))
            S["deli"][k] = z
            if k not in S["modeli"]:
                S["modeli"][k] = dict(pot=pot, cfg=cfg, vrsta="DEL", navidezno=False, **pregled_modela(m))
            log("  ", os.path.basename(pot), "[%s]" % cfg, "STEP" if ok else "NAPAKA %s" % koda,
                "%.0f mm3" % z.get("prostornina", -1))
    finally:
        zapri(m)


BREZ_PODMAP = [x.strip().lower() for x in (os.environ.get("SW_BREZ_PODMAP") or "").split(";") if x.strip()]


def datoteke(konc):
    """Vse datoteke s končnico v izvorni mapi; podmape iz SW_BREZ_PODMAP (relativno na izvor) se izpustijo."""
    sez = []
    for kor, mape, dat in os.walk(IZVOR):
        rel = os.path.relpath(kor, IZVOR).replace(os.sep, "/").lower()
        mape[:] = [m for m in mape if (m.lower() if rel == "." else rel + "/" + m.lower()) not in BREZ_PODMAP]
        for d in dat:
            if d.lower().endswith(konc) and not d.startswith("~$"):
                sez.append(os.path.join(kor, d))
    return sorted(sez)


def main():
    zazeni()
    # 1) sestavi
    for pot in datoteke(".sldasm"):
        if pot.lower() in S["sestavi"]:
            continue
        log("SESTAV", os.path.relpath(pot, IZVOR))
        try:
            S["sestavi"][pot.lower()] = preberi_sestav(pot)
        except Exception as e:  # noqa: BLE001
            S["napake"].append({"pot": pot, "faza": "sestav", "napaka": str(e)})
            S["sestavi"][pot.lower()] = {"pot": pot, "napaka": str(e)}
            log("  NAPAKA", e)
            ponovno()
        shrani_stanje()
    # 2) deli: vsi v mapi (dejavna konfiguracija) + vsi iz dreves (uporabljena konfiguracija)
    potrebe = {}
    for pot in datoteke(".sldprt"):
        potrebe.setdefault(pot.lower(), [pot, set()])[1].add(None)

    def zberi(vozli):
        for x in vozli:
            if x["zatrto"] or x["navidezno"]:
                zberi(x.get("otroci", []))
                continue
            if x["vrsta"] == "DEL" and x["obstaja"]:
                potrebe.setdefault(x["pot"].lower(), [x["pot"], set()])[1].add(x["cfg"])
            zberi(x.get("otroci", []))

    for s in S["sestavi"].values():
        zberi(s.get("drevo", []))
    log("delov za izvoz:", len(potrebe))
    for pl, (pot, cfgs) in sorted(potrebe.items()):
        dej = S.get("dejavne", {}).get(pl)
        if dej is not None and dej.get("dejavna") is None:
            continue                       # del se ni odprl (napaka je zapisana)
        if dej is not None:
            manjka = [c for c in cfgs if not S["deli"].get(kljuc(pot, c or dej["dejavna"]), {}).get("step")]
            if not manjka:
                continue
        log("DEL", pot.replace(IZVOR, "~"))
        try:
            preberi_del(pot, cfgs)
        except Exception as e:  # noqa: BLE001
            S["napake"].append({"pot": pot, "faza": "del", "napaka": str(e)})
            S.setdefault("dejavne", {})[pl] = {"dejavna": None, "napaka": str(e)}
            log("  NAPAKA", e)
            ponovno()
        shrani_stanje()
    # 3) risbe brez PDF-ja
    for pot in datoteke(".slddrw"):
        if pot.lower() in S["risbe"]:
            continue
        pdf = os.path.splitext(pot)[0] + ".pdf"
        if os.path.exists(pdf):
            S["risbe"][pot.lower()] = {"pot": pot, "pdf": pdf, "izvoz": False}
            continue
        cilj = os.path.join(PODATKI, "risbe", os.path.splitext(os.path.relpath(pot, IZVOR))[0] + ".pdf")
        os.makedirs(os.path.dirname(cilj), exist_ok=True)
        log("RISBA", os.path.relpath(pot, IZVOR))
        try:
            m = odpri(pot, 3)
            koda = izvozi_pdf(m, cilj)
            zapri(m)
            S["risbe"][pot.lower()] = {"pot": pot, "pdf": cilj, "izvoz": True, "ok": os.path.exists(cilj), "koda": koda}
        except Exception as e:  # noqa: BLE001
            S["risbe"][pot.lower()] = {"pot": pot, "napaka": str(e)}
            log("  NAPAKA", e)
        shrani_stanje()
    log("KONEC: sestavov %d, delov %d, napak %d" % (len(S["sestavi"]), len(S["deli"]), len(S["napake"])))
    with open(os.path.join(PODATKI, "preberi.konec"), "w", encoding="utf-8") as f:
        f.write("ok sestavov %d, delov %d, napak %d\n" % (len(S["sestavi"]), len(S["deli"]), len(S["napake"])))


try:
    main()
except Exception:  # noqa: BLE001
    log("PADLO", traceback.format_exc())
    shrani_stanje()
    raise
finally:
    vrni_nastavitve()
    try:
        sw.CloseAllDocuments(True)
        sw.ExitApp()
    except Exception:  # noqa: BLE001
        pass
