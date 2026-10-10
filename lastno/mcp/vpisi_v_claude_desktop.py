# -*- coding: utf-8 -*-
"""Vpis strežnika MCP »freecad« v namizno aplikacijo Claude (pogovor, Cowork).

Aplikacija (paket Microsoft Store) nastavitve claude_desktop_config.json drži v pomnilniku in datoteko med delovanjem
prepisuje: vpis, narejen med njenim delovanjem, v nekaj sekundah izgine (preverjeno 10. 10. 2026). Zato:

    pythonw vpisi_v_claude_desktop.py --cakaj     (v ozadju)

počaka, da se aplikacija zapre, vpiše strežnik (ostale nastavitve ostanejo nespremenjene), po ponovnem zagonu
aplikacije preveri, da vpis obstane, in se konča. Če ga aplikacija vseeno odstrani, ponovi ob naslednjem zaprtju
(največ 3-krat). Brez --cakaj vpiše takoj (le, ko aplikacija ne teče). Dnevnik:
%LOCALAPPDATA%/FreeCAD-splet/vpis-claude-desktop.log. Brez odvisnosti (ctypes za seznam procesov).
"""
import ctypes
import ctypes.wintypes as wt
import datetime
import json
import os
import sys
import time

PYTHON = r"C:\Users\Uporabnik\AppData\Local\Programs\Python\Python311\python.exe"
MOST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "freecad_mcp.py")
KONFIG = os.path.join(os.environ.get("APPDATA") or "", "Claude", "claude_desktop_config.json")
LOKALNO = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "FreeCAD-splet")
DNEVNIK = os.path.join(LOKALNO, "vpis-claude-desktop.log")
ZAKLEP = os.path.join(LOKALNO, "vpis-claude-desktop.pid")
ZNAK_APLIKACIJE = "\\windowsapps\\claude_"   # pot glavnega procesa namizne aplikacije (ne Claude Code)
VNOS = {"command": PYTHON.replace("\\", "/"), "args": [MOST.replace("\\", "/")]}


def dnevnik(besedilo):
    os.makedirs(LOKALNO, exist_ok=True)
    with open(DNEVNIK, "a", encoding="utf-8") as f:
        f.write("%s %s\n" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), besedilo))


def aplikacija_tece():
    """Ali teče kak proces namizne aplikacije Claude (pot v WindowsApps\\Claude_...)."""
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi")
    pidi = (wt.DWORD * 8192)()
    vrnjeno = wt.DWORD()
    if not psapi.EnumProcesses(ctypes.byref(pidi), ctypes.sizeof(pidi), ctypes.byref(vrnjeno)):
        return True   # ne vemo: raje počakaj
    k32.OpenProcess.restype = wt.HANDLE
    for pid in pidi[:vrnjeno.value // ctypes.sizeof(wt.DWORD)]:
        h = k32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            continue
        try:
            buf = ctypes.create_unicode_buffer(1024)
            dolzina = wt.DWORD(1024)
            if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(dolzina)) and \
                    ZNAK_APLIKACIJE in buf.value.lower() and buf.value.lower().endswith("claude.exe"):
                return True
        finally:
            k32.CloseHandle(h)
    return False


def vpisano():
    try:
        with open(KONFIG, encoding="utf-8") as f:
            return (json.load(f).get("mcpServers") or {}).get("freecad") is not None
    except (OSError, ValueError):
        return False


def vpisi():
    with open(KONFIG, encoding="utf-8") as f:
        d = json.load(f)
    if (d.get("mcpServers") or {}).get("freecad") == VNOS:
        return False
    d.setdefault("mcpServers", {})["freecad"] = VNOS
    zac = KONFIG + ".delno"
    with open(zac, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    os.replace(zac, KONFIG)
    return True


def cakaj_na(pogoj, rok):
    zaporedno = 0
    while time.time() < rok:
        zaporedno = zaporedno + 1 if pogoj() else 0
        if zaporedno >= 2:
            return True
        time.sleep(3)
    return False


def main(argv):
    if "--cakaj" not in argv:
        if aplikacija_tece():
            print("Namizna aplikacija Claude teče: vpis bi prepisala. Zaženi s --cakaj (v ozadju) ali jo najprej zapri.")
            return 1
        print("Vpisano." if vpisi() else "Že vpisano.")
        return 0
    try:   # en čakalnik naenkrat
        with open(ZAKLEP, encoding="utf-8") as f:
            star = int(f.read().strip() or 0)
        h = ctypes.WinDLL("kernel32").OpenProcess(0x1000, False, star) if star else 0
        if h:
            ctypes.WinDLL("kernel32").CloseHandle(h)
            dnevnik("čakalnik že teče (pid %d), končujem" % star)
            return 0
    except (OSError, ValueError):
        pass
    os.makedirs(LOKALNO, exist_ok=True)
    with open(ZAKLEP, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))
    rok = time.time() + 30 * 24 * 3600
    try:
        dnevnik("čakam na zaprtje namizne aplikacije Claude (vpis strežnika freecad)")
        for poskus in range(3):
            if not cakaj_na(lambda: not aplikacija_tece(), rok):
                dnevnik("rok potekel, aplikacija se ni zaprla")
                return 1
            dnevnik("aplikacija zaprta, poskus %d: %s" % (poskus + 1, "vpisano" if vpisi() else "že vpisano"))
            if not cakaj_na(aplikacija_tece, rok):
                dnevnik("rok potekel, aplikacija se ni znova zagnala")
                return 1
            time.sleep(90)   # aplikacija med zagonom in prvimi minutami nastavitve zapiše
            if vpisano():
                dnevnik("aplikacija teče, vpis je obstal: končano")
                return 0
            dnevnik("aplikacija je vpis odstranila; poskusim ob naslednjem zaprtju")
        dnevnik("po 3 poskusih vpis ni obstal: namesti razširitev freecad.mcpb ročno (Nastavitve, Razširitve)")
        return 1
    finally:
        try:
            os.remove(ZAKLEP)
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
