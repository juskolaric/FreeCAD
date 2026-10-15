# -*- coding: utf-8 -*-
"""Samodejno shranjevanje in tiha obnova dokumentov (od 2026-10-11, želja uporabnika).

- **Obnova dokumentov**: FreeCAD-ovo okno »Obnovitev dokumenta« (po nasilnem koncu prejšnjega primerka) se ne pokaže
  več v brskalniku: strežnik obnovo izvede sam (`accept()` dvakrat: obnovi, nato Konec). Obnovljen dokument, katerega
  datoteka na disku je novejša od obnovitvene kopije, se samodejno ne shranjuje (sicer bi starejša vsebina prepisala
  novejšo); strežnik to javi z obvestilom.
- **Samodejno shranjevanje**: vsak spremenjen dokument z datoteko se shrani, ko MIROVANJE sekund ni nove spremembe
  ali najkasneje NAJDLJE sekund po prvi neshranjeni spremembi. Ne shranjuje med urejanjem (opravilo, skica v
  brskalniku), med odprtim modalnim oknom, med nalaganjem, delno naloženih dokumentov, ogledov različic iz oblaka in
  datotek, ki jih je medtem spremenil kdo drug (odjemalec oblaka, drug program): te javi in pusti neshranjene.
  Shranjevanje je tiho (brskalnik ne vpraša »Kaj si spremenil?«).
- Izklop: okoljska `SPLET_SAMODEJNO_SHRANJEVANJE=0`.

Vse teče na glavni niti (klic `korak(stanje)` iz `Stanje.obdelaj`)."""
import os
import time
import traceback

import FreeCAD as App

try:
    import FreeCADGui as Gui
except ImportError:  # pragma: no cover
    Gui = None

VKLOPLJENO = os.environ.get("SPLET_SAMODEJNO_SHRANJEVANJE", "1") not in ("0", "false", "ne")
MIROVANJE = 8.0      # s brez nove spremembe -> shrani
NAJDLJE = 90.0       # s od prve neshranjene spremembe -> shrani tudi med delom
PREGLED = 1.0        # s med pregledi
PONOVI_PO = 300.0    # s po neuspelem shranjevanju

_zadnji = 0.0
_sledi = {}          # ime dokumenta -> {"odtis", "prva", "zadnja", "mtime", "pot", "napaka_do", "javljeno"}
_brez = {}           # ime dokumenta -> razlog, zakaj se ne shranjuje samodejno


def _log(besedilo):
    App.Console.PrintMessage("[splet] samodejno: %s\n" % besedilo)


def _mtime(pot):
    try:
        return os.path.getmtime(pot)
    except OSError:
        return None


def _modalno():
    try:
        from PySide6 import QtWidgets
        return QtWidgets.QApplication.activeModalWidget()
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Tiha obnova

def obnovi_tiho(stanje):
    """Če čaka FreeCAD-ovo okno »Obnovitev dokumenta«, obnovo izvede in okno zapre. Vrne True, če je kaj naredil."""
    okno = _modalno()
    if okno is None or okno.metaObject().className() != "Gui::Dialog::DocumentRecovery":
        return False
    prej = set(App.listDocuments())
    _log("obnova dokumentov po nasilnem koncu: obnavljam brez vprašanja")
    try:
        okno.accept()      # 1. klic: obnovi vse, gumb postane »Konec«
        if okno.isVisible():
            okno.accept()  # 2. klic: zapre okno
    except Exception:  # noqa: BLE001
        _log("obnova ni uspela: %s" % traceback.format_exc())
        return True
    novi = [d for ime, d in App.listDocuments().items() if ime not in prej]
    for d in novi:
        oznaci_obnovljenega(stanje, d)
    if novi:
        stanje.oddaj("obvestilo", {"sporocilo": "Obnovljeni dokumenti po nepričakovanem koncu: %s." %
                                   ", ".join(d.Label for d in novi)})
    return True


def oznaci_obnovljenega(stanje, doc):
    """Obnovljen dokument: če je datoteka na disku novejša od obnovitvene kopije, ga samodejno ne shranjuj."""
    if not doc.FileName:
        return
    kopija = os.path.join(doc.TransientDir or "", "fc_recovery_file.fcstd")
    t_kopija, t_disk = _mtime(kopija), _mtime(doc.FileName)
    if t_kopija is not None and t_disk is not None and t_disk > t_kopija + 1:
        _brez[doc.Name] = "datoteka na disku je novejša od obnovljene kopije"
        _log("%s: %s; samodejno shranjevanje izklopljeno za ta dokument" % (doc.Label, _brez[doc.Name]))
        stanje.oddaj("obvestilo", {"sporocilo": "»%s«: datoteka na disku je novejša od obnovljene kopije. Ne shranjujem "
                                   "je samodejno; shrani ročno, če želiš obdržati obnovljeno." % doc.Label, "slabo": True})


# ---------------------------------------------------------------------------
# Samodejno shranjevanje

def _odtis(doc):
    return (doc.UndoCount, doc.RedoCount, len(doc.Objects))


def _ovira(stanje, doc, gdoc):
    """Razlog, zakaj dokumenta zdaj ne shranimo (ali None)."""
    if getattr(doc, "Restoring", False) or getattr(doc, "Partial", False):
        return "nalaganje"
    if getattr(doc, "HasPendingTransaction", False):
        return "transakcija"
    if gdoc.getInEdit() is not None:
        return "urejanje"
    if getattr(stanje, "skica", "") and App.ActiveDocument is doc:
        return "skica"
    try:
        oblak = getattr(stanje, "_oblak", None)
        if oblak is not None and oblak.je_razlicica(doc.FileName):
            return "različica"
    except Exception:  # noqa: BLE001
        pass
    if "FreeCAD-splet" in doc.FileName.replace("\\", "/").split("/"):
        return "začasna datoteka"
    return None


