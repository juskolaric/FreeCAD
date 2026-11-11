"""Izdaje projekta: zamrznjeni posnetki vseh modelov projekta v mapi <projekt>/Izdaje/ (od 2026-11-10).

Različice v oblaku (oblak.py) so zgodovina ene datoteke. Izdaja je stanje CELEGA projekta ob nekem trenutku: kopija vseh
datotek FCStd z isto razporeditvijo map, tako da se glavni sestav izdaje odpre z deli iz iste izdaje (»pokaži izdajo 1«).

    <projekt>/Izdaje/izdaje.json                    seznam izdaj in povezava kosov med njimi
    <projekt>/Izdaje/Izdaja 1 (2026-02-03)/...      kopija map projekta
    <projekt>/Izdaje/Izdaja 2 (2026-06-15)/...

Povezave med datotekami znotraj izdaje so relativne in ostanejo; povezave navzven (Standard box, Standardni deli) se
preračunajo na novo lego, ti kosi pa ostanejo skupni (niso zamrznjeni). Delovne datoteke projekta se ne spreminjajo.
Modul ne potrebuje FreeCAD-a (samo datoteke), zato teče tudi iz ukazne vrstice:

    python izdaje.py seznam "<mapa projekta>"
    python izdaje.py nova "<mapa projekta>" --opis "..." [--datum 2026-06-15] [--glavni "PHOTO BOX 43 7.FCStd"] [--izvor "<mapa>"]
"""
import datetime
import json
import os
import re
import shutil
import sys
import zipfile

MAPA_IZDAJ = "Izdaje"
SEZNAM = "izdaje.json"
# mape projekta, ki niso modeli (podatki prenosa, skice z iPada, toplotna analiza, stroški) ali so same izdaje
IZPUSTI_MAPE = {MAPA_IZDAJ.lower(), "skripte", "skice", "toplota", "stroski", "stroški", "izvoz"}
KONCNICE = {".fcstd", ".pdf"}   # modeli in risbe; varnostne kopije .FCBak ne
_XLINK_DATOTEKA = re.compile(r'(<XLink\b[^>]*?\bfile=")([^"]+)(")')


class NapakaIzdaje(Exception):
    pass


def mapa_izdaj(projekt):
    return os.path.join(projekt, MAPA_IZDAJ)


