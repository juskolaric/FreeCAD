# -*- coding: utf-8 -*-
"""Baza standardnih delov (Oblak/3D modeliranje/Standardni deli): uporabnik sam označi, kateri kos je standardni.

Kos je dokument FCStd (del ali sestav); oznaka je lastnost Vrsta na njegovem glavnem objektu (»standardni del« /
»standardni sestav«, enako kot jo zapišejo skripte prenosa iz SolidWorksa). Označen kos se iz projekta premakne v bazo
(<baza>/<kategorija>/<ime>.FCStd, zraven STEP in DXF razgrnitve); vsi sestavi, ki ga uporabljajo, se preusmerijo nanj
in shranijo. Če je v bazi že kos z istim imenom in enako geometrijo, se sestavi preusmerijo nanj (dvojnik ostane
neuporabljen v projektu). Odznačen kos se iz baze vrne v projekt, ki ga uporablja (Deli/Ostali, Deli/Pločevina, Sestavi).

Kako FreeCAD drži povezave (preizkušeno 2026-10-09): App::Link na drug dokument hrani pot relativno na sestav. Ko se del
shrani drugam (saveAs), FreeCAD poti v vseh odprtih sestavih, ki nanj kažejo, popravi sam; sestave je treba le shraniti.
Zato se pred premikom odprejo vsi sestavi iz 3D modeliranja, ki kažejo na kos (iskanje po Document.xml). Ko pa se
premakne sestav, njegove odhodne povezave obdržijo staro relativno pot in se morajo nastaviti znova (_osvezi_povezave).

Samo glavna nit FreeCAD-a: kliče ga Stanje._izvedi (ukaz "standardni", POST /standardni).
"""
import html
import os
import re
import zipfile

import FreeCAD as App

try:
    import FreeCADGui as Gui
except ImportError:  # FreeCADCmd
    Gui = None

KOREN = os.environ.get("SPLET_MODELIRANJE") or os.path.join(os.path.expanduser("~"), "Oblak", "3D modeliranje")
BAZA = os.environ.get("SPLET_BAZA") or os.path.join(KOREN, "Standardni deli")
BREZ_KATEGORIJE = "Ostalo"


class Napaka(Exception):
    """Napaka, ki jo vidi uporabnik (sporočilo v brskalniku)."""


def _norm(pot):
    return os.path.normcase(os.path.normpath(os.path.abspath(pot))) if pot else ""


def v_bazi(pot):
    return bool(pot) and _norm(pot).startswith(_norm(BAZA) + os.sep)


def tarca(doc):
    """Glavni objekt dokumenta-kosa: sestav (Assembly), objekt s podatki prenosa (Izvor), App::Part ali edino telo."""
    for o in doc.Objects:
        if o.TypeId == "Assembly::AssemblyObject":
            return o
    for o in doc.Objects:
        if "Izvor" in o.PropertiesList and not o.Name.startswith(("Razgrnitev", "DXF_rez")):
            return o
    # Koreni po tem dokumentu: RootObjects izpusti kos, na katerega kaže povezava iz drugega odprtega dokumenta
    # (sestav, ki ga uporablja), zato je za kose v bazi pogosto prazen.
    koreni = [o for o in doc.Objects if not any(p.Document is doc for p in o.InList)
              and not o.TypeId.startswith(("App::Origin", "Sketcher::"))
              and not o.Name.startswith(("Razgrnitev", "DXF_rez"))]
    for tip in ("App::Part", "PartDesign::Body"):
        kandidati = [o for o in koreni if o.TypeId == tip]
        if len(kandidati) == 1:
            return kandidati[0]
    trdni = []
    for o in koreni:
        try:
            if o.Shape.Solids:
                trdni.append(o)
        except Exception:  # noqa: BLE001
            pass
    return trdni[0] if trdni else None


def je_standardni(obj):
    return obj is not None and "standardni" in str(getattr(obj, "Vrsta", "") or "").lower()


