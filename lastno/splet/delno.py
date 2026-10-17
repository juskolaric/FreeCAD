# -*- coding: utf-8 -*-
"""Delno naloženi dokumenti (`App.Document.Partial`), od 2026-10-17.

Ko FreeCAD odpre sestav s povezavami (App::Link) na druge datoteke, te datoteke naloži le delno (samo objekte, ki jih
povezava potrebuje), razen če je nastavitev BaseApp/Preferences/Document/NoPartialLoading = True. Delen dokument se
ne da shraniti, FreeCAD pa to skrije:

- `App::Document::save()` zapiše le FC_ERR in vrne True (Gui pokaže »shranjeno«, na disk ne gre nič);
- `saveAs()` dokumentu nastavi novo pot in prav tako ne zapiše ničesar;
- `saveCopy()` zapiše samo naložene objekte (okrnjena datoteka);
- `restore()` dokument naloži z diska v celoti in spremembe v pomnilniku zavrže (tudi razveljavitve).

17. 10. 2026 so se tako izgubile spremembe skript na veži in spalnici v celoti stanovanja. Ta modul:

- `zagotovi_nastavitev()`: ob zagonu strežnika NoPartialLoading = True (izklop: okoljska SPLET_DELNO_NALAGANJE=1),
- `nalozi_v_celoti(doc)`: polno nalaganje BREZ izgube sprememb (lastnosti naloženih objektov in njihovih pogledov se
  pred `restore()` zapišejo z `dumpPropertyContent`, po nalaganju se vrnejo tiste, ki se od diska razlikujejo; pred
  tem gre okrnjena varnostna kopija v %LOCALAPPDATA%/FreeCAD-splet/delni),
- `opis(doc)`: besedilo za napake in obvestila.

Vse razen `zagotovi_nastavitev` teče na glavni niti."""
import io
import os
import time
import traceback
import zipfile

import FreeCAD as App

try:
    import FreeCADGui as Gui
except ImportError:  # pragma: no cover
    Gui = None

SKUPINA = "User parameter:BaseApp/Preferences/Document"
MAPA_KOPIJ = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "FreeCAD-splet", "delni")


def _log(besedilo):
    App.Console.PrintMessage("[splet] delno: %s\n" % besedilo)


def je_delen(doc):
    return bool(doc is not None and getattr(doc, "Partial", False))


def zagotovi_nastavitev():
    """NoPartialLoading = True: FreeCAD jo prebere ob vsakem odpiranju (Application::openDocuments), zato velja takoj.
    Vrne (vrednost prej, vrednost zdaj)."""
    p = App.ParamGet(SKUPINA)
    prej = p.GetBool("NoPartialLoading", False)
    if os.environ.get("SPLET_DELNO_NALAGANJE", "0") in ("1", "true", "da"):
        return prej, prej
    if not prej:
        p.SetBool("NoPartialLoading", True)
    return prej, True


def _spremenjen(doc):
    try:
        return bool(Gui.getDocument(doc.Name).Modified) if (Gui is not None and App.GuiUp) else False
    except Exception:  # noqa: BLE001
        return False


def uporabniki(doc):
    """Oznake odprtih dokumentov, ki imajo povezavo na objekt tega dokumenta (kdo ga je naložil delno)."""
    izid = []
    for d in App.listDocuments().values():
        if d is doc:
            continue
        for o in d.Objects:
            if o.TypeId != "App::Link" and not o.hasExtension("App::LinkBaseExtension"):
                continue
            try:
                cilj = o.getLinkedObject(False)
            except Exception:  # noqa: BLE001
                continue
            if cilj is not None and cilj.Document is doc:
                izid.append(d.Label)
                break
    return izid


def opis(doc):
    """»X« (naložen le delno, prek povezave iz »Y«)."""
    od = uporabniki(doc)
    return "»%s« je naložen le delno%s" % (doc.Label, (" (odprt prek povezave iz »%s«)" % "«, »".join(od[:3])) if od else "")


# ---------------------------------------------------------------------------
# Polno nalaganje brez izgube sprememb

def _shranljive(vsebnik):
    """Imena lastnosti, ki gredo v datoteko (brez Transient / NoPersist)."""
    imena = []
    for ime in vsebnik.PropertiesList:
        try:
            vrsta = vsebnik.getTypeOfProperty(ime)
            stanje = vsebnik.getPropertyStatus(ime)
        except Exception:  # noqa: BLE001
            continue
        if "Transient" in vrsta or "NoPersist" in vrsta or "Transient" in stanje:
            continue
        imena.append(ime)
    return imena


def _vsebina(podatki):
    """Vsebina zip zapisa `dumpPropertyContent` brez časov in stiskanja (za primerjavo z vrednostjo z diska)."""
    try:
        with zipfile.ZipFile(io.BytesIO(bytes(podatki))) as z:
            return tuple((i.filename, z.read(i)) for i in z.infolist())
    except Exception:  # noqa: BLE001
        return bytes(podatki)


