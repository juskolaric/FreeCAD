# -*- coding: utf-8 -*-
"""Pomočnik AI v spletnem FreeCAD-u (MCP-PLAN.md, korak 6): klepet v stranski plošči strani, Claude dela z istimi
orodji kot most MCP (mcp_orodja.py), uporabnik vidi vsak korak in potrdi spremembe.

Zanka teče v svoji niti procesa FreeCAD-a in FreeCAD-ovega API-ja ne kliče sama: orodja gredo skozi
mcp_orodja.izvedi_slovar (ta jih po potrebi pošlje na glavno nit). Pogovor je samo z dodajanjem (bloki odgovora se
vrnejo nespremenjeni, sicer razmišljanje ne velja več); shranjen je v %LOCALAPPDATA%/FreeCAD-splet/pomocnik
(pogovor.json, prikaz.json, slike/), »Nov pogovor« prejšnjega premakne v arhiv/.

Potrditve: orodja, ki samo berejo (in izbira, render, seznam dokumentov), tečejo brez vprašanja; spremembe modela
(python, ukaz, obrazec, razveljavi, natisni, oblikovanje) vprašajo, razen če uporabnik v plošči dovoli spremembe;
shrani, izhod, splet in koda z dovoli_pisanje vprašajo vedno.

Ključ: ANTHROPIC_API_KEY iz okolja, sicer %LOCALAPPDATA%/FreeCAD-splet/kljuci.env, sicer .env plošče Tiskaj (kot AI
oblikovalec v Oblikovanju). Ključ se nikoli ne izpiše in ne gre v stran. Knjižnica anthropic za Python FreeCAD-a je
nameščena v %LOCALAPPDATA%/FreeCAD-splet/python-freecad (pip --target, okolje pixi ostane nespremenjeno).

Strežnik: GET /pomocnik?od=N (stanje in koraki od N), GET /pomocnik/slika?id=, POST /pomocnik {dejanje: poslji |
potrdi | ustavi | nov}; dogodek SSE "pomocnik" ob spremembi stanja.
"""

import base64
import datetime
import json
import os
import re
import sys
import threading
import time
import traceback
import uuid

LOKALNO = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "FreeCAD-splet")
KNJIZNICE = os.path.join(LOKALNO, "python-freecad")
MAPA_POGOVORA = os.path.join(LOKALNO, "pomocnik")
MAPA = os.path.dirname(os.path.abspath(__file__))
MODEL = "claude-opus-5-5"
NAJVEC_KORAKOV = 40          # klicev API v enem odgovoru
NAPOR = {"hitro": "low", "obicajno": "medium", "temeljito": "high"}
VARNA = {"izberi", "dokumenti", "render", "opravilo"}     # poleg orodij, ki samo berejo
NEVARNA = {"shrani", "izhod", "splet"}                     # vedno vprašaj
OPIS_ORODIJ = {"stanje": "Stanje", "dokumenti": "Dokumenti", "drevo": "Drevo", "slika": "Slika", "izmeri": "Meritve",
               "python": "Python", "ukaz": "Ukaz", "obrazec": "Obrazec", "izberi": "Izbira", "isci": "Iskanje",
               "razveljavi": "Razveljavi", "shrani": "Shrani", "splet": "Strežnik", "natisni": "Natisni",
               "render": "Render", "oblikovanje": "Oblikovanje", "opravilo": "Opravilo", "dnevnik": "Dnevnik",
               "izhod": "Izhod"}

