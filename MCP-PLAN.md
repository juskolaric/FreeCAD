# Master plan: spletni FreeCAD kot MCP strežnik (AI z dostopom do vseh funkcij)

Pripravljeno in izvedeno 2026-10-10 (koraki 1–6; glej Stanje). Izhodišče: spletni FreeCAD (`lastno/splet`, vrata 3020) že zna vse, kar AI potrebuje — izvaja Python
na glavni niti (`/python`, `izvedi.py`), sproži vseh 198 ukazov okolij, pozna drevo, izbiro, skice, obrazce, bazo
standardnih delov, videz, tiskanje, render in oblak. Claude Code (pa tudi Claude Desktop in Cursor) pa do tega pride le
obvozno: seja mora vedeti za `izvedi.py`, brati `CLAUDE.md` in ugibati imena funkcij. Zgled, ki ga že imamo in deluje:
`simplyprint-mcp` (Python brez odvisnosti, stdio, 30 orodij, registriran za vse projekte).

**Cilj.** Vsaka seja Claude Code (tudi v drugi mapi, npr. ob modelih v Oblaku) ima orodja `mcp__freecad__*`, s katerimi
vidi stanje programa in model (slika, drevo, mere), požene **katero koli** funkcijo (Python, ukaz okolja, spletna končna
točka, obrazec) in **sama najde, kaj obstaja** (iskanje ukazov, FreeCAD API-ja in naših modulov). Brez branja izvorne
kode, brez obvozov, z varovalkami pri shranjevanju, brisanju, tisku in izhodu.

## Načelo: malo močnih orodij in iskanje, ne 250 tankih orodij

Vsako orodje stane kontekst v vsaki seji (~150 žetonov na opis; 250 orodij = ~40.000 žetonov, preden AI kaj naredi).
Anthropicove smernice za agente: širina prek izvajanja kode, namensko orodje le tam, kjer je treba vratariti, stisniti,
izmeriti ali vrniti sliko. Zato tri plasti:

1. **Vse funkcije** skozi štiri široka orodja: `python` (celoten FreeCAD API, vsi moduli strežnika: drevo, baza, videz,
   oblak, elektro, pločevina), `ukaz` (vseh 198 ukazov okolij in dodatkov, tudi tisti le iz menijev), `splet` (vsaka
   končna točka strežnika: skica, drevo, videz, knjižnica, standardni, oblak, tiskaj, render, oblikovanje) in `obrazec`
   (vsako FreeCAD-ovo okno, ki ga strežnik že izrisuje v brskalniku: prebere, vpiše, potrdi).
2. **Odkrivanje** namesto pomnjenja: `isci` po ključni besedi najde ukaze (ime, naslov, namig), funkcije FreeCAD API-ja
   (docstringi modulov Part, PartDesign, Sketcher, Assembly …), funkcije naših modulov in skripte projektov (`Skripte/`,
   `PREBERI.txt`); viri (resources) nosijo pravila iz `CLAUDE.md` (nit strežnika, pasti skic, pločevina, brez Boolovih
   zank, povezave in vsebniki) in katalog oblik JSON za `splet`.
3. **Namenska orodja** le z razlogom: `stanje`, `dokumenti`, `drevo`, `izberi`, `slika`, `izmeri`, `razveljavi`, `shrani`,
   `natisni`, `render`, `zazeni`, `izhod` — ker jih je treba vratariti (shranjevanje, zapiranje, brisanje, tisk, izhod),
   stisniti (drevo kot zamaknjeno besedilo brez ikon in geometrije) ali vrniti kot sliko (AI model **vidi**).

Narejeno: 21 orodij (19 v strežniku, `zazeni` in `freecadcmd` v mostu). Opisi so skupaj ~7.000 žetonov (slovenščina se
razreže na več žetonov, kot je bilo ocenjeno); Claude Code sheme orodij MCP nalaga po potrebi. ~1.000 ukazov, API in
naši moduli ostanejo zunaj konteksta, dokler jih AI ne poišče.

## Zgradba

- **Možgani v FreeCAD-u**: modul `lastno/splet/mcp_orodja.py` s katalogom orodij (ime, opis, shema, funkcija, oznaka
  samo-branje / uničujoče). Strežnik dobi `GET /mcp/orodja` (katalog) in `POST /mcp/orodje {ime, argumenti}` (z žetonom,
  izvedba na glavni niti prek vrste kot `/python`). Novo orodje = ena funkcija v tem modulu, vroče zamenljiva brez
  ponovnega zagona; katalog se ob zagonu zapiše še v `%LOCALAPPDATA%/FreeCAD-splet/mcp-orodja.json`.
