# Predaja projekta: lastna kopija FreeCAD-a z vmesnikom v brskalniku

Stanje: **11. oktober 2026** (prva različica 29. 9. 2026). Lastnik: Jus Kolarič (GitHub `juskolaric`). Napisano za
človeka (in njegov Claude Code ali Codex), ki prevzame delo. Vse, kar je tu, je preverjeno na Windows 11.

**Vrstni red branja:** ta dokument → `CLAUDE.md` (podrobna pravila in pasti po področjih, vir resnice za vse
podrobnosti; `AGENTS.md` je ista vsebina za Codex) → `PLAN.md` in ločeni plani (`PDM-PLAN.md`, `TISKANJE-PLAN.md`,
`OBLIKOVANJE-PLAN.md`, `MCP-PLAN.md`) → odprte naloge v `Apps/TODO.md`, razdelek »FreeCAD«.

---

## 1. Kaj je to in kam gre

- **Lastna kopija FreeCAD-a** (fork uradnega repozitorija), osnova uradna veja `releases/FreeCAD-1-1` (1.1.4).
  Program se prevede na računalniku s pixi.
- **Smer od 29. 9. 2026:** FreeCAD je samo motor (geometrija, reševalnik, ukazi, datoteke). **Uporabnik dela
  izključno v brskalniku** (http://127.0.0.1:3020/, three.js z WebGPU). Okno FreeCAD-a je skrito in se samo od sebe
  nikoli ne pokaže; vsa njegova okna (pogovori, nastavitve ukazov, izbira datotek) se izrišejo kot obrazci v brskalniku.
- Delo v brskalniku poteka v **treh stopnjah** (levo v glavi strani): **1 Oblikovanje** (proste oblike v Blenderju)
  → **2 Strojno risanje** (FreeCAD) → **3 Tiskanje** (plošča Tiskaj za tiskalnik Bambu Lab P2S). Vse tri so ena stran
  z enako podobo.
- **AI je del orodja:** seje Claude Code imajo orodja `mcp__freecad__*` (isti primerek, ki ga gleda uporabnik), v
  brskalniku je Pomočnik (✦), v Oblikovanju AI oblikovalec.
- Uporabnik je konstruktor (prej SolidWorks): pričakuje vodenje pogleda, izraze in potek dela kot v SolidWorksu.

## 2. Kaj že deluje (11. 10. 2026)

| Področje | Kaj zna |
|---|---|
| 3D pogled | Vodenje kot SolidWorks (srednji gumb vrti, pravokotna projekcija, standardni pogledi, tipke), videz kot Fusion (okolje, senčenje v kotih), razstavitev (E), izbira ploskev in robov v obe smeri |
| Dokumenti in drevo | Odprti dokumenti (sestavi/deli, sličice, iskanje), drevo s FreeCAD-ovo logiko, vidnost, urejanje (✎), spoji pod obema kosoma, telesa, povezave na druge datoteke (↗), Zgradba sestava (☰) |
| Ukazi | Trak z vsemi nameščenimi okolji (Snovanje delov, Skica, Del, Pločevina, Sestav, TechDraw, BIM, FEM, Kabli …), slovenska imena, »Ostali ukazi« iz menijev |
| Skica | Lasten urejevalnik v brskalniku: črta, pravokotnik, krog, točka, kote (urejanje in vlečenje), omejitve, pripenjanje na robove modela kot v SolidWorksu |
| Pločevina | Dodatek SheetMetal + lastna parametrična objekta (telo v pločevino, razgrnitev), DXF za delavnico |
| Baza standardnih delov | Desni klik → Označi kot standardni (premik v bazo, preusmeritev sestavov), Knjižnica (▦) za vstavljanje, število kosov (×n) |
| Videz kosov | Prednastavitve materialov (pločevina, nerjavna, les …), PBR v brskalniku |
| Elektro | Parametrični kanal in DIN letev, priključki kosov, kabli (dodatek Cables z lastnima popravkoma) |
| Različice (PDM) | Zgodovina iz lastnega oblaka, povrni, komentar ob shranjevanju, stanja, zaklepi, reference |
| Tiskanje | Natisni iz drevesa → STEP v ploščo Tiskaj → okno Pripravi; Lega za tisk (⊥) predlaga lego z najmanj podporami |
| Oblikovanje in render | Blender 5.2 v ozadju (vrata 3030), ideje in različice, parametrične oblike, AI oblikovalec, render (Cycles) slik in videa 360° |
| AI | MCP strežnik (21 orodij), skill `freecad`, Pomočnik v brskalniku |

## 3. Repozitoriji, veje, kaj je našega

| Kaj | Kje |
|---|---|
| Fork (**javen**) | https://github.com/juskolaric/FreeCAD, `origin` |
| Uradni FreeCAD | https://github.com/FreeCAD/FreeCAD, `upstream` (nikoli ne potiskaj tja) |
| Delovna veja | `moje-spremembe` (privzeta veja forka) |
| Ustavljeno | `ukazna-vrstica` (C++ trak v slogu SolidWorksa, nadomestil ga je spletni); ne nadaljuj brez naročila |

Fork je javen: **ključev, gesel in modelov strank ne commitaj**. Modeli so zunaj repozitorija (glej 5).

| Pot | Vsebina |
|---|---|
| `PREDAJA.md`, `PLAN.md`, `*-PLAN.md`, `CLAUDE.md`, `AGENTS.md` | predaja, plani, pravila za AI |
| `POSTAVI.bat`, `ZAZENI.bat` | postavitev računalnika; gradnja + zagon namiznega FreeCAD-a |
| `lastno/splet/` | strežnik v FreeCAD-u (`streznik.py` + moduli `drevo`, `baza`, `videz`, `oblak`, `tisk_lega`, `mcp_orodja`, `pomocnik`), stran `index.html`, `ZAZENI-SPLET.bat`, `izvedi.py` |
| `lastno/mcp/` | most MCP (stdio), skill, razširitev za aplikacijo Claude, namestitvene skripte |
| `lastno/oblikovanje/` | strežnik Blenderja, stran Oblikovanje, render, AI oblikovalec |
| `lastno/plocevina/`, `lastno/elektro/` | lastni parametrični objekti (v `Mod` prek stičišč) |
| `lastno/kabli/` | popravek dodatka Cables (patch) |
| `lastno/raziskava/plocevina.md` | znanje o pločevini (preberi pred modeliranjem pločevine) |
| `src/Gui/MainWindow.cpp` | edina sprememba v C++: oznaka »[lastna gradnja]« v naslovu okna |

## 4. Postavitev na novem računalniku

Potrebno: Windows 10/11 x64, ~40 GB prostora, 16 GB RAM ali več, 1–2 uri. Kratka pot brez posebnosti.

1. `git clone --recurse-submodules -b moje-spremembe https://github.com/juskolaric/FreeCAD.git FreeCAD`, nato
   `git remote add upstream https://github.com/FreeCAD/FreeCAD.git`.
2. `POSTAVI.bat`: git, pixi, VS Build Tools 2022 s C++, podmoduli, gradnja Release (prvič 30–90 min).
3. **Kar `POSTAVI.bat` še ne naredi (ročno):**
   - Dodatka **SheetMetal** (Addon Manager) in **networkx**; **Cables** v0.3.7 kot git klon v
     `%APPDATA%/FreeCAD/v1-1/Mod/Cables` + `git apply lastno/kabli/cables-0.3.7-popravki.patch`.
   - Stičišči v `%APPDATA%/FreeCAD/v1-1/Mod`: `lastna_plocevina` → `lastno/plocevina`, `lastna_elektro` →
     `lastno/elektro` (README v mapah).
   - **Blender 5.2** (Program Files) za Oblikovanje in render; **ffmpeg** (`winget install Gyan.FFmpeg`) za video.
   - Knjižnica `anthropic`: za Python FreeCAD-a (3.11) `pip --target %LOCALAPPDATA%/FreeCAD-splet/python-freecad`,
     za Python Blenderja (3.13) v `.../python-blender`. Ključ `ANTHROPIC_API_KEY` v okolju ali
     `%LOCALAPPDATA%/FreeCAD-splet/kljuci.env` (nikoli v repozitorij).
   - MCP: registracija `claude mcp add --scope user freecad ...` in kopija skilla v `~/.claude/skills/freecad/`
     (postopek v `lastno/mcp/README.md`).
   - Plošča Tiskaj (ločen repo `juskolaric/3D-print`, mapa `3D tisk/3D print/tiskaj`) in odjemalec lastnega oblaka.
4. Zagon: `lastno\splet\ZAZENI-SPLET.bat` (brez vidne konzole; odpre brskalnik in po potrebi ploščo Tiskaj).
   Konec: gumb **Izhod** v brskalniku (ne ubijaj procesa: ostanejo obnovljeni dvojniki dokumentov).

Vedno gradi `-release` (`pixi run configure-release`, `build-release`, `install-release`); `configure`/`build` brez
pripone na tej veji pomenita debug. Opozorilo o starem `pixi.lock` ignoriraj, `pixi lock` ne poganjaj.

## 5. Kje so podatki (zunaj repozitorija)

| Kaj | Kje |
|---|---|
| Modeli (projekti) | `%USERPROFILE%\Oblak\3D modeliranje\<Projekt>\` (FCStd, STEP, DXF; skripte v `Skripte/`, `PREBERI.txt`) |
| Baza standardnih delov | `Oblak\3D modeliranje\Standardni deli\<kategorija>\` (proizvajalci v `_Proizvajalci`, skripte v `_Skripte`) |
| Ideje Oblikovanja | `Oblak\3D modeliranje\Oblikovanje\Ideje\<ime>\` |
| Stanje strežnika | `%LOCALAPPDATA%\FreeCAD-splet\` (žeton `povezava.json`, sličice, renderji, pogovori AI, ključi) |
| Nastavitve FreeCAD-a | `%APPDATA%\FreeCAD\v1-1` (skupne z nameščenim FreeCAD 1.1.3) |
| Dnevniki | `build/splet-zagon.log`, `build/splet-zagon-napake.log` |

Mapa Oblak se sinhronizira z lastnim oblakom (repo `oblak`); brez dostopa do nje prevzemnik nima modelov.

## 6. Zgradba v enem odstavku

Strežnik (`streznik.py`) teče kot skripta v FreeCAD-u. HTTP nit **nikoli ne kliče FreeCAD API-ja**: streže
pripravljene posnetke (JSON), zahteve odloži v vrsto, ki jo glavna nit obdela vsakih 50 ms. Posnetek geometrije ima
predpomnilnik po objektih in se v mirovanju vnaprej pripravi za vse odprte dokumente. Dogodki gredo v brskalnik prek
SSE (`/events`), vsak POST potrebuje žeton `X-Zeton`. Ukazi se sprožijo kot klik na QAction prek Qt vrste dogodkov
(ne `Gui.runCommand`, ker bi modalno okno zamrznilo strežnik). Stran (`index.html`) je ena datoteka brez gradnje,
three.js prek CDN (brez interneta ne dela). Blender teče kot drug strežnik po istem pravilu niti. Seznam končnih točk
in podrobnosti vsakega področja: `CLAUDE.md`.

## 7. Kako delati in preverjati

- **Z AI:** seja Claude Code naj dela z orodji `mcp__freecad__*` (`stanje`, `drevo`, `slika` preden trdi, da je prav,
  `izmeri`, `python` = ena transakcija, `shrani` edini piše na disk, `postopki` za potek dela). Skill `freecad` se
  naloži sam.
- **Skripte brez orodij:** v tekočem strežniku `.pixi/envs/default/python.exe lastno/splet/izvedi.py skripta.py`;
  brez strežnika `FreeCADCmd.exe` (brez okna). **Nameščenega `FreeCAD.exe` z oknom ne odpiraj** (moti uporabnika;
  kavelj `~/.claude/hooks/blokiraj-freecad-okno.py` to zavrne), `.FCStd` ne odpiraj prek povezave datotek.
- **Spremembe kode:** Python in HTML ne potrebujeta prevajanja. `index.html` se bere ob vsakem klicu (F5 zadošča).
  Spremembe strežnika: Izhod in ponoven zagon, ali vroča zamenjava (`lastno/mcp/namesti_v_tekoci.py`; postopek v
  `CLAUDE.md`), ker je ob zagonu odprtih ~140 dokumentov in prvi posnetki trajajo minute.
- **Preizkus vzporedno:** drug primerek na `SPLET_VRATA=3031` z ločenim `LOCALAPPDATA` (3021 je plošča Tiskaj,
  3029 pogosto zasede drug primerek).
- **Brskalnik:** Chrome/Edge z WebGPU. Če stran visi pri »Povezujem«, so zasedene vse povezave (SSE) na gostitelja:
  odpri `http://localhost:3020/` namesto `127.0.0.1`.
- **Več sej hkrati:** na `index.html` in `streznik.py` delajo pogosto vzporedne seje: samo ciljni popravki, nikoli
  zapis cele datoteke.
- Commit sporočila v slovenščini, push samo na `origin`. Posodobitev z uradnim: `git fetch upstream`,
  `git merge upstream/releases/FreeCAD-1-1`.

## 8. Najpomembnejše pasti (podrobnosti v `CLAUDE.md`)

1. **Boolove operacije v zanki** v strežniku (npr. `common` lupin) zamrznejo glavno nit za več deset minut. Trke
   preverjaj z oglišči/obsegi ali orodjem `izmeri`.
2. **Shranjevanje:** odprt tok na datoteko (tudi v istem procesu) → »file is marked as read-only«. Tokove iz zipa
   zapiraj z `with`. Po shranjevanju iz skripte nastavi `Gui.getDocument(ime).Modified = False`.
3. **Ne dodajaj `Gui.addDocumentObserver` s `slotChangedObject`**: pokvari ViewProviderje (SheetMetal pade).
4. Kliki iz brskalnika gredo mimo modalnosti: oznaka okna je lastnost `_spletOkno`, ponovljen klik v 1,5 s se zavrne
   (dvojni »Počisti« v Obnovitvi je odprl 284 dokumentov).
5. **Obnova dokumentov** ob zagonu odpre dvojnike; strežnik jih zapre sam (kopije v `FreeCAD-splet/dvojniki`).
   FreeCAD-ova preverba obnove vse označi kot pokvarjene (napaka v `DocumentRecovery.cpp`, odprta naloga).
6. **Pomočnik/AI oblikovalec:** sistemskih navodil in orodij ne spreminjaj sredi pogovora (API vrne 400 zaradi vezave
   razmišljanja); effort `medium`, ne `high`.
7. **Spoji iz skripte:** najprej odmiki, šele nato reference (sicer `preSolve` premakne kos).
8. Skice iz skript: lok podaj s središčem in kotoma, ne s tremi točkami. Ime objekta mora biti ASCII.
9. Imena lastnosti: ne `Debelina` na nepločevinastih kosih (baza po njej prepozna pločevino).
10. Poln disk pokvari `user.cfg` nastavitev; obnova z `App.saveParameter()` iz tekočega strežnika.
11. Python niz s potjo `"C:\Users"` je napaka (`\U`); piši `r"C:\..."` ali `/`.
12. OptiX v Blenderju 5.2 z gonilnikom 566.03 ne dela; render sam preklopi na CUDA.
13. `Thumbnail.png` z 0 bajti v FCStd (shranjeno iz skritega okna) ni uporabna sličica; stran jo izriše sama.

## 9. Stanje in odprte naloge (11. 10. 2026)

Vse delo do 11. 10. je commitano in potisnjeno na `moje-spremembe`. Glavne odprte točke (popoln seznam v
`Apps/TODO.md` → FreeCAD):

- `POSTAVI.bat` naj namesti še dodatke, stičišča, Blender, knjižnico anthropic in MCP (zdaj ročno, točka 4.3).
- Lega za tisk: naslednji koraki (močne linije, optimizacija oblike za tisk).
- Oblikovanje: nadaljnje faze po `OBLIKOVANJE-PLAN.md`.
- Videz pogleda: izris le ob spremembi (zdaj vsako sličico; pri velikih sestavih obremeni GPU).
- Razstavitev znotraj podsestavov; okna preostalih ukazov kot lastni obrazci.
- PDM: objava lastnega oblaka je predpogoj za delo na več računalnikih; zaklep nima poteka.
- Photobox Slim A: preveri priključke na kupljenih ploščah, mate → spoji za ostale podsestave, kupljeni deli v bazo.
- Ločen repozitorij za spletni vmesnik (Next.js) ostaja možnost, ni začet.
- Selitev mape iz `Desktop/Apps/FreeCAD` v `Desktop/Apps/3D tisk/FreeCAD` še ni dokončana (strežnik drži mapo); ob
  selitvi popravi registracijo MCP in vpis v aplikaciji Claude.

## 10. Dnevnik odločitev

| Datum | Odločitev |
|---|---|
| 2026-09-29 | Osnova `releases/FreeCAD-1-1`, javen fork, gradnja s pixi, samo Release. |
| 2026-09-29 | FreeCAD kot motor, vmesnik in grafika v brskalniku (three.js, WebGPU); C++ trak ustavljen. |
| 2026-09-29 | Skica se ureja v brskalniku prek API-ja skice, brez FreeCAD-ovega načina urejanja. |
| 2026-10-07 | Vsa okna FreeCAD-a v brskalnik, okno se ne pokaže nikoli; nameščenega FreeCAD-a z oknom seje ne odpirajo. |
| 2026-10-07 | Modeli v `Oblak/3D modeliranje`, ne v repozitoriju; PDM nad lastnim oblakom. |
| 2026-10-08 | Pločevina z lastnimi parametričnimi objekti (geometrijsko iskanje ploskev namesto shranjenih imen). |
| 2026-10-09 | Baza standardnih delov: uporabnik kos označi sam, kos se premakne in sestavi preusmerijo. |
| 2026-10-09 | Plošča Tiskaj kot zavihek (okvir), ostane svoj proces; tisk se nikoli ne zažene sam. |
| 2026-10-10 | Blender kot drugi motor (Oblikovanje, render); okno Blenderja dovoljeno le za »Odpri v Blenderju«. |
| 2026-10-10 | Program je MCP strežnik; katalog orodij živi v strežniku, most je tanek. |
| 2026-10-10 | Tri stopnje (Oblikovanje → Strojno risanje → Tiskanje) z enotno podobo. |
