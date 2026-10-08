# -*- coding: utf-8 -*-
"""Drevo dokumenta za spletni pogled (del posnetka GET /model, ključ "drevo"; dejanja POST /drevo).

Drevo je tako, kot ga kaže FreeCAD-ovo drevo: otroci objekta so tisti, ki jih njegov pogledni
objekt »zahteva« (claimChildren: pri Part::Cut osnova in orodje, pri Part::Fillet osnova, pri
App::Part člani skupine ...). Koreni so objekti, ki jih nihče ne zahteva. Vsak vozel nosi ime,
oznako, tip, vidnost, ikono in urejljive lastnosti (dolžine, koti, števila, besedila, kljukice,
naštevanja, lega), da se mere popravljajo kar v brskalniku.

Samo glavna nit FreeCAD-a: kliče ga Stanje.zgradi (posnetek) in Stanje._izvedi (ukaz "drevo").
"""
import FreeCAD as App

try:
    import FreeCADGui as Gui
except ImportError:  # FreeCADCmd
    Gui = None

# lastnosti, ki se urejajo v brskalniku (tip -> vrsta vnosa)
UREDLJIVI = {
    "App::PropertyLength": "stevilo", "App::PropertyDistance": "stevilo", "App::PropertyAngle": "stevilo",
    "App::PropertyFloat": "stevilo", "App::PropertyFloatConstraint": "stevilo", "App::PropertyQuantity": "stevilo",
    "App::PropertyPrecision": "stevilo", "App::PropertyInteger": "celo", "App::PropertyIntegerConstraint": "celo",
    "App::PropertyPercent": "celo", "App::PropertyBool": "kljukica", "App::PropertyString": "besedilo",
    "App::PropertyEnumeration": "izbira", "App::PropertyPlacement": "lega",
}
ENOTE = {"App::PropertyLength": "mm", "App::PropertyDistance": "mm", "App::PropertyAngle": "°"}
PRESKOCI = {"Label2", "ExpressionEngine", "Proxy", "Visibility", "Shape", "AttachmentOffset", "MapMode",
            "MapReversed", "MapPathParameter", "AttacherType", "AttacherEngine", "AttachmentSupport", "Support", "_Body"}


def _otroci(obj):
    if Gui is not None and App.GuiUp:
        vo = getattr(obj, "ViewObject", None)
        if vo is not None:
            try:
                return [o for o in vo.claimChildren() if o is not None]
            except Exception:  # noqa: BLE001
                pass
    try:
        return [o for o in obj.OutList if o is not None]
    except Exception:  # noqa: BLE001
        return []


def _vrednost(obj, ime, tip):
    v = getattr(obj, ime)
    if tip == "App::PropertyPlacement":
        b = v.Base
        return "%g; %g; %g" % (round(b.x, 4), round(b.y, 4), round(b.z, 4))
    if hasattr(v, "Value"):
        v = v.Value
    if isinstance(v, float):
        return round(v, 4)
    if isinstance(v, (bool, int, str)):
        return v
    return str(v)


def _lastnosti(obj):
    sez = []
    for ime in obj.PropertiesList:
        if ime in PRESKOCI:
            continue
        tip = obj.getTypeIdOfProperty(ime)
        vrsta = UREDLJIVI.get(tip)
        if vrsta is None:
            continue
        try:
            nacin = obj.getEditorMode(ime)
        except Exception:  # noqa: BLE001
            nacin = []
        if "Hidden" in nacin:
            continue
        try:
            vnos = {"ime": ime, "vrsta": vrsta, "vrednost": _vrednost(obj, ime, tip),
                    "enota": ENOTE.get(tip, ""), "urejanje": "ReadOnly" not in nacin}
            if vrsta == "izbira":
                vnos["moznosti"] = list(obj.getEnumerationsOfProperty(ime) or [])
            sez.append(vnos)
        except Exception:  # noqa: BLE001
            continue
    return sez


