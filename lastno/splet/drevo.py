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

from baza import oznaka_vozla, tarca

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


def drevo_dokumenta(doc, ikona_uri=None, kljuc_oblike=None):
    """Posnetek drevesa aktivnega dokumenta: {"koreni": [imena], "vozli": {ime: vozel}}.
    `kljuc_oblike(obj)` (stabilen ključ oblike iz strežnika) omogoči predpomnjenje prostornin teles."""
    if doc is None:
        return {"koreni": [], "vozli": {}}
    vozli = {}
    zahtevani = set()
    koreni_kosa = [tarca(doc)] if doc.FileName else []   # glavni objekt dokumenta-kosa se označi kot standardni
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
        deli = _deli_spoja(obj)
        if deli:   # spoj sestava: kosa (otroka sestava), ki ju povezuje; brskalnik ga pokaže tudi pod njima
            vozli[obj.Name]["deli"] = deli
        cilj = _cilj_povezave(obj)
        if cilj is not None:   # povezava na podsestav ali del v drugi datoteki: Uredi ga odpre
            vozli[obj.Name]["povezava"] = {"dokument": cilj.Document.Label,
                                           "sestav": cilj.TypeId in ("Assembly::AssemblyObject", "App::Part")}
            if cilj.TypeId != "Assembly::AssemblyObject":   # del: sestav ga lahko vstavi kot vrsto več kosov
                vozli[obj.Name]["kosov"] = max(1, int(getattr(obj, "ElementCount", 0) or 0))
        if cilj is not None or obj in koreni_kosa:
            std = oznaka_vozla(obj)   # kos v svoji datoteki: standardni / v bazi (meni Standardni del)
            if std is not None:
                vozli[obj.Name]["standardni"] = std
    koreni = [o.Name for o in doc.Objects if o.Name not in zahtevani]
    return {"koreni": koreni, "vozli": vozli, "telesa": _telesa(doc, koreni, kljuc_oblike)}


def _deli_spoja(obj):
    """Imena kosov sestava, ki jih povezuje spoj (Reference1/2) ali pritrdi (GroundedJoint: ObjectToGround), sicer [].
    Referenca kaže na kos sam ali na sestav s podpotjo »Kos.Podkos.Face9«; tedaj je kos prvi del podpoti."""
    if hasattr(obj, "ObjectToGround"):
        kos = obj.ObjectToGround
        return [kos.Name] if kos is not None else []
    if not (hasattr(obj, "JointType") and hasattr(obj, "Reference1")):
        return []
    deli = []
    for lastnost in ("Reference1", "Reference2"):
        try:
            ref, poti = getattr(obj, lastnost) or (None, [])
        except Exception:  # noqa: BLE001
            continue
        if ref is None:
            continue
        kos = ref
        if ref.TypeId in ("Assembly::AssemblyObject", "Assembly::AssemblyLink") and poti and "." in poti[0]:
            kos = ref.Document.getObject(poti[0].split(".", 1)[0]) or ref
        if kos.Name not in deli:
            deli.append(kos.Name)
    return deli


# (dokument, objekt) -> (ključ oblike, število teles, prostornina v cm³). Prostornina sestava (Slim zadaj A: 70 teles)
# traja 1,5 s, drevo pa se gradi ob vsakem posnetku (tudi ob preklopu na že pregledan dokument).
_PROSTORNINE = {}


def _telo(doc, obj, kljuc_oblike):
    kljuc = None
    if kljuc_oblike is not None:
        try:
            kljuc = kljuc_oblike(obj)
        except Exception:  # noqa: BLE001
            kljuc = None
        vnos = _PROSTORNINE.get((doc.Name, obj.Name))
        if kljuc is not None and vnos is not None and vnos[0] == kljuc:
            return vnos[1], vnos[2]
    oblika = obj.Shape
    stevilo = len(oblika.Solids)
    prostornina = None
    if stevilo:
        try:
            prostornina = round(oblika.Volume / 1000.0, 1)
        except Exception:  # noqa: BLE001
            prostornina = None
    if kljuc is not None:
        _PROSTORNINE[(doc.Name, obj.Name)] = (kljuc, stevilo, prostornina)
    return stevilo, prostornina


