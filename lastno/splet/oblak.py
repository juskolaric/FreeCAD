# -*- coding: utf-8 -*-
"""Različice datotek iz lastnega oblaka (PDM, korak 2) za spletni pogled FreeCAD-a.

Oblak (Apps/oblak) hrani vsako shranjeno datoteko kot revizijo. Ta modul se v imenu uporabnika prijavi v oblak
kot lastna naprava »FreeCAD (splet)«, lokalno pot datoteke v mapi odjemalca oblaka (privzeto %USERPROFILE%\\Oblak)
preslika v prostor in pot v oblaku (enako kot spletni vmesnik oblaka: Osebno, skupine, prostori brez skupine),
našteje različice (GET /v1/zgodovina), prenese izbrano različico v začasno mapo (GET /v1/content?rev=) in obnovi
starejšo (POST /v1/obnovi).

Vse tu teče na niti strežnika (klici HTTP v oblak), FreeCAD-ovega API-ja ne kliče. Odpiranje prenesene različice
in osvežitev dokumenta po obnovi gresta prek vrste na glavno nit (ukaz "projekt": odpri-razlicico, osvezi).

Seja (osvežitveni žeton) je v %LOCALAPPDATA%/FreeCAD-splet/oblak.json; naslov API-ja in mapa sinhronizacije se
privzeto prebereta iz nastavitev odjemalca za Windows (%APPDATA%/Oblak/nastavitve.json; žetona odjemalca ne
uporabljamo, ker bi oblak spremembe štel za njegove in jih odjemalec ne bi prenesel). Okolje: SPLET_OBLAK_API.
"""
import json
import os
import platform
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

MAPA_NASTAVITEV = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "FreeCAD-splet")
DATOTEKA_SEJE = os.path.join(MAPA_NASTAVITEV, "oblak.json")
MAPA_RAZLICIC = os.path.join(MAPA_NASTAVITEV, "razlicice")
NASTAVITVE_ODJEMALCA = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "Oblak", "nastavitve.json")
OSEBNA_MAPA = "Osebno"
PRIVZETI_API = "http://127.0.0.1:8790"
CAS_PROSTOROV = 60.0          # sekund, kolikor velja predpomnjen seznam prostorov
CAKANJE_NA_ODJEMALCA = 180.0  # sekund, kolikor po obnovi čakamo, da odjemalec oblaka posodobi lokalno datoteko


class NapakaOblaka(Exception):
    def __init__(self, status, koda, sporocilo):
        super().__init__(sporocilo)
        self.status = status
        self.koda = koda


def varno_ime(ime):
    """Ime prostora kot ime mape na disku (enako kot odjemalec in spletni vmesnik oblaka)."""
    ocisceno = "".join("-" if (c in '<>:"/\\|?*' or ord(c) < 0x20) else c for c in str(ime or "")).strip()
    ocisceno = re.sub(r"[. ]+$", "", ocisceno)
    if len(ocisceno) > 80:
        ocisceno = ocisceno[:80].rstrip()
    return ocisceno or "Prostor"


def _skupina(prostor):
    return varno_ime(prostor["skupina"]) if prostor.get("kind") != "personal" and prostor.get("skupina") else None


def razresi_pot(deli, prostori):
    """Deli relativne poti v mapi odjemalca -> (prostor, pot v prostoru) ali None, če prostora ni.

    /Osebno/... je osebni prostor, /<skupina>/<prostor>/... prostor v skupini, /<prostor>/... prostor brez skupine.
    """
    if not deli:
        return None
    prvi = deli[0].lower()
    osebni = next((p for p in prostori if p.get("kind") == "personal"), None)
    if prvi == OSEBNA_MAPA.lower() and osebni is not None:
        return osebni, "/" + "/".join(deli[1:])
    v_skupini = [p for p in prostori if (_skupina(p) or "").lower() == prvi]
    if v_skupini:
        if len(deli) < 2:
            return None
        prostor = next((p for p in v_skupini if varno_ime(p["name"]).lower() == deli[1].lower()), None)
        return (prostor, "/" + "/".join(deli[2:])) if prostor else None
    prostor = next((p for p in prostori if p.get("kind") != "personal" and not _skupina(p)
                    and varno_ime(p["name"]).lower() == prvi), None)
    return (prostor, "/" + "/".join(deli[1:])) if prostor else None