def drevo_dokumenta(doc, ikona_uri=None):
    """Posnetek drevesa aktivnega dokumenta: {"koreni": [imena], "vozli": {ime: vozel}}."""
    if doc is None:
        return {"koreni": [], "vozli": {}}
    vozli = {}
    zahtevani = set()
    for obj in doc.Objects:
        otroci = [o.Name for o in _otroci(obj) if o.Document is doc]
        zahtevani.update(otroci)
        ikona = ""
        if ikona_uri is not None and Gui is not None and App.GuiUp:
            try:
                vo = obj.ViewObject
                # ikona se bere leno: za že znan tip objekta jo ikona_uri vrne iz medpomnilnika brez klica vo.Icon
                ikona = ikona_uri(lambda vo=vo: vo.Icon, "objekt:" + obj.TypeId) if vo is not None else ""
            except Exception:  # noqa: BLE001
                ikona = ""
        try:
            viden = bool(obj.Visibility)
        except Exception:  # noqa: BLE001
            viden = True
        vozli[obj.Name] = {"ime": obj.Name, "oznaka": obj.Label, "tip": obj.TypeId, "viden": viden,
                           "ikona": ikona, "otroci": otroci, "lastnosti": _lastnosti(obj)}
        cilj = _cilj_povezave(obj)
        if cilj is not None:   # povezava na podsestav ali del v drugi datoteki: Uredi ga odpre
            vozli[obj.Name]["povezava"] = {"dokument": cilj.Document.Label,
                                           "sestav": cilj.TypeId in ("Assembly::AssemblyObject", "App::Part")}
    koreni = [o.Name for o in doc.Objects if o.Name not in zahtevani]
    return {"koreni": koreni, "vozli": vozli, "telesa": _telesa(doc, koreni)}


def _telesa(doc, koreni):
    """Končna telesa dokumenta (kot mapa »Solid Bodies« v SolidWorksu): koreni drevesa, ki imajo trdno obliko
    (skice, ravnine, skupine in objekti brez oblike ne štejejo). Objekt z več ločenimi telesi (npr. rez, ki je kos
    razdelil) nosi njihovo število. Vidnost se ne upošteva: tudi skrito telo je del dokumenta."""
    telesa = []
    for ime in koreni:
        obj = doc.getObject(ime)
        if obj is None or obj.TypeId.startswith(("Sketcher::", "App::Origin", "App::DocumentObjectGroup")):
            continue
        try:
            oblika = obj.Shape
            stevilo = len(oblika.Solids)
        except Exception:  # noqa: BLE001
            continue
        if stevilo == 0:
            continue
        try:
            prostornina = round(oblika.Volume / 1000.0, 1)
        except Exception:  # noqa: BLE001
            prostornina = None
        telesa.append({"ime": obj.Name, "oznaka": obj.Label, "solidov": stevilo, "prostornina": prostornina,
                       "viden": bool(getattr(obj, "Visibility", True))})
    return telesa


def _pretvori(obj, ime, vrednost):
    tip = obj.getTypeIdOfProperty(ime)
    vrsta = UREDLJIVI.get(tip)
    if vrsta == "kljukica":
        return bool(vrednost) if not isinstance(vrednost, str) else vrednost.strip().lower() in ("1", "true", "da", "yes")
    if vrsta == "celo":
        return int(float(str(vrednost).replace(",", ".")))
    if vrsta == "stevilo":
        return float(str(vrednost).replace(",", "."))
    if vrsta == "lega":
        deli = [float(x.strip().replace(",", ".")) for x in str(vrednost).replace(",", ".").split(";")]
        if len(deli) != 3:
            raise ValueError("lega: pričakovane tri vrednosti x; y; z")
        p = obj.Placement
        p.Base = App.Vector(*deli)
        return p
    return str(vrednost)


def _v_urejanju(doc):
    try:
        return Gui.getDocument(doc.Name).getInEdit() is not None or bool(Gui.Control.activeDialog())
    except Exception:  # noqa: BLE001
        return False


def _cilj_povezave(obj):
    """Objekt v drugem dokumentu, na katerega kaže povezava (App::Link na podsestav ali del), sicer None."""
    if obj.TypeId != "App::Link":
        return None
    cilj = getattr(obj, "LinkedObject", None)
    if isinstance(cilj, tuple):
        cilj = cilj[0]
    if cilj is None or cilj.Document is obj.Document:
        return None
    return cilj