SISTEM = """Si pomočnik v spletnem FreeCAD-u (lastna gradnja FreeCAD 1.1; uporabnik dela v brskalniku, okno FreeCAD-a je
skrito). Uporabnik je izdelovalec (Photobox, pločevina, 3D tisk, elektro plošče) in govori slovensko. Pogovor teče v
plošči ob 3D pogledu: uporabnik ves čas vidi model, ki ga spreminjaš, in vsak tvoj klic orodja.

Delo:
- Najprej razumi stanje (na začetku vsakega sporočila je povzetek), po potrebi `drevo`, `slika`, `izmeri`.
- Ne veš, kako kaj narediti? `isci` (ukazi okolij, FreeCAD API, tipi objektov z lastnostmi, naši moduli, skripte
  projektov, pravila). Ne ugibaj imen funkcij.
- Spremembe delaj z `python` (en klic = en korak za Razveljavi) ali z `ukaz` + `obrazec`. Po vsaki spremembi oblike
  poglej `slika` in preveri mere z `izmeri`, preden trdiš, da je prav.
- Nekatera orodja potrebujejo potrditev uporabnika. Če jo zavrne, ne ponavljaj istega klica; vprašaj, kaj želi.
- Shranjuj samo, kadar uporabnik to želi (`shrani`). Ne briši uporabnikovih objektov ali datotek brez naročila.
- Odgovarjaj kratko v slovenščini (nekaj stavkov): kaj si naredil, kaj vidiš, kaj predlagaš. Kode ne piši v odgovor,
  razen če uporabnik zanjo prosi.
- Razmišljaj in piši kratka pojasnila med koraki v slovenščini (uporabnik jih bere v plošči).

Pravila programa:
"""


def najdi_kljuc():
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"].strip()
    koren = os.path.normpath(os.path.join(MAPA, "..", ".."))
    kandidati = [os.path.join(LOKALNO, "kljuci.env"),
                 os.path.join(koren, "..", "3D print", "tiskaj", ".env"),
                 os.path.join(koren, "..", "3D tisk", "3D print", "tiskaj", ".env"),
                 os.path.join(koren, "..", "..", "3D print", "tiskaj", ".env")]
    for pot in kandidati:
        try:
            with open(pot, encoding="utf-8") as f:
                for vrstica in f:
                    k, _, v = vrstica.strip().partition("=")
                    if k.strip() == "ANTHROPIC_API_KEY" and v.strip():
                        return v.strip().strip('"').strip("'")
        except OSError:
            continue
    return ""


def _knjiznica():
    # preizkusni primerek z ločenim LOCALAPPDATA uporabi knjižnico iz uporabnikove mape
    for mapa in (KNJIZNICE, os.path.join(os.path.expanduser("~"), "AppData", "Local", "FreeCAD-splet", "python-freecad")):
        if os.path.isdir(mapa):
            if mapa not in sys.path:
                sys.path.append(mapa)
            break
    try:
        import anthropic  # noqa: F401
        return True
    except ImportError:
        return False


def _v_dict(blok):
    return blok.to_dict() if hasattr(blok, "to_dict") else dict(blok)


TIPI_JSON = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "array": list, "object": dict}


def _preveri_vhod(shema, vhod):
    """Vhod orodja po pretakanju (eager_input_streaming) strežnik ne preveri: preveri ga po shemi kataloga."""
    if not isinstance(vhod, dict):
        return "vhod ni objekt"
    lastnosti = shema.get("properties") or {}
    for ime in shema.get("required") or []:
        if ime not in vhod:
            return "manjka %s" % ime
    for ime, vrednost in vhod.items():
        if ime not in lastnosti:
            if shema.get("additionalProperties") is False:
                return "neznan argument %s" % ime
            continue
        tip = lastnosti[ime].get("type")
        if tip in TIPI_JSON:
            if isinstance(vrednost, bool) and tip in ("integer", "number"):
                return "%s: pričakovano število" % ime
            if not isinstance(vrednost, TIPI_JSON[tip]):
                return "%s: pričakovan tip %s" % (ime, tip)
        moznosti = lastnosti[ime].get("enum")
        if moznosti and vrednost not in moznosti:
            return "%s: dovoljeno %s" % (ime, ", ".join(map(str, moznosti)))
    return ""


def dobi(S):
    """Pomočnik tega strežnika (na STANJE, da preživi reload modula; po reloadu nov razred, ko ne dela)."""
    p = getattr(S.STANJE, "pomocnik", None)
    if p is None or (not isinstance(p, Pomocnik) and p.stanje != "dela"):
        p = Pomocnik(S)
        S.STANJE.pomocnik = p
    p.S = S
    return p


