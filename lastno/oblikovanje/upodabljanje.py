# Upravljalnik renderjev: naloge v vrsti, vsaka v svojem procesu Blenderja brez okna (render.py).
#
# Čisti Python brez FreeCAD-a in bpy: uporabljata ga strežnik spletnega FreeCAD-a (nit strežnika) in strežnik
# Oblikovanja v Blenderju. Render teče v ločenem procesu, zato ne zaustavi ne FreeCAD-a ne Oblikovanja, sesutje
# Blenderja pa ne podre strežnika. Naenkrat teče en render (grafična kartica); ostali čakajo v vrsti.
#
# Datoteke: %LOCALAPPDATA%/FreeCAD-splet/renderji/<id>/ (naloga.json, scena.json ali scena.blend, render.png ali
# vrtenje.mp4, dnevnik.txt). Če je podana `kopija` (mapa projekta), se končna slika kopira še tja.

import datetime
import glob
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid

MAPA = os.path.dirname(os.path.abspath(__file__))
RENDER_PY = os.path.join(MAPA, "render.py")
DELOVNA = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "FreeCAD-splet", "renderji")

KAKOVOST = {   # vzorci, merilo velikosti
    "osnutek": (32, 0.5),
    "dobro": (128, 1.0),
    "najboljse": (512, 1.0),
}
OSVETLITVE = ["studio", "mehka", "soncni", "mesto", "gozd", "notranjost", "noc"]
BREZ_OPTIX = os.path.join(DELOVNA, "brez-optix.txt")
OZADJA = ["svetlo", "belo", "temno", "prozorno", "okolje"]


def _razlicica(pot):
    m = re.search(r"Blender (\d+)\.(\d+)", pot)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def najdi_blender():
    """Najnovejši nameščeni Blender (prepis: okoljska SPLET_BLENDER)."""
    pot = os.environ.get("SPLET_BLENDER")
    if pot and os.path.isfile(pot):
        return pot
    kandidati = []
    for koren in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                  os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")):
        kandidati += glob.glob(os.path.join(koren, "Blender Foundation", "Blender *", "blender.exe"))
    kandidati.sort(key=_razlicica)
    return kandidati[-1] if kandidati else None


def najdi_ffmpeg():
    pot = shutil.which("ffmpeg")
    if pot:
        return pot
    vzorec = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Packages", "*FFmpeg*", "*", "bin", "ffmpeg.exe")
    najdeni = sorted(glob.glob(vzorec))
    return najdeni[-1] if najdeni else None


def _brez_okna():
    if os.name == "nt":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return {"startupinfo": si, "creationflags": 0x08000000}   # CREATE_NO_WINDOW
    return {}


def _cisto_okolje():
    """Okolje brez Pythona FreeCAD-a (PYTHONHOME/PYTHONPATH bi Blenderju podtaknili tuj Python)."""
    okolje = dict(os.environ)
    for k in ("PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP", "PYTHONNOUSERSITE"):
        okolje.pop(k, None)
    return okolje


