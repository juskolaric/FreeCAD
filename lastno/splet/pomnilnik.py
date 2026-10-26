"""Pomnilnik spletnega FreeCAD-a: seznam dokumentov brez puščanja in opozorilo, ko proces zraste čez prag.

Vzrok (izmerjeno 2026-10-16, proces z 185 odprtimi dokumenti in 57,7 GB zasebnega pomnilnika): FreeCAD-ov
`App.listDocuments()` (C++ `Application::sListDocuments`, tudi v upstream main) ključ slovarja ustvari s
`PyUnicode_FromString` in ga po `PyDict_SetItem` nikoli ne sprosti. Vsak klic zato pusti po en niz na odprt
dokument (185 dokumentov = ~15 kB na klic). Strežnik ga kliče večkrat na sekundo (ogrevanje, okolja, samodejno
shranjevanje, seznam projektov), v dveh dneh se je nabralo 48 GB nizov z imeni dokumentov v arenah Pythona
(49.000 aren po 1 MB, 99 % `str` z refcnt 1). Teh nizov ni mogoče sprostiti; pomaga le nov zagon procesa.

`namesti()` zamenja `App.listDocuments` z ovojem, ki slovar hrani in ga zgradi znova le, ko se dokument odpre,
ustvari ali zapre (opazovalec dokumentov) ali ko kateri od hranjenih dokumentov ni več veljaven. Ob gradnji pusti
C++ še vedno po en niz na dokument, a le ob odpiranju in zapiranju, ne več večkrat na sekundo. Popravek v C++
(`Py_DECREF(pKey)`) je v `src/App/ApplicationPy.cpp`; ko je v tekočem programu, `preizkusi_puscanje` to opazi.

Pravilo niti: `stanje()` (branje števcev procesa in sistema) sme teči na niti strežnika; `namesti()` in
`preveri()` tečeta na glavni niti.
"""
import ctypes
import ctypes.wintypes as wt
import os
import shutil
import sys
import time
import types

import FreeCAD as App

GB = 1024 ** 3
PRAG_GB = float(os.environ.get("SPLET_POMNILNIK_OPOZORILO_GB", "16"))   # zasebni pomnilnik procesa
PRAG_DISK_GB = 5.0           # prost prostor na disku ostranjevalne datoteke (C:)
PRAG_COMMIT = 0.90           # delež porabljene meje zavezanega pomnilnika (RAM + ostranjevalna datoteka)
RAZMIK_PREVERJANJA = 30.0    # s med preverjanji v glavni zanki
RAZMIK_OPOZORILA = 3600.0    # s med ponovljenimi opozorili v brskalniku, če se stanje ne poslabša


class SeznamDokumentov:
    """Nadomestek `App.listDocuments` brez puščanja nizov (glej opis modula). Vrne vedno nov slovar (klicatelj ga
    sme spreminjati), z istimi ključi in vrstnim redom kot C++ (abecedno po imenu)."""

    def __init__(self, izvirnik):
        self.izvirnik = izvirnik
        self.slovar = None
        self.pusca = None            # True/False po prvi gradnji z vsaj enim dokumentom
        self.klicev = 0
        self.gradenj = 0             # klicev izvirnika (vsak pusti po en niz na dokument, dokler C++ ni popravljen)
        self.zacetek = time.time()

    # opazovalec dokumentov (App.addDocumentObserver): ob odpiranju, ustvarjanju in zapiranju slovar zavrže
    def slotCreatedDocument(self, doc):
        self.slovar = None

    def slotDeletedDocument(self, doc):
        # signal pride, preden je dokument odstranjen iz seznama; če ga kdo vmes zgradi znova, ga ob naslednjem
        # klicu zavrže preverjanje veljavnosti (zaprt dokument vrže ReferenceError)
        self.slovar = None

    def _veljaven(self):
        try:
            for d in self.slovar.values():
                d.Name
        except Exception:  # noqa: BLE001  (ReferenceError za zaprt dokument)
            return False
        return True

    def __call__(self, *args):
        self.klicev += 1
        if args and args != (False,):
            # razvrščanje po odvisnostih (sort=True) se spremeni tudi brez odpiranja in zapiranja: vedno iz C++
            self.gradenj += 1
            return self.izvirnik(*args)
        if self.slovar is None or not self._veljaven():
            self.slovar = self.izvirnik()
            self.gradenj += 1
            if self.pusca is None and self.slovar:
                self.pusca = preizkusi_puscanje(self.slovar)
        return dict(self.slovar)

    def povzetek(self):
        cas = max(time.time() - self.zacetek, 1e-6)
        return {"klicev": self.klicev, "gradenj": self.gradenj, "na_sekundo": round(self.klicev / cas, 2),
                "pusca_cpp": self.pusca}


