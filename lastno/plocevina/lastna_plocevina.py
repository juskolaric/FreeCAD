# -*- coding: utf-8 -*-
"""Lastni parametrični objekti za pločevino nad dodatkom SheetMetal (shaise), odporni na preimenovanje topologije.

SheetMetal objekti hranijo izbrane ploskve in robove po imenih (``Face4``, ``Edge14``). Ko se mera osnovnega
telesa spremeni (npr. višina izbokline pod posnetim robom), FreeCAD 1.x teh imen pogosto ne zna več preslikati
(»missing element reference … ?Edge14«) in kos se pokvari. Objekta tukaj imen ne hranita: ob vsakem preračunu
geometrijsko poiščeta, kar potrebujeta, in pokličeta jedro dodatka SheetMetal.

- ``TeloVPlocevino``: telo -> pločevina (SheetMetal »Solid to Sheet Metal«). Odstrani ravne ploskve na dnu
  (najnižji Z, normala navzdol) in razreže vse nevodoravne robove (navpični vogali, diagonale posnetih robov);
  vodoravni robovi postanejo upogibi. Primerno za škatle, korita, podstavke, odprte spodaj.
- ``Razgrnitev``: razgrnitev kosa (SheetMetal V2) z največje ravne ploskve z normalo navzgor (+Z).

Vsi trije objekti nosijo lastnost ``Material`` (ključ iz ``plocevina_materiali.MATERIALI``): dokler je ``Samodejno``
vklopljeno, se notranji polmer (``Polmer``) in K (``KFaktor``, ``KTabela``) ob vsaki spremembi materiala ali debeline
vzameta iz tabele Amada (odprtina V po debelini, R kot delež V, K po R/T). Vrednost delavnice vpiši ročno in izklopi
``Samodejno``.

Modul mora biti na poti Pythona, ko se odpre dokument: mapa ``lastno/plocevina`` je z mapo uporabniških dodatkov
povezana kot ``%APPDATA%/FreeCAD/v1-1/Mod/lastna_plocevina`` (stičišče, glej README.md v tej mapi).
Brez modula se dokument odpre, objekta pa obdržita zadnjo shranjeno obliko in se ne preračunata.
"""
import os
import sys

import FreeCAD as App
import Part

import plocevina_materiali as materiali


def _lastnosti_materiala(obj, skupina, nov):
    """Skupne lastnosti: Material (seznam iz tabele), Samodejno (polmer in K iz tabele). Pri starem kosu, ki lastnosti
    še nima (``nov`` False), je Samodejno izklopljeno, da se mu polmer ob odprtju ne spremeni."""
    _lastnost(obj, "App::PropertyEnumeration", "Material", skupina, "Material pločevine (tabela Amada: V, R, K po debelini)")
    if not obj.Material:
        obj.Material = list(materiali.MATERIALI)
        obj.Material = materiali.PRIVZETI
    _lastnost(obj, "App::PropertyBool", "Samodejno", skupina,
              "Polmer in K iz tabele materiala ob spremembi materiala ali debeline (izklopi za vrednosti delavnice)", nov)


def _med_branjem(obj):
    """Med branjem dokumenta se lastnosti nastavljajo iz datoteke: tabela takrat ne sme prepisati shranjenih vrednosti."""
    return "Restore" in obj.State or getattr(obj.Document, "Restoring", False)


def _uporabi_material(obj, debelina):
    """Ob vklopljenem Samodejno vpiše Polmer (če obstaja), KFaktor in KTabela (če obstajata) iz tabele materiala."""
    if not getattr(obj, "Samodejno", False) or not obj.Material or not debelina or _med_branjem(obj):
        return
    p = materiali.parametri(obj.Material, float(debelina))
    if "Polmer" in obj.PropertiesList and abs(obj.Polmer.Value - p["R"]) > 1e-9:
        obj.Polmer = p["R"]
    if "KFaktor" in obj.PropertiesList and abs(obj.KFaktor - p["K"]) > 1e-9:
        obj.KFaktor = p["K"]
    if "KTabela" in obj.PropertiesList and obj.KTabela != p["KTabela"]:
        obj.KTabela = p["KTabela"]


def _sheetmetal_na_poti():
    """FreeCAD, zagnan pred namestitvijo dodatka SheetMetal, mape dodatka še nima v sys.path."""
    try:
        import SheetMetalFromSolid  # noqa: F401
    except ImportError:
        sys.path.append(os.path.join(App.getUserAppDataDir(), "Mod", "sheetmetal"))
        dodatni = os.path.join(App.getUserAppDataDir(), "AdditionalPythonPackages", "py%d%d" % sys.version_info[:2])
        if os.path.isdir(dodatni) and dodatni not in sys.path:
            sys.path.append(dodatni)


def _lastnost(obj, tip, ime, skupina, opis, vrednost=None):
    if ime not in obj.PropertiesList:
        obj.addProperty(tip, ime, skupina, opis)
        if vrednost is not None:
            setattr(obj, ime, vrednost)


TOL = 1e-6


