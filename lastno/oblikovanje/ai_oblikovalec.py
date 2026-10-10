# -*- coding: utf-8 -*-
"""AI oblikovalec v Oblikovanju: Claude (Anthropic API) gradi oblike v Blenderju, jih pogleda in popravi.

Zanka teče v svoji niti procesa Blenderja; orodja (bpy) se izvedejo na glavni niti prek `na_glavni(fn)` iz strežnika.
Orodja: nastavi_obliko (parametrična oblika z drsniki), izvedi_kodo (prost bpy), poglej (4 pogledi kot slika),
preberi_obliko. Pogovor je po idejah (pogovor.json, samo dodajanje: bloki odgovora se vrnejo nespremenjeni, sicer
razmišljanje ne velja več), koraki za stran so v prikaz.json.

Ključ: ANTHROPIC_API_KEY iz okolja, sicer %LOCALAPPDATA%/FreeCAD-splet/kljuci.env, sicer .env plošče Tiskaj
(3D print/tiskaj ali 3D tisk/3D print/tiskaj). Ključ se nikoli ne izpiše.
Knjižnica anthropic je nameščena za Python Blenderja v %LOCALAPPDATA%/FreeCAD-splet/python-blender (pip --target).
"""

import base64
import datetime
import json
import os
import sys
import threading
import time
import traceback

LOKALNO = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "FreeCAD-splet")
KNJIZNICE = os.path.join(LOKALNO, "python-blender")
if os.path.isdir(KNJIZNICE) and KNJIZNICE not in sys.path:
    sys.path.append(KNJIZNICE)

MODEL = "claude-opus-5-5"
NAJVEC_KORAKOV = 30          # klicev API v enem odgovoru
MAPA = os.path.dirname(os.path.abspath(__file__))

SISTEM = """Si oblikovalec prostih, organskih 3D oblik v programu Oblikovanje (Blender 5.2 v ozadju, Python bpy).
Uporabnik je izdelovalec, ki oblike nato tiska na 3D tiskalniku ali jih prenese v FreeCAD za tehnično dodelavo.
Tvoja naloga: iz ideje uporabnika zgradi lepo, smiselno obliko, jo poglej in popravljaj, dokler ni dobra.

Okolje:
- Enote so milimetri (1 enota Blenderja = 1 mm), os Z gleda gor, tla so pri Z = 0, model naj stoji na tleh in bo
  okvirno centriran okoli osi Z. Izberi realne mere (ročaj ~110-130 mm, skodelica ~80 mm ...).
- V kodi so na voljo: bpy, bmesh, np (numpy), math, Vector, Matrix, C (bpy.context), D (bpy.data) in pomočniki:
  dodaj_obliko(vrsta, velikost=40, lega=(0,0,0), ime=None) – vrsta: kocka (gladka kletka s SubD), krogla, valj, torus, stozec, kaplja
  gladko(obj, nivo=2, nivo_render=3) – Subdivision Surface + gladko senčenje
  material(ime, barva=(r,g,b) v sRGB 0..1, kovinskost=0, hrapavost=0.4) – Principled BSDF; dodaj z obj.data.materials.append(...)
  nov_objekt(ime, mreza_ali_krivulja) – poveže nov objekt v sceno
- Dobre tehnike za organske oblike: kletka iz bmesh (malo ploskev, štirikotniki) + Subdivision Surface; zrcaljenje
  (Mirror modifikator) za simetrijo; Solidify za debelino sten; metaball za zlivajoče se gmote; krivulje z bevel_depth
  za cevi in ročaje; Remesh (voxel) + Smooth Corrective za zlitje več teles v eno; Displace s teksturo za relief.
- Za 3D tisk: zaprta telesa, stene vsaj 1,5 mm, brez lebdečih delov, ravno dno, kadar ima smisel.

Delo:
1. Obliko zgradi z orodjem nastavi_obliko: koda definira funkcijo zgradi(p), ki iz nič zgradi vse objekte oblike
   (vsakič znova; prejšnji objekti oblike se pred klicem samodejno odstranijo). Parametri so drsniki, s katerimi bo
   uporabnik obliko oblikoval sam: izberi 3-8 smiselnih (dolžina, debelina, zaobljenost, zasuk, število reber ...),
   s slovenskimi oznakami, enoto mm ali °, in razumnimi mejami (oblika naj bo lepa v celotnem razponu).
2. Po vsaki večji spremembi uporabi poglej in kritično oceni proporce, gladkost, napake (preboji, zvite ploskve,
   lebdeči deli). Popravi in poglej znova; običajno zadostujejo 2-4 pogledi.
3. izvedi_kodo uporabi za preverjanja ali enkratne posege; trajne spremembe oblike naj gredo v nastavi_obliko.
4. Ko je oblika dobra, odgovori kratko v slovenščini (2-4 stavki): kaj si naredil, katere drsnike ima, in en ali dva
   predloga za naslednji korak. Ne piši kode v odgovor.
Ne briši objektov, ki niso del oblike, razen če uporabnik to izrecno želi.
Uporabnik je Slovenec: razmišljaj, piši odgovore in kratka pojasnila med koraki v slovenščini."""