def _posnemi_vsebnik(vsebnik):
    lastnosti = {}
    for ime in _shranljive(vsebnik):
        try:
            lastnosti[ime] = {
                "vsebina": vsebnik.dumpPropertyContent(ime),
                "tip": vsebnik.getTypeIdOfProperty(ime),
                "skupina": vsebnik.getGroupOfProperty(ime),
                "opis": vsebnik.getDocumentationOfProperty(ime),
            }
        except Exception:  # noqa: BLE001
            pass   # lastnost brez zapisa (npr. nekatere Python lastnosti): ostane, kot je na disku
    return lastnosti


def _odtis_oblike(obj):
    oblika = getattr(obj, "Shape", None)
    if oblika is None or oblika.isNull():
        return None
    try:
        bb = oblika.BoundBox
        return (round(oblika.Volume, 3), round(oblika.Area, 3), len(oblika.Faces),
                tuple(round(x, 4) for x in (bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax)))
    except Exception:  # noqa: BLE001
        return None


def posnemi(doc):
    """Stanje naloženih objektov delnega dokumenta (lastnosti objekta in pogleda, vrsta, oblika za preverjanje)."""
    objekti = {}
    for obj in doc.Objects:
        vo = getattr(obj, "ViewObject", None) if App.GuiUp else None
        objekti[obj.Name] = {
            "tip": obj.TypeId,
            "oznaka": obj.Label,
            "lastnosti": _posnemi_vsebnik(obj),
            "pogled": _posnemi_vsebnik(vo) if vo is not None and hasattr(vo, "dumpPropertyContent") else {},
            "dotaknjen": "Touched" in obj.State,
            "oblika": _odtis_oblike(obj),
        }
    return {"objekti": objekti, "vrstni_red": [o.Name for o in doc.Objects]}


def _vrni_vsebnik(vsebnik, lastnosti, napake, kje):
    vrnjene = 0
    for ime, p in lastnosti.items():
        try:
            if ime not in vsebnik.PropertiesList:
                vsebnik.addProperty(p["tip"], ime, p["skupina"] or "Base", p["opis"] or "")
            elif _vsebina(vsebnik.dumpPropertyContent(ime)) == _vsebina(p["vsebina"]):
                continue   # enako kot na disku
            vsebnik.restorePropertyContent(ime, p["vsebina"])
            vrnjene += 1
        except Exception as e:  # noqa: BLE001
            napake.append("%s.%s: %s" % (kje, ime, e))
    return vrnjene


def vrni(doc, posnetek):
    """Po polnem nalaganju vrne lastnosti iz posnetka (le tiste, ki se od diska razlikujejo). Vrne povzetek."""
    napake, novi, vrnjene, pogledi = [], [], 0, 0
    objekti = posnetek["objekti"]
    for ime in posnetek["vrstni_red"]:   # najprej objekti, ki jih na disku ni (ustvarjeni v pomnilniku)
        if doc.getObject(ime) is None:
            try:
                nov = doc.addObject(objekti[ime]["tip"], ime)
                if nov.Name != ime:
                    napake.append("%s: ustvarjen kot %s" % (ime, nov.Name))
                novi.append(nov.Name)
            except Exception as e:  # noqa: BLE001
                napake.append("%s (%s): ni ga mogoče ustvariti: %s" % (ime, objekti[ime]["tip"], e))
    for prehod in (0, 1):   # drugi prehod: lastnosti, ki se ob prvem niso dale (povezave na kasnejše objekte)
        for ime in posnetek["vrstni_red"]:
            obj = doc.getObject(ime)
            if obj is None:
                continue
            n = objekti[ime]
            napake_obj = []
            vrnjene += _vrni_vsebnik(obj, n["lastnosti"], napake_obj, ime)
            vo = getattr(obj, "ViewObject", None) if App.GuiUp else None
            if vo is not None and n["pogled"]:
                pogledi += _vrni_vsebnik(vo, n["pogled"], napake_obj, ime + ".ViewObject")
            if prehod == 1:
                napake.extend(napake_obj)
    for ime in posnetek["vrstni_red"]:   # dotaknjenost kot prej: brez preračuna, ki bi lahko spremenil obliko
        obj = doc.getObject(ime)
        if obj is not None and not objekti[ime]["dotaknjen"] and "Touched" in obj.State:
            try:
                obj.purgeTouched()
            except Exception:  # noqa: BLE001
                pass
    razlike = []
    for ime, n in objekti.items():
        obj = doc.getObject(ime)
        if obj is not None and n["oblika"] is not None and _odtis_oblike(obj) != n["oblika"]:
            razlike.append(n["oznaka"])
    na_disku = [o.Label for o in doc.Objects if o.Name not in objekti]
    return {"novi": novi, "lastnosti": vrnjene, "pogledi": pogledi, "napake": napake, "razlike_oblik": razlike,
            "samo_na_disku": na_disku}