def izbira_za_skatlo(oblika):
    """Imena ploskev in robov za »Solid to Sheet Metal«: ravne ploskve na dnu (odstranijo se) in vsi
    nevodoravni robovi (razrežejo se)."""
    zmin = oblika.BoundBox.ZMin
    dno = ["Face%d" % k for k, f in enumerate(oblika.Faces, 1)
           if f.Surface.TypeId == "Part::GeomPlane" and abs(f.BoundBox.ZMax - zmin) < TOL]
    rezi = ["Edge%d" % k for k, e in enumerate(oblika.Edges, 1)
            if abs(e.BoundBox.ZMax - e.BoundBox.ZMin) > TOL]
    return dno + rezi


class TeloVPlocevino:
    def __init__(self, obj, osnova=None):
        obj.Proxy = self
        self._lastnosti(obj, nov=True)
        if osnova is not None:
            obj.Osnova = osnova

    def _lastnosti(self, obj, nov=False):
        _lastnost(obj, "App::PropertyLink", "Osnova", "Pločevina", "Telo, ki se pretvori v pločevino")
        _lastnost(obj, "App::PropertyLength", "Debelina", "Pločevina", "Debelina pločevine", 1.0)
        _lastnost(obj, "App::PropertyLength", "Polmer", "Pločevina", "Notranji polmer upogiba", 1.0)
        _lastnost(obj, "App::PropertyBool", "Navznoter", "Pločevina",
                  "Material navznoter od ploskev telesa (privzeto navzven)", False)
        _lastnosti_materiala(obj, "Pločevina", nov)

    def onDocumentRestored(self, obj):
        self._lastnosti(obj)

    def onChanged(self, obj, ime):
        if ime in ("Material", "Debelina", "Samodejno") and "Samodejno" in obj.PropertiesList:
            _uporabi_material(obj, obj.Debelina.Value)

    def execute(self, obj):
        if obj.Osnova is None or obj.Osnova.Shape.isNull():
            return
        _sheetmetal_na_poti()
        import SheetMetalFromSolid
        oblika = obj.Osnova.Shape
        izbira = izbira_za_skatlo(oblika)
        obj.Shape = SheetMetalFromSolid.smMakeSheetMetalFromSolid(
            oblika, izbira, obj.Polmer.Value, obj.Debelina.Value, 0.1, obj.Navznoter)

    def dumps(self):
        return None

    def loads(self, stanje):
        return None


def _ravnina(f):
    return f.Surface.TypeId == "Part::GeomPlane"


def debelina_kosa(oblika):
    """Debelina pločevine: najpogostejša razdalja med vzporednima nasprotnima ravnima ploskvama (velike ploskve)."""
    ravne = sorted([f for f in oblika.Faces if _ravnina(f)], key=lambda f: -f.Area)[:12]
    stevec = {}
    for i, a in enumerate(ravne):
        na = a.normalAt(0, 0)
        for b in ravne[i + 1:]:
            if na.dot(b.normalAt(0, 0)) < -1 + 1e-6:
                d = round(abs((b.CenterOfMass - a.CenterOfMass).dot(na)), 3)
                if d > 0.05:
                    stevec[d] = stevec.get(d, 0) + min(a.Area, b.Area)
    return max(stevec, key=stevec.get) if stevec else None


def upogibi(oblika, t, zvito=10.0):
    """Valjasti ploskvi upogibov: pari koaksialnih valjev s polmeroma r in r + t. Upogibi z notranjim polmerom
    nad ``zvito`` × t so zviti (valjani) deli kosa in niso upogibi za prenovo (vrne jih ločeno)."""
    vsi = _pari_valjev(oblika, t)
    return [f for f in vsi if min(f.Surface.Radius, _par_polmer(f, vsi, t)) < zvito * t]


def _par_polmer(f, vsi, t):
    r = f.Surface.Radius
    for g in vsi:
        if g is not f and abs(abs(g.Surface.Radius - r) - t) < 1e-3 and \
                (g.Surface.Center - f.Surface.Center).cross(f.Surface.Axis).Length < 1e-3:
            return g.Surface.Radius
    return r


def _osna_dolzina(f):
    u0, u1, v0, v1 = f.ParameterRange
    return abs(v1 - v0)


def _pari_valjev(oblika, t):
    # stene lukenj (os pravokotna na pločevino) so visoke le t: izločijo se, sicer povežejo obe strani
    valji = [f for f in oblika.Faces if f.Surface.TypeId == "Part::GeomCylinder" and _osna_dolzina(f) > 1.2 * t]
    izbrani = set()
    for i, a in enumerate(valji):
        sa = a.Surface
        for j, b in enumerate(valji):
            if j <= i:
                continue
            sb = b.Surface
            if abs(abs(sa.Axis.dot(sb.Axis)) - 1) > 1e-6:
                continue
            if (sb.Center - sa.Center).cross(sa.Axis).Length > 1e-3:
                continue
            if abs(abs(sa.Radius - sb.Radius) - t) < 1e-3:
                izbrani.update((i, j))
    return [valji[k] for k in sorted(izbrani)]