def _je_plocevina(doc):
    return any(o.Name.startswith("Razgrnitev") or "Debelina" in o.PropertiesList for o in doc.Objects)


def _je_sestav(obj):
    return obj is not None and obj.TypeId == "Assembly::AssemblyObject"


def oznaka_vozla(obj):
    """Za drevo: {standardni, vBazi, sestav} za vozel, ki predstavlja kos v svoji datoteki (povezava na drug dokument
    ali glavni objekt shranjenega dokumenta), sicer None."""
    try:
        cilj = getattr(obj, "LinkedObject", None) if obj.TypeId == "App::Link" else None
        if isinstance(cilj, tuple):
            cilj = cilj[0]
        if cilj is not None and cilj.Document is not obj.Document:
            doc = cilj.Document
            t = tarca(doc)
        else:
            doc = obj.Document
            t = tarca(doc)
            if t is not obj:
                return None
        if t is None or not doc.FileName:
            return None
        return {"standardni": je_standardni(t), "vBazi": v_bazi(doc.FileName), "sestav": _je_sestav(t)}
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------- iskanje datotek, ki kažejo na kos
def _xlink_poti(pot_fcstd):
    """Absolutne poti datotek, na katere kažejo povezave v FCStd (iz Document.xml, brez odpiranja v FreeCAD-u)."""
    try:
        with zipfile.ZipFile(pot_fcstd) as z, z.open("Document.xml") as f:
            besedilo = f.read().decode("utf-8", "replace")
    except (OSError, KeyError, zipfile.BadZipFile):
        return []
    mapa = os.path.dirname(pot_fcstd)
    poti = []
    for m in re.finditer(r'<XLink file="([^"]*)"', besedilo):
        rel = html.unescape(m.group(1))
        if rel:
            poti.append(os.path.normpath(rel if os.path.isabs(rel) else os.path.join(mapa, rel)))
    return poti


def kdo_uporablja(pot):
    """Datoteke FCStd v 3D modeliranju, katerih povezave kažejo na pot (shranjeno stanje na disku)."""
    iskana = _norm(pot)
    ime = os.path.basename(pot)
    najdene = []
    for koren, mape, datoteke in os.walk(KOREN):
        mape[:] = [m for m in mape if not m.startswith((".", "_"))]
        for d in datoteke:
            if not d.lower().endswith(".fcstd"):
                continue
            p = os.path.join(koren, d)
            if _norm(p) == iskana:
                continue
            if any(_norm(x) == iskana for x in _xlink_poti(p)):
                najdene.append(p)
    return najdene


def _odprti_uporabniki(doc):
    """Odprti dokumenti, ki imajo povezavo na kateri koli objekt dokumenta (tudi še neshranjeno)."""
    docs = {}
    for o in doc.Objects:
        for x in o.InList:
            if x.Document is not doc:
                docs[x.Document.Name] = x.Document
    return list(docs.values())


def _projekt(pot):
    """Mapa projekta (prva raven pod 3D modeliranjem) za datoteko, sicer None."""
    if not pot or not _norm(pot).startswith(_norm(KOREN) + os.sep) or v_bazi(pot):
        return None
    rel = os.path.relpath(pot, KOREN)
    prvi = rel.split(os.sep)[0]
    return os.path.join(KOREN, prvi) if prvi != rel else None


# ---------------------------------------------------------------- shranjevanje
def _odpri(pot):
    for d in App.listDocuments().values():
        if d.FileName and _norm(d.FileName) == _norm(pot):
            return d
    return App.openDocument(pot)


def _shrani(doc, pot=None):
    if pot:
        doc.saveAs(pot)
    else:
        doc.save()
    if Gui is not None and App.GuiUp:
        try:
            Gui.getDocument(doc.Name).Modified = False
        except Exception:  # noqa: BLE001
            pass