def _telesa(doc, koreni, kljuc_oblike=None):
    """Končna telesa dokumenta (kot mapa »Solid Bodies« v SolidWorksu): koreni drevesa, ki imajo trdno obliko
    (skice, ravnine, skupine in objekti brez oblike ne štejejo). Objekt z več ločenimi telesi (npr. rez, ki je kos
    razdelil) nosi njihovo število. Vidnost se ne upošteva: tudi skrito telo je del dokumenta."""
    telesa = []
    for ime in koreni:
        obj = doc.getObject(ime)
        if obj is None or obj.TypeId.startswith(("Sketcher::", "App::Origin", "App::DocumentObjectGroup")):
            continue
        try:
            stevilo, prostornina = _telo(doc, obj, kljuc_oblike)
        except Exception:  # noqa: BLE001
            continue
        if stevilo == 0:
            continue
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


def _spoji_na(obj):
    """Spoji sestava (razen pritrditve), ki se sklicujejo na povezavo obj (podpot »<ime>.« v Reference1/2)."""
    spoji = []
    for x in obj.Document.Objects:
        for ref in ("Reference1", "Reference2"):
            vrednost = getattr(x, ref, None) if ref in x.PropertiesList else None
            if isinstance(vrednost, tuple) and len(vrednost) > 1 and any(
                    s == obj.Name or s.startswith(obj.Name + ".") for s in vrednost[1]):
                spoji.append(x)
                break
    return spoji


def _nastavi_kosov(stanje, obj, n):
    """Konfiguracija »število kosov« (kot konfiguracije v SolidWorksu, npr. spone na DIN letvi): povezava na en kos
    postane vrsta n kosov vzdolž osi X kosa, razmik je lastnost Korak na kosu (sicer širina kosa).
    Vrsta je FreeCAD-ova povezava z elementi (ElementCount, ShowElement): sestav zahteva, da ima taka povezava ničelno
    lego, lego nosi vsak element (AssemblyObject::ensureIdentityPlacements, sicer kose ob preračunu vrže v izhodišče)."""
    cilj = _cilj_povezave(obj)
    if cilj is None:
        return
    n = max(1, min(200, int(n)))
    prej = max(1, int(obj.ElementCount or 0))
    if n == prej:
        return
    spoji = _spoji_na(obj)
    if spoji:
        stanje.oddaj("obvestilo", {"sporocilo": "»%s« je vezan s spoji (%s); število kosov spremeni, ko jih odstraniš."
                                   % (obj.Label, ", ".join(s.Label for s in spoji)), "slabo": True})
        return
    try:
        korak = float(cilj.Korak) if "Korak" in cilj.PropertiesList else cilj.Shape.BoundBox.XLength
    except Exception:  # noqa: BLE001
        korak = 0.0
    if korak <= 0:
        stanje.oddaj("obvestilo", {"sporocilo": "»%s« nima širine za razmik med kosi." % cilj.Label, "slabo": True})
        return
    prvi = obj.Placement
    if prej > 1 and obj.ElementList:
        prvi = obj.Placement.multiply(obj.ElementList[0].Placement)
    doc = obj.Document
    doc.openTransaction("Število kosov")
    try:
        if n == 1:
            obj.ElementCount = 0
            obj.Placement = prvi
        else:
            obj.Placement = App.Placement()
            obj.ShowElement = True
            obj.ElementCount = n
            for i, e in enumerate(obj.ElementList):
                e.Placement = prvi.multiply(App.Placement(App.Vector(i * korak, 0, 0), App.Rotation()))
        doc.recompute()
    finally:
        doc.commitTransaction()
    stanje.oddaj("obvestilo", {"sporocilo": "»%s«: %d %s v vrsti (razmik %g mm)." % (
        obj.Label, n, "kos" if n == 1 else ("kosa" if n == 2 else ("kosi" if n < 5 else "kosov")), korak)})


def drevo_dejanje(stanje, podatki):
    """POST /drevo: {dejanje: vidnost, ime, vidno} | {dejanje: lastnost, ime, lastnost, vrednost} | {dejanje: uredi, ime}
    | {dejanje: kosov, ime, stevilo}."""
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
    elif dejanje == "kosov":
        _nastavi_kosov(stanje, obj, podatki.get("stevilo", 1))
    stanje.umazano = True
