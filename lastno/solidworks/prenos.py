# -*- coding: utf-8 -*-
"""Prenos map SolidWorks (Dropbox PROJEKTI) v Oblak/3D modeliranje po seznamu v prenos.json. Vodi vse korake:

  python prenos.py beri            bere projekte po vrsti iz SolidWorksa (sw_preberi.py; brez okna; nadaljuje, kjer je ostal)
  python prenos.py gradi           za vsak prebran projekt: gradnja v skritem FreeCAD-u (zagon_gradnje.py prek pixi),
                                   kontrola (preveri.py v FreeCADCmd), ostale datoteke (PDF, DXF ...), PREBERI.txt,
                                   podatki prenosa v <projekt>/Skripte/podatki, skupina projekta v _skupine projektov.json
  python prenos.py stanje          tabela: kaj je prebrano, zgrajeno, preverjeno
  python prenos.py beri PHOTOBOX/Mini 3     samo en projekt (tudi gradi)

»beri« in »gradi« tečeta vsak v svojem procesu hkrati (branje je ozko grlo: ~10 s na dokument v SolidWorksu).
Zagon v ozadju brez okna: PowerShell Start-Process python -ArgumentList prenos.py,beri -WindowStyle Hidden.
Dnevnik: <delovna>/prenos.log. Zaustavitev: datoteka <delovna>/STOP (procesa končata po trenutnem projektu).
"""
import json
import os
import shutil
import subprocess
import sys
import time

TU = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TU)
import prenos_cfg as cfg  # noqa: E402

REPO = os.path.dirname(os.path.dirname(TU))                          # CAD in 3D/FreeCAD
FREECAD = os.path.join(REPO, ".pixi", "envs", "default", "Library", "bin", "FreeCAD.exe")
FREECADCMD = os.path.join(REPO, ".pixi", "envs", "default", "Library", "bin", "FreeCADCmd.exe")
USER_CFG = os.path.join(cfg.DELOVNA, "user.cfg")
TEMP = os.path.join(cfg.DELOVNA, "temp")
STOP = os.path.join(cfg.DELOVNA, "STOP")
DNEVNIK = os.path.join(cfg.DELOVNA, "prenos.log")
CAD = (".sldprt", ".sldasm", ".slddrw")
NO_WINDOW = 0x08000000


def log(*a):
    s = time.strftime("%Y-%m-%d %H:%M:%S ") + " ".join(str(x) for x in a)
    print(s, flush=True)
    os.makedirs(cfg.DELOVNA, exist_ok=True)
    with open(DNEVNIK, "a", encoding="utf-8") as f:
        f.write(s + "\n")


def konec(kljuc, ime):
    p = os.path.join(cfg.podatki(kljuc), ime)
    if not os.path.exists(p):
        return None
    return open(p, encoding="utf-8", errors="replace").read().strip()


def ok(kljuc, ime):
    k = konec(kljuc, ime)
    return bool(k) and k.startswith("ok")


def projekti(samo=None):
    sez = [p for p in cfg.PRENOS["projekti"] if not samo or p["kljuc"] == samo]
    if samo and not sez:
        raise SystemExit("projekt %r ni v prenos.json" % samo)
    return sez


# ---------------------------------------------------------------- branje
def beri(p):
    kljuc = p["kljuc"]
    pod = cfg.podatki(kljuc)
    os.makedirs(pod, exist_ok=True)
    os.makedirs(cfg.STEP, exist_ok=True)
    env = dict(os.environ)
    if p.get("brez_podmap"):
        env["SW_BREZ_PODMAP"] = ";".join(p["brez_podmap"])
    log("BERI", kljuc)
    with open(os.path.join(pod, "sw.stdout.log"), "a", encoding="utf-8") as out:
        r = subprocess.run([sys.executable, os.path.join(TU, "sw_preberi.py"), cfg.izvor(kljuc), pod, cfg.STEP],
                           env=env, stdout=out, stderr=subprocess.STDOUT, creationflags=NO_WINDOW)
    log("BERI konec", kljuc, "koda", r.returncode, "|", konec(kljuc, "preberi.konec"))
    return ok(kljuc, "preberi.konec")


# ---------------------------------------------------------------- gradnja
def pripravi_cfg():
    """Kopija uporabnikovega user.cfg za skriti primerek (brez varnostnih kopij, ločen TEMP)."""
    os.makedirs(TEMP, exist_ok=True)
    if not os.path.exists(USER_CFG):
        izv = os.path.join(os.environ.get("APPDATA", ""), "FreeCAD", "user.cfg")
        if os.path.exists(izv):
            shutil.copy2(izv, USER_CFG)
        else:
            open(USER_CFG, "w").write('<?xml version="1.0" encoding="UTF-8" standalone="no" ?>\n<FCParameters>\n'
                                      '<FCParamGroup Name="Root">\n</FCParamGroup>\n</FCParameters>\n')