class _BrezVarnostnihKopij:
    """Premik ni sprememba vsebine: brez .FCBak v bazi (nastavitev je skupna z nameščenim FreeCAD-om, zato se vrne)."""

    def __enter__(self):
        self.p = App.ParamGet("User parameter:BaseApp/Preferences/Document")
        self.prej = self.p.GetBool("CreateBackupFiles", True)
        self.p.SetBool("CreateBackupFiles", False)

    def __exit__(self, *a):
        self.p.SetBool("CreateBackupFiles", self.prej)


def _kaze_ven(vrednost, doc):
    """Ali vrednost povezave (objekt, (objekt, podelementi) ali seznam teh) kaže v drug dokument."""
    if isinstance(vrednost, list):
        return any(_kaze_ven(v, doc) for v in vrednost)
    if isinstance(vrednost, tuple):
        vrednost = vrednost[0] if vrednost else None
    return vrednost is not None and hasattr(vrednost, "Document") and vrednost.Document is not doc


def _osvezi_povezave(doc):
    """Po premiku sestava: povezave na druge datoteke nastavi znova, da se relativne poti izračunajo od nove lege.
    Povezave znotraj dokumenta (npr. reference spojev) ostanejo nedotaknjene."""
    for o in doc.Objects:
        for ime in o.PropertiesList:
            try:
                tip = o.getTypeIdOfProperty(ime)
            except Exception:  # noqa: BLE001
                continue
            if not tip.startswith("App::PropertyXLink"):
                continue
            vrednost = getattr(o, ime)
            if not vrednost or not _kaze_ven(vrednost, doc):
                continue
            setattr(o, ime, [] if isinstance(vrednost, list) else None)
            setattr(o, ime, vrednost)


def _premakni_spremljevalce(stari, novi):
    """STEP ob kosu in DXF razgrnitve (podmapa DXF) gresta s kosom."""
    premaknjeni = []
    osnova_s, osnova_n = os.path.splitext(stari)[0], os.path.splitext(novi)[0]
    pari = [(osnova_s + k, osnova_n + k) for k in (".step", ".stp", ".STEP")]
    ime = os.path.basename(osnova_s)
    pari.append((os.path.join(os.path.dirname(stari), "DXF", ime + ".dxf"),
                 os.path.join(os.path.dirname(novi), "DXF", os.path.basename(osnova_n) + ".dxf")))
    for s, n in pari:
        if os.path.exists(s) and not os.path.exists(n):
            os.makedirs(os.path.dirname(n), exist_ok=True)
            os.replace(s, n)
            premaknjeni.append(os.path.basename(n))
    return premaknjeni


def _prestavi(stanje, doc, nova_pot):
    """Premakne dokument kosa na novo pot; sestavi, ki ga uporabljajo, se preusmerijo in shranijo.
    Vrne (imena shranjenih sestavov, premaknjeni spremljevalci)."""
    stara = doc.FileName
    pred = set(App.listDocuments())
    for p in kdo_uporablja(stara):   # na disku: odpremo, da jih FreeCAD ob premiku popravi
        _odpri(p)
    odprti_zdaj = set(App.listDocuments()) - pred
    uporabniki = _odprti_uporabniki(doc)
    for d in uporabniki:   # podsestave odprtega sestava FreeCAD naloži le delno; takega ni mogoče shraniti
        if getattr(d, "Partial", False):
            d.restore()
    uporabniki = _odprti_uporabniki(doc)
    stanje.tiho_shranjevanje = True
    try:
        with _BrezVarnostnihKopij():
            os.makedirs(os.path.dirname(nova_pot), exist_ok=True)
            os.replace(stara, nova_pot)   # premik (ne kopija): stara pot ne ostane
            try:
                oznaka = doc.Label
                _shrani(doc, nova_pot)
                if _je_sestav(tarca(doc)):
                    _osvezi_povezave(doc)
                if doc.Label != oznaka:
                    doc.Label = oznaka
                _shrani(doc)
            except Exception:
                if not os.path.exists(stara) and os.path.exists(nova_pot) and _norm(doc.FileName) != _norm(nova_pot):
                    os.replace(nova_pot, stara)
                raise
            shranjeni = []
            for d in uporabniki:
                _shrani(d)
                shranjeni.append(d.Label)
        spremljevalci = _premakni_spremljevalce(stara, nova_pot)
        mapa = os.path.dirname(stara)   # prazne mape kategorij v bazi ne ostanejo (samo prazne, samo v bazi)
        for m in (os.path.join(mapa, "DXF"), mapa, os.path.dirname(mapa)):
            if v_bazi(os.path.join(m, "x")) and os.path.isdir(m) and not os.listdir(m):
                os.rmdir(m)
    finally:
        stanje.tiho_shranjevanje = False
        for ime in odprti_zdaj:   # kar smo odprli le za preusmeritev, zapremo
            if ime in App.listDocuments() and ime != doc.Name:
                try:
                    App.closeDocument(ime)
                except Exception:  # noqa: BLE001
                    pass
    stanje.premaknjene_poti = getattr(stanje, "premaknjene_poti", []) + [stara]   # PDM: zaklep stare poti se sprosti
    return shranjeni, spremljevalci