class Upodabljanje:
    def __init__(self):
        self.naloge = {}          # id -> stanje (dict)
        self.vrsta = []           # id-ji, ki čakajo
        self.zaklep = threading.Lock()
        self.proces = None
        self.tekoca = None
        self.nit = None
        # OptiX se ni prevedel (star gonilnik NVIDIA): odslej CUDA. Zapomni se v datoteko (oba strežnika, ponovni zagoni)
        # za 7 dni, nato se OptiX poskusi znova (morda je gonilnik medtem posodobljen).
        try:
            self.brez_optix = time.time() - os.path.getmtime(BREZ_OPTIX) < 7 * 86400
        except OSError:
            self.brez_optix = False

    # -- javno ------------------------------------------------------------------------------------------------

    def zacni(self, vir, nastavitve, ime="render", kopija=None):
        """vir: {"posnetek_bajti": bytes} (posnetek spletnega FreeCAD-a) ali {"blend": pot} (že shranjena kopija).
        nastavitve: kamera, premiki, osvetlitev, ozadje, kakovost, sirina, visina, vrtenje. Vrne id naloge."""
        blender = najdi_blender()
        if not blender:
            raise RuntimeError("Blender ni nameščen (Program Files/Blender Foundation; prepis SPLET_BLENDER).")
        nid = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        mapa = os.path.join(DELOVNA, nid)
        os.makedirs(mapa, exist_ok=True)
        if "posnetek_bajti" in vir:
            pot = os.path.join(mapa, "scena.json")
            with open(pot, "wb") as f:
                f.write(vir["posnetek_bajti"])
            vir_naloge = {"posnetek": pot}
        else:
            vir_naloge = {"blend": vir["blend"]}
        vzorci, merilo = KAKOVOST.get(nastavitve.get("kakovost"), KAKOVOST["dobro"])
        sirina = max(64, min(7680, int(nastavitve.get("sirina") or 1600)))
        visina = max(64, min(4320, int(nastavitve.get("visina") or 1000)))
        vrtenje = int(nastavitve.get("vrtenje") or 0)
        if vrtenje:
            vrtenje = max(24, min(240, vrtenje))
            merilo = min(merilo, 0.5)              # video: polovična velikost, da ne traja ure
            vzorci = min(vzorci, 64)
        naloga = {
            "vir": vir_naloge,
            "kamera": nastavitve.get("kamera"),
            "premiki": nastavitve.get("premiki") or {},
            "osvetlitev": nastavitve.get("osvetlitev") if nastavitve.get("osvetlitev") in OSVETLITVE else "studio",
            "ozadje": nastavitve.get("ozadje") if nastavitve.get("ozadje") in OZADJA else "svetlo",
            "sirina": int(sirina * merilo) // 2 * 2,
            "visina": int(visina * merilo) // 2 * 2,
            "vzorci": vzorci,
            "vrtenje": vrtenje,
            "izhod": mapa,
        }
        with open(os.path.join(mapa, "naloga.json"), "w", encoding="utf-8") as f:
            json.dump(naloga, f, ensure_ascii=False, indent=1)
        varno_ime = re.sub(r'[\\/:*?"<>|]+', "_", ime).strip() or "render"
        stanje = {"id": nid, "stanje": "caka", "napredek": 0.0, "sporocilo": "Čaka v vrsti",
                  "ustvarjeno": time.time(), "zacetek": None, "konec": None, "mapa": mapa, "blender": blender,
                  "ime": varno_ime, "kopija": kopija, "datoteka": None, "shranjeno": None, "video": bool(vrtenje),
                  "sirina": naloga["sirina"], "visina": naloga["visina"], "vzorci": vzorci}
        with self.zaklep:
            self.naloge[nid] = stanje
            self.vrsta.append(nid)
            if self.nit is None or not self.nit.is_alive():
                self.nit = threading.Thread(target=self._delavec, name="upodabljanje", daemon=True)
                self.nit.start()
        return nid

    def stanje(self, nid):
        with self.zaklep:
            s = self.naloge.get(nid)
            if s is None:
                return None
            izid = {k: v for k, v in s.items() if k not in ("blender", "mapa")}
        zac = izid.get("zacetek")
        izid["cas"] = round((izid.get("konec") or time.time()) - zac, 1) if zac else 0
        if izid["stanje"] == "caka":
            izid["pred"] = self.vrsta.index(nid) if nid in self.vrsta else 0
        return izid

    def seznam(self):
        with self.zaklep:
            ids = sorted(self.naloge, reverse=True)[:30]
        return [self.stanje(i) for i in ids]

    def datoteka(self, nid):
        with self.zaklep:
            s = self.naloge.get(nid)
            return s and s.get("datoteka")

    def ustavi(self, nid):
        with self.zaklep:
            s = self.naloge.get(nid)
            if s is None:
                return False
            if nid in self.vrsta:
                self.vrsta.remove(nid)
                s.update(stanje="ustavljeno", sporocilo="Preklicano", konec=time.time())
                return True
            if self.tekoca == nid and self.proces is not None:
                s["ustavljam"] = True
                try:
                    self.proces.kill()
                except OSError:
                    pass
                return True
        return False

    # -- delavec ----------------------------------------------------------------------------------------------

    def _delavec(self):
        while True:
            with self.zaklep:
                if not self.vrsta:
                    self.nit = None
                    return
                nid = self.vrsta.pop(0)
                s = self.naloge[nid]
                s.update(stanje="tece", sporocilo="Zaganjam Blender …", zacetek=time.time())
                self.tekoca = nid
            try:
                self._izvedi(s)
            except Exception as e:  # noqa: BLE001
                with self.zaklep:
                    s.update(stanje="napaka", sporocilo=str(e), konec=time.time())
            finally:
                with self.zaklep:
                    self.tekoca, self.proces = None, None

    def _posodobi(self, s, **kw):
        with self.zaklep:
            s.update(**kw)

    def _izvedi(self, s):
        if self.brez_optix:
            self._naprave(s["mapa"], ["CUDA", "HIP", "ONEAPI", "METAL"])
        try:
            self._izvedi_enkrat(s)
        except RuntimeError:
            with open(os.path.join(s["mapa"], "dnevnik.txt"), encoding="utf-8", errors="replace") as f:
                optix = "OptiX kernel" in f.read()
            if not optix or self.brez_optix or s.get("ustavljam"):
                raise
            self.brez_optix = True
            try:
                os.makedirs(DELOVNA, exist_ok=True)
                with open(BREZ_OPTIX, "w", encoding="utf-8") as f:
                    f.write("OptiX v %s se s tem gonilnikom NVIDIA ni prevedel; render teče s CUDA.\n" % s["blender"])
            except OSError:
                pass
            self._posodobi(s, napredek=0.0, sporocilo="OptiX ne dela s tem gonilnikom; ponavljam s CUDA")
            self._naprave(s["mapa"], ["CUDA", "HIP", "ONEAPI", "METAL"])
            self._izvedi_enkrat(s)

    @staticmethod
    def _naprave(mapa, vrste):
        pot = os.path.join(mapa, "naloga.json")
        with open(pot, encoding="utf-8") as f:
            naloga = json.load(f)
        naloga["naprave"] = vrste
        with open(pot, "w", encoding="utf-8") as f:
            json.dump(naloga, f, ensure_ascii=False, indent=1)

    def _izvedi_enkrat(self, s):
        mapa = s["mapa"]
        ukaz = [s["blender"], "-b", "--factory-startup", "--python-exit-code", "1",
                "--python", RENDER_PY, "--", os.path.join(mapa, "naloga.json")]
        dnevnik = open(os.path.join(mapa, "dnevnik.txt"), "w", encoding="utf-8", errors="replace")
        proces = subprocess.Popen(ukaz, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=mapa,
                                  env=_cisto_okolje(), **_brez_okna())
        with self.zaklep:
            self.proces = proces
        napaka = ""
        slicic = 0
        for vrstica in iter(proces.stdout.readline, b""):
            v = vrstica.decode("utf-8", "replace").rstrip()
            dnevnik.write(v + "\n")
            dnevnik.flush()
            m = re.search(r"Sample (\d+)/(\d+)", v) or re.search(r"(\d+)\s*/\s*(\d+)\s+samples", v)
            if m and not s["video"]:
                a, b = int(m.group(1)), max(int(m.group(2)), 1)
                self._posodobi(s, napredek=0.1 + 0.85 * a / b, sporocilo="Rišem: vzorec %d od %d" % (a, b))
            elif v.startswith("SLICICA "):
                a, b = (int(x) for x in v.split()[1].split("/"))
                slicic = b
                self._posodobi(s, napredek=0.05 + 0.85 * a / b, sporocilo="Rišem sličico %d od %d" % (a, b))
            elif v.startswith("SCENA "):
                self._posodobi(s, napredek=0.06, sporocilo="Scena pripravljena")
            elif v.startswith("NAPRAVA "):
                self._posodobi(s, naprava=v[8:].strip(), sporocilo="Pripravljam render (" + v[8:].split(",")[0].strip() + ")")
            elif v.startswith("Compiling") or "Loading render kernels" in v:
                self._posodobi(s, sporocilo="Pripravljam jedra grafične kartice (prvič traja dlje)")
            elif v.startswith("NAPAKA"):
                napaka = v[6:].strip(" :")
        koda = proces.wait()
        dnevnik.close()
        if s.get("ustavljam"):
            self._posodobi(s, stanje="ustavljeno", sporocilo="Ustavljeno", konec=time.time())
            return
        if s["video"]:
            if koda != 0:
                raise RuntimeError(napaka or "Blender je končal s kodo %d (dnevnik.txt)" % koda)
            self._posodobi(s, napredek=0.93, sporocilo="Sestavljam video")
            datoteka = self._video(mapa, slicic)
        else:
            datoteka = os.path.join(mapa, "render.png")
            if koda != 0 or not os.path.isfile(datoteka):
                raise RuntimeError(napaka or "Blender je končal s kodo %d (dnevnik.txt)" % koda)
        shranjeno = None
        if s.get("kopija"):
            try:
                os.makedirs(s["kopija"], exist_ok=True)
                konc = os.path.splitext(datoteka)[1]
                shranjeno = os.path.join(s["kopija"], "%s %s%s" % (s["ime"], datetime.datetime.now().strftime("%Y-%m-%d %H-%M-%S"), konc))
                shutil.copyfile(datoteka, shranjeno)
            except OSError:
                shranjeno = None
        self._posodobi(s, stanje="koncano", napredek=1.0, datoteka=datoteka, shranjeno=shranjeno,
                       sporocilo="Končano", konec=time.time())

    def _video(self, mapa, slicic):
        ffmpeg = najdi_ffmpeg()
        if not ffmpeg:
            raise RuntimeError("Za video manjka ffmpeg (winget install Gyan.FFmpeg); sličice so v " + mapa)
        izhod = os.path.join(mapa, "vrtenje.mp4")
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-framerate", "30", "-i", os.path.join(mapa, "slicica_%04d.png"),
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-movflags", "+faststart", izhod],
                       check=True, cwd=mapa, **_brez_okna())
        return izhod


UPODABLJANJE = Upodabljanje()