def varnostna_kopija(doc):
    """Okrnjena kopija delnega dokumenta (le naloženi objekti, s spremembami) pred polnim nalaganjem."""
    os.makedirs(MAPA_KOPIJ, exist_ok=True)
    ime = "".join(c if c.isalnum() or c in " -_" else "_" for c in doc.Label)[:60] or doc.Name
    pot = os.path.join(MAPA_KOPIJ, "%s %s.FCStd" % (ime, time.strftime("%Y-%m-%d %H%M%S")))
    doc.saveCopy(pot)
    return pot


def nalozi_v_celoti(doc, ohrani=None):
    """Delen dokument naloži v celoti. Če ima neshranjene spremembe (ali ohrani=True), jih ohrani: varnostna kopija,
    posnetek lastnosti, `restore()`, vrnitev lastnosti. Vrne povzetek (dict) ali None, če dokument ni bil delen.
    Po klicu so stari Python objekti dokumenta neveljavni (iskati jih je treba znova po imenu); razveljavitev ni več."""
    if not je_delen(doc):
        return None
    spremenjen = _spremenjen(doc)
    if ohrani is None:
        ohrani = spremenjen
    aktiven = App.ActiveDocument is doc
    izid = {"dokument": doc.Label, "ohranjeno": bool(ohrani), "naloženih_prej": len(doc.Objects)}
    posnetek = None
    if ohrani:
        izid["kopija"] = varnostna_kopija(doc)
        posnetek = posnemi(doc)
    zacetek = time.time()
    doc.restore()
    if je_delen(doc):
        raise RuntimeError("»%s« po restore() ostaja delen" % doc.Label)
    izid["objektov"] = len(doc.Objects)
    if posnetek is not None:
        try:
            izid.update(vrni(doc, posnetek))
        except Exception:  # noqa: BLE001
            izid["napake"] = ["vrnitev sprememb: %s" % traceback.format_exc()]
        if Gui is not None and App.GuiUp and (spremenjen or izid.get("lastnosti") or izid.get("novi")):
            try:
                Gui.getDocument(doc.Name).Modified = True   # spremembe še niso na disku
            except Exception:  # noqa: BLE001
                pass
    if aktiven:
        App.setActiveDocument(doc.Name)
    izid["sekund"] = round(time.time() - zacetek, 2)
    _log("%s naložen v celoti (%d objektov, prej %d)%s" % (
        doc.Label, izid["objektov"], izid["naloženih_prej"],
        ", vrnjenih lastnosti %d, pogledov %d, kopija %s" % (izid.get("lastnosti", 0), izid.get("pogledi", 0),
                                                             izid.get("kopija")) if ohrani else ""))
    return izid


def nalozi_in_javi(stanje, doc, ohrani=None):
    """`nalozi_v_celoti` za strežnik: osveži seznam odprtih, ob ohranjenih spremembah obvestilo v brskalnik.
    Ob napaki dokument ostane delen (vrne None)."""
    try:
        izid = nalozi_v_celoti(doc, ohrani)
    except Exception:  # noqa: BLE001
        _log("polno nalaganje %s: %s" % (doc.Label, traceback.format_exc()))
        stanje.oddaj("obvestilo", {"sporocilo": "»%s« ni bilo mogoče naložiti v celoti; ostaja delno naložen in se ne "
                                                "shrani." % doc.Label, "slabo": True})
        return None
    if izid:
        stanje.umazano = True
        stanje.zadnji_projekti = 0.0
        if izid.get("ohranjeno"):
            stanje.oddaj("obvestilo", {"sporocilo": povzetek(izid),
                                       "slabo": bool(izid.get("napake") or izid.get("razlike_oblik"))})
    return izid


def povzetek(izid):
    """Kratko besedilo povzetka nalaganja (za orodja in obvestila)."""
    if not izid:
        return ""
    v = ["»%s« naložen v celoti (%d objektov, prej v pomnilniku %d)" % (izid["dokument"], izid["objektov"],
                                                                        izid["naloženih_prej"])]
    if izid.get("ohranjeno"):
        v.append("ohranjene spremembe: %d lastnosti, %d pogledov%s" % (
            izid.get("lastnosti", 0), izid.get("pogledi", 0),
            (", novi objekti " + ", ".join(izid["novi"])) if izid.get("novi") else ""))
        if izid.get("razlike_oblik"):
            v.append("POZOR, oblika se razlikuje od posnetka: " + ", ".join(izid["razlike_oblik"][:10]))
        if izid.get("napake"):
            v.append("ni vrnjeno (%d): %s" % (len(izid["napake"]), "; ".join(izid["napake"][:5])))
        v.append("varnostna kopija naloženega dela: %s" % izid.get("kopija"))
    return "; ".join(v) + "."