def _odtis(obj):
    import Part
    sh = Part.getShape(obj)
    bb = sh.BoundBox
    return {"telesa": len(sh.Solids), "ploskve": len(sh.Faces), "vol": sum(s.Volume for s in sh.Solids),
            "povrsina": sh.Area, "bb": [bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax]}


def _enaka_geometrija(a, b):
    try:
        x, y = _odtis(a), _odtis(b)
    except Exception:  # noqa: BLE001
        return False

    def blizu(p, q, rel=1e-3, absolutno=1e-2):
        return abs(p - q) <= max(absolutno, rel * max(abs(p), abs(q)))
    return (x["telesa"] == y["telesa"] and x["ploskve"] == y["ploskve"] and blizu(x["vol"], y["vol"])
            and blizu(x["povrsina"], y["povrsina"]) and all(blizu(p, q, 0, 0.05) for p, q in zip(x["bb"], y["bb"])))


def _preusmeri_na(stanje, doc, cilj_doc):
    """Sestave, ki kažejo na doc, preusmeri na isti kos v bazi (cilj_doc) in jih shrani."""
    pred = set(App.listDocuments())
    for p in kdo_uporablja(doc.FileName):
        _odpri(p)
    odprti_zdaj = set(App.listDocuments()) - pred
    nova_tarca = tarca(cilj_doc)
    shranjeni = []
    stanje.tiho_shranjevanje = True
    try:
        for d in _odprti_uporabniki(doc):
            if getattr(d, "Partial", False):
                d.restore()
        for d in _odprti_uporabniki(doc):
            for o in d.Objects:
                if o.TypeId != "App::Link":
                    continue
                c = o.LinkedObject[0] if isinstance(o.LinkedObject, tuple) else o.LinkedObject
                if c is not None and c.Document is doc:
                    o.LinkedObject = cilj_doc.getObject(c.Name) or nova_tarca
            d.recompute()
            _shrani(d)
            shranjeni.append(d.Label)
    finally:
        stanje.tiho_shranjevanje = False
        for ime in odprti_zdaj:
            if ime in App.listDocuments():
                try:
                    App.closeDocument(ime)
                except Exception:  # noqa: BLE001
                    pass
    return shranjeni


# ---------------------------------------------------------------- dejanja
def _cisto_ime_mape(kategorija):
    deli = [re.sub(r'[<>:"|?*]', "_", d).strip(" .") for d in re.split(r"[\\/]+", kategorija or "")]
    deli = [d for d in deli if d and d != ".." and not d.startswith("_")]
    return os.path.join(*deli) if deli else BREZ_KATEGORIJE


def kategorije():
    """Obstoječe mape baze (do dveh ravni), za izbiro ob označevanju."""
    sez = []
    if os.path.isdir(BAZA):
        for koren, mape, _ in os.walk(BAZA):
            mape[:] = sorted(m for m in mape if not m.startswith((".", "_")) and m != "DXF")
            rel = os.path.relpath(koren, BAZA)
            if rel != ".":
                sez.append(rel.replace(os.sep, "/"))
            if rel != "." and rel.count(os.sep) >= 1:
                mape[:] = []
    return sez