class Pomocnik:
    def __init__(self, S):
        self.S = S
        self.zaklep = threading.Lock()
        self.nit = None
        self.ustavi = False
        self.koraki = []
        self.stanje = "miruje"          # miruje | dela
        self.sporocilo = ""
        self.potrditve = {}             # id -> {"dogodek", "odgovor"}
        os.makedirs(os.path.join(MAPA_POGOVORA, "slike"), exist_ok=True)
        try:
            with open(os.path.join(MAPA_POGOVORA, "prikaz.json"), encoding="utf-8") as f:
                self.koraki = json.load(f)
        except (OSError, ValueError):
            self.koraki = []
        for k in self.koraki:   # potrditev, ki je ob ponovnem zagonu ostala odprta, ne velja več
            if k.get("vrsta") == "potrditev" and k.get("odgovor") is None:
                k["odgovor"] = False

    # -- shranjevanje --
    def _sporocila(self):
        try:
            with open(os.path.join(MAPA_POGOVORA, "pogovor.json"), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return []

    def _shrani(self, sporocila=None):
        os.makedirs(MAPA_POGOVORA, exist_ok=True)
        if sporocila is not None:
            zac = os.path.join(MAPA_POGOVORA, "pogovor.json.delno")
            with open(zac, "w", encoding="utf-8") as f:
                json.dump(sporocila, f, ensure_ascii=False)
            os.replace(zac, os.path.join(MAPA_POGOVORA, "pogovor.json"))
        with self.zaklep:
            vsebina = json.dumps(self.koraki, ensure_ascii=False)
        zac = os.path.join(MAPA_POGOVORA, "prikaz.json.delno")
        with open(zac, "w", encoding="utf-8") as f:
            f.write(vsebina)
        os.replace(zac, os.path.join(MAPA_POGOVORA, "prikaz.json"))

    def _korak(self, vrsta, besedilo="", **dodatno):
        with self.zaklep:
            k = {"i": len(self.koraki), "vrsta": vrsta, "besedilo": besedilo,
                 "cas": datetime.datetime.now().strftime("%H:%M:%S"), **dodatno}
            self.koraki.append(k)
        return k

    def _oddaj(self):
        try:
            self.S.STANJE.oddaj("pomocnik", {"stanje": self.stanje, "skupaj": len(self.koraki)})
        except Exception:  # noqa: BLE001
            pass

    # -- za stran --
    def stanje_od(self, od=0):
        od = max(0, min(int(od or 0), len(self.koraki)))
        od = max(0, od - 1)   # zadnji korak se med pretakanjem še dopolnjuje
        with self.zaklep:
            return {"stanje": self.stanje, "sporocilo": self.sporocilo, "od": od, "koraki": self.koraki[od:],
                    "skupaj": len(self.koraki), "kljuc": bool(najdi_kljuc()), "knjiznica": _knjiznica_obstaja(),
                    "model": MODEL}

    def poslji(self, besedilo, nastavitve):
        besedilo = (besedilo or "").strip()
        if not besedilo:
            return {"ok": False, "sporocilo": "Prazno sporočilo."}
        with self.zaklep:
            if self.stanje == "dela":
                return {"ok": False, "sporocilo": "Pomočnik še dela; počakaj ali ga ustavi."}
            self.stanje, self.sporocilo, self.ustavi = "dela", "Začenjam …", False
        self.nit = threading.Thread(target=self._zanka, args=(besedilo, dict(nastavitve or {})), daemon=True,
                                    name="pomocnik")
        self.nit.start()
        self._oddaj()
        return {"ok": True}

    def potrdi(self, pid, odobri):
        p = self.potrditve.get(pid)
        if p is None:
            return {"ok": False, "sporocilo": "Ta potrditev ne čaka več."}
        p["odgovor"] = bool(odobri)
        p["dogodek"].set()
        return {"ok": True}

    def ustavi_delo(self):
        self.ustavi = True
        for p in list(self.potrditve.values()):
            p["odgovor"] = False
            p["dogodek"].set()
        return {"ok": True}

    def nov(self):
        with self.zaklep:
            if self.stanje == "dela":
                return {"ok": False, "sporocilo": "Pomočnik še dela; najprej ga ustavi."}
            arhiv = os.path.join(MAPA_POGOVORA, "arhiv", datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
            premaknjeno = False
            for ime in ("pogovor.json", "prikaz.json", "seja.json", "slike"):
                pot = os.path.join(MAPA_POGOVORA, ime)
                if os.path.exists(pot):
                    os.makedirs(arhiv, exist_ok=True)
                    os.replace(pot, os.path.join(arhiv, ime))
                    premaknjeno = True
            os.makedirs(os.path.join(MAPA_POGOVORA, "slike"), exist_ok=True)
            self.koraki = []
        self._oddaj()
        return {"ok": True, "arhiv": arhiv if premaknjeno else ""}

    # -- zanka --
    def _zanka(self, besedilo, nastavitve):
        try:
            self._delo(besedilo, nastavitve)
        except Exception as e:  # noqa: BLE001
            self._korak("napaka", self._opis_napake(e))
            traceback.print_exc()
        finally:
            with self.zaklep:
                self.stanje, self.sporocilo = "miruje", ""
            self.potrditve.clear()
            try:
                self._shrani()
            except OSError:
                pass
            self._oddaj()

    def _opis_napake(self, e):
        ime = type(e).__name__
        if ime == "AuthenticationError":
            return "Ključ API ni veljaven (ANTHROPIC_API_KEY)."
        if ime == "RateLimitError":
            return "Omejitev zahtev API je dosežena; poskusi čez minuto."
        if ime in ("APIStatusError", "InternalServerError", "BadRequestError", "PermissionDeniedError", "NotFoundError"):
            return "Napaka API (%s): %s" % (getattr(e, "status_code", "?"), getattr(e, "message", str(e))[:500])
        return "%s: %s" % (ime, str(e)[:500])

    def _seja(self, mcp, sporocila):
        """Sistemska navodila in orodja pogovora. Razmišljanje modela je vezano na predpono pogovora (system, tools in vsa
        prejšnja sporočila): spremenjena navodila ali orodja sredi pogovora bi API zavrnil, zato si jih pogovor ob
        začetku zapomni (seja.json); posodobitve kataloga veljajo od naslednjega novega pogovora."""
        pot = os.path.join(MAPA_POGOVORA, "seja.json")
        if sporocila:
            try:
                with open(pot, encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, ValueError):
                pass
        k = mcp.katalog()
        seja = {"zacetek": datetime.datetime.now().isoformat(timespec="seconds"), "katalog": k.get("verzija"),
                "sistem": SISTEM + k.get("navodila", ""),
                "orodja": [{"name": o["name"], "description": o["description"], "input_schema": o["inputSchema"],
                            "eager_input_streaming": True} for o in k["orodja"]]}
        os.makedirs(MAPA_POGOVORA, exist_ok=True)
        with open(pot + ".delno", "w", encoding="utf-8") as f:
            json.dump(seja, f, ensure_ascii=False)
        os.replace(pot + ".delno", pot)
        return seja

    def _klic(self, client, sporocila, orodja, sistem, napor):
        """En klic API s pretakanjem: besedilo in povzetek razmišljanja gresta sproti v korake. Prekinjena povezava se
        ponovi do dvakrat, nerazčlenljiv JSON orodja (ValueError iz toka) se ponovi do dvakrat. Vrne končno sporočilo
        ali None, če je uporabnik ustavil."""
        import anthropic
        try:
            import httpx2
            prenos = (anthropic.APIConnectionError, httpx2.TransportError)
        except ImportError:
            prenos = (anthropic.APIConnectionError,)
        napake_json = 0
        poskus = 0
        while True:
            self.sporocilo = "Claude razmišlja …" if not poskus else "Povezava prekinjena, ponavljam …"
            tekoci = None
            try:
                with client.beta.messages.stream(
                    model=MODEL,
                    max_tokens=64000,
                    system=sistem,
                    tools=orodja,
                    messages=sporocila,
                    # drop_block: če se predpona vseeno razlikuje (pogovor iz starejše različice pomočnika), API izpusti
                    # neveljavne bloke razmišljanja namesto napake 400
                    thinking={"type": "adaptive", "display": "summarized",
                              "block_binding": {"prefix_mismatch_behavior": "drop_block"}},
                    output_config={"effort": napor},
                    cache_control={"type": "ephemeral"},
                    betas=["server-side-fallback-2026-07-01", "thinking-binding-controls-2026-08-01"],
                    fallbacks="default",
                ) as tok:
                    for dogodek in tok:
                        if self.ustavi:
                            return None
                        vrsta = getattr(getattr(dogodek, "delta", None), "type", "")
                        if dogodek.type == "content_block_start":
                            if getattr(dogodek.content_block, "type", "") == "tool_use":
                                self.sporocilo = "Pripravlja: %s …" % OPIS_ORODIJ.get(dogodek.content_block.name,
                                                                                     dogodek.content_block.name)
                            tekoci = None
                        elif dogodek.type == "content_block_delta" and vrsta in ("text_delta", "thinking_delta"):
                            kos = dogodek.delta.text if vrsta == "text_delta" else dogodek.delta.thinking
                            if not kos:
                                continue
                            korak = "besedilo" if vrsta == "text_delta" else "razmislek"
                            if tekoci is None or tekoci["vrsta"] != korak:
                                tekoci = self._korak(korak, "")
                            with self.zaklep:
                                tekoci["besedilo"] += kos
                            self.sporocilo = "Piše odgovor …" if korak == "besedilo" else "Razmišlja …"
                        elif dogodek.type == "content_block_stop":
                            tekoci = None
                    return tok.get_final_message()
            except ValueError:
                # JSON vhoda orodja, ki ga SDK ne zna razčleniti: blok ni končan, zato ni tool_use_id; ponovi klic
                napake_json += 1
                if napake_json > 2:
                    raise
                self._korak("stanje", "Neveljaven vhod orodja; ponavljam klic.")
            except prenos as e:
                poskus += 1
                if poskus > 2:
                    raise
                self._korak("stanje", "Povezava se je prekinila (%s); ponavljam." % type(e).__name__)
                time.sleep(2 + 3 * poskus)

    def _potrebuje_potrditev(self, ime, vhod, anotacije, nastavitve):
        if ime in NEVARNA or vhod.get("dovoli_pisanje") or (ime == "izhod"):
            return True
        if anotacije.get("readOnlyHint") or ime in VARNA:
            return False
        return not nastavitve.get("dovoliSpremembe")

    def _cakaj_potrditev(self, ime, vhod):
        pid = uuid.uuid4().hex[:10]
        dogodek = threading.Event()
        self.potrditve[pid] = {"dogodek": dogodek, "odgovor": None}
        korak = self._korak("potrditev", OPIS_ORODIJ.get(ime, ime), id=pid, orodje=ime,
                            argumenti=json.dumps(vhod, ensure_ascii=False, indent=1)[:6000], odgovor=None)
        self.sporocilo = "Čaka na tvojo potrditev …"
        self._shrani()
        self._oddaj()
        dogodek.wait(1800)
        odgovor = bool(self.potrditve.pop(pid, {}).get("odgovor"))
        with self.zaklep:
            korak["odgovor"] = odgovor
        return odgovor

    def _delo(self, besedilo, nastavitve):
        if not _knjiznica():
            raise RuntimeError("Knjižnica anthropic ni nameščena (%s)." % KNJIZNICE)
        import anthropic
        import mcp_orodja
        kljuc = najdi_kljuc()
        if not kljuc:
            raise RuntimeError("Ni ključa ANTHROPIC_API_KEY (okolje, %s ali .env plošče Tiskaj)."
                               % os.path.join(LOKALNO, "kljuci.env"))
        client = anthropic.Anthropic(api_key=kljuc, max_retries=3)
        napor = NAPOR.get(nastavitve.get("napor"), "medium")
        sporocila = self._sporocila()
        seja = self._seja(mcp_orodja, sporocila)
        orodja, sistem = seja["orodja"], seja["sistem"]
        anotacije = {o["name"]: o.get("annotations") or {} for o in mcp_orodja.katalog()["orodja"]}
        sheme = {t["name"]: (t["input_schema"], anotacije.get(t["name"], {})) for t in orodja}
        try:
            stanje_programa = mcp_orodja.izvedi_slovar("stanje", {}, "pomocnik")["besedilo"]
        except Exception as e:  # noqa: BLE001
            stanje_programa = "(stanja ni bilo mogoče prebrati: %s)" % e
        nov_tekst = {"type": "text", "text": "%s\n\n[Stanje FreeCAD-a ob sporočilu]\n%s" % (besedilo, stanje_programa)}
        zadnje = sporocila[-1] if sporocila else None
        if zadnje is not None and zadnje.get("role") == "assistant":
            odprti = [b.get("id") for b in zadnje.get("content") or [] if isinstance(b, dict) and b.get("type") == "tool_use"]
            if odprti:   # prekinjen krog (ustavitev, ponovni zagon): vsak klic orodja mora dobiti rezultat
                sporocila.append({"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": i, "is_error": True, "content": "Prekinjeno, orodje ni teklo."}
                    for i in odprti] + [nov_tekst]})
            else:
                sporocila.append({"role": "user", "content": [nov_tekst]})
        elif zadnje is not None and zadnje.get("role") == "user":
            # prejšnje sporočilo ni dobilo odgovora (napaka API, ustavitev): dodaj na konec istega sporočila
            vsebina = zadnje.get("content")
            zadnje["content"] = (vsebina if isinstance(vsebina, list) else [{"type": "text", "text": str(vsebina)}]) + [nov_tekst]
        else:
            sporocila.append({"role": "user", "content": [nov_tekst]})
        self._korak("uporabnik", besedilo)
        self._shrani(sporocila)
        self._oddaj()

        for _ in range(NAJVEC_KORAKOV):
            if self.ustavi:
                self._korak("stanje", "Ustavljeno.")
                break
            odgovor = self._klic(client, sporocila, orodja, sistem, napor)
            if odgovor is None:
                self._korak("stanje", "Ustavljeno.")
                break
            sporocila.append({"role": "assistant", "content": [_v_dict(b) for b in odgovor.content]})
            self._shrani(sporocila)
            if odgovor.stop_reason == "refusal":
                self._korak("napaka", "Claude je zahtevo zavrnil.")
                break
            if odgovor.stop_reason == "pause_turn":
                continue
            klici = [b for b in odgovor.content if b.type == "tool_use"]
            if not klici:
                break
            if odgovor.stop_reason == "max_tokens":
                self._korak("napaka", "Odgovor je bil predolg in je prekinjen (vhod orodja ni cel); orodja ne izvedem.")
                break
            rezultati = []
            for klic in klici:
                vhod = klic.input if isinstance(klic.input, dict) else {}
                shema, anot = sheme.get(klic.name, ({}, {}))
                napaka = _preveri_vhod(shema, klic.input) if klic.name in sheme else "neznano orodje"
                if napaka:
                    rezultati.append({"type": "tool_result", "tool_use_id": klic.id, "is_error": True,
                                      "content": json.dumps({"INVALID_JSON": json.dumps(klic.input, ensure_ascii=False),
                                                             "napaka": napaka}, ensure_ascii=False)})
                    self._korak("napaka", "Neveljaven vhod orodja %s: %s" % (klic.name, napaka))
                    continue
                if self.ustavi:
                    rezultati.append({"type": "tool_result", "tool_use_id": klic.id, "is_error": True,
                                      "content": "Uporabnik je ustavil pomočnika."})
                    continue
                if self._potrebuje_potrditev(klic.name, vhod, anot, nastavitve) and \
                        not self._cakaj_potrditev(klic.name, vhod):
                    rezultati.append({"type": "tool_result", "tool_use_id": klic.id, "is_error": True,
                                      "content": "Uporabnik tega klica ni dovolil. Ne ponavljaj ga; vprašaj, kaj želi."})
                    continue
                self.sporocilo = "%s …" % OPIS_ORODIJ.get(klic.name, klic.name)
                zacetek = time.time()
                try:
                    izid = mcp_orodja.izvedi_slovar(klic.name, vhod, "pomocnik")
                except Exception:  # noqa: BLE001
                    izid = {"napaka": True, "besedilo": traceback.format_exc(limit=4), "slike": []}
                vsebina, slike = [], []
                for mime, bajti in izid.get("slike") or []:
                    sid = uuid.uuid4().hex[:12] + (".jpg" if "jpeg" in mime else ".png")
                    with open(os.path.join(MAPA_POGOVORA, "slike", sid), "wb") as f:
                        f.write(bajti)
                    slike.append(sid)
                    vsebina.append({"type": "image", "source": {"type": "base64", "media_type": mime,
                                                                "data": base64.standard_b64encode(bajti).decode("ascii")}})
                besedilo_izida = izid.get("besedilo") or "Opravljeno."
                vsebina.append({"type": "text", "text": besedilo_izida[-30000:]})
                self._korak("orodje", OPIS_ORODIJ.get(klic.name, klic.name), orodje=klic.name,
                            argumenti=json.dumps(vhod, ensure_ascii=False, indent=1)[:6000],
                            izid=besedilo_izida[:4000], slike=slike, napaka=bool(izid.get("napaka")),
                            trajanje=round(time.time() - zacetek, 1))
                rezultati.append({"type": "tool_result", "tool_use_id": klic.id, "content": vsebina,
                                  "is_error": bool(izid.get("napaka"))})
                self._shrani()
            sporocila.append({"role": "user", "content": rezultati})
            self._shrani(sporocila)
        else:
            self._korak("napaka", "Preveč korakov v enem odgovoru (%d); ustavljeno." % NAJVEC_KORAKOV)