def preizkusi_puscanje(slovar):
    """Ali C++ `listDocuments` pušča ključe: v slovarju, ki ga je pravkar vrnil, ima ključ brez puščanja 3
    reference (slovar, spremenljivka, argument getrefcount), s puščanjem 4. Ne deluje na praznem slovarju."""
    if not slovar:
        return None
    k = next(iter(slovar))
    return sys.getrefcount(k) > 3


def _izvirnik():
    """C++ funkcija ne glede na to, kaj je trenutno v App.listDocuments (ponovna namestitev, števci iz preiskave)."""
    for kandidat in (App.__dict__.get("_listDocuments_cpp"), App.__dict__.get("_listDocuments_izvirnik"),
                     App.__dict__.get("listDocuments")):
        if isinstance(kandidat, types.BuiltinFunctionType):
            return kandidat
        if _je_ovoj(kandidat):
            return kandidat.izvirnik
    return None


def _je_ovoj(x):
    """Ovoj iz tega modula, tudi iz prejšnjega nalaganja (po reload je razred drug, zato ne isinstance)."""
    return isinstance(getattr(x, "izvirnik", None), types.BuiltinFunctionType) and hasattr(x, "slotDeletedDocument")


SEZNAM = None


def namesti():
    """Zamenja App.listDocuments z ovojem brez puščanja (glavna nit). Varno večkrat: prejšnji ovoj in njegov
    opazovalec se odstranita. Vrne SeznamDokumentov ali None, če C++ funkcije ni mogoče najti."""
    global SEZNAM
    izvirnik = _izvirnik()
    if izvirnik is None:
        return None
    App._listDocuments_cpp = izvirnik
    star = App.__dict__.get("listDocuments")
    if _je_ovoj(star):
        try:
            App.removeDocumentObserver(star)
        except Exception:  # noqa: BLE001
            pass
    SEZNAM = SeznamDokumentov(izvirnik)
    App.addDocumentObserver(SEZNAM)
    App.listDocuments = SEZNAM
    return SEZNAM


def odstrani():
    """Vrne izvirni App.listDocuments (npr. ko je C++ popravljen in ovoja ne želimo)."""
    global SEZNAM
    if SEZNAM is not None:
        try:
            App.removeDocumentObserver(SEZNAM)
        except Exception:  # noqa: BLE001
            pass
    izvirnik = _izvirnik()
    if izvirnik is not None:
        App.listDocuments = izvirnik
    SEZNAM = None


# ---------------------------------------------------------------------------------------------------------------
# Merjenje pomnilnika (Windows; drugje vrne prazno)

class _PMC(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t), ("PrivateUsage", ctypes.c_size_t)]


class _MSE(ctypes.Structure):
    _fields_ = [("dwLength", wt.DWORD), ("dwMemoryLoad", wt.DWORD), ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


def _meritev():
    if os.name != "nt":
        return {}
    k32 = ctypes.WinDLL("kernel32")
    pmc = _PMC()
    pmc.cb = ctypes.sizeof(pmc)
    k32.GetCurrentProcess.restype = wt.HANDLE
    k32.K32GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.POINTER(_PMC), wt.DWORD]
    izid = {}
    if k32.K32GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
        izid["zasebni_gb"] = round(pmc.PrivateUsage / GB, 2)
        izid["delovni_gb"] = round(pmc.WorkingSetSize / GB, 2)
    mse = _MSE()
    mse.dwLength = ctypes.sizeof(mse)
    if k32.GlobalMemoryStatusEx(ctypes.byref(mse)):
        izid["commit_gb"] = round((mse.ullTotalPageFile - mse.ullAvailPageFile) / GB, 1)
        izid["commit_meja_gb"] = round(mse.ullTotalPageFile / GB, 1)
        izid["ram_gb"] = round(mse.ullTotalPhys / GB, 1)
    try:
        izid["disk_prosto_gb"] = round(shutil.disk_usage(os.environ.get("SystemDrive", "C:") + "\\").free / GB, 1)
    except OSError:
        pass
    return izid