def _predlog_kategorije(pot):
    """Mapa nad kosom, če je v projektu pod »Standardni deli/<kategorija>/« (tako so razvrščeni deli iz SolidWorksa)."""
    deli = os.path.normpath(pot).split(os.sep)
    for i, d in enumerate(deli[:-1]):
        if d.lower() == "standardni deli" and i + 2 < len(deli):
            return "/".join(deli[i + 1:-1])
    return ""


def _kos(podatki):
    """(dokument kosa, glavni objekt) za vozel drevesa aktivnega dokumenta ali za dokument po imenu."""
    if podatki.get("dokument"):
        doc = App.listDocuments().get(podatki["dokument"])
    else:
        aktivni = App.ActiveDocument
        obj = aktivni.getObject(podatki.get("ime", "")) if aktivni else None
        if obj is None:
            raise Napaka("Objekt ni več v drevesu.")
        cilj = getattr(obj, "LinkedObject", None) if obj.TypeId == "App::Link" else None
        if isinstance(cilj, tuple):
            cilj = cilj[0]
        doc = cilj.Document if cilj is not None else obj.Document
    if doc is None:
        raise Napaka("Dokument ni odprt.")
    t = tarca(doc)
    if t is None:
        raise Napaka("»%s« nima glavnega objekta (dela ali sestava)." % doc.Label)
    if not doc.FileName:
        raise Napaka("»%s« še ni shranjen; shrani ga, nato ga označi." % doc.Label)
    if getattr(doc, "Partial", False):
        doc.restore()
        t = tarca(doc)
    return doc, t


def _nastavi_vrsto(doc, t, standardni):
    if "Vrsta" not in t.PropertiesList:
        t.addProperty("App::PropertyString", "Vrsta", "Baza", "Vrsta kosa: standardni del, del, pločevina, sestav")
    if standardni:
        t.Vrsta = "standardni sestav" if _je_sestav(t) else "standardni del"
    else:
        t.Vrsta = "sestav" if _je_sestav(t) else ("pločevina" if _je_plocevina(doc) else "del")


def _oznaci(stanje, podatki):
    doc, t = _kos(podatki)
    vrsta = "sestav" if _je_sestav(t) else "del"
    if v_bazi(doc.FileName):
        if not je_standardni(t):
            _nastavi_vrsto(doc, t, True)
            _shrani(doc)
        return {"ok": True, "sporocilo": "»%s« je že v bazi standardnih delov." % doc.Label}
    novo_ime = re.sub(r'[<>:"/\\|?*]', "_", podatki.get("novo_ime") or "").strip(" .")   # preimenovanje ob premiku
    datoteka = (novo_ime + ".FCStd") if novo_ime else os.path.basename(doc.FileName)
    nova = os.path.join(BAZA, _cisto_ime_mape(podatki.get("kategorija")), datoteka)
    if novo_ime:
        doc.Label = novo_ime
    if os.path.exists(nova):
        obstojeci = _odpri(nova)
        if tarca(obstojeci) is None or not _enaka_geometrija(t, tarca(obstojeci)):
            raise Napaka("V bazi je pod »%s« že drug kos z imenom »%s«. Izberi drugo kategorijo ali kos preimenuj."
                         % (os.path.relpath(os.path.dirname(nova), BAZA).replace(os.sep, "/"), obstojeci.Label))
        shranjeni = _preusmeri_na(stanje, doc, obstojeci)
        return {"ok": True, "sporocilo": "»%s« je v bazi že bil (enaka geometrija). Preusmerjeni sestavi: %s. Kopija v "
                "projektu ni več uporabljena, lahko jo izbrišeš." % (obstojeci.Label, ", ".join(shranjeni) or "nobeden")}
    _nastavi_vrsto(doc, t, True)
    shranjeni, spremljevalci = _prestavi(stanje, doc, nova)
    mapa = os.path.relpath(os.path.dirname(nova), BAZA).replace(os.sep, "/")
    zraven = " S kosom sta šla tudi STEP in DXF." if len(spremljevalci) > 1 else (
        " S kosom je šel tudi %s." % ("DXF" if spremljevalci[0].lower().endswith(".dxf") else "STEP")
        if spremljevalci else "")
    return {"ok": True, "sporocilo": "»%s« je standardni %s v bazi (%s). Preusmerjeni sestavi: %s.%s" % (
        doc.Label, vrsta, mapa, ", ".join(shranjeni) or "nobeden", zraven)}