class Oblak:
    def __init__(self, dnevnik=None, vrsta=None, oddaj=None):
        self._log = dnevnik or (lambda b: None)
        self._vrsta = vrsta          # vrsta zahtev za glavno nit (STANJE.vrsta) ali None
        self._oddaj = oddaj          # oddaja dogodkov SSE (STANJE.oddaj) ali None
        self.kljuc = threading.Lock()
        self.seja = self._preberi_sejo()
        self._odjemalec = self._preberi_odjemalca()
        self._prostori = []
        self._prostori_cas = 0.0
        self._zaklepi = {}       # pot (normcase) -> zaklep iz oblaka (slovar) ali None; predpomnilnik za seznam dokumentov
        self._moji = set()       # poti, ki jih je zaklenil ta primerek (ob zaprtju/izhodu jih sprosti)
        self._zahtevani = set()  # poti, za katere je samodejni zaklep ob odprtju že sprožen

    # ------------------------------------------------------------------ nastavitve
    @staticmethod
    def _preberi_sejo():
        try:
            with open(DATOTEKA_SEJE, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    @staticmethod
    def _preberi_odjemalca():
        try:
            with open(NASTAVITVE_ODJEMALCA, encoding="utf-8") as f:
                n = json.load(f)
            return {"api": n.get("api") or "", "mapa": n.get("folder") or ""}
        except (OSError, ValueError):
            return {}

    def _zapisi_sejo(self):
        try:
            os.makedirs(MAPA_NASTAVITEV, exist_ok=True)
            if self.seja:
                with open(DATOTEKA_SEJE, "w", encoding="utf-8") as f:
                    json.dump(self.seja, f)
            elif os.path.exists(DATOTEKA_SEJE):
                os.remove(DATOTEKA_SEJE)
        except OSError as e:
            self._log("oblak: seje ni bilo mogoče zapisati: %s" % e)

    def api(self):
        return (self.seja.get("api") or os.environ.get("SPLET_OBLAK_API") or self._odjemalec.get("api")
                or PRIVZETI_API).rstrip("/")

    def mapa_sinhronizacije(self):
        """Mapa, ki jo odjemalec oblaka drži usklajeno (SPLET_OBLAK_MAPA za preizkuse)."""
        return os.path.normpath(os.environ.get("SPLET_OBLAK_MAPA") or self._odjemalec.get("mapa")
                                or os.path.join(os.path.expanduser("~"), "Oblak"))

    def prijavljen(self):
        return bool(self.seja.get("refresh_token"))

    def stanje(self):
        return {
            "prijavljen": self.prijavljen(),
            "email": self.seja.get("email", ""),
            "ime": self.seja.get("ime", ""),
            "api": self.api(),
            "mapa": self.mapa_sinhronizacije(),
            "mapaRazlicic": MAPA_RAZLICIC,
            "odjemalec": bool(self._odjemalec),
            "zaklepov": len(self._moji),
        }

    # ------------------------------------------------------------------ klici v oblak
    def _zahteva(self, metoda, pot, telo=None, poizvedba=None, zeton=None, surovo=False, timeout=60):
        url = self.api() + pot
        if poizvedba:
            url += "?" + urllib.parse.urlencode({k: v for k, v in poizvedba.items() if v is not None})
        glave = {"Accept": "application/json"}
        podatki = None
        if telo is not None:
            glave["Content-Type"] = "application/json"
            podatki = json.dumps(telo).encode("utf-8")
        if zeton:
            glave["Authorization"] = "Bearer " + zeton
        zahteva = urllib.request.Request(url, data=podatki, headers=glave, method=metoda)
        try:
            odgovor = urllib.request.urlopen(zahteva, timeout=timeout)
        except urllib.error.HTTPError as e:
            besedilo = e.read().decode("utf-8", "replace")
            try:
                napaka = json.loads(besedilo)
            except ValueError:
                napaka = {}
            raise NapakaOblaka(e.code, napaka.get("error", "napaka"), napaka.get("message") or besedilo or str(e))
        except urllib.error.URLError as e:
            raise NapakaOblaka(503, "nedosegljiv", "Oblak ni dosegljiv (%s): %s" % (self.api(), e.reason))
        if surovo:
            return odgovor
        with odgovor:
            besedilo = odgovor.read().decode("utf-8")
        return json.loads(besedilo) if besedilo else {}

    def _zeton(self):
        """Dostopni žeton (15 min); po poteku ga osveži z osvežitvenim."""
        with self.kljuc:
            if not self.seja.get("refresh_token"):
                raise NapakaOblaka(401, "neprijavljen", "V oblak nisi prijavljen")
            if self.seja.get("dostop") and self.seja.get("velja_do", 0) - 30 > time.time():
                return self.seja["dostop"]
            try:
                r = self._zahteva("POST", "/v1/auth/refresh", {"refresh_token": self.seja["refresh_token"]})
            except NapakaOblaka as e:
                if e.status in (401, 403):
                    self.seja = {}
                    self._zapisi_sejo()
                    raise NapakaOblaka(401, "neprijavljen", "Prijava v oblak je potekla; prijavi se znova")
                raise
            self.seja["dostop"] = r["access_token"]
            self.seja["velja_do"] = time.time() + float(r.get("expires_in", 900))
            self._zapisi_sejo()
            return self.seja["dostop"]

    def _klic(self, metoda, pot, telo=None, poizvedba=None, surovo=False, timeout=60):
        return self._zahteva(metoda, pot, telo, poizvedba, self._zeton(), surovo, timeout)

    # ------------------------------------------------------------------ zaklepi (PDM, korak 4)
    @staticmethod
    def _kljuc(pot):
        return os.path.normcase(os.path.normpath(pot))

    def zaklep_dokumenta(self, lokalna_pot):
        """Za seznam odprtih dokumentov (glavna nit, brez klica v oblak): zaklep iz predpomnilnika. Ob prvem klicu
        za pot sproži samodejni zaklep v ozadju (odprt dokument = check-out)."""
        if not (self.prijavljen() and self.v_oblaku(lokalna_pot) and not self.je_razlicica(lokalna_pot)):
            return None
        k = self._kljuc(lokalna_pot)
        if k not in self._zahtevani:
            self._zahtevani.add(k)
            threading.Thread(target=self._samodejni_zaklep, args=(lokalna_pot,), name="oblak-zaklep", daemon=True).start()
        return self._zaklepi.get(k)

    def _samodejni_zaklep(self, lokalna_pot):
        ime = os.path.basename(lokalna_pot)
        try:
            r = self.zakleni(lokalna_pot)
        except NapakaOblaka as e:
            self._log("oblak: zaklep %s: %s" % (ime, e))
            self._osvezi_seznam()
            return
        z = r.get("zaklep") or {}
        if r.get("zaklenjeno"):
            if not r.get("ze"):
                self._oddaj_dogodek("zaklep", lokalna_pot, "»%s« je zaklenjena zate (odprta v FreeCAD-u)." % ime)
        else:
            kdo = (z.get("user") or {}).get("name") or "drug uporabnik"
            naprava = (z.get("device") or {}).get("name")
            self._oddaj_dogodek("zaklep-tuj", lokalna_pot,
                                "»%s« ima zaklenjeno %s%s. Odpri jo le za ogled; shranjene spremembe bodo nasprotujoča kopija."
                                % (ime, kdo, " (%s)" % naprava if naprava else ""))
        self._osvezi_seznam()

    def _osvezi_seznam(self):
        if self._vrsta is not None:
            self._vrsta.put(("projekt", {"dejanje": "osvezi-seznam"}, None))

    def zakleni(self, lokalna_pot):
        """Zaklene datoteko zame. Vrne {zaklenjeno, ze, zaklep}; če jo ima drug uporabnik, zaklenjeno=False."""
        prostor, pot = self.razresi(lokalna_pot)
        k = self._kljuc(lokalna_pot)
        try:
            r = self._klic("POST", "/v1/zakleni", {"namespace_id": prostor["id"], "path": pot,
                                                    "opomba": "odprto v FreeCAD-u"})
        except NapakaOblaka as e:
            if e.koda == "locked":
                z = self._klic("GET", "/v1/zaklep", poizvedba={"namespace_id": prostor["id"], "path": pot}).get("zaklep")
                self._zaklepi[k] = z
                return {"zaklenjeno": False, "ze": False, "zaklep": z}
            raise
        self._zaklepi[k] = r.get("zaklep")
        self._moji.add(k)
        return {"zaklenjeno": True, "ze": bool(r.get("ze")), "zaklep": r.get("zaklep")}

    def odkleni(self, lokalna_pot, force=False, timeout=60):
        prostor, pot = self.razresi(lokalna_pot)
        r = self._klic("POST", "/v1/odkleni", {"namespace_id": prostor["id"], "path": pot, "force": bool(force)},
                       timeout=timeout)
        k = self._kljuc(lokalna_pot)
        self._zaklepi[k] = None
        self._moji.discard(k)
        return r

    def prevzemi(self, lokalna_pot):
        """Prevzame tuj zaklep (sprosti ga s force in zaklene zase)."""
        self.odkleni(lokalna_pot, force=True)
        return self.zakleni(lokalna_pot)

    # ------------------------------------------------------------------ reference in kosovnica (PDM, korak 5)
    def reference(self, lokalna_pot, osvezi=False):
        """Vsebuje / kje je uporabljeno / kosovnica trenutne revizije (oblak bere Document.xml sam). Poti povezanih
        datotek v oblaku se preslikajo nazaj v lokalne poti, da jih brskalnik lahko odpre."""
        prostor, pot = self.razresi(lokalna_pot)
        r = self._klic("GET", "/v1/reference", poizvedba={"namespace_id": prostor["id"], "path": pot,
                                                          "osvezi": "1" if osvezi else None})
        mapa = self.mapa_sinhronizacije()
        koren = os.path.dirname(os.path.normpath(lokalna_pot))
        rel = os.path.relpath(os.path.normpath(lokalna_pot), mapa).replace("\\", "/")
        predpona = rel[: len(rel) - len(pot.lstrip("/"))].rstrip("/")   # del lokalne poti pred potjo v prostoru
        for v in r.get("vsebuje", []):
            cilj = v.get("cilj_pot_zdaj") or v.get("pot")
            if v.get("zunanja"):
                v["lokalno"] = v.get("pot")
            else:
                v["lokalno"] = os.path.normpath(os.path.join(mapa, predpona, cilj.lstrip("/")))
            v["obstaja_lokalno"] = bool(v["lokalno"]) and os.path.isfile(v["lokalno"])
        for u in r.get("uporabljeno_v", []):
            u["lokalno"] = os.path.normpath(os.path.join(mapa, predpona, u["pot"].lstrip("/")))
            u["obstaja_lokalno"] = os.path.isfile(u["lokalno"])
        r["pot"] = lokalna_pot
        r["mapa"] = koren
        return r

    def stanje_zaklepa(self, lokalna_pot):
        """Sveže stanje zaklepa iz oblaka (nit strežnika)."""
        prostor, pot = self.razresi(lokalna_pot)
        z = self._klic("GET", "/v1/zaklep", poizvedba={"namespace_id": prostor["id"], "path": pot}).get("zaklep")
        self._zaklepi[self._kljuc(lokalna_pot)] = z
        return {"pot": lokalna_pot, "zaklep": z, "moj_primerek": self._kljuc(lokalna_pot) in self._moji}

    def dokument_zaprt(self, lokalna_pot):
        """Ob zaprtju dokumenta sprosti zaklep, če ga je dal ta primerek (v ozadju)."""
        k = self._kljuc(lokalna_pot)
        self._zahtevani.discard(k)
        if k not in self._moji:
            return

        def sprosti():
            try:
                self.odkleni(lokalna_pot)
            except NapakaOblaka as e:
                self._log("oblak: odklep %s: %s" % (os.path.basename(lokalna_pot), e))
            self._osvezi_seznam()

        threading.Thread(target=sprosti, name="oblak-odklep", daemon=True).start()

    def odkleni_vse(self):
        """Ob izhodu iz FreeCAD-a: sprosti vse zaklepe tega primerka (sinhrono, kratek rok)."""
        for k in list(self._moji):
            try:
                self.odkleni(k, timeout=5)
            except Exception as e:  # noqa: BLE001
                self._log("oblak: odklep ob izhodu %s: %s" % (os.path.basename(k), e))

    # ------------------------------------------------------------------ prijava
    def prijava(self, email, geslo):
        if not email or not geslo:
            raise NapakaOblaka(400, "manjka", "Vpiši e-pošto in geslo")
        ime_naprave = "FreeCAD (splet) · %s" % (platform.node() or "računalnik")
        r = self._zahteva("POST", "/v1/auth/login",
                          {"email": email, "password": geslo, "device_name": ime_naprave, "platform": "cli"})
        with self.kljuc:
            self.seja = {
                "api": self.api(),
                "refresh_token": r["refresh_token"],
                "dostop": r.get("access_token"),
                "velja_do": time.time() + float(r.get("expires_in", 900)),
                "email": (r.get("user") or {}).get("email", email),
                "ime": (r.get("user") or {}).get("name", ""),
            }
            self._zapisi_sejo()
            self._prostori_cas = 0.0
        self._log("oblak: prijavljen kot %s" % self.seja["email"])
        return self.stanje()

    def odjava(self):
        try:
            if self.prijavljen():
                self._klic("POST", "/v1/auth/logout")
        except NapakaOblaka:
            pass
        with self.kljuc:
            self.seja = {}
            self._zapisi_sejo()
            self._prostori = []
        return self.stanje()

    # ------------------------------------------------------------------ preslikava poti
    def prostori(self, osvezi=False):
        if osvezi or time.time() - self._prostori_cas > CAS_PROSTOROV:
            jaz = self._klic("GET", "/v1/me")
            self._prostori = jaz.get("namespaces") or []
            self._prostori_cas = time.time()
            if jaz.get("user"):
                with self.kljuc:
                    self.seja["ime"] = jaz["user"].get("name") or self.seja.get("ime", "")
        return self._prostori

    def v_oblaku(self, lokalna_pot):
        """Ali je datoteka v mapi odjemalca oblaka (brez klica v oblak)."""
        return self._pod_mapo(lokalna_pot, self.mapa_sinhronizacije())

    def je_razlicica(self, lokalna_pot):
        """Ali je to prenesena kopija starejše različice (mapa različic), ne delovna datoteka."""
        return self._pod_mapo(lokalna_pot, MAPA_RAZLICIC)

    @staticmethod
    def _pod_mapo(pot, mapa):
        try:
            rel = os.path.relpath(os.path.normpath(pot), os.path.normpath(mapa))
        except ValueError:  # drug pogon
            return False
        return not rel.startswith("..") and not os.path.isabs(rel)

    def razresi(self, lokalna_pot):
        """Lokalna pot -> (prostor, pot v prostoru). Napaka 404, če datoteka ni v nobenem prostoru."""
        if not self.v_oblaku(lokalna_pot):
            raise NapakaOblaka(404, "ni-v-oblaku", "Datoteka ni v mapi oblaka (%s)" % self.mapa_sinhronizacije())
        rel = os.path.relpath(os.path.normpath(lokalna_pot), self.mapa_sinhronizacije())
        deli = [d for d in rel.replace("\\", "/").split("/") if d]
        rez = razresi_pot(deli, self.prostori())
        if rez is None:
            rez = razresi_pot(deli, self.prostori(osvezi=True))
        if rez is None or not rez[1].strip("/"):
            raise NapakaOblaka(404, "ni-prostora", "Za mapo »%s« v oblaku ni prostora, do katerega bi imel dostop" % (deli[0] if deli else ""))
        return rez

    # ------------------------------------------------------------------ različice
    def zgodovina(self, lokalna_pot):
        prostor, pot = self.razresi(lokalna_pot)
        z = self._klic("GET", "/v1/zgodovina", poizvedba={"namespace_id": prostor["id"], "path": pot})
        lokalno = None
        try:
            lokalno = int(os.stat(lokalna_pot).st_mtime)
        except OSError:
            pass
        razlicice = z.get("revisions") or []
        n = len(razlicice)
        po_id = {r["rev_id"]: n - i for i, r in enumerate(razlicice)}
        for i, r in enumerate(razlicice):
            r["st"] = n - i
            r["obnovljenaIz"] = po_id.get(r.get("restored_from"))
        return {"pot": lokalna_pot, "ime": z.get("name"), "prostor": prostor["name"], "potVOblaku": pot,
                "trenutna": z.get("current_rev"), "razlicice": razlicice, "lokalnoSpremenjeno": lokalno,
                "pdm": z.get("pdm") or {}, "mapaRazlicic": MAPA_RAZLICIC}

    def prenesi(self, lokalna_pot, rev, st=None):
        """Prenese različico v mapo različic in vrne (pot, oznaka za naslov dokumenta)."""
        prostor, pot = self.razresi(lokalna_pot)
        z = self._klic("GET", "/v1/zgodovina", poizvedba={"namespace_id": prostor["id"], "path": pot})
        razlicice = z.get("revisions") or []
        n = len(razlicice)
        izbrana = next(((n - i, r) for i, r in enumerate(razlicice) if r["rev_id"] == rev), None)
        if izbrana is None:
            raise NapakaOblaka(404, "ni-razlicice", "Te različice datoteka nima")
        st, r = izbrana
        ime, koncnica = os.path.splitext(os.path.basename(lokalna_pot))
        datum = (r.get("at") or "")[:16].replace("T", " ")
        cilj = os.path.join(MAPA_RAZLICIC, "%s · različica %d%s" % (ime, st, koncnica))
        os.makedirs(MAPA_RAZLICIC, exist_ok=True)
        odgovor = self._klic("GET", "/v1/content", poizvedba={"ns": prostor["id"], "node": z["node_id"], "rev": rev, "dl": "1"},
                             surovo=True)
        zacasna = cilj + ".del"
        with odgovor, open(zacasna, "wb") as f:
            while True:
                kos = odgovor.read(1 << 20)
                if not kos:
                    break
                f.write(kos)
        os.replace(zacasna, cilj)
        oznaka = "%s · različica %d (%s)" % (ime, st, datum)
        return cilj, oznaka, st

    # ------------------------------------------------------------------ komentar in stanje (PDM, korak 3)
    @staticmethod
    def _vsebinski_hash(lokalna_pot):
        """content_hash, kot ga računa oblak: sha256 nad zaporedjem sha256 kosov po 4 MiB (hex)."""
        import hashlib
        kosi = []
        with open(lokalna_pot, "rb") as f:
            while True:
                kos = f.read(4 * 1024 * 1024)
                if not kos:
                    break
                kosi.append(hashlib.sha256(kos).hexdigest())
        return hashlib.sha256("".join(kosi).encode("ascii")).hexdigest()

    def revizija(self, lokalna_pot, rev, komentar=None, stanje=None):
        """Komentar in/ali stanje (osnutek, v_pregledu, izdano) obstoječe revizije."""
        prostor, _pot = self.razresi(lokalna_pot)
        telo = {"namespace_id": prostor["id"], "rev": rev}
        if komentar is not None:
            telo["komentar"] = komentar
        if stanje:
            telo["stanje"] = stanje
        return self._klic("POST", "/v1/revizija", telo)

    def komentar_ob_shranjevanju(self, lokalna_pot, komentar):
        """Po shranjevanju v FreeCAD-u datoteko v oblak pošlje odjemalec oblaka. Komentar zato zapišemo k reviziji,
        katere vsebina (content_hash) se ujema z datoteko na disku - takoj, če je že tam, sicer ko pride
        (čakanje v ozadju, obvestilo prek dogodka »oblak«)."""
        prostor, pot = self.razresi(lokalna_pot)
        komentar = (komentar or "").strip()
        if not komentar:
            raise NapakaOblaka(400, "prazen", "Komentar je prazen")
        hash_ = self._vsebinski_hash(lokalna_pot)

        def poisci():
            z = self._klic("GET", "/v1/zgodovina", poizvedba={"namespace_id": prostor["id"], "path": pot})
            razlicice = z.get("revisions") or []
            for i, r in enumerate(razlicice):
                if r.get("content_hash") == hash_:
                    return r, len(razlicice) - i
            return None, None

        try:
            r, st = poisci()
        except NapakaOblaka as e:
            if e.status != 404:
                raise
            r, st = None, None
        if r is not None:
            self.revizija(lokalna_pot, r["rev_id"], komentar=komentar)
            return {"ok": True, "takoj": True, "st": st, "rev": r["rev_id"]}

        def cakaj():
            konec = time.time() + CAKANJE_NA_ODJEMALCA
            ime = os.path.basename(lokalna_pot)
            while time.time() < konec:
                time.sleep(2.0)
                try:
                    r2, st2 = poisci()
                except NapakaOblaka:
                    continue
                if r2 is not None:
                    try:
                        self.revizija(lokalna_pot, r2["rev_id"], komentar=komentar)
                    except NapakaOblaka as e:
                        self._oddaj_dogodek("napaka", lokalna_pot, "Komentarja k »%s« ni bilo mogoče zapisati: %s" % (ime, e))
                        return
                    self._oddaj_dogodek("komentar", lokalna_pot, "Komentar je zapisan k različici #%d datoteke »%s«." % (st2, ime))
                    return
            self._oddaj_dogodek("cakanje", lokalna_pot,
                                "Odjemalec oblaka nove različice »%s« še ni poslal; komentar ni zapisan. Preveri, ali odjemalec teče, "
                                "in komentar dodaj v plošči z različicami." % ime)

        threading.Thread(target=cakaj, name="oblak-komentar", daemon=True).start()
        return {"ok": True, "takoj": False}

    def _oddaj_dogodek(self, vrsta, pot, sporocilo):
        if self._oddaj is not None:
            self._oddaj("oblak", {"vrsta": vrsta, "pot": pot, "sporocilo": sporocilo})

    def obnovi(self, lokalna_pot, rev):
        prostor, pot = self.razresi(lokalna_pot)
        rezultat = self._klic("POST", "/v1/obnovi", {"namespace_id": prostor["id"], "path": pot, "rev": rev})
        if not rezultat.get("unchanged"):
            self._pocakaj_odjemalca(lokalna_pot)
        return rezultat

    def _pocakaj_odjemalca(self, lokalna_pot):
        """Obnova nastane v oblaku; lokalno datoteko posodobi odjemalec oblaka. Ko se spremeni, FreeCAD dokument
        osveži (glavna nit) in brskalnik dobi obvestilo."""
        try:
            prej = os.stat(lokalna_pot).st_mtime_ns
        except OSError:
            prej = None

        def cakaj():
            konec = time.time() + CAKANJE_NA_ODJEMALCA
            while time.time() < konec:
                time.sleep(1.0)
                try:
                    zdaj = os.stat(lokalna_pot).st_mtime_ns
                except OSError:
                    continue
                if zdaj != prej:
                    time.sleep(1.0)  # odjemalec datoteko preimenuje iz začasne; počakamo, da je cela
                    if self._vrsta is not None:
                        self._vrsta.put(("projekt", {"dejanje": "osvezi", "pot": lokalna_pot}, None))
                    if self._oddaj is not None:
                        self._oddaj("oblak", {"vrsta": "osvezeno", "pot": lokalna_pot,
                                              "sporocilo": "Odjemalec oblaka je posodobil »%s« na obnovljeno različico."
                                              % os.path.basename(lokalna_pot)})
                    return
            if self._oddaj is not None:
                self._oddaj("oblak", {"vrsta": "cakanje", "pot": lokalna_pot,
                                      "sporocilo": "Obnova je v oblaku, odjemalec oblaka pa datoteke »%s« še ni posodobil. "
                                                   "Preveri, ali odjemalec teče." % os.path.basename(lokalna_pot)})

        threading.Thread(target=cakaj, name="oblak-cakanje", daemon=True).start()


def obdelaj_zahtevo(oblak, metoda, pot, podatki):
    """Usmerjanje poti /oblak/* (nit strežnika). Vrne (koda, slovar); odpiranje dokumenta da v vrsto glavne niti."""
    try:
        if metoda == "GET" and pot == "/oblak/stanje":
            return 200, oblak.stanje()
        if metoda == "GET" and pot == "/oblak/zgodovina":
            return 200, oblak.zgodovina(podatki.get("pot", ""))
        if metoda == "POST" and pot == "/oblak/prijava":
            return 200, oblak.prijava(podatki.get("email", "").strip(), podatki.get("geslo", ""))
        if metoda == "POST" and pot == "/oblak/odjava":
            return 200, oblak.odjava()
        if metoda == "POST" and pot == "/oblak/obnovi":
            return 200, oblak.obnovi(podatki.get("pot", ""), podatki.get("rev", ""))
        if metoda == "GET" and pot == "/oblak/zaklep":
            return 200, oblak.stanje_zaklepa(podatki.get("pot", ""))
        if metoda == "GET" and pot == "/oblak/reference":
            return 200, oblak.reference(podatki.get("pot", ""), osvezi=podatki.get("osvezi") in ("1", "true"))
        if metoda == "POST" and pot == "/oblak/zakleni":
            r = oblak.zakleni(podatki.get("pot", ""))
            oblak._osvezi_seznam()
            return 200, r
        if metoda == "POST" and pot == "/oblak/odkleni":
            r = oblak.odkleni(podatki.get("pot", ""), force=bool(podatki.get("force")))
            oblak._osvezi_seznam()
            return 200, r
        if metoda == "POST" and pot == "/oblak/prevzemi":
            r = oblak.prevzemi(podatki.get("pot", ""))
            oblak._osvezi_seznam()
            return 200, r
        if metoda == "POST" and pot == "/oblak/komentar":
            return 200, oblak.komentar_ob_shranjevanju(podatki.get("pot", ""), podatki.get("komentar", ""))
        if metoda == "POST" and pot == "/oblak/revizija":
            return 200, oblak.revizija(podatki.get("pot", ""), podatki.get("rev", ""),
                                       podatki.get("komentar"), podatki.get("stanje"))
        if metoda == "POST" and pot == "/oblak/odpri":
            cilj, oznaka, st = oblak.prenesi(podatki.get("pot", ""), podatki.get("rev", ""))
            if oblak._vrsta is not None:
                oblak._vrsta.put(("projekt", {"dejanje": "odpri-razlicico", "pot": cilj, "oznaka": oznaka,
                                              "izvirnik": podatki.get("pot", "")}, None))
            return 200, {"ok": True, "pot": cilj, "oznaka": oznaka, "st": st}
        return 404, {"napaka": "ni take poti"}
    except NapakaOblaka as e:
        return e.status, {"napaka": str(e), "koda": e.koda}
    except Exception as e:  # noqa: BLE001
        oblak._log("oblak: nepričakovana napaka: %r" % e)
        return 500, {"napaka": "Napaka pri delu z oblakom: %s" % e}