def preberi(projekt):
    """Seznam izdaj projekta: {"projekt", "izdaje": [...], "kosi": [...]}; brez datoteke prazen."""
    pot = os.path.join(mapa_izdaj(projekt), SEZNAM)
    try:
        with open(pot, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    d.setdefault("projekt", os.path.basename(os.path.normpath(projekt)))
    d.setdefault("izdaje", [])
    d.setdefault("kosi", [])
    return d


def zapisi(projekt, podatki):
    os.makedirs(mapa_izdaj(projekt), exist_ok=True)
    pot = os.path.join(mapa_izdaj(projekt), SEZNAM)
    zacasna = pot + ".tmp"
    with open(zacasna, "w", encoding="utf-8") as f:
        json.dump(podatki, f, ensure_ascii=False, indent=1)
    os.replace(zacasna, pot)


def seznam(projekt):
    """Izdaje z absolutno potjo mape in glavnega sestava (za strežnik in orodja)."""
    izhod = []
    for i in preberi(projekt)["izdaje"]:
        mapa = os.path.join(mapa_izdaj(projekt), i["mapa"])
        glavni = os.path.join(mapa, i["glavni"]) if i.get("glavni") else ""
        izhod.append(dict(i, potMape=mapa.replace("\\", "/"), potGlavnega=glavni.replace("\\", "/"),
                          obstaja=os.path.isdir(mapa), glavniObstaja=bool(glavni) and os.path.isfile(glavni)))
    return izhod


def datoteke_projekta(izvor):
    """Relativne poti modelov in risb pod izvorom (brez map, ki niso modeli)."""
    najdene = []
    for koren, podmape, imena in os.walk(izvor):
        podmape[:] = sorted(d for d in podmape if d.lower() not in IZPUSTI_MAPE and not d.startswith((".", "__")))
        for ime in sorted(imena, key=str.lower):
            if os.path.splitext(ime)[1].lower() in KONCNICE:
                najdene.append(os.path.relpath(os.path.join(koren, ime), izvor))
    return najdene


def _znotraj(pot, mapa):
    pot, mapa = os.path.normcase(os.path.normpath(pot)), os.path.normcase(os.path.normpath(mapa))
    return pot == mapa or pot.startswith(mapa + os.sep)


def kopiraj_fcstd(izvorna, ciljna, koren_izvora):
    """Kopira FCStd; povezave na datoteke zunaj izvora preračuna na lego kopije. Vrne (povezav navzven, manjkajoče)."""
    mapa_izvorne, mapa_ciljne = os.path.dirname(izvorna), os.path.dirname(ciljna)
    with zipfile.ZipFile(izvorna) as z:
        vnosi = [(i, z.read(i.filename)) for i in z.infolist()]
    navzven, manjka = 0, []

    def popravi(m):
        nonlocal navzven
        rel = m.group(2)
        if rel.startswith("https://"):
            return m.group(0)
        tarca = os.path.normpath(rel if os.path.isabs(rel) else os.path.join(mapa_izvorne, rel))
        if not os.path.isfile(tarca):
            manjka.append(rel)
        if _znotraj(tarca, koren_izvora):
            return m.group(0)   # ista izdaja: relativna pot velja tudi v kopiji
        navzven += 1
        try:
            nova = os.path.relpath(tarca, mapa_ciljne)
        except ValueError:   # drug disk
            nova = tarca
        return m.group(1) + nova.replace("\\", "/") + m.group(3)

    vnosi = [(i, _XLINK_DATOTEKA.sub(popravi, b.decode("utf-8")).encode("utf-8") if i.filename == "Document.xml" else b)
             for i, b in vnosi]
    os.makedirs(mapa_ciljne, exist_ok=True)
    zacasna = ciljna + ".tmp"
    with zipfile.ZipFile(zacasna, "w", zipfile.ZIP_DEFLATED) as z:
        for i, b in vnosi:   # vrstni red ostane (Document.xml prvi)
            z.writestr(i, b, compress_type=i.compress_type)
    os.replace(zacasna, ciljna)
    shutil.copystat(izvorna, ciljna)   # datum spremembe modela ostane datum izvirnika
    return navzven, manjka


def odtis_geometrije(pot):
    """Odtis oblike v FCStd (CRC vseh datotek .brp); enak odtis = ista geometrija, čeprav je datoteka znova shranjena."""
    try:
        with zipfile.ZipFile(pot) as z:
            return sorted((i.CRC, i.file_size) for i in z.infolist() if i.filename.lower().endswith(".brp"))
    except (OSError, zipfile.BadZipFile):
        return None


def primerjaj(mapa_prej, mapa_zdaj):
    """Kosi dveh izdaj po isti relativni poti: enak, spremenjen, nov, opuščen."""
    prej = {p.lower(): p for p in datoteke_projekta(mapa_prej) if p.lower().endswith(".fcstd")}
    zdaj = {p.lower(): p for p in datoteke_projekta(mapa_zdaj) if p.lower().endswith(".fcstd")}
    kosi = []
    for k in sorted(set(prej) | set(zdaj)):
        a, b = prej.get(k), zdaj.get(k)
        if a and b:
            enak = odtis_geometrije(os.path.join(mapa_prej, a)) == odtis_geometrije(os.path.join(mapa_zdaj, b))
            stanje = "enak" if enak else "spremenjen"
        else:
            stanje = "nov" if b else "opuščen"
        kosi.append({"prej": a and a.replace("\\", "/"), "zdaj": b and b.replace("\\", "/"), "stanje": stanje})
    return kosi


def nova(projekt, opis="", datum=None, glavni="", izvor=None, st=None, kosi=None, dnevnik=print, ime_mape=None):
    """Zamrzne stanje izvora (privzeto delovne datoteke projekta) kot naslednjo izdajo. Vrne zapis izdaje."""
    projekt = os.path.normpath(projekt)
    izvor = os.path.normpath(izvor or projekt)
    if not os.path.isdir(izvor):
        raise NapakaIzdaje("Mape %s ni" % izvor)
    podatki = preberi(projekt)
    st = int(st or (max([i["st"] for i in podatki["izdaje"]] or [0]) + 1))
    if any(i["st"] == st for i in podatki["izdaje"]):
        raise NapakaIzdaje("Izdaja %d že obstaja" % st)
    datum = datum or datetime.date.today().isoformat()
    ime_mape = ime_mape or "Izdaja %d (%s)" % (st, datum)   # Malibu S: »Izdaja 2.2« (verzija 2.2 izdaje 2)
    cilj = os.path.join(mapa_izdaj(projekt), ime_mape)
    if os.path.exists(cilj):
        raise NapakaIzdaje("Mapa %s že obstaja" % cilj)
    datoteke = datoteke_projekta(izvor)
    if not any(d.lower().endswith(".fcstd") for d in datoteke):
        raise NapakaIzdaje("V %s ni modelov" % izvor)
    if glavni and not os.path.isfile(os.path.join(izvor, glavni)):
        raise NapakaIzdaje("Glavnega sestava %s ni v %s" % (glavni, izvor))
    modelov = navzven = 0
    manjkajo = []
    for rel in datoteke:
        izvorna, ciljna = os.path.join(izvor, rel), os.path.join(cilj, rel)
        if rel.lower().endswith(".fcstd"):
            n, m = kopiraj_fcstd(izvorna, ciljna, izvor)
            modelov += 1
            navzven += n
            manjkajo += [(rel, x) for x in m]
        else:
            os.makedirs(os.path.dirname(ciljna), exist_ok=True)
            shutil.copy2(izvorna, ciljna)
    zapis = {"st": st, "ime": "Izdaja %d" % st, "datum": datum, "opis": opis, "mapa": ime_mape,
             "glavni": glavni.replace("\\", "/"), "modelov": modelov, "povezavNavzven": navzven,
             "ustvarjeno": datetime.datetime.now().isoformat(timespec="seconds")}
    prejsnja = max((i for i in podatki["izdaje"] if i["st"] < st), key=lambda i: i["st"], default=None)
    if kosi is None and prejsnja is not None:
        kosi = primerjaj(os.path.join(mapa_izdaj(projekt), prejsnja["mapa"]), cilj)
    if kosi is not None and prejsnja is not None:
        podatki["kosi"] = [k for k in podatki["kosi"] if k.get("med") != [prejsnja["st"], st]]
        podatki["kosi"].append({"med": [prejsnja["st"], st], "kosi": kosi,
                                "povzetek": {s: sum(1 for k in kosi if k["stanje"] == s)
                                             for s in ("enak", "spremenjen", "nov", "opuščen")}})
    podatki["izdaje"].append(zapis)
    podatki["izdaje"].sort(key=lambda i: i["st"])
    zapisi(projekt, podatki)
    dnevnik("%s: %d modelov, %d povezav navzven, manjkajočih tarč %d" % (ime_mape, modelov, navzven, len(manjkajo)))
    for rel, x in manjkajo[:20]:
        dnevnik("  manjka: %s -> %s" % (rel, x))
    return zapis


def preveri(projekt, st):
    """Vse povezave izdaje: koliko jih kaže v izdajo, koliko navzven in katere tarče manjkajo."""
    zapis = next((i for i in preberi(projekt)["izdaje"] if i["st"] == int(st)), None)
    if zapis is None:
        raise NapakaIzdaje("Izdaje %s ni" % st)
    mapa = os.path.join(mapa_izdaj(projekt), zapis["mapa"])
    znotraj = navzven = 0
    v_delovne, manjka = [], []
    for rel in datoteke_projekta(mapa):
        if not rel.lower().endswith(".fcstd"):
            continue
        pot = os.path.join(mapa, rel)
        with zipfile.ZipFile(pot) as z:
            xml = z.read("Document.xml").decode("utf-8")
        for m in _XLINK_DATOTEKA.finditer(xml):
            tarca = os.path.normpath(os.path.join(os.path.dirname(pot), m.group(2)))
            if not os.path.isfile(tarca):
                manjka.append((rel, m.group(2)))
            elif _znotraj(tarca, mapa):
                znotraj += 1
            else:
                navzven += 1
                if _znotraj(tarca, projekt):
                    v_delovne.append((rel, m.group(2)))   # izdaja ne sme kazati na delovne datoteke projekta
    return {"st": zapis["st"], "znotraj": znotraj, "navzven": navzven, "vDelovne": v_delovne, "manjka": manjka}


# ---------------------------------------------------------------------------
# Različice kosa čez izdaje: isti kos ima v vsaki izdaji (in v delovni mapi) svojo datoteko; zaporedne datoteke z enako
# vsebino so ista različica. Vrstica različic pod pogledom tako pokaže V1, V2 ... in v kateri izdaji je katera vključena.

_KONCNICA_KOPIJE = re.compile(r" \(v [^)]*\)(?: [0-9a-f]{6}| \d+)?$")   # »(v nadsestav) 0cf629« pri gibljivih podsestavih
_PODPISI = {}   # (pot, mtime) -> podpis vsebine


def ime_kosa(datoteka):
    """Ime kosa brez pripone gibljivega podsestava: »VLOŽEK 7 (v PHOTO BOX 43 7) 473f2e.FCStd« -> »vložek 7«."""
    ime = os.path.splitext(os.path.basename(datoteka))[0]
    return _KONCNICA_KOPIJE.sub("", ime).strip().lower()


def podpis_sestava(pot, ime=ime_kosa):
    """Sestav: urejen seznam (kos, lega na 0,1 mm, zasuk) vseh povezav; None, če datoteka nima povezav."""
    import xml.etree.ElementTree as ET
    with zipfile.ZipFile(pot) as z:
        koren = ET.fromstring(z.read("Document.xml"))
    kosi = []
    for o in koren.iter("Object"):
        lastnosti = {p.get("name"): p for p in o.findall("./Properties/Property")}
        xl = lastnosti["LinkedObject"].find(".//XLink") if "LinkedObject" in lastnosti else None
        pl = lastnosti["Placement"].find(".//PropertyPlacement") if "Placement" in lastnosti else None
        if xl is None or pl is None or not xl.get("file"):
            continue
        q = [float(pl.get(k, 0)) for k in ("Q0", "Q1", "Q2", "Q3")]
        if q[3] < 0:
            q = [-x for x in q]
        kosi.append((ime(xl.get("file")),) + tuple(round(float(pl.get(k, 0)), 1) for k in ("Px", "Py", "Pz"))
                    + tuple(round(x, 3) for x in q))
    return sorted(kosi) or None


def podpis(pot):
    """Podpis vsebine modela za primerjavo dveh datotek istega kosa: sestav po legah kosov, del po geometriji."""
    try:
        kljuc = (os.path.normcase(pot), os.stat(pot).st_mtime)
    except OSError:
        return None
    if kljuc not in _PODPISI:
        try:
            s = podpis_sestava(pot)
            _PODPISI[kljuc] = ("sestav", s) if s else ("del", odtis_geometrije(pot))
        except Exception:  # noqa: BLE001
            _PODPISI[kljuc] = None
        if len(_PODPISI) > 5000:
            _PODPISI.pop(next(iter(_PODPISI)))
    return _PODPISI[kljuc]


def projekt_datoteke(pot, meja=None):
    """Mapa projekta z izdajami, v katerem je datoteka (delovna ali iz izdaje), ali None."""
    mapa = os.path.dirname(os.path.normpath(pot))
    meja = os.path.normcase(os.path.normpath(meja)) if meja else None
    while True:
        if os.path.isfile(os.path.join(mapa, MAPA_IZDAJ, SEZNAM)):
            return mapa
        visje = os.path.dirname(mapa)
        if visje == mapa or (meja and os.path.normcase(mapa) == meja):
            return None
        mapa = visje


def razlicice_kosa(pot, meja=None):
    """Različice kosa čez izdaje in delovno mapo. Vrne None, če projekt nima izdaj, sicer
    {"projekt", "kje": 0 = delovno | št. izdaje, "trenutna": V, "razlicice": [{"v", "clani": [{"st", "ime"}], "pot", "datum",
    "vkljucena": ali je v njej odprta datoteka}]}; najnovejša prva."""
    projekt = projekt_datoteke(pot, meja)
    if projekt is None:
        return None
    podatki = preberi(projekt)
    izd = sorted(podatki["izdaje"], key=lambda i: i["st"])
    if not izd:
        return None
    mape = {i["st"]: os.path.join(mapa_izdaj(projekt), i["mapa"]) for i in izd}
    pari = {tuple(k["med"]): k["kosi"] for k in podatki["kosi"]}
    pot = os.path.normpath(pot)
    kje = next((st for st, m in mape.items() if _znotraj(pot, m)), 0)
    if kje == 0 and _znotraj(pot, mapa_izdaj(projekt)):
        return None
    rel = os.path.relpath(pot, mape[kje] if kje else projekt).replace("\\", "/")
    stevilke = [i["st"] for i in izd]
    zadnja = stevilke[-1]
    veriga = {kje: rel}        # št. izdaje (0 = delovno) -> relativna pot kosa
    prehod = {}                # št. izdaje (0 = delovno) -> stanje glede na prejšnji člen verige

    def sosed(a, b, znana, smer):
        """Kos v sosednji izdaji: smer -1 išče prejšnjega (znana je pot v b), +1 naslednjega (znana je pot v a)."""
        for k in pari.get((a, b), []):
            if smer < 0 and (k.get("zdaj") or "").lower() == znana.lower():
                return k.get("prej"), k.get("stanje")
            if smer > 0 and (k.get("prej") or "").lower() == znana.lower():
                return k.get("zdaj"), k.get("stanje")
        return None, None

    def delovna_proti_zadnji(rel_delovna=None, rel_zadnja=None):
        r = rel_delovna or rel_zadnja
        a, b = os.path.join(mape[zadnja], r), os.path.join(projekt, r)
        if not (os.path.isfile(a) and os.path.isfile(b)):
            return None, None
        pa, pb = podpis(a), podpis(b)
        return r, ("enak" if pa is not None and pa == pb else "spremenjen")

    # nazaj od znanega člena
    if kje == 0:
        r, s = delovna_proti_zadnji(rel_delovna=rel)
        if r:
            veriga[zadnja], prehod[0] = r, s
    tek = zadnja if kje == 0 else kje
    while tek in veriga:
        i = stevilke.index(tek)
        if i == 0:
            break
        r, s = sosed(stevilke[i - 1], tek, veriga[tek], -1)
        if not r:
            break
        veriga[stevilke[i - 1]], prehod[tek] = r, s
        tek = stevilke[i - 1]
    # naprej od znanega člena
    tek = kje
    while tek and tek in veriga and tek != zadnja:
        i = stevilke.index(tek)
        r, s = sosed(tek, stevilke[i + 1], veriga[tek], +1)
        if not r:
            break
        veriga[stevilke[i + 1]], prehod[stevilke[i + 1]] = r, s
        tek = stevilke[i + 1]
    if kje and zadnja in veriga and 0 not in veriga:
        r, s = delovna_proti_zadnji(rel_zadnja=veriga[zadnja])
        if r:
            veriga[0], prehod[0] = r, s

    razlicice = []
    for st in [s for s in stevilke if s in veriga] + ([0] if 0 in veriga else []):
        clan = {"st": st, "ime": "Izdaja %d" % st if st else "Delovno"}
        datoteka = os.path.join(mape[st] if st else projekt, veriga[st]).replace("\\", "/")
        if razlicice and prehod.get(st) == "enak":
            razlicice[-1]["clani"].append(clan)
            if st == kje or not razlicice[-1]["vkljucena"]:
                razlicice[-1]["pot"] = datoteka   # odprta datoteka, sicer najnovejši član (delovna ima sličico in se odpre za delo)
        else:
            razlicice.append({"v": len(razlicice) + 1, "clani": [clan], "pot": datoteka, "vkljucena": False,
                              "datum": next((i["datum"] for i in izd if i["st"] == st), "") if st else ""})
        if st == kje:
            razlicice[-1]["vkljucena"] = True
            razlicice[-1]["pot"] = datoteka
    trenutna = next((r["v"] for r in razlicice if r["vkljucena"]), 0)
    return {"projekt": podatki["projekt"], "kje": kje, "trenutna": trenutna, "razlicice": razlicice[::-1]}


def _ukazna_vrstica(argumenti):
    import argparse
    p = argparse.ArgumentParser(description="Izdaje projekta (zamrznjeni posnetki modelov)")
    p.add_argument("ukaz", choices=["seznam", "nova", "preveri"])
    p.add_argument("projekt")
    p.add_argument("--opis", default="")
    p.add_argument("--datum")
    p.add_argument("--glavni", default="")
    p.add_argument("--izvor")
    p.add_argument("--st", type=int)
    a = p.parse_args(argumenti)
    if a.ukaz == "seznam":
        print(json.dumps(seznam(a.projekt), ensure_ascii=False, indent=1))
    elif a.ukaz == "nova":
        print(json.dumps(nova(a.projekt, a.opis, a.datum, a.glavni, a.izvor, a.st), ensure_ascii=False, indent=1))
    else:
        print(json.dumps(preveri(a.projekt, a.st or 1), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    _ukazna_vrstica(sys.argv[1:])