def _odznaci(stanje, podatki):
    doc, t = _kos(podatki)
    if not v_bazi(doc.FileName):
        _nastavi_vrsto(doc, t, False)
        _shrani(doc)
        return {"ok": True, "sporocilo": "»%s« ni več označen kot standardni (ostane v projektu)." % doc.Label}
    projekti = {}
    for p in kdo_uporablja(doc.FileName) + [d.FileName for d in _odprti_uporabniki(doc) if d.FileName]:
        pr = _projekt(p)
        if pr is not None:
            projekti[_norm(pr)] = pr
        elif v_bazi(p):
            raise Napaka("»%s« uporablja sestav v bazi (%s); iz baze ga ni mogoče vzeti." % (doc.Label, os.path.basename(p)))
    if not projekti and App.ActiveDocument is not None and _projekt(App.ActiveDocument.FileName):
        pr = _projekt(App.ActiveDocument.FileName)
        projekti[_norm(pr)] = pr
    if len(projekti) != 1:
        if not projekti:
            raise Napaka("»%s« ne uporablja noben projekt; ostane v bazi." % doc.Label)
        raise Napaka("»%s« uporablja več projektov (%s), zato ostane v bazi." % (
            doc.Label, ", ".join(sorted(os.path.basename(p) for p in projekti.values()))))
    projekt = next(iter(projekti.values()))
    _nastavi_vrsto(doc, t, False)
    podmapa = "Sestavi" if _je_sestav(t) else os.path.join("Deli", "Pločevina" if _je_plocevina(doc) else "Ostali")
    nova = os.path.join(projekt, podmapa, os.path.basename(doc.FileName))
    if os.path.exists(nova):
        raise Napaka("V projektu že obstaja %s; kos ostane v bazi." % os.path.relpath(nova, projekt))
    shranjeni, _ = _prestavi(stanje, doc, nova)
    return {"ok": True, "sporocilo": "»%s« ni več standardni; premaknjen je v projekt %s (%s). Preusmerjeni sestavi: %s."
            % (doc.Label, os.path.basename(projekt), podmapa.replace(os.sep, "/"), ", ".join(shranjeni) or "nobeden")}


def baza_dejanje(stanje, podatki):
    """POST /standardni: {dejanje: podatki|oznaci|odznaci, ime (vozel drevesa aktivnega dokumenta) ali dokument,
    kategorija, pri »oznaci« neobvezno novo_ime = ime datoteke in dokumenta v bazi}. Vrne {ok, sporocilo} ali za »podatki« {ime, kategorije, predlog, standardni, vBazi}."""
    dejanje = podatki.get("dejanje", "")
    try:
        if dejanje == "podatki":
            doc, t = _kos(podatki)
            return {"ok": True, "ime": doc.Label, "kategorije": kategorije(), "sestav": _je_sestav(t),
                    "predlog": _predlog_kategorije(doc.FileName), "standardni": je_standardni(t),
                    "vBazi": v_bazi(doc.FileName), "uporablja": len(kdo_uporablja(doc.FileName))}
        if dejanje == "oznaci":
            r = _oznaci(stanje, podatki)
        elif dejanje == "odznaci":
            r = _odznaci(stanje, podatki)
        else:
            raise Napaka("Neznano dejanje: %s" % dejanje)
    except Napaka as e:
        return {"ok": False, "sporocilo": str(e)}
    stanje.umazano = True
    stanje.zadnji_projekti = 0.0
    return r