def strani_plocevine(oblika, t):
    """Veliki ravni ploskvi (z nasprotnim dvojčkom na razdalji t, ki ni ploskev debeline) razdeljeni v strani pločevine
    po sosednosti (skupni rob)."""
    ravne = [f for f in oblika.Faces if _ravnina(f)]
    velike = []
    for a in ravne:
        if a.Area < 4 * t * t:
            continue
        na = a.normalAt(0, 0)
        for b in ravne:
            if b is a or na.dot(b.normalAt(0, 0)) > -1 + 1e-6:
                continue
            d = (b.CenterOfMass - a.CenterOfMass).dot(na)
            if abs(abs(d) - t) > 1e-3:
                continue
            # dvojček mora ležati nasproti (prekrivanje projekcije), ne le v vzporedni ravnini na razdalji t
            try:
                prekrivanje = a.common(b.translated(na * -d)).Area
            except Exception:  # noqa: BLE001
                prekrivanje = 0
            if prekrivanje > 0.3 * min(a.Area, b.Area) or prekrivanje > 2 * t * t * 25:
                velike.append(a)
                break
    velike += _pari_valjev(oblika, t)   # zviti (valjani) deli spadajo k svoji strani
    sosedi = {k: set() for k in range(len(velike))}
    for i, a in enumerate(velike):
        for j in range(i + 1, len(velike)):
            b = velike[j]
            if any(ea.isSame(eb) for ea in a.Edges for eb in b.Edges):
                sosedi[i].add(j)
                sosedi[j].add(i)
    strani, videno = [], set()
    for k in range(len(velike)):
        if k in videno:
            continue
        sk, vrsta = [], [k]
        videno.add(k)
        while vrsta:
            x = vrsta.pop()
            sk.append(velike[x])
            for y in sosedi[x]:
                if y not in videno:
                    videno.add(y)
                    vrsta.append(y)
        strani.append(sk)
    return strani


def _sredina(f):
    u0, u1, v0, v1 = f.ParameterRange
    return (u0 + u1) / 2, (v0 + v1) / 2


def _izbocen(oblika_tocka, f1, f2, rob):
    """Rob med ploskvama iste strani je izbočen (zunanji), če f2 leži pod ravnino f1 (glede na zunanjo normalo f1)."""
    p = rob.valueAt((rob.FirstParameter + rob.LastParameter) / 2)
    return (f2.CenterOfMass - p).dot(f1.normalAt(0, 0)) < -1e-6


def _odebeli_valj(f, d):
    """Valjasto ploskev odebeli za d v smeri njene normale analitično: pravokotnik (r … r ± d) × osna dolžina v
    ravnini osi se zavrti okoli osi čez kotni obseg ploskve (pokrije ves pravokotnik (u, v) ploskve)."""
    s = f.Surface
    u0, u1, v0, v1 = f.ParameterRange
    c0 = s.value(u0, v0)
    os_t = s.Center + s.Axis * (c0 - s.Center).dot(s.Axis)
    radial = c0 - os_t
    radial.normalize()
    navzven = f.normalAt((u0 + u1) / 2, (v0 + v1) / 2).dot(s.value((u0 + u1) / 2, v0) - (s.Center + s.Axis * (s.value((u0 + u1) / 2, v0) - s.Center).dot(s.Axis))) > 0
    r1 = s.Radius
    r2 = r1 + d if navzven else r1 - d
    if r2 <= 1e-6:
        raise ValueError("polmer bi postal ničeln")
    a, b = min(r1, r2), max(r1, r2)
    p = lambda r, v: os_t + radial * r + s.Axis * (v - v0)
    pr = Part.Face(Part.makePolygon([p(a, v0), p(b, v0), p(b, v1), p(a, v1), p(a, v0)]))
    import math
    return pr.revolve(os_t, s.Axis, math.degrees(u1 - u0))


def _odebeli_ukrivljeno(f, d, kandidati):
    """Ukrivljena ploskev: odmik (več kandidatov), za valje še analitična odebelitev. Vrne seznam teles."""
    for g in kandidati:
        try:
            o = g.makeOffsetShape(d if g.normalAt(*_sredina(g)).dot(f.normalAt(*_sredina(f))) > 0 else -d,
                                  1e-6, False, False, 0, 0, True)
        except Exception:  # noqa: BLE001
            continue
        x = o.Solids or ([Part.Solid(Part.Shell(o.Faces))] if o.Faces else [])
        ok = [q for q in x if abs(abs(q.Volume) - g.Area * d) < 0.2 * g.Area * d]
        if ok:
            return ok
    if f.Surface.TypeId == "Part::GeomCylinder":
        try:
            x = _odebeli_valj(f, d)
            if x.Volume > 0:
                return [x]
        except Exception:  # noqa: BLE001
            pass
    return []