def _javi_oblaku(stanje, oblak, doc):
    """Samodejno shranjena datoteka iz mape oblaka je nova različica: stran pošlje sličico (brez vprašanja »Kaj si
    spremenil?«) in vrstico različic osveži, ko odjemalec oblaka revizijo pošlje (dogodek »razlicica«)."""
    try:
        if oblak is None or not oblak.prijavljen() or not oblak.v_oblaku(doc.FileName) or oblak.je_razlicica(doc.FileName):
            return
        stanje.oddaj("oblak", {"vrsta": "shranjeno", "samodejno": True, "pot": doc.FileName, "ime": doc.Label,
                               "verzija": int(doc.Meta.get("Verzija", "0") or 0)})
    except Exception as e:  # noqa: BLE001
        _log("dogodek oblaka po shranjevanju: %r" % e)


def korak(stanje, oblak=None):
    """En pregled; kliče ga glavna nit pogosto, dela pa največ enkrat na PREGLED sekund."""
    global _zadnji
    if Gui is None:
        return
    if obnovi_tiho(stanje):   # vsak klic: okno obnove ne sme priti do brskalnika (obrazec se zajame na 0,25 s)
        return
    zdaj = time.time()
    if zdaj - _zadnji < PREGLED:
        return
    _zadnji = zdaj
    if not VKLOPLJENO:
        return
    if oblak is not None:
        stanje._oblak = oblak
    dokumenti = App.listDocuments()
    for ime in list(_sledi):
        if ime not in dokumenti:
            _sledi.pop(ime, None)
            _brez.pop(ime, None)
    modalno = _modalno() is not None
    shranjeno = []
    for ime, doc in dokumenti.items():
        if not doc.FileName:
            continue
        try:
            gdoc = Gui.getDocument(ime)
        except Exception:  # noqa: BLE001
            continue
        if gdoc is None:
            continue
        s = _sledi.get(ime)
        if s is None or s["pot"] != doc.FileName:
            s = _sledi[ime] = {"odtis": None, "prva": None, "zadnja": zdaj, "mtime": _mtime(doc.FileName),
                               "pot": doc.FileName, "napaka_do": 0.0, "javljeno": False}
        if not gdoc.Modified:
            s.update(prva=None, odtis=None, javljeno=False, mtime=_mtime(doc.FileName))
            continue
        odtis = _odtis(doc)
        if odtis != s["odtis"]:
            s["odtis"], s["zadnja"] = odtis, zdaj
        if s["prva"] is None:
            s["prva"] = zdaj
        if ime in _brez or modalno or zdaj < s["napaka_do"]:
            continue
        if zdaj - s["zadnja"] < MIROVANJE and zdaj - s["prva"] < NAJDLJE:
            continue
        if _ovira(stanje, doc, gdoc):
            continue
        disk = _mtime(doc.FileName)
        if disk is not None and s["mtime"] is not None and abs(disk - s["mtime"]) > 1:
            if not s["javljeno"]:
                s["javljeno"] = True
                _log("%s: datoteko je medtem spremenil kdo drug; ne shranjujem" % doc.Label)
                stanje.oddaj("obvestilo", {"sporocilo": "»%s« je na disku medtem spremenil drug program (morda oblak). "
                                           "Samodejno ga ne shranim; odloči ročno." % doc.Label, "slabo": True})
            continue
        if os.path.exists(doc.FileName) and not os.access(doc.FileName, os.W_OK):
            s["napaka_do"] = zdaj + PONOVI_PO
            continue
        stanje.tiho_shranjevanje = True
        try:
            doc.save()
            gdoc.Modified = False
            s.update(prva=None, odtis=None, mtime=_mtime(doc.FileName))
            shranjeno.append(doc.Label)
            _javi_oblaku(stanje, oblak, doc)
        except Exception as e:  # noqa: BLE001
            s["napaka_do"] = zdaj + PONOVI_PO
            _log("%s: shranjevanje ni uspelo (%s); poskusim znova čez %d s" % (doc.Label, e, PONOVI_PO))
            stanje.oddaj("obvestilo", {"sporocilo": "Samodejno shranjevanje »%s« ni uspelo: %s" % (doc.Label, e),
                                       "slabo": True})
        finally:
            stanje.tiho_shranjevanje = False
    if shranjeno:
        _log("shranjeno: %s" % ", ".join(shranjeno))
        stanje.zadnji_projekti = 0.0


def velja_za(doc):
    """Ali se dokument shranjuje sam (za seznam odprtih: vrstica različic namesto gumba Shrani pokaže stanje)."""
    return bool(VKLOPLJENO and doc.FileName and doc.Name not in _brez
                and "FreeCAD-splet" not in doc.FileName.replace("\\", "/").split("/"))


def stanje_samodejnega():
    """Za diagnostiko (python orodje): kaj se sledi in kaj je izključeno."""
    return {"vklopljeno": VKLOPLJENO, "brez": dict(_brez),
            "sledi": {k: {kk: v for kk, v in s.items() if kk != "odtis"} for k, s in _sledi.items()}}