- **Most** `lastno/mcp/freecad_mcp.py`: stdio MCP strežnik brez odvisnosti (sistemski Python 3.11 ali pixi, po vzoru
  simplyprint), ki orodja prevede v klice na 3020 (vrata in žeton iz `povezava.json`). FreeCAD-a ne pozna; ko ta ne teče,
  ponudi `zazeni` (požene `ZAZENI-SPLET.bat`) in zadnji znani katalog. Registracija enkrat za vse projekte:
  `claude mcp add --scope user freecad -- python .../lastno/mcp/freecad_mcp.py`; isti most tudi za Claude Desktop in Cursor.
- Isti katalog bo pozneje služil **pomočniku v brskalniku** (Claude API z zanko orodij, Oblikovanje korak 3) in
  Oblikovanju (Blender na 3030 dobi enako zgradbo: katalog v strežniku, most ga le prevaja).

## Stanje (2026-10-10)

Koraki 1–5 so narejeni in preverjeni na preizkusnem primerku (vrata 3031) in na tekočem strežniku (3020, vroča
zamenjava `lastno/mcp/namesti_v_tekoci.py`, brez ponovnega zagona). Most je registriran za vse projekte (`claude mcp
add --scope user freecad`); nova seja Claude Code (`claude -p`) je z orodji prebrala stanje in s slike opisala aktivni kos.
Preizkus protokola: `lastno/mcp/preizkus_protokola.py` (initialize, orodja, klici, slika, viri, predloge). Korak 6:
Oblikovanje (`oblikovanje`: Python in slika v Blenderju), rezerva `freecadcmd` in pomočnik v brskalniku
(`lastno/splet/pomocnik.py`, gumb ✦ Pomočnik) so narejeni.
Uporabnik naj zavihek spletnega FreeCAD-a enkrat osveži (F5), da `slika` riše prek strani (sicer preprost izris iz mreže).
Za namizno aplikacijo Claude je razširitev `lastno/mcp/freecad.mcpb` (preverjena z `mcpb validate`), za znanje o
upravljanju skill `freecad` (Claude Code: `~/.claude/skills/freecad`, preverjeno z novo sejo; aplikacija: zip za nalaganje).

## Koraki (vsak preverljiv posebej)

1. [x] 2026-10-10 **Jedro**: katalog, most in orodja `stanje`, `dokumenti`, `drevo`, `python`, `slika`, `zazeni`. Slika: strežnik prek SSE
   prosi stran v brskalniku za izris pogleda (kot sličice dokumentov), brez odprtega brskalnika rezerva `lastno/slika_stl.py`
   (numpy iz mreže posnetka). Preverba: nova seja Claude Code vidi orodja, naredi kocko s posnetim robom in jo opiše s slike.
   Preverjeno: kocka s posnetjem in zaokrožitvijo (python, ukaz, obrazec), slika iz brskalnika in rezervna, zagon in izhod.
2. [x] 2026-10-10 **Odkrivanje**: `isci` (ukazi, API, moduli, skripte), `ukaz`, `obrazec`, viri s pravili, predloge (prompts) za pogoste
   naloge: nov kos iz skice, pločevina, sestav s spoji, kos v bazo, napeljava kablov. Preverba: AI brez branja kode najde in
   izvede »Make Wall« iz Pločevine in izpolni njegov obrazec. Preverjeno: isci → SheetMetal_AddWall, izbira roba, obrazec
   (dolžina 25 mm, Material Inside), potrdi, izmeri in slika upognjene stene.
3. [x] 2026-10-10 **Merjenje in varovalke**: `izmeri` (okvir, prostornina, masa, razdalja med kosi, trk prek `distToShape` — brez Boolovih
   zank), `razveljavi`, vsak `python` v transakciji (Razveljavi dela), `shrani` edino piše na disk; koda s `save`, `close`,
   `restore`, brisanjem ali premikanjem datotek in `quit` brez `dovoli_pisanje` se zavrne (`removeObject` je dovoljen, ker
   ga transakcija razveljavi); napaka v kodi razveljavi cel klic; uničujoča orodja nosijo `destructiveHint`.