def _vogalne_razbremenitve(s, robovi, velikost):
    """Izreže kvadratno razbremenitev ``velikost`` × ``velikost`` (čez ves kos v smeri normale) v vsakem vogalu, kjer se
    končata dva nevzporedna zunanja robova upogibov. Vrne novo telo (ali nespremenjeno, če vogalov ni)."""
    L = s.BoundBox.DiagonalLength
    stebri, videni = [], []
    for i, e1 in enumerate(robovi):
        d1 = e1.Vertexes[-1].Point - e1.Vertexes[0].Point
        d1.normalize()
        for e2 in robovi[i + 1:]:
            d2 = e2.Vertexes[-1].Point - e2.Vertexes[0].Point
            d2.normalize()
            if abs(d1.dot(d2)) > 0.1:
                continue
            if min((v1.Point - v2.Point).Length for v1 in e1.Vertexes for v2 in e2.Vertexes) > 3 * velikost:
                continue
            l1 = Part.LineSegment(e1.Vertexes[0].Point - d1 * L, e1.Vertexes[0].Point + d1 * L).toShape()
            l2 = Part.LineSegment(e2.Vertexes[0].Point - d2 * L, e2.Vertexes[0].Point + d2 * L).toShape()
            dist, pari, _ = l1.distToShape(l2)
            if dist > 1e-3:
                continue
            p = pari[0][0]
            if any((p - q).Length < 1e-3 for q in videni):
                continue
            videni.append(p)
            n = d1.cross(d2)
            n.normalize()
            a = e1.CenterOfMass - p
            a = a - n * a.dot(n)
            a.normalize()
            b = e2.CenterOfMass - p
            b = b - n * b.dot(n)
            b.normalize()
            kv = Part.Face(Part.makePolygon([p, p + a * velikost, p + (a + b) * velikost, p + b * velikost, p]))
            stebri.append(kv.translated(n * -L).extrude(n * 2 * L))
    if not stebri:
        return s
    r = s.cut(Part.Compound(stebri))
    try:
        r = r.removeSplitter()
    except Exception:  # noqa: BLE001
        pass
    return r.Solids[0] if len(r.Solids) == 1 else Part.Compound(r.Solids)