ORODJA = [
    {
        "name": "nastavi_obliko",
        "description": "Nastavi parametrično obliko in jo zgradi. Koda mora definirati def zgradi(p): (p je slovar ime -> vrednost) "
                       "in iz nič zgraditi vse objekte oblike. Vrne povzetek scene (objekti, mere v mm) ali napako s sledjo.",
        "strict": True,
        "eager_input_streaming": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "koda": {"type": "string", "description": "Python koda z def zgradi(p)."},
                "parametri": {
                    "type": "array",
                    "description": "Drsniki oblike.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "ime": {"type": "string", "description": "Pythonovo ime ključa v p, npr. dolzina"},
                            "oznaka": {"type": "string", "description": "Slovenska oznaka drsnika, npr. Dolžina"},
                            "vrednost": {"type": "number"},
                            "min": {"type": "number"},
                            "max": {"type": "number"},
                            "korak": {"type": "number"},
                            "enota": {"type": "string", "description": "mm, ° ali prazno"},
                        },
                        "required": ["ime", "oznaka", "vrednost", "min", "max", "korak", "enota"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["koda", "parametri"],
            "additionalProperties": False,
        },
    },
    {
        "name": "izvedi_kodo",
        "description": "Izvede poljubno Python kodo (bpy) v sceni. Izpis print() in spremenljivka rezultat se vrneta, "
                       "zraven povzetek scene.",
        "strict": True,
        "eager_input_streaming": True,
        "input_schema": {
            "type": "object",
            "properties": {"koda": {"type": "string"}},
            "required": ["koda"],
            "additionalProperties": False,
        },
    },
    {
        "name": "poglej",
        "description": "Izriše trenutno sceno v štirih pogledih (izometrija, spredaj, desno, zgoraj; pravokotna projekcija, "
                       "studio luč, robovi) in vrne sliko 2 × 2 ter povzetek mer.",
        "strict": True,
        "input_schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    },
    {
        "name": "preberi_obliko",
        "description": "Vrne trenutno kodo parametrične oblike in vrednosti drsnikov (uporabnik jih je morda premaknil "
                       "ali odprl drugo različico).",
        "strict": True,
        "input_schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    },
]


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


def _preveri_vhod(ime, vhod):
    """Vhod orodja po pretakanju (eager_input_streaming) ni preverjen na strežniku: preveri ga tu."""
    if not isinstance(vhod, dict):
        return "vhod ni objekt"
    if ime in ("nastavi_obliko", "izvedi_kodo") and not isinstance(vhod.get("koda"), str):
        return "manjka koda (niz)"
    if ime == "nastavi_obliko":
        par = vhod.get("parametri")
        if not isinstance(par, list):
            return "parametri morajo biti seznam"
        for p in par:
            if not isinstance(p, dict) or not isinstance(p.get("ime"), str):
                return "vsak parameter potrebuje ime"
            for k in ("vrednost", "min", "max", "korak"):
                if not isinstance(p.get(k), (int, float)):
                    return "parameter %s: %s mora biti število" % (p.get("ime"), k)
    return ""


def _v_dict(blok):
    return blok.to_dict() if hasattr(blok, "to_dict") else dict(blok)


class AIOblikovalec:
    def __init__(self, na_glavni):
        self.na_glavni = na_glavni          # fn(callable, cas) -> rezultat; izvede na glavni niti Blenderja
        self.zaklep = threading.Lock()
        self.nit = None
        self.ustavi = False
        self.mapa = ""                      # mapa ideje, ki ji pripada pogovor
        self.koraki = []                    # prikaz za stran
        self.stanje = "miruje"              # miruje | dela
        self.sporocilo = ""

    # -- shranjevanje --
    def _pot(self, ime):
        return os.path.join(self.mapa, ime)

    def nalozi(self, mapa):
        with self.zaklep:
            if self.stanje == "dela":
                return
            self.mapa = mapa or ""
            self.koraki = []
            if self.mapa:
                try:
                    with open(self._pot("prikaz.json"), encoding="utf-8") as f:
                        self.koraki = json.load(f)
                except (OSError, ValueError):
                    self.koraki = []

    def _sporocila(self):
        try:
            with open(self._pot("pogovor.json"), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return []

    def _shrani(self, sporocila=None):
        if not self.mapa:
            return
        if sporocila is not None:
            zac = self._pot("pogovor.json.delno")
            with open(zac, "w", encoding="utf-8") as f:
                json.dump(sporocila, f, ensure_ascii=False)
            os.replace(zac, self._pot("pogovor.json"))
        with open(self._pot("prikaz.json"), "w", encoding="utf-8") as f:
            json.dump(self.koraki, f, ensure_ascii=False)

    def _korak(self, vrsta, besedilo="", **dodatno):
        with self.zaklep:
            k = {"i": len(self.koraki), "vrsta": vrsta, "besedilo": besedilo,
                 "cas": datetime.datetime.now().strftime("%H:%M:%S"), **dodatno}
            self.koraki.append(k)
            return k

    def stanje_od(self, od=0):
        with self.zaklep:
            return {"stanje": self.stanje, "sporocilo": self.sporocilo, "koraki": self.koraki[od:],
                    "skupaj": len(self.koraki), "kljuc": bool(najdi_kljuc())}

    # -- zagon --
    def poslji(self, besedilo, slike, kontekst):
        """kontekst: dict z 'mapa' (ideja), 'povzetek' (fn), 'orodja' (dict ime -> fn(vhod) -> (besedilo, slika_pot|None)),
        'konec' (fn(opomba) na koncu odgovora: shrani različico)."""
        with self.zaklep:
            if self.stanje == "dela":
                raise RuntimeError("Claude še dela na prejšnjem sporočilu.")
            self.stanje, self.sporocilo, self.ustavi = "dela", "Pošiljam …", False
        self.mapa = kontekst["mapa"]
        self.nit = threading.Thread(target=self._zanka, args=(besedilo, slike, kontekst), daemon=True, name="ai")
        self.nit.start()

    def prekini(self):
        self.ustavi = True

    def _zanka(self, besedilo, slike, kontekst):
        try:
            self._delo(besedilo, slike, kontekst)
        except Exception as e:  # noqa: BLE001
            self._korak("napaka", "%s: %s" % (type(e).__name__, e))
            traceback.print_exc()
        finally:
            with self.zaklep:
                self.stanje, self.sporocilo = "miruje", ""
            self._shrani()

    def _klic(self, client, sporocila):
        """En klic API s pretakanjem: besedilo in povzetek razmišljanja gresta sproti na stran. Prekinjena povezava
        (dolgo razmišljanje, omrežje) se ponovi do dvakrat. Vrne končno sporočilo ali None, če je uporabnik ustavil."""
        import anthropic
        import httpx2
        for poskus in range(3):
            self.sporocilo = "Claude razmišlja …" if not poskus else "Povezava prekinjena, ponavljam …"
            tekoci = None
            try:
                with client.beta.messages.stream(
                    model=MODEL,
                    max_tokens=64000,
                    system=SISTEM,
                    tools=ORODJA,
                    messages=sporocila,
                    thinking={"type": "adaptive", "display": "summarized"},
                    output_config={"effort": "medium"},
                    cache_control={"type": "ephemeral"},
                    betas=["server-side-fallback-2026-07-01"],
                    fallbacks="default",
                ) as tok:
                    for dogodek in tok:
                        if self.ustavi:
                            return None
                        vrsta = getattr(getattr(dogodek, "delta", None), "type", "")
                        if dogodek.type == "content_block_start":
                            blok = getattr(dogodek.content_block, "type", "")
                            if blok == "tool_use":
                                self.sporocilo = {"nastavi_obliko": "Piše kodo oblike …", "izvedi_kodo": "Piše kodo …",
                                                  "poglej": "Bo pogledal obliko …"}.get(dogodek.content_block.name, "Pripravlja orodje …")
                            tekoci = None
                        elif dogodek.type == "content_block_delta" and vrsta in ("text_delta", "thinking_delta"):
                            del_besedila = dogodek.delta.text if vrsta == "text_delta" else dogodek.delta.thinking
                            if not del_besedila:
                                continue
                            korak = "besedilo" if vrsta == "text_delta" else "razmislek"
                            if tekoci is None or tekoci["vrsta"] != korak:
                                tekoci = self._korak(korak, "")
                            with self.zaklep:
                                tekoci["besedilo"] += del_besedila
                            self.sporocilo = "Piše odgovor …" if korak == "besedilo" else "Razmišlja …"
                        elif dogodek.type == "content_block_stop":
                            tekoci = None
                    return tok.get_final_message()
            except (anthropic.APIConnectionError, httpx2.TransportError) as e:
                if poskus == 2:
                    raise
                self._korak("stanje", "Povezava se je prekinila (%s); ponavljam." % type(e).__name__)
                time.sleep(2 + 3 * poskus)
        return None

    def _delo(self, besedilo, slike, kontekst):
        import anthropic

        kljuc = najdi_kljuc()
        if not kljuc:
            raise RuntimeError("Ni ključa ANTHROPIC_API_KEY (okolje, %s ali .env plošče Tiskaj)." % os.path.join(LOKALNO, "kljuci.env"))
        client = anthropic.Anthropic(api_key=kljuc, max_retries=3)
        sporocila = self._sporocila()
        vsebina = []
        for i, s in enumerate(slike or []):
            glava, _, podatki = s.partition(",")
            vrsta = glava.split(";")[0].split(":")[-1] or "image/png"
            vsebina.append({"type": "image", "source": {"type": "base64", "media_type": vrsta, "data": podatki}})
        stanje_scene = self.na_glavni(kontekst["povzetek"], 30)
        vsebina.append({"type": "text", "text": "%s\n\n[Trenutno stanje scene]\n%s" % (besedilo, stanje_scene)})
        sporocila.append({"role": "user", "content": vsebina})
        self._korak("uporabnik", besedilo, slik=len(slike or []))
        self._shrani(sporocila)
        spremenjeno = False

        for _ in range(NAJVEC_KORAKOV):
            if self.ustavi:
                self._korak("stanje", "Ustavljeno.")
                break
            odgovor = self._klic(client, sporocila)
            if odgovor is None:
                self._korak("stanje", "Ustavljeno.")
                break
            sporocila.append({"role": "assistant", "content": [_v_dict(b) for b in odgovor.content]})
            self._shrani(sporocila)

            if odgovor.stop_reason == "refusal":
                self._korak("napaka", "Claude je zahtevo zavrnil.")
                break
            if odgovor.stop_reason == "max_tokens":
                self._korak("napaka", "Odgovor je bil predolg in je prekinjen.")
                break
            if odgovor.stop_reason == "pause_turn":
                continue
            klici = [b for b in odgovor.content if b.type == "tool_use"]
            if not klici:
                break
            rezultati = []
            for klic in klici:
                vhod = klic.input if isinstance(klic.input, dict) else {}
                napaka = _preveri_vhod(klic.name, vhod)
                if napaka:
                    rezultati.append({"type": "tool_result", "tool_use_id": klic.id, "is_error": True,
                                      "content": "Neveljaven vhod: " + napaka})
                    continue
                fn = kontekst["orodja"].get(klic.name)
                if fn is None:
                    rezultati.append({"type": "tool_result", "tool_use_id": klic.id, "is_error": True, "content": "Neznano orodje."})
                    continue
                self.sporocilo = {"nastavi_obliko": "Gradim obliko …", "izvedi_kodo": "Izvajam kodo …",
                                  "poglej": "Gledam obliko …", "preberi_obliko": "Berem obliko …"}.get(klic.name, klic.name)
                zacetek = time.time()
                try:
                    izid, slika = self.na_glavni(lambda fn=fn, vhod=vhod: fn(vhod), 300)
                    ok = True
                except Exception:  # noqa: BLE001
                    izid, slika, ok = traceback.format_exc(limit=6), None, False
                if klic.name in ("nastavi_obliko", "izvedi_kodo") and ok:
                    spremenjeno = True
                opis = {"nastavi_obliko": "Zgradil obliko", "izvedi_kodo": "Izvedel kodo", "poglej": "Pogledal obliko",
                        "preberi_obliko": "Prebral obliko"}.get(klic.name, klic.name)
                self._korak("pogled" if klic.name == "poglej" else ("koda" if ok else "napaka"),
                            opis if ok else "Napaka pri orodju %s" % klic.name,
                            koda=vhod.get("koda", ""), izid=izid[-4000:], parametri=vhod.get("parametri"),
                            slika=os.path.basename(slika) if slika else "", trajanje=round(time.time() - zacetek, 1))
                vsebina = [{"type": "text", "text": izid[-12000:]}]
                if slika:
                    with open(slika, "rb") as f:
                        vsebina.insert(0, {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                                       "data": base64.standard_b64encode(f.read()).decode("ascii")}})
                rezultati.append({"type": "tool_result", "tool_use_id": klic.id, "content": vsebina, "is_error": not ok})
            sporocila.append({"role": "user", "content": rezultati})
            self._shrani(sporocila)
        else:
            self._korak("napaka", "Preveč korakov v enem odgovoru; ustavljeno.")
        if spremenjeno:
            rid = self.na_glavni(lambda: kontekst["konec"](besedilo), 60)
            if rid:
                self._korak("razlicica", "Shranjeno kot različica %s" % rid, razlicica=rid)