# ---------------------------------------------------------------------------------------------------------------
# Končne točke (nit strežnika)

def zahteva_get(S, pot, poizvedba):
    """GET /pomocnik?od=N, GET /pomocnik/slika?id=. Vrne (koda, vrsta, bajti)."""
    p = dobi(S)
    if pot == "/pomocnik/slika":
        sid = os.path.basename(str(poizvedba.get("id", "")))
        if not re.match(r"^[0-9a-f]{12}\.(jpg|png)$", sid):
            return 404, "text/plain", b""
        try:
            with open(os.path.join(MAPA_POGOVORA, "slike", sid), "rb") as f:
                return 200, "image/jpeg" if sid.endswith(".jpg") else "image/png", f.read()
        except OSError:
            return 404, "text/plain", b""
    return 200, "application/json; charset=utf-8", json.dumps(p.stanje_od(poizvedba.get("od", 0)),
                                                                ensure_ascii=False).encode("utf-8")


def zahteva_post(S, podatki):
    """POST /pomocnik {dejanje: poslji (besedilo, nastavitve) | potrdi (id, odobri) | ustavi | nov}."""
    p = dobi(S)
    dejanje = podatki.get("dejanje")
    if dejanje == "poslji":
        return p.poslji(podatki.get("besedilo", ""), podatki.get("nastavitve") or {})
    if dejanje == "potrdi":
        return p.potrdi(str(podatki.get("id", "")), podatki.get("odobri"))
    if dejanje == "ustavi":
        return p.ustavi_delo()
    if dejanje == "nov":
        return p.nov()
    return {"ok": False, "sporocilo": "Neznano dejanje."}


_UVOZ = []


def _knjiznica_obstaja():
    """Za stran (nit strežnika): ali je knjižnica nameščena, brez uvoza. Prvi uvoz (pydantic, httpx2 ...) v velikem
    primerku traja do minute, zato ga ob prvem odprtju plošče začne nit v ozadju, ne zahteva strani."""
    if "anthropic" in sys.modules:
        return True
    mape = (KNJIZNICE, os.path.join(os.path.expanduser("~"), "AppData", "Local", "FreeCAD-splet", "python-freecad"))
    obstaja = any(os.path.isdir(os.path.join(m, "anthropic")) for m in mape)
    if obstaja and not _UVOZ:
        _UVOZ.append(threading.Thread(target=_knjiznica, daemon=True, name="pomocnik-uvoz"))
        _UVOZ[0].start()
    return obstaja
