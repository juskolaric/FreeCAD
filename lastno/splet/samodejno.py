# -*- coding: utf-8 -*-
"""Samodejno shranjevanje in tiha obnova dokumentov (od 2026-10-11, želja uporabnika).

- **Obnova dokumentov**: FreeCAD-ovo okno »Obnovitev dokumenta« (po nasilnem koncu prejšnjega primerka) se ne pokaže
  v brskalniku in **ne odpre dokumentov** (od 2026-10-29, želja uporabnika: ob zagonu se odprejo le dokumenti, ki jih
  izbere sam). Strežnik obnovitvene kopije premakne v `%LOCALAPPDATA%/FreeCAD-splet/obnova/<čas>/` (s `PREBERI.txt`)
  in okno zapre; kopije, novejše od datoteke na disku, javi z obvestilom. Do 28. 10. je obnovo izvedel sam (`accept()`).
- **Samodejno shranjevanje**: vsak spremenjen dokument z datoteko se shrani, ko MIROVANJE sekund ni nove spremembe
  ali najkasneje NAJDLJE sekund po prvi neshranjeni spremembi. Ne shranjuje med urejanjem (opravilo, skica v
  brskalniku), med odprtim modalnim oknom, med nalaganjem, delno naloženih dokumentov, ogledov različic iz oblaka in
  datotek, ki jih je medtem spremenil kdo drug (odjemalec oblaka, drug program): te javi in pusti neshranjene.
  Shranjevanje je tiho (brskalnik ne vpraša »Kaj si spremenil?«).
- **Delno naložen dokument** (odprt prek povezave iz sestava, `Partial`; od 2026-10-17): FreeCAD ga ne shrani
  (`save()` ne zapiše nič in vrne uspeh). S spremembami ga strežnik enkrat javi z obvestilom (ne tihega preskoka);
  shrani ga »Shrani različico« v brskalniku ali orodje `shrani` z nalozi_v_celoti (delno.py ohrani spremembe).
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
# Obnova brez odpiranja (od 2026-10-29)

def _podatki_kopije(mapa):
    """Oznaka, izvirna pot in ali ima obnovitvena kopija v `mapa` spremembe, ki jih na disku ni."""
    oznaka, pot = os.path.basename(mapa), ""
    try:
        import xml.etree.ElementTree as ET
        koren = ET.parse(os.path.join(mapa, "fc_recovery_file.xml")).getroot()
        oznaka = koren.findtext("Label") or oznaka
        pot = koren.findtext("FileName") or ""
    except Exception:  # noqa: BLE001
        pass
    kopija = os.path.join(mapa, "fc_recovery_file.fcstd")
    t_kopija, t_disk = _mtime(kopija), _mtime(pot) if pot else None
    novejsa = bool(t_kopija is not None and os.path.getsize(kopija) > 0 and (t_disk is None or t_kopija > t_disk + 1))
    return oznaka, pot, novejsa


def umakni_obnovo(stanje):
    """Če čaka FreeCAD-ovo okno »Obnovitev dokumenta«, dokumentov ne odpre: obnovitvene kopije prejšnjih (nasilno
    končanih) primerkov premakne v FreeCAD-splet/obnova/<čas>/ in okno zapre. Ob zagonu se tako odprejo le dokumenti,
    ki jih uporabnik izbere sam (želja uporabnika 2026-10-29; prej se je odprlo ~150 dokumentov in zagon je trajal
    minute). Samodejno shranjevanje (8 s) skrbi, da kopije redko vsebujejo kaj, česar na disku ni; tiste, ki
    vsebujejo, javi z obvestilom. Vrne True, če je kaj naredil."""
    okno = _modalno()
    if okno is None or okno.metaObject().className() != "Gui::Dialog::DocumentRecovery":
        return False
    import shutil
    from PySide6 import QtWidgets
    cilj = os.path.join(os.environ.get("LOCALAPPDATA", ""), "FreeCAD-splet", "obnova", time.strftime("%Y-%m-%d_%H%M%S"))
    umaknjeni, novejsi = [], []
    try:
        drevo = okno.findChild(QtWidgets.QTreeWidget)
        mape = set()
        for i in range(drevo.topLevelItemCount() if drevo is not None else 0):
            projekt = drevo.topLevelItem(i).toolTip(1)   # pot do fc_recovery_file.fcstd ali Document.xml v mapi kopije
            if projekt:
                mape.add(os.path.dirname(os.path.normpath(projekt)))
        for mapa in sorted(mape):
            if not os.path.isdir(mapa):
                continue
            oznaka, pot, novejsa = _podatki_kopije(mapa)
            os.makedirs(cilj, exist_ok=True)
            shutil.move(mapa, os.path.join(cilj, os.path.basename(mapa)))
            umaknjeni.append("%s\t%s\t%s\t%s" % (os.path.basename(mapa), oznaka, pot,
                                                 "NOVEJŠA OD DISKA" if novejsa else "enaka ali starejša"))
            if novejsa:
                novejsi.append(oznaka)
        if umaknjeni:
            with open(os.path.join(cilj, "PREBERI.txt"), "w", encoding="utf-8") as f:
                f.write("Obnovitvene kopije FreeCAD-a po nasilnem koncu, umaknjene ob zagonu %s (dokumenti se niso\n"
                        "odprli sami). Vsaka mapa ima fc_recovery_file.fcstd = običajna datoteka FCStd; odpri jo, če rabiš\n"
                        "spremembe, ki jih na disku ni (vrstice NOVEJŠA OD DISKA).\n\nmapa\toznaka\tizvirna pot\tstanje\n"
                        % time.strftime("%d. %m. %Y %H:%M"))
                f.write("\n".join(umaknjeni) + "\n")
    except Exception:  # noqa: BLE001
        _log("umik obnovitvenih kopij ni uspel: %s" % traceback.format_exc())
    okno.reject()   # okno zapre brez obnove; česar ni bilo mogoče umakniti, ostane v predpomnilniku za naslednji zagon
    _log("prejšnji primerek se je končal nasilno: dokumentov ne odpiram, %d kopij umaknjenih v %s" % (len(umaknjeni), cilj))
    if novejsi:
        stanje.oddaj("obvestilo", {"sporocilo": "FreeCAD se je zadnjič končal nepričakovano. Dokumentov ne odpiram samih; "
                                   "neshranjene spremembe so imeli: %s. Kopije so v %s." % (", ".join(novejsi), cilj),
                                   "slabo": True})
    return True


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


def _javi_delnega(stanje, doc):
    """Delen dokument s spremembami: samodejno se ne shrani (FreeCAD ga ne zapiše); enkrat obvestilo v brskalnik."""
    try:
        import delno
        kaj = delno.opis(doc)
    except Exception:  # noqa: BLE001
        kaj = "»%s« je naložen le delno" % doc.Label
    _log("%s; ima spremembe, samodejno se ne shrani" % kaj)
    stanje.oddaj("obvestilo", {"sporocilo": "%s, zato se njegove spremembe ne shranijo (niti samodejno). Shrani ga z "
                                            "»Shrani različico« (strežnik ga naloži v celoti in spremembe ohrani), sicer "
                                            "se ob zaprtju ali ponovnem zagonu izgubijo." % kaj, "slabo": True})


def korak(stanje, oblak=None):
    """En pregled; kliče ga glavna nit pogosto, dela pa največ enkrat na PREGLED sekund."""
    global _zadnji
    if Gui is None:
        return
    if umakni_obnovo(stanje):   # vsak klic: okno obnove ne sme priti do brskalnika (obrazec se zajame na 0,25 s)
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
            s.update(prva=None, odtis=None, javljeno=False, delno_javljeno=False, mtime=_mtime(doc.FileName))
            continue
        if getattr(doc, "Partial", False) and not getattr(doc, "Restoring", False):
            if not s.get("delno_javljeno"):
                s["delno_javljeno"] = True
                _javi_delnega(stanje, doc)
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
        if not os.path.exists(doc.FileName):
            continue   # datoteke ni več (projekt izbrisan ali umaknjen): ne zapiši je nazaj; zapre jo _zapri_izbrisane
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
    return bool(VKLOPLJENO and doc.FileName and doc.Name not in _brez and not getattr(doc, "Partial", False)
                and "FreeCAD-splet" not in doc.FileName.replace("\\", "/").split("/"))


def stanje_samodejnega():
    """Za diagnostiko (python orodje): kaj se sledi in kaj je izključeno."""
    return {"vklopljeno": VKLOPLJENO, "brez": dict(_brez),
            "sledi": {k: {kk: v for kk, v in s.items() if kk != "odtis"} for k, s in _sledi.items()}}