4. [x] 2026-10-10 **Vse ostalo**: `splet` (prehod na vse končne točke s katalogom oblik), `natisni` (vedno okno Pripravi), `render` (slika
   nazaj v pogovor), knjižnica, baza, oblak; odgovori omejeni (60.000 znakov, strani), dolgi posli (`cakaj`, nadaljevanje
   po id-ju, `opravilo` za stanje). Preverjeno: render osnutka (7 s), natisni (plošča datoteke ni narezala sama).
5. [x] 2026-10-10 **Več sej hkrati in dnevnik**: oznaka seje v vsakem klicu in v dnevniku strežnika, `dnevnik` (rep dnevnika z napakami),
   vroča zamenjava kataloga z obvestilom mostu, zapis načina dela v `CLAUDE.md` (seje naj uporabljajo orodja, ne `izvedi.py`).
6. [x] 2026-10-10 Orodja za Oblikovanje (Blender) in FreeCADCmd brez strežnika kot rezerva. **Pomočnik v brskalniku**:
   stranska plošča desno od pogleda, zanka Claude (claude-opus-5-5, prilagodljivo razmišljanje, napor po izbiri) teče v
   niti strežnika nad istim katalogom; ključ ostane na strežniku (okolje, kljuci.env ali .env plošče Tiskaj), knjižnica
   anthropic v `%LOCALAPPDATA%/FreeCAD-splet/python-freecad`. Spremembe modela vprašajo (razen s kljukico), shrani, izhod
   in splet vedno. Pogovor samo z dodajanjem; navodila in orodja se zapomnijo ob začetku pogovora (seja.json), ker API
   razmišljanje veže na predpono, in vsak klic nastavi `drop_block` za pogovore iz starejše različice. Preverjeno na
   3031: dodaj kvader (potrditev, meritev, slika, odgovor), zavrnitev, Ustavi, nadaljevanje po ustavitvi, Nov pogovor.

## Odločitve (sprejete z naročilom »Izvedi ta plan«, 2026-10-10)

- Most kot ločen proces prek stdio, ne MCP po HTTP znotraj strežnika: Claude ga zažene sam, FreeCAD ni vezan na sejo,
  več sej si deli en FreeCAD (strežnik klice že vrsti na glavno nit), sesutje mostu ne podre FreeCAD-a, brez novih vrat.
- Imena in opisi orodij slovenski, kot končne točke in koda strežnika; angleška imena le pri ukazih FreeCAD-a.
- AI nikoli ne shrani, ne zapre brez shranjevanja, ne briše, ne tiska in ne konča programa brez namenskega orodja z
  izrecno potrditvijo; `python` tega ne sme obiti (korak 3).
- Geometrija (posnetek 1,5 MB) nikoli v odgovor orodja: AI vidi sliko, drevo in mere, ne trikotnikov.

## Tehnično (na kratko)

- MCP: JSON-RPC 2.0 po vrsticah na stdin/stdout; `initialize` (protocolVersion 2025-06-18), `tools/list`, `tools/call`
  (`content` besedilo in `image` png/jpeg base64, `isError`, `structuredContent`), `resources/list|read`,
  `prompts/list|get`, `notifications/tools/list_changed` ob vroči zamenjavi kataloga; `annotations {readOnlyHint,
  destructiveHint, idempotentHint}` na orodjih. Paket `mcp` ni nameščen in ni potreben (standardna knjižnica).
- Katalog: dekorator `@orodje(ime, opis, shema, samo_branje, unicujoce)` v `mcp_orodja.py`; funkcija dobi `argumenti` in
  vrne `dict` (besedilo, slike, podatki); napake kot `isError` s kratkim zadnjim stavkom sledi (kot `/knjiznica`).
- Drevo kot besedilo: `- Telo (PartDesign::Body) [viden] 125 cm³` z zamikom, globina in iskanje kot v `drevo.py`.
- Slika: dogodek SSE `mcp {id, zahteva: slika, smer, velikost, objekti, dokument}` → stran izriše (isti izris kot
  sličice, `izrisiIzometrijo` s smerjo; drug dokument prek `/posnetek`) → `POST /mcp/odgovor`; velja prvi odgovor, skriti
  zavihki počakajo 1,5 s. Stran ob vsaki povezavi SSE pošlje `zdravo`; brez njega strežnik ne čaka in riše rezervno
  (numpy + Pillow, slikarjev algoritem z delitvijo velikih trikotnikov). Privzeto 800 px JPEG.
- Preizkus iz ukazne vrstice kot pri simplyprint: `python freecad_mcp.py test | tools | call <orodje> [json]`.
- Vrata ostanejo 3020 (`Photolandia-Apps/ports.json` nespremenjen); most nima vrat.
