# -*- coding: utf-8 -*-
"""Manjkajoče sličice različic idej: izris v ločenem Blenderju brez okna (`slicica_izris.py`), v ozadju, ena naloga naenkrat.

Stran izriše sličico le za različico, ki jo gleda; različice iz skript (Claude, `shrani_razlicico` brez strani) in kosi
sestavov je nimajo. `Slicice.preveri(koren)` poišče vse `Rxx.blend` brez `Rxx.png` v `Ideje/*/` in jih izriše v ozadju;
ob koncu pokliče `ob_koncu()` (strežnik dvigne `verzija_ideje`, stran sličice naloži znova). Datoteke, pri katerih izris
pade, si zapomni (po času spremembe) in jih ne poskuša znova, dokler se ne spremenijo. Vse teče na niti; bpy se ne kliče.
"""
import json
import os
import re
import subprocess
import threading
import time

from upodabljanje import DELOVNA, _brez_okna, _cisto_okolje, najdi_blender

MAPA = os.path.dirname(os.path.abspath(__file__))
IZRIS_PY = os.path.join(MAPA, "slicica_izris.py")
DELOVNA_SLICIC = os.path.join(os.path.dirname(DELOVNA), "slicice")


class Slicice:
    def __init__(self, ob_koncu=None, dnevnik=print):
        self.ob_koncu = ob_koncu
        self.dnevnik = dnevnik
        self.zaklep = threading.Lock()
        self.tece = False
        self.neuspele = {}        # pot .blend -> mtime ob neuspehu
        self.zadnji_pregled = 0.0
        self.narejenih = 0

    def manjkajoce(self, koren):
        """[(blend, png)] različic brez sličice (po ideja.json; ne vključuje datotek, ki so nazadnje padle)."""
        izid = []
        if not os.path.isdir(koren):
            return izid
        for ime in sorted(os.listdir(koren)):
            mapa = os.path.join(koren, ime)
            try:
                with open(os.path.join(mapa, "ideja.json"), encoding="utf-8") as f:
                    p = json.load(f)
            except (OSError, ValueError):
                continue
            for r in p.get("razlicice", []):
                rid = r.get("id", "")
                if not re.match(r"R\d+$", rid):
                    continue
                blend, png = os.path.join(mapa, rid + ".blend"), os.path.join(mapa, rid + ".png")
                if not os.path.isfile(blend) or os.path.isfile(png):
                    continue
                try:
                    mtime = os.path.getmtime(blend)
                except OSError:
                    continue
                if self.neuspele.get(blend) == mtime:
                    continue
                if time.time() - mtime < 3:      # datoteka se morda še piše (shrani_razlicico, kopija)
                    continue
                izid.append((blend, png))
        return izid

    def preveri(self, koren, najmanj_sekund=5.0):
        """Če kaj manjka in nič ne teče, zažene izris v ozadju. Vrne število datotek v nalogi."""
        with self.zaklep:
            if self.tece or time.time() - self.zadnji_pregled < najmanj_sekund:
                return 0
            self.zadnji_pregled = time.time()
            naloge = self.manjkajoce(koren)
            if not naloge:
                return 0
            self.tece = True
        threading.Thread(target=self._izvedi, args=(naloge,), daemon=True, name="slicice").start()
        return len(naloge)

    def _izvedi(self, naloge):
        try:
            blender = najdi_blender()
            if not blender:
                self.dnevnik("sličice: Blender ni najden")
                for blend, _ in naloge:
                    self.neuspele[blend] = os.path.getmtime(blend)
                return
            os.makedirs(DELOVNA_SLICIC, exist_ok=True)
            pot_naloge = os.path.join(DELOVNA_SLICIC, "naloga-%d.json" % int(time.time()))
            with open(pot_naloge, "w", encoding="utf-8") as f:
                json.dump([{"blend": b, "png": p} for b, p in naloge], f, ensure_ascii=False, indent=1)
            ukaz = [blender, "-b", "--factory-startup", "--python-exit-code", "1", "--python", IZRIS_PY, "--", pot_naloge]
            self.dnevnik("sličice: izrisujem %d (%s)" % (len(naloge), ", ".join(os.path.relpath(p, os.path.dirname(os.path.dirname(p))) for _, p in naloge[:4])))
            zacetek = time.time()
            with open(os.path.join(DELOVNA_SLICIC, "dnevnik.txt"), "w", encoding="utf-8", errors="replace") as dnevnik:
                proces = subprocess.Popen(ukaz, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=DELOVNA_SLICIC,
                                          env=_cisto_okolje(), **_brez_okna())
                ok, napake = 0, []
                for vrstica in iter(proces.stdout.readline, b""):
                    v = vrstica.decode("utf-8", "replace").rstrip()
                    dnevnik.write(v + "\n")
                    if v.startswith("SLICICA OK "):
                        ok += 1
                    elif v.startswith("SLICICA NAPAKA "):
                        napake.append(v[15:])
                proces.wait()
            for blend, png in naloge:
                if png in napake or not os.path.isfile(png):
                    try:
                        self.neuspele[blend] = os.path.getmtime(blend)
                    except OSError:
                        pass
                else:
                    self.neuspele.pop(blend, None)
            self.narejenih += ok
            self.dnevnik("sličice: %d narejenih, %d napak, %.1f s" % (ok, len(napake), time.time() - zacetek))
            try:
                os.remove(pot_naloge)
            except OSError:
                pass
            if ok and self.ob_koncu:
                self.ob_koncu()
        except Exception as e:      # noqa: BLE001 - nit v ozadju ne sme pasti tiho
            self.dnevnik("sličice: napaka %s" % e)
            for blend, _ in naloge:
                try:
                    self.neuspele[blend] = os.path.getmtime(blend)
                except OSError:
                    pass
        finally:
            with self.zaklep:
                self.tece = False