def _odpri_povezano(stanje, cilj):
    """Kot »Odpri podsestav« v SolidWorksu: dokument povezave postane dejaven (seznam odprtih, drevo, pogled).
    Povezane dokumente FreeCAD ob odpiranju sestava naloži le delno (samo potrebne objekte); tak se naloži v celoti."""
    cdoc = cilj.Document
    if getattr(cdoc, "Partial", False):
        try:
            cdoc.restore()
        except Exception as e:  # noqa: BLE001
            App.Console.PrintWarning("[splet] polno nalaganje %s: %r\n" % (cdoc.Name, e))
    App.setActiveDocument(cdoc.Name)
    try:
        Gui.setActiveDocument(cdoc.Name)
    except Exception:  # noqa: BLE001
        pass
    vrsta = "sestav" if cilj.TypeId in ("Assembly::AssemblyObject", "App::Part") else "del"
    stanje.oddaj("obvestilo", {"sporocilo": "Odprt %s »%s«." % (vrsta, cdoc.Label)})


def _uredi(stanje, obj):
    """Urejanje objekta iz drevesa, kot dvojni klik v FreeCAD-ovem drevesu (ViewObject.doubleClicked):
    značilnost (izboklina, žep, zaokrožitev, luknja ...) odpre svoje opravilo, ki ga strežnik pokaže kot obrazec
    v brskalniku; telo ali App::Part postane dejavno (oz. ni več); skica se odpre v urejevalniku skic v brskalniku."""
    doc = obj.Document
    if obj.isDerivedFrom("Sketcher::SketchObject"):
        stanje.skica = obj.Name
        stanje.umazano = True
        stanje.oddaj_skico()
        return
    if Gui is None or not App.GuiUp:
        return
    cilj = _cilj_povezave(obj)
    if cilj is not None:
        _odpri_povezano(stanje, cilj)
        return
    if _v_urejanju(doc):
        stanje.oddaj("obvestilo", {"sporocilo": "Najprej zaključi trenutno urejanje: OK ali Prekliči v obrazcu desno.",
                                   "slabo": True})
        return
    if stanje.skica:   # skico, odprto v brskalniku, zapremo (kot Zapri skico), da se urejanje ne prekriva
        stanje.skica = ""
        doc.recompute()
        stanje.oddaj("skica", None)
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc.Name, obj.Name)
    vo = getattr(obj, "ViewObject", None)
    ok = False
    if vo is not None:
        try:
            ok = bool(vo.doubleClicked())
        except Exception as e:  # noqa: BLE001
            App.Console.PrintWarning("[splet] uredi %s: %r\n" % (obj.Name, e))
    if _v_urejanju(doc):
        return   # obrazec opravila pošlje preveri_obrazec, urejanje skice preusmeri preveri_okolje
    if obj.isDerivedFrom("PartDesign::Body") or obj.TypeId == "App::Part":
        try:
            dejavno = Gui.ActiveDocument.ActiveView.getActiveObject(
                "pdbody" if obj.isDerivedFrom("PartDesign::Body") else "part")
        except Exception:  # noqa: BLE001
            dejavno = None
        sporocilo = ("»%s« je zdaj dejavno: nove skice in značilnosti gredo vanj." % obj.Label if dejavno is obj
                     else "»%s« ni več dejavno." % obj.Label)
        stanje.oddaj("obvestilo", {"sporocilo": sporocilo})
        return
    if not ok:
        stanje.oddaj("obvestilo", {"sporocilo": "»%s« nima posebnega urejanja; mere uredi v lastnostih pod drevesom."
                                   % obj.Label})


def drevo_dejanje(stanje, podatki):
    """POST /drevo: {dejanje: vidnost, ime, vidno} | {dejanje: lastnost, ime, lastnost, vrednost} | {dejanje: uredi, ime}."""
    doc = App.ActiveDocument
    if doc is None:
        return
    obj = doc.getObject(podatki.get("ime", ""))
    if obj is None:
        return
    dejanje = podatki.get("dejanje", "")
    if dejanje == "vidnost":
        obj.Visibility = bool(podatki.get("vidno", True))
        vo = getattr(obj, "ViewObject", None)
        if vo is not None:
            vo.Visibility = obj.Visibility
    elif dejanje == "lastnost":
        ime = podatki.get("lastnost", "")
        if ime not in obj.PropertiesList or ime in PRESKOCI:
            return
        if obj.getTypeIdOfProperty(ime) not in UREDLJIVI:
            return
        setattr(obj, ime, _pretvori(obj, ime, podatki.get("vrednost")))
        doc.recompute()
    elif dejanje == "uredi":
        _uredi(stanje, obj)
    stanje.umazano = True