def pixi(exe, skripta, env):
    """Lastna gradnja FreeCAD-a se zažene SAMO prek pixi (sicer manjka PySide6)."""
    return subprocess.run(["pixi", "run", "-q", "--no-progress", "--", exe] + skripta, cwd=REPO, env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=NO_WINDOW)


def gradi(p):
    kljuc = p["kljuc"]
    pod = cfg.podatki(kljuc)
    pripravi_cfg()
    env = dict(os.environ, SW_PROJEKT=kljuc, TEMP=TEMP, TMP=TEMP)
    for ime in ("gradnja.konec",):
        try:
            os.remove(os.path.join(pod, ime))
        except OSError:
            pass
    log("GRADI", kljuc, "->", cfg.cilj(kljuc))
    t0 = time.time()
    r = pixi(FREECAD, ["--user-cfg", USER_CFG, os.path.join(TU, "zagon_gradnje.py")], env)
    with open(os.path.join(pod, "gradnja.stdout.log"), "ab") as f:
        f.write(r.stdout or b"")
    k = konec(kljuc, "gradnja.konec")
    log("GRADI konec", kljuc, "koda", r.returncode, "%.0f min" % ((time.time() - t0) / 60), "|", (k or "ni gradnja.konec")[:200])
    return bool(k) and k == "ok"


def preveri(p):
    kljuc = p["kljuc"]
    pod = cfg.podatki(kljuc)
    env = dict(os.environ, SW_PROJEKT=kljuc, TEMP=TEMP, TMP=TEMP)
    try:
        os.remove(os.path.join(pod, "kontrola.konec"))
    except OSError:
        pass
    log("PREVERI", kljuc)
    r = pixi(FREECADCMD, [os.path.join(TU, "preveri.py")], env)
    with open(os.path.join(pod, "kontrola.stdout.log"), "wb") as f:
        f.write(r.stdout or b"")
    log("PREVERI konec", kljuc, "koda", r.returncode, "|", konec(kljuc, "kontrola.konec"))
    return ok(kljuc, "kontrola.konec")


def kopiraj_ostalo(p):
    """Datoteke, ki niso modeli SolidWorks (PDF, DXF, DOCX, STL, slike ...), v isto zgradbo map projekta, in PDF risb,
    ki jih je sw_preberi.py izvozil iz SLDDRW brez obstoječega PDF-ja. Obstoječih datotek ne prepiše."""
    kljuc = p["kljuc"]
    izvor, mapa = cfg.izvor(kljuc), cfg.cilj(kljuc)
    brez = [b.lower() for b in p.get("brez_podmap", [])]
    S = json.load(open(os.path.join(cfg.podatki(kljuc), "struktura.json"), encoding="utf-8"))
    n = 0
    for kor, mape, dat in os.walk(izvor):
        rel = os.path.relpath(kor, izvor).replace(os.sep, "/").lower()
        mape[:] = [m for m in mape if (m.lower() if rel == "." else rel + "/" + m.lower()) not in brez]
        for d in dat:
            if d.startswith("~$") or d.lower().endswith(CAD) or d.lower() == "desktop.ini":
                continue
            cilj = os.path.join(mapa, os.path.relpath(os.path.join(kor, d), izvor))
            if not os.path.exists(cilj):
                os.makedirs(os.path.dirname(cilj), exist_ok=True)
                shutil.copy2(os.path.join(kor, d), cilj)
                n += 1
    for r in S.get("risbe", {}).values():
        if r.get("izvoz") and r.get("ok"):
            cilj = os.path.join(mapa, os.path.splitext(os.path.relpath(r["pot"], izvor))[0] + ".pdf")
            if not os.path.exists(cilj) and os.path.exists(r["pdf"]):
                os.makedirs(os.path.dirname(cilj), exist_ok=True)
                shutil.copy2(r["pdf"], cilj)
                n += 1
    log("OSTALO", kljuc, "kopiranih", n)