def prenovi_plocevino(oblika, debelina, polmer, obrni=False):
    """Uvožen kos iz pločevine v novo debelino in notranji polmer upogibov; zunanja stran (izbočena stran upogibov) in
    vse luknje v njej ostanejo, material raste navznoter. Vrne (oblika, opis)."""
    t = debelina_kosa(oblika)
    if t is None:
        raise ValueError("debeline ni mogoče določiti")
    upog = upogibi(oblika, t)
    try:
        ostra = oblika.defeaturing(upog) if upog else oblika.copy()
    except Exception:  # noqa: BLE001
        ostra = None
    strani = strani_plocevine(ostra, t) if ostra is not None and ostra.isValid() and len(ostra.Solids) == len(oblika.Solids) else []
    strani.sort(key=lambda s: -sum(f.Area for f in s))
    if len(strani) < 2:   # brez ostrega kosa ostane le postopek C (upogibi izvirnika)
        ostra = oblika
        strani = strani_plocevine(oblika, t)
        strani.sort(key=lambda s: -sum(f.Area for f in s))
        if len(strani) < 2:
            raise ValueError("strani pločevine ni mogoče ločiti (%d)" % len(strani))
        upog_ab = False
    else:
        upog_ab = True
    a, b = strani[0], strani[1]

    def izbocenih(stran):
        n = 0
        for i, f1 in enumerate(stran):
            for f2 in stran[i + 1:]:
                for e1 in f1.Edges:
                    if any(e1.isSame(e2) for e2 in f2.Edges):
                        n += 1 if _izbocen(ostra, f1, f2, e1) else -1
        return n
    ia, ib = izbocenih(a), izbocenih(b)
    # zviti deli: zunanja stran ima večji polmer para valjev
    for f in a:
        if f.Surface.TypeId == "Part::GeomCylinder":
            for g in b:
                if g.Surface.TypeId == "Part::GeomCylinder" and abs(abs(f.Surface.Radius - g.Surface.Radius) - t) < 1e-3:
                    ia += 2 if f.Surface.Radius > g.Surface.Radius else -2
                    ib += 2 if g.Surface.Radius > f.Surface.Radius else -2
                    break
    zunaj = a if ia >= ib else b
    if ia == ib == 0:   # ravna plošča: material raste nasproti normale največje ploskve
        zunaj = a
    if obrni:
        zunaj = b if zunaj is a else a
    notri = b if zunaj is a else a
    luknje, ravnine = [], []
    for f in zunaj:
        n = f.normalAt(*_sredina(f))
        if _ravnina(f):
            ravnine.append((n, f.CenterOfMass.dot(n)))
        for w in f.Wires:   # luknje zunanje strani: na koncu se izrežejo skozi novo debelino
            if not w.isSame(f.OuterWire):
                luknje.append(Part.Face(w).extrude(n * -(debelina + 1.0)).translated(n * 0.5))

    def na_zunanji(f):
        if not _ravnina(f):
            return False
        n = f.normalAt(0, 0)
        return any(n.isEqual(m, 1e-6) and abs(f.CenterOfMass.dot(m) - d) < 1e-4 for m, d in ravnine)

    def telo(o):
        try:
            o = o.removeSplitter()
        except Exception:  # noqa: BLE001  (OCC včasih ne zna zliti ploskev; oblika je vseeno pravilna)
            pass
        return o.Solids[0] if len(o.Solids) == 1 else Part.Compound(o.Solids)

    def zunanji_robovi(s):
        r = []
        for e in s.Edges:
            if e.Curve.TypeId != "Part::GeomLine":
                continue
            fs = s.ancestorsOfType(e, Part.Face)
            if len(fs) == 2 and all(na_zunanji(f) for f in fs) and \
                    abs(abs(fs[0].normalAt(0, 0).dot(fs[1].normalAt(0, 0))) - 1) > 1e-6 and _izbocen(s, fs[0], fs[1], e):
                r.append(e)
        return r

    def postopek_a():
        """Debelina: vsaka ploskev notranje strani se odebeli navznoter (posamezna ploskev), unija z ostrim kosom.
        Upogib: zunanji rob z R + T, nato obroč R … R + T okoli iste osi (odebelitev zunanje valjaste ploskve)."""
        d = debelina - t
        s = ostra
        if d < -1e-6:
            raise ValueError("tanjšanje pločevine ni podprto")
        if d > 1e-6:
            dodatki = []
            for f in notri:
                if _ravnina(f):   # ravna ploskev: izvlek po zunanji normali (točen in zanesljiv)
                    dodatki.append(f.extrude(f.normalAt(*_sredina(f)) * d))
                    continue
                ok = []
                kandidati = [f]
                if f.Wires[1:] or f.Surface.TypeId == "Part::GeomCylinder":   # znova sestavljena ploskev brez lukenj
                    try:
                        kandidati.append(Part.Face(f.Surface, f.OuterWire))
                    except Exception:  # noqa: BLE001
                        pass
                ok = _odebeli_ukrivljeno(f, d, kandidati)
                if not ok:
                    raise ValueError("odebelitev ukrivljene ploskve ni uspela")
                dodatki += ok
            s = telo(ostra.fuse(dodatki))
        robovi = zunanji_robovi(s) if upog and polmer > 0 else []
        if robovi:
            # luknje med upogibanjem zapolnjene (luknja ob upogibu zmoti zaokroževanje), izrežejo se na koncu
            cepi = []
            for f in zunaj:
                n = f.normalAt(*_sredina(f))
                cepi += [Part.Face(w).extrude(n * -debelina) for w in f.Wires if not w.isSame(f.OuterWire)]
            if cepi:
                s = telo(s.fuse(cepi))
            # vogalne razbremenitve: kjer se srečata dva upogiba, kvadrat R + T + 0,5 (stara razbremenitev je bila
            # le za stari polmer in novega zaokroževanja ne pusti skozi)
            rz = polmer + debelina
            s = _vogalne_razbremenitve(s, zunanji_robovi(s), rz + 0.5)
            robovi = zunanji_robovi(s)
        if robovi:
            rz = polmer + debelina
            z = s.makeFillet(rz, robovi)
            obroci = []
            for f in z.Faces:
                if f.Surface.TypeId == "Part::GeomCylinder" and abs(f.Surface.Radius - rz) < 1e-6:
                    o = f.makeOffsetShape(-debelina, 1e-6, False, False, 0, 0, True)
                    obroci += o.Solids or [Part.Solid(Part.Shell(o.Faces))]
            s = telo(z.fuse(obroci)) if obroci else z
        return s

    def postopek_b():
        """Zunanja stran brez lukenj se kot lupina odebeli navznoter; po zaokrožitvi zunanjih robov (R + T) znova."""
        polne = []
        for f in zunaj:
            if f.Wires[1:]:
                n = f.normalAt(*_sredina(f))
                p = Part.Face(Part.Plane(f.CenterOfMass, n), [f.OuterWire]) if _ravnina(f) else Part.Face(f.Surface, f.OuterWire)
                if p.normalAt(*_sredina(p)).dot(n) < 0:
                    p.reverse()
                polne.append(p)
            else:
                polne.append(f)

        def odebeli(ploskve):
            o = Part.Shell(ploskve).makeOffsetShape(-debelina, 1e-6, False, False, 0, 2, True)
            tel = []
            for x in o.Solids:
                if x.Volume < 0:
                    x.reverse()
                tel.append(x)
            if not tel:
                raise ValueError("odebelitev zunanje strani ni dala telesa")
            return tel[0] if len(tel) == 1 else Part.Compound(tel)
        s = odebeli(polne)
        robovi = zunanji_robovi(s) if upog and polmer > 0 else []
        if robovi:
            rz = polmer + debelina
            z = s.makeFillet(rz, robovi)
            zviti = [f.Surface for f in polne if f.Surface.TypeId == "Part::GeomCylinder"]

            def zvit(q):
                return any(abs(q.Radius - x.Radius) < 1e-6 and abs(abs(q.Axis.dot(x.Axis)) - 1) < 1e-6 and
                           (q.Center - x.Center).cross(x.Axis).Length < 1e-4 for x in zviti)
            s = odebeli([f for f in z.Faces if na_zunanji(f) or (f.Surface.TypeId == "Part::GeomCylinder" and
                                                                 (abs(f.Surface.Radius - rz) < 1e-6 or zvit(f.Surface)))])
        return s

    def postopek_c(druga=False):
        """Zadnja možnost: upogibi izvirnika ostanejo (zunanji polmer enak), notranja stran izvirnika se odebeli
        navznoter -> notranji polmer = stari zunanji − nova debelina (manjši od želenega). ``druga``: obrne izbiro strani."""
        st = strani_plocevine(oblika, t)
        st.sort(key=lambda x: -sum(f.Area for f in x))
        if len(st) < 2:
            raise ValueError("strani izvirnika ni mogoče ločiti")
        sa, sb = st[0], st[1]
        ocena = 0
        for f in sa:   # zunanja stran ima večje polmere parov valjev
            if f.Surface.TypeId == "Part::GeomCylinder":
                for g in sb:
                    if g.Surface.TypeId == "Part::GeomCylinder" and abs(abs(f.Surface.Radius - g.Surface.Radius) - t) < 1e-3 and \
                            (g.Surface.Center - f.Surface.Center).cross(f.Surface.Axis).Length < 1e-3:
                        ocena += 1 if f.Surface.Radius > g.Surface.Radius else -1
        zn, nt = (sa, sb) if ocena > 0 or (ocena == 0 and zunaj is a) else (sb, sa)
        if obrni != druga:
            zn, nt = nt, zn
        d = debelina - t
        dodatki = []
        for f in nt:
            if _ravnina(f):
                dodatki.append(f.extrude(f.normalAt(*_sredina(f)) * d))
            else:
                ok = _odebeli_ukrivljeno(f, d, [f])
                if not ok:
                    raise ValueError("odebelitev ukrivljene ploskve izvirnika ni uspela")
                dodatki += ok
        return telo(oblika.fuse(dodatki))

    sproscen = [False]   # drugi krog: okvir sme zrasti za prirastek debeline (Z-prirobnice: zunanja stran se menja)

    def okvir_ok(x):
        """Zunanje mere ostanejo: okvir se sme spremeniti največ za prirastek debeline (ravne plošče)."""
        b0, b1 = oblika.BoundBox, x.BoundBox
        odm = max(abs(getattr(b0, k) - getattr(b1, k)) for k in ("XMin", "XMax", "YMin", "YMax", "ZMin", "ZMax"))
        return odm <= (debelina - t) + 1e-3 if (not upog or sproscen[0]) else odm <= 1e-2

    napake = []
    nova = None
    zahtevan = polmer
    for r in (sorted({zahtevan, min(zahtevan, 1.0), min(zahtevan, 0.5)}, reverse=True) if upog_ab else []):
        polmer = r   # postopka A in B bereta polmer ob klicu
        for postopek in (postopek_a, postopek_b):
            try:
                x = postopek()
                if luknje:
                    x = telo(x.cut(Part.Compound(luknje)))
                pricakovano = ostra.Volume * debelina / t
                if x.isValid() and x.Solids and abs(x.Volume - pricakovano) < 0.1 * pricakovano and okvir_ok(x):
                    nova = x
                    break
                napake.append("%s R%g: neveljavna, napačna prostornina ali okvir" % (postopek.__name__, r))
            except Exception as e:  # noqa: BLE001
                napake.append("%s R%g: %s" % (postopek.__name__, r, str(e).strip() or type(e).__name__))
        if nova is not None:
            break
    dosezen = "R %g" % polmer if upog else "brez upogibov"
    for druga, sprosti in ((False, False), (True, False), (False, True), (True, True)):
        if nova is not None:
            break
        sproscen[0] = sprosti
        try:
            postopek = postopek_c
            x = postopek_c(druga)
            pricakovano = oblika.Volume * debelina / t
            if x.isValid() and x.Solids and abs(x.Volume - pricakovano) < 0.1 * pricakovano and okvir_ok(x):
                nova = x
                rs = sorted({round(f.Surface.Radius, 2) for f in upog}) if upog else []
                dosezen = "upogibi izvirnika (notranji R %s)%s%s" % (
                    ", ".join("%g" % (r_ - (debelina - t)) for r_ in rs[:1]) if rs else "-", ", druga stran" if druga else "",
                    ", okvir +%g mm" % (debelina - t) if sprosti else "")
            else:
                napake.append("postopek_c%s: neveljavna, prostornina ali okvir" % (" (druga stran)" if druga else ""))
        except Exception as e:  # noqa: BLE001
            napake.append("postopek_c: %s" % (str(e).strip() or type(e).__name__))
    if nova is None:
        raise ValueError("; ".join(napake))
    opis = "T %.2f -> %.2f, upogibov %d, strani %d (izbočenih %d / %d), %s, %s" % (
        t, debelina, len(upog) // 2, len(strani), ia, ib, postopek.__name__, dosezen)
    return nova, opis


class PrenovaPlocevine:
    """Kos iz pločevine v novi debelini in polmeru upogibov iz uvoženega izvirnika (``prenovi_plocevino``): zunanje
    mere in luknje ostanejo, material raste navznoter. Debelina, polmer in stran so parametri."""

    def __init__(self, obj, izvirnik=None):
        obj.Proxy = self
        self._lastnosti(obj, nov=True)
        if izvirnik is not None:
            obj.Izvirnik = izvirnik

    def _lastnosti(self, obj, nov=False):
        _lastnost(obj, "App::PropertyLink", "Izvirnik", "Pločevina", "Uvožen kos, ki se prenovi")
        _lastnost(obj, "App::PropertyLength", "Debelina", "Pločevina", "Nova debelina pločevine", 2.0)
        _lastnost(obj, "App::PropertyLength", "Polmer", "Pločevina", "Notranji polmer upogibov", 2.0)
        _lastnost(obj, "App::PropertyBool", "Obrni", "Pločevina",
                  "Ohrani drugo stran (material raste navzven namesto navznoter)", False)
        if "Material" in obj.PropertiesList and obj.getTypeIdOfProperty("Material") == "App::PropertyString":
            # starejši kosi: prosto besedilo (»Al EN AW-5754 H22«) -> ključ iz tabele; polmer ostane, kot je
            staro = obj.Material
            obj.removeProperty("Material")
            _lastnosti_materiala(obj, "Pločevina", False)
            obj.Material = materiali.najdi(staro) or materiali.PRIVZETI
        else:
            _lastnosti_materiala(obj, "Pločevina", nov)
        _lastnost(obj, "App::PropertyString", "Vrsta", "Kos", "Vrsta kosa", "pločevina")
        _lastnost(obj, "App::PropertyString", "Opis", "Pločevina", "Izid zadnje prenove", "")
        obj.setEditorMode("Opis", 1)

    def onDocumentRestored(self, obj):
        self._lastnosti(obj)

    def onChanged(self, obj, ime):
        if ime in ("Material", "Debelina", "Samodejno") and "Samodejno" in obj.PropertiesList:
            _uporabi_material(obj, obj.Debelina.Value)

    def execute(self, obj):
        if obj.Izvirnik is None or obj.Izvirnik.Shape.isNull():
            return
        _sheetmetal_na_poti()
        nova, opis = prenovi_plocevino(obj.Izvirnik.Shape, obj.Debelina.Value, obj.Polmer.Value, obj.Obrni)
        if obj.Opis != opis:
            obj.Opis = opis
        obj.Shape = nova

    def dumps(self):
        return None

    def loads(self, stanje):
        return None


def racun_upogiba(k, standard="ansi", tabela=""):
    """BendAllowanceCalculator dodatka SheetMetal: en K ali tabela »R/T:K; R/T:K«. Interpolacija dodatka je pravilna le
    med prvima vrsticama (zanka v get_k_factor ne napreduje), zato tabela z več kot dvema vrsticama javi napako."""
    from SheetMetalNewUnfolder import BendAllowanceCalculator
    vrstice = [v.split(":") for v in (tabela or "").replace(",", ".").split(";") if ":" in v]
    if not vrstice:
        return BendAllowanceCalculator.from_single_value(k, standard)
    if len(vrstice) > 2:
        raise ValueError("KTabela: največ dve vrstici (napaka interpolacije v SheetMetal V2)")
    bac = BendAllowanceCalculator.from_single_value(float(vrstice[0][1]), standard)
    bac.radius_thickness_values = [float(rt) for rt, _ in vrstice]
    bac.k_factor_values = [float(kk) for _, kk in vrstice]
    return bac


class Razgrnitev:
    def __init__(self, obj, kos=None):
        obj.Proxy = self
        self._lastnosti(obj, nov=True)
        if kos is not None:
            obj.Kos = kos

    def _lastnosti(self, obj, nov=False):
        _lastnost(obj, "App::PropertyLink", "Kos", "Razgrnitev", "Kos iz pločevine, ki se razgrne")
        _lastnost(obj, "App::PropertyFloat", "KFaktor", "Razgrnitev", "K-faktor (lega nevtralne osi)", 0.44)
        _lastnost(obj, "App::PropertyEnumeration", "Standard", "Razgrnitev", "ANSI: K glede na debelino; DIN: glede na polovico")
        if not obj.Standard:
            obj.Standard = ["ANSI", "DIN"]
            obj.Standard = "ANSI"
        _lastnost(obj, "App::PropertyString", "KTabela", "Razgrnitev",
                  "K po razmerju R/T, npr. »1:0.40; 3:0.50« (pod prvo vrstico prva vrednost, nad zadnjo zadnja, vmes "
                  "linearno); prazno = KFaktor za vse upogibe", "")
        if "Material" in obj.PropertiesList and obj.getTypeIdOfProperty("Material") == "App::PropertyString":
            staro = obj.Material   # starejše razgrnitve: prosto besedilo -> ključ; K ostane, kot je bil
            obj.removeProperty("Material")
            _lastnosti_materiala(obj, "Razgrnitev", False)
            obj.Material = materiali.najdi(staro) or materiali.PRIVZETI
        else:
            _lastnosti_materiala(obj, "Razgrnitev", nov)
        _lastnost(obj, "App::PropertyBool", "ObStrani", "Razgrnitev",
                  "Razgrnitev leži ob kosu (desno, na višini dna), ne na mestu zgornje ploskve", True)
        _lastnost(obj, "App::PropertyLength", "Razmik", "Razgrnitev", "Razmik med kosom in razgrnitvijo", 50.0)

    def onDocumentRestored(self, obj):
        self._lastnosti(obj)

    def onChanged(self, obj, ime):
        # debelina se izmeri iz kosa; K iz tabele materiala pri razmerju R/T najmanjšega upogiba kosa
        if ime in ("Material", "Samodejno", "Kos") and "Samodejno" in obj.PropertiesList and obj.Samodejno \
                and not _med_branjem(obj) and obj.Kos is not None and not obj.Kos.Shape.isNull():
            t = debelina_kosa(obj.Kos.Shape)
            if t:
                r = [f.Surface.Radius for f in upogibi(obj.Kos.Shape, t)]
                p = materiali.parametri(obj.Material, t, r=min(r) if r else None)
                if abs(obj.KFaktor - p["K"]) > 1e-9:
                    obj.KFaktor = p["K"]
                if obj.KTabela != p["KTabela"]:
                    obj.KTabela = p["KTabela"]

    @staticmethod
    def korenska_ploskev(oblika):
        """Izhodiščna ploskev razgrnitve: največja ravna ploskev kosa. Prednost ima ploskev z normalo +Z (kos, ki leži
        plosko, se razgrne iz zgornje ploskve), a le, če ni bistveno manjša od največje: pri kosih, ki stojijo pokonci
        (kotniki, nosilci), je največja ploskev z normalo +Z pogosto ploskev debeline in razgrnitev iz nje pade
        (»Wire is not closed«)."""
        ravne = [(k, f) for k, f in enumerate(oblika.Faces, 1) if f.Surface.TypeId == "Part::GeomPlane"]
        najvecja = max(ravne, key=lambda t: t[1].Area)
        zgoraj = [t for t in ravne if t[1].normalAt(0, 0).z > 0.99 and t[1].Area >= 0.5 * najvecja[1].Area]
        izbrana = max(zgoraj, key=lambda t: t[1].Area) if zgoraj else najvecja
        return "Face%d" % izbrana[0]

    def execute(self, obj):
        if obj.Kos is None or obj.Kos.Shape.isNull():
            return
        _sheetmetal_na_poti()
        from SheetMetalNewUnfolder import getUnfold
        bac = racun_upogiba(obj.KFaktor, obj.Standard.lower(), getattr(obj, "KTabela", ""))
        koren = self.korenska_ploskev(obj.Kos.Shape)
        # razgrnjevalnik z nekaterih ploskev pade (»Two points are coincident«): poskusi še druge velike ravne ploskve
        kandidati = [koren] + ["Face%d" % k for k, f in sorted(enumerate(obj.Kos.Shape.Faces, 1), key=lambda x: -x[1].Area)
                               if _ravnina(f) and "Face%d" % k != koren][:6]
        napaka = None
        for koren in kandidati:
            try:
                _koren, ravno, _pregibi, normala, _info = getUnfold(bac, obj.Kos, koren)
                break
            except Exception as e:  # noqa: BLE001
                napaka = e
        else:
            raise napaka
        # razgrnjena ploskev ne leži nujno v ravnini izhodiščne ploskve; njeno normalo vrne razgrnjevalnik
        normala = App.Vector(normala) if normala is not None else obj.Kos.Shape.getElement(koren).normalAt(0, 0)
        zasuk = App.Rotation()
        if abs(normala.z) < 0.99:   # razgrnjevalnik vrne ploskev pokonci: položi jo vodoravno
            zasuk = App.Rotation(normala, App.Vector(0, 0, 1))
        # zasuk in premik gresta v lego objekta (`transformed` zasuk zapiše le v lego oblike, ki jo prirejanje
        # obj.Placement spodaj prepiše); okvir za premik se vzame z zasukane oblike
        premik = App.Vector()
        if obj.ObStrani:   # desno od kosa, na višini dna, da se ne prekrivata
            k = obj.Kos.Shape.BoundBox
            r = ravno.transformed(App.Placement(App.Vector(), zasuk).toMatrix()).BoundBox
            premik = App.Vector(k.XMax + obj.Razmik.Value - r.XMin, (k.YMin + k.YMax - r.YMin - r.YMax) / 2, k.ZMin - r.ZMin)
        obj.Shape = ravno
        nova = App.Placement(premik, zasuk)
        if not obj.Placement.isSame(nova, 1e-7):   # le ob spremembi, sicer bi se objekt sam označil kot spremenjen
            obj.Placement = nova

    def dumps(self):
        return None

    def loads(self, stanje):
        return None


def _ikona_sheetmetal(ime):
    pot = os.path.join(App.getUserAppDataDir(), "Mod", "sheetmetal", "Resources", "icons", ime)
    return pot if os.path.exists(pot) else ""


class PogledTelesaVPlocevino:
    """Pogled: osnovno telo je v drevesu pod pločevino (kot pri FreeCAD-ovih značilnostih)."""

    def __init__(self, vobj):
        vobj.Proxy = self

    def attach(self, vobj):
        self.Object = vobj.Object

    def claimChildren(self):
        o = getattr(self, "Object", None)
        return [o.Osnova] if o is not None and getattr(o, "Osnova", None) is not None else []

    def getIcon(self):
        return _ikona_sheetmetal("SheetMetal_FromSolid.svg")

    def dumps(self):
        return None

    def loads(self, stanje):
        return None


class PogledRazgrnitve:
    def __init__(self, vobj):
        vobj.Proxy = self

    def attach(self, vobj):
        self.Object = vobj.Object

    def getIcon(self):
        return _ikona_sheetmetal("SheetMetal_Unfold.svg")

    def dumps(self):
        return None

    def loads(self, stanje):
        return None


def obris_za_laser(razgrnitev_oblika):
    """Zanke (zunanji obris in izrezi) zgornje ploskve razgrnitve, poravnane na XY in v izhodišče — za DXF."""
    ploskev = max(razgrnitev_oblika.Faces, key=lambda f: f.Area)
    n = ploskev.normalAt(0, 0)
    pl = App.Placement(App.Vector(), App.Rotation(n, App.Vector(0, 0, 1)))
    oblika = Part.Compound(ploskev.Wires).transformed(pl.toMatrix())
    b = oblika.BoundBox
    oblika.translate(App.Vector(-b.XMin, -b.YMin, -b.ZMin))
    return oblika