def stanje():
    """Meritve procesa in sistema ter opozorila (sme na niti strežnika). Ključ `opozorila` je seznam besedil."""
    izid = _meritev()
    if SEZNAM is not None:
        izid["seznam_dokumentov"] = SEZNAM.povzetek()
    opozorila = []
    if izid.get("zasebni_gb", 0) >= PRAG_GB:
        opozorila.append("FreeCAD drži %.1f GB pomnilnika (prag %g GB). Shrani dokumente in ga zaženi znova "
                         "(Izhod, nato zagon); odvečne dokumente zapri." % (izid["zasebni_gb"], PRAG_GB))
    if izid.get("commit_meja_gb") and izid.get("commit_gb", 0) >= PRAG_COMMIT * izid["commit_meja_gb"]:
        opozorila.append("Sistem je porabil %.0f od %.0f GB zavezanega pomnilnika; ostranjevalna datoteka raste na "
                         "disku." % (izid["commit_gb"], izid["commit_meja_gb"]))
    if "disk_prosto_gb" in izid and izid["disk_prosto_gb"] < PRAG_DISK_GB:
        opozorila.append("Na disku C je prostih le %.1f GB; shranjevanje lahko odpove." % izid["disk_prosto_gb"])
    if SEZNAM is None and _izvirnik() is not None:
        opozorila.append("Seznam dokumentov teče brez ovoja: App.listDocuments pušča pomnilnik ob vsakem klicu.")
    izid["opozorila"] = opozorila
    return izid


def povzetek_vrstica(st=None):
    """Ena vrstica za orodje `stanje`."""
    st = st if st is not None else stanje()
    if "zasebni_gb" not in st:
        return ""
    v = "Pomnilnik FreeCAD-a: %.1f GB zasebnega (prag %g GB), v RAM %.1f GB" % (
        st["zasebni_gb"], PRAG_GB, st.get("delovni_gb", 0))
    if "commit_gb" in st:
        v += " · sistem %.0f/%.0f GB zavezanega" % (st["commit_gb"], st["commit_meja_gb"])
    if "disk_prosto_gb" in st:
        v += " · disk C prosto %.1f GB" % st["disk_prosto_gb"]
    sd = st.get("seznam_dokumentov")
    if sd:
        v += " · listDocuments: ovoj (%s)" % {True: "C++ pušča", False: "C++ ne pušča", None: "?"}[sd["pusca_cpp"]]
    for o in st.get("opozorila", []):
        v += "\nOPOZORILO: " + o
    return v


_ZADNJE = {"preverjeno": 0.0, "opozorjeno": 0.0, "raven": 0.0}


def preveri(oddaj):
    """Iz glavne zanke: največ vsakih RAZMIK_PREVERJANJA s izmeri in ob prekoračenju praga v brskalnik pošlje
    obvestilo (`oddaj(dogodek, podatki)`): ob prvem prestopu, ob rasti za nadaljnjih 25 % in sicer največ na uro."""
    zdaj = time.time()
    if zdaj - _ZADNJE["preverjeno"] < RAZMIK_PREVERJANJA:
        return None
    _ZADNJE["preverjeno"] = zdaj
    st = stanje()
    if not st.get("opozorila"):
        _ZADNJE["raven"] = 0.0
        return st
    raven = max(st.get("zasebni_gb", 0.0), 0.01)
    if raven >= 1.25 * _ZADNJE["raven"] or zdaj - _ZADNJE["opozorjeno"] >= RAZMIK_OPOZORILA:
        _ZADNJE["opozorjeno"] = zdaj
        _ZADNJE["raven"] = raven
        oddaj("obvestilo", {"sporocilo": " ".join(st["opozorila"]), "slabo": True})
    return st