def skupina(p):
    """Projekt v skupino projektov spletnega FreeCAD-a (_skupine projektov.json); podmapa projekta ni svoj projekt."""
    if "/" in p["cilj"] or not p.get("skupina"):
        return
    pot = os.path.join(cfg.CILJ_KOREN, "_skupine projektov.json")
    try:
        d = json.load(open(pot, encoding="utf-8"))
    except Exception:  # noqa: BLE001
        d = {"skupine": {}}
    d.setdefault("skupine", {})[p["cilj"]] = p["skupina"]
    json.dump(d, open(pot, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def preberi_txt(p):
    kljuc = p["kljuc"]
    pod, mapa = cfg.podatki(kljuc), cfg.cilj(kljuc)
    S = json.load(open(os.path.join(pod, "struktura.json"), encoding="utf-8"))
    try:
        REZ = json.load(open(os.path.join(pod, "rezultat.json"), encoding="utf-8"))
    except Exception:  # noqa: BLE001
        REZ = {}
    try:
        K = json.load(open(os.path.join(pod, "kontrola.json"), encoding="utf-8")).get("povzetek", {})
    except Exception:  # noqa: BLE001
        K = {}
    fc = [z for z in REZ.values() if os.path.exists(z.get("datoteka", ""))]
    tu = [z for z in fc if z.get("projekt") == kljuc]
    drugje = {}
    for z in fc:
        if z.get("projekt") != kljuc:
            drugje[z.get("projekt") or "Zunanji deli"] = drugje.get(z.get("projekt") or "Zunanji deli", 0) + 1
    napake = [z for z in REZ.values() if z.get("opombe")]
    sestavi_koren = sorted(os.path.basename(s["pot"]) for s in S["sestavi"].values()
                           if "drevo" in s and os.path.dirname(s["pot"]).lower() == cfg.izvor(kljuc).lower())
    datum = time.strftime("%d. %m. %Y")
    b = []
    b.append("%s — prenos iz SolidWorksa v naš FreeCAD (%s)" % (p["cilj"].upper(), datum))
    b.append("")
    b.append("Izvor: PHOTOLANDIA Dropbox/PHOTOLANDIA/PROJEKTI/%s (SolidWorks je bil odprt samo za branje, nobena izvorna" % kljuc)
    b.append("datoteka ni spremenjena). Prenos je samodejen: CAD in 3D/FreeCAD/lastno/solidworks (prenos.py, prenos.json).")
    b.append("")
    b.append("ZGRADBA: enaka kot v Dropboxu. Vsak .SLDPRT je .FCStd z istim imenom v isti mapi, vsak .SLDASM je sestav (Assembly)")
    b.append("z istim imenom, ki kaže na iste dele in podsestave na istih legah kot v SolidWorksu. Vse stoji z osjo Z navzgor")
    b.append("(SolidWorks ima Y navzgor). Del ali sestav v konfiguraciji, ki ni dejavna, ima pripono »(konfiguracija)«; sestav, ki")
    b.append("ima v isti mapi del z istim imenom, pripono »(sestav)«. Gibljiv podsestav z drugačnimi legami kosov v nadsestavu je")
    b.append("svoja datoteka »<podsestav> (v <nadsestav>)« v podmapi »Gibljivi podsestavi«.")
    b.append("")
    b.append("KOSI IZ DRUGIH MAP: del ali podsestav, ki ga sestavi uporabljajo iz druge mape PROJEKTI (STANDARD BOX, TOOLBOX,")
    b.append("drug photobox ...), ima FCStd v projektu tiste mape (npr. 3D modeliranje/Standard box/...), ne kopije tukaj;")
    b.append("Zunanji deli/ le za poti zunaj PROJEKTI.")
    if sestavi_koren:
        b.append("")
        b.append("SESTAVI V KORENU MAPE: " + ", ".join(sestavi_koren))
    b.append("")
    b.append("ŠTEVILKE: v tej mapi %d datotek FCStd (%d delov, %d sestavov); kosov iz drugih projektov %s." % (
        len(tu), sum(1 for z in tu if z["vrsta"] == "del"), sum(1 for z in tu if z["vrsta"] == "sestav"),
        ", ".join("%s %d" % kv for kv in sorted(drugje.items())) or "0"))
    if K:
        b.append("KONTROLA (%s): delov preverjenih %d, odstopa %d; v %d sestavih je %d od %d vidnih teles na isti legi kot v" % (
            datum, K.get("deli_preverjenih", 0), K.get("deli_odstopa", 0), K.get("sestavi_preverjenih", 0),
            K.get("teles_na_legi", 0), K.get("teles_pricakovanih", 0)))
        b.append("SolidWorksu (±0,5 mm); sestavov z odstopanji %d." % K.get("sestavi_z_odstopanji", 0))
        for x in (K.get("slabi_deli") or [])[:15]:
            b.append("  - del: %s" % " | ".join(str(y) for y in x))
        for x in (K.get("slabi_sestavi") or [])[:15]:
            b.append("  - sestav: %s" % " | ".join(str(y) for y in x))
    if napake:
        b.append("")
        b.append("OPOMBE GRADNJE (%d):" % len(napake))
        for z in napake[:40]:
            b.append("  - %s: %s" % (z.get("ime"), "; ".join(z["opombe"])))
    if S.get("napake"):
        b.append("")
        b.append("NAPAKE BRANJA V SOLIDWORKSU (%d):" % len(S["napake"]))
        for n in S["napake"][:30]:
            b.append("  - %s [%s]: %s" % (os.path.basename(n.get("pot", "")), n.get("faza"), str(n.get("napaka"))[:120]))
    b.append("")
    b.append("KAJ NI PRENESENO: zgodovina značilnosti (deli so uvožena geometrija z barvami in lastnostmi SolidWorksa: Izvor,")
    b.append("Konfiguracija, MaterialSW, Vrsta, pločevina Debelina/Polmer/KFaktor; pločevina ima skrito Razgrnitev); mate (vsak")
    b.append("sestav ima en talni spoj, lege so točne); risbe SLDDRW so le PDF (izvožene, kjer PDF-ja ni bilo).")
    b.append("")
    b.append("Skripte/podatki: struktura.json (drevesa iz SolidWorksa), rezultat.json (kaj je kam zgrajeno), kontrola.json, dnevniki.")
    b.append("STEP vseh delov je lokalno v %s (ni v oblaku)." % cfg.STEP)
    b.append("PONOVNI PRENOS po spremembi v Dropboxu: python lastno/solidworks/prenos.py beri \"%s\" (nato gradi)." % kljuc)
    os.makedirs(mapa, exist_ok=True)
    with open(os.path.join(mapa, "PREBERI.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(b) + "\n")
    # podatki prenosa v projekt (brez STEP)
    cilj = os.path.join(mapa, "Skripte", "podatki")
    os.makedirs(cilj, exist_ok=True)
    for ime in ("struktura.json", "rezultat.json", "kontrola.json", "sw.log", "gradnja.log", "kontrola.stdout.log"):
        p2 = os.path.join(pod, ime)
        if os.path.exists(p2):
            shutil.copy2(p2, os.path.join(cilj, ime))
    with open(os.path.join(mapa, "Skripte", "PREBERI.txt"), "w", encoding="utf-8") as f:
        f.write("Skripte prenosa so skupne: CAD in 3D/FreeCAD/lastno/solidworks (sw_preberi.py, zgradi.py, preveri.py, prenos.py).\n"
                "Tu so le podatki tega projekta (podatki/). Ponovni prenos: python prenos.py beri \"%s\"; python prenos.py gradi \"%s\"\n"
                % (kljuc, kljuc))


def obdelaj(p):
    """Vse po branju: gradnja -> kontrola -> ostale datoteke -> PREBERI -> skupina."""
    kljuc = p["kljuc"]
    if not ok(kljuc, "gradnja.konec"):
        if not gradi(p):
            return False
    if not ok(kljuc, "kontrola.konec"):
        preveri(p)
    kopiraj_ostalo(p)
    preberi_txt(p)
    skupina(p)
    with open(os.path.join(cfg.podatki(kljuc), "prenos.konec"), "w", encoding="utf-8") as f:
        f.write("ok " + time.strftime("%Y-%m-%d %H:%M") + "\n")
    log("PRENOS konec", kljuc)
    return True


# ---------------------------------------------------------------- ukazi
def ukaz_beri(samo):
    for p in projekti(samo):
        if os.path.exists(STOP):
            log("STOP"); return
        if ok(p["kljuc"], "preberi.konec"):
            continue
        beri(p)
    log("BERI: vsi projekti prebrani")


def ukaz_gradi(samo):
    """Gradi vsak prebran projekt po vrsti; na projekt, ki še ni prebran, počaka (branje teče vzporedno)."""
    for p in projekti(samo):
        while not ok(p["kljuc"], "preberi.konec"):
            if os.path.exists(STOP):
                log("STOP"); return
            time.sleep(60)
        if os.path.exists(STOP):
            log("STOP"); return
        if ok(p["kljuc"], "prenos.konec"):
            continue
        obdelaj(p)
    log("GRADI: vsi projekti zgrajeni")


def ukaz_stanje():
    print("%-28s %-10s %-10s %-10s %s" % ("projekt", "prebrano", "zgrajeno", "kontrola", "prenos"))
    for p in cfg.PRENOS["projekti"]:
        k = p["kljuc"]
        print("%-28s %-10s %-10s %-10s %s" % (k[:28], "da" if ok(k, "preberi.konec") else ("teče" if os.path.exists(os.path.join(cfg.podatki(k), "sw.log")) else "-"),
                                              "da" if ok(k, "gradnja.konec") else ("napaka" if konec(k, "gradnja.konec") else "-"),
                                              "da" if ok(k, "kontrola.konec") else "-", "da" if ok(k, "prenos.konec") else "-"))


if __name__ == "__main__":
    u = sys.argv[1] if len(sys.argv) > 1 else "stanje"
    samo = sys.argv[2] if len(sys.argv) > 2 else None
    if u == "beri":
        ukaz_beri(samo)
        if samo:
            obdelaj(cfg.projekt(samo))
    elif u == "gradi":
        ukaz_gradi(samo)
    else:
        ukaz_stanje()
