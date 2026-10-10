# FreeCAD — lastna kopija (navodila za Claude Code)

Fork uradnega FreeCAD-a: `origin` = `juskolaric/FreeCAD` (**javen** repozitorij), `upstream` = `FreeCAD/FreeCAD`.
Osnova je veja `releases/FreeCAD-1-1` (nameščen FreeCAD v Program Files je 1.1.3, veja je pri 1.1.4), delo poteka
na veji `moje-spremembe`. Samostojen projekt v `Desktop/Apps`; ni del Photolandie, veljajo pa splošna pravila iz
`Apps/CLAUDE.md` (slovenščina, ne briši podatkov, zaključni povzetki v naravnem jeziku, odprte naloge v
`Apps/TODO.md` pod »FreeCAD«). Plan in stanje: `PLAN.md`. **Predaja za prevzem na drugem računalniku: `PREDAJA.md`** (postavitev `POSTAVI.bat`).

## Gradnja (pixi, Windows)

Orodja: VS Build Tools 2022 z »Desktop development with C++« (MSVC 14.44, Windows SDK 10.0.26100) in pixi
(`C:\Users\Uporabnik\AppData\Local\pixi\bin\pixi.exe`; v PATH je le v terminalih, odprtih po namestitvi; v terminalu znotraj
aplikacije Claude ga ni, dokler se aplikacija ne zažene znova, zato tam uporabi `ZAZENI.bat` ali polno pot).
Vse knjižnice (Qt 6.8, OCCT 7.8, Python 3.11, Boost, Coin3D …) prinese pixi v `.pixi/` (približno 9 GB);
sistem ostane nedotaknjen.

Vedno gradi **Release**. Privzeti `pixi run configure` / `build` / `freecad` na tej veji pomenijo **debug**; ne uporabljaj jih.

```powershell
pixi run configure-release   # enkrat: posodobi podmodule, pripravi build/release (Ninja, preset conda-windows-release)
pixi run build-release       # prevajanje; prvič 30–90 min, potem le spremenjene datoteke
pixi run install-release     # kopira v .pixi/envs/default/Library (od tam se na Windows zaganja)
pixi run freecad-release     # install-release + zagon .pixi/envs/default/Library/bin/FreeCAD.exe (NE prevaja; prej build-release)
```

- Najenostavnejši zagon: `ZAZENI.bat` v korenu mape (dvoklik ali iz terminala od koderkoli): prevede spremenjeno, namesti
  in zažene; uporablja polno pot do pixi, ob prvem zagonu sam požene `configure-release`.
- Prevedeni program zaganjaj **samo** prek `pixi run freecad-release` ali iz `pixi shell` (sicer manjkajo DLL-ji).
- `build/` in `.pixi/` sta izven gita. **Ne briši ju** brez naročila: polna gradnja traja do uro in pol.
- Dnevniki gradnje gredo v `build/` (npr. `build/build-release.log`), ne v koren repozitorija.
- Preverjanje spremembe: prevedi, namesti, zaženi in preveri v oknu. Konzolna različica:
  `.pixi\envs\default\Library\bin\FreeCADCmd.exe --version`.
- Hitri preizkus, da prevedeni program teče: `pixi run -- .pixi/envs/default/Library/bin/FreeCAD.exe lastno/preveri-naslov.py`
  zapiše naslov okna in verzijo v `build/naslov-okna.txt` in program zapre. Naslov nosi oznako »[lastna gradnja]«.
- Opozorilo pixi o starem formatu `pixi.lock` (v6) ignoriraj; `pixi lock` ne poganjaj, da se datoteka ne razide z upstream.
- Nastavitve uporabnika si prevedeni program deli z nameščenim 1.1.x (`%APPDATA%\FreeCAD\v1-1`), ker je `ExeName`
  isti (`src/Main/MainGui.cpp`). Sprememba imena bi premaknila tudi mapo nastavitev.

## Spletni pogled (`lastno/splet`), smer od 2026-09-29

FreeCAD je motor, vmesnik in grafika nastajata v brskalniku (plan, korak 8 naprej). Dokaz koncepta:

- Zagon: `lastno\splet\ZAZENI-SPLET.bat` (FreeCAD s strežnikom, odpre brskalnik) ali `FreeCAD.exe lastno/splet/streznik.py`.
  Skripta od 2026-10-07 pixi zažene **brez vidne konzole** (PowerShell `Start-Process -WindowStyle Hidden`, `pixi run -q --no-progress`);
  izpis FreeCAD-a gre v `build/splet-zagon.log` in `build/splet-zagon-napake.log`. Program se konča z gumbom Izhod v brskalniku;
  `SPLET_KONZOLA=vidna` vrne pomanjšano konzolo. Okoljski `PIXI_NO_PROGRESS` ne nastavljaj na `1` (pixi sprejme le `true`/`false`).
  Naslov `http://127.0.0.1:3020/` (vrata po `Photolandia-Apps/ports.json`). Okolje: `SPLET_VRATA`, `SPLET_BRSKALNIK=0` ne odpre brskalnika,
  `SPLET_OKNO=vidno` pusti okno FreeCAD-a vidno (privzeto je **skrito** in se samo od sebe nikoli ne pokaže; gumba v
  brskalniku: Pokaži/Skrij FreeCAD in Izhod). Možnost `--hidden` FreeCAD-a ni uporabna: po skripti se program konča.
  Zaprtje okna z X konča program, ko ni več odprtih vprašanj (`setQuitOnLastWindowClosed(False)` + filter dogodkov).
  Vrata 3021 zaseda tuj program (python.exe); za testni primerek uporabi `SPLET_VRATA=3029`.
- Pravilo niti: nit strežnika **nikoli** ne kliče FreeCAD API-ja. Bere le posnetek (bajti JSON), zahteve daje v vrsto,
  ki jo obdela glavna nit (QTimer 50 ms; brez okna zanka). Posnetek se zgradi ob spremembi dokumenta z zamikom 300 ms.
- Končne točke: `GET /` stran, `GET /model` posnetek, `GET /ukazi` seznam ukazov (okolja, orodne vrstice, skupine, ikone),
  `GET /events` SSE (`model`, `izbira`, `aktivni`, `okolje`), `GET /stanje`, `POST /select {objekt, element, dodaj}`,
  `POST /ukaz {ime, indeks}` (sproži QAction prek Qt vrste dogodkov), `POST /okolje {ime}` (Gui.activateWorkbench),
  `POST /okno {prikazi}`, `POST /izhod` (zapre dokumente brez shranjevanja in konča), `POST /python {koda, cakaj}` (počaka na izvedbo,
  vrne `izpis`, `napaka`, `rezultat`), `POST /obrazec`. Vsak POST potrebuje glavo `X-Zeton` (žeton nastane ob
  zagonu in je vpisan v stran), da tuja spletna stran v brskalniku ne more poganjati kode v FreeCAD-u.
- **MCP strežnik (AI z dostopom do vseh funkcij)** (od 2026-10-10, plan `MCP-PLAN.md`, `lastno/mcp/README.md`): seje
  Claude Code imajo orodja `mcp__freecad__*` (registracija `--scope user freecad`, most `lastno/mcp/freecad_mcp.py`,
  stdio brez odvisnosti). Katalog orodij je v strežniku (`lastno/splet/mcp_orodja.py`; `GET /mcp/orodja`, `GET /mcp/vir`,
  `POST /mcp/orodje`, `POST /mcp/odgovor`; ukaz glavne niti "mcp"); novo orodje = funkcija z `@orodje`, vroča zamenjava
  `importlib.reload(mcp_orodja); mcp_orodja.povezi(S)` ali `lastno/mcp/namesti_v_tekoci.py` (prek `izvedi.py`; zamenja še
  `Stanje._izvedi`, `do_GET`, `do_POST`). Most ob novi verziji kataloga javi `tools/list_changed`. Orodja: stanje,
  dokumenti, drevo, slika, izmeri, python, ukaz, obrazec, izberi, isci, razveljavi, shrani, splet, natisni, render,
  oblikovanje, opravilo, dnevnik, izhod; v mostu zazeni in freecadcmd. **Seje naj delajo z orodji, ne z `izvedi.py`.**
  Varovalke: `python` je ena transakcija (napaka jo razveljavi), brez `dovoli_pisanje` zavrne save/close/brisanje datotek;
  na disk piše le `shrani`. Slika: dogodek SSE `mcp` → stran izriše → `POST /mcp/odgovor` (stran ob povezavi pošlje
  `zdravo`; brez tega rezervni izris numpy). Preizkus: `python lastno/mcp/preizkus_protokola.py`.
  Namizna aplikacija Claude: razširitev `lastno/mcp/freecad.mcpb` (zaganjalnik poišče most pred in po selitvi mape);
  skill `freecad` z delovnimi postopki je v `lastno/mcp/skill/` in nameščen v `~/.claude/skills/freecad/` (po spremembi
  ga kopiraj znova); isto besedilo vrne orodje `postopki`. V namizni aplikaciji Claude vpis v claude_desktop_config.json
  med njenim delovanjem ne obstane (prepiše ga iz pomnilnika): `lastno/mcp/vpisi_v_claude_desktop.py --cakaj` vpiše ob
  zaprtju aplikacije. Ob selitvi mape v »3D tisk« popravi še registracijo `claude mcp` in vpis v aplikaciji (pot do mostu).
- **Pomočnik AI v brskalniku** (od 2026-10-10, `lastno/splet/pomocnik.py`, gumb ✦ Pomočnik v glavi, plošča `#pomocnik`
  desno od pogleda): zanka Claude API teče v niti strežnika in kliče `mcp_orodja.izvedi_slovar` (isti katalog kot MCP).
  `GET /pomocnik?od=N` (koraki, zadnji se med pretakanjem dopolnjuje), `GET /pomocnik/slika?id=`, `POST /pomocnik
  {dejanje: poslji | potrdi | ustavi | nov}`, dogodek SSE `pomocnik`. Ključ: `ANTHROPIC_API_KEY` iz okolja, sicer
  `%LOCALAPPDATA%/FreeCAD-splet/kljuci.env`, sicer `.env` plošče Tiskaj (nikoli v stran). Knjižnica anthropic 1.13 za
  Python 3.11 FreeCAD-a je v `%LOCALAPPDATA%/FreeCAD-splet/python-freecad` (`pip --target`; tista za Blender je cp313).
  Pogovor v `%LOCALAPPDATA%/FreeCAD-splet/pomocnik` (pogovor.json samo z dodajanjem, prikaz.json, seja.json, slike/;
  Nov → arhiv/). **Ne spreminjaj sistemskih navodil ali orodij sredi pogovora**: API razmišljanje veže na predpono
  (system, tools, sporočila) in na tem računu vrne 400; zato seja.json, vsak klic pa še `block_binding: drop_block`
  (beta `thinking-binding-controls-2026-08-01`). Prvi uvoz knjižnice v velikem primerku traja do minute: začne se v
  ozadju ob prvem odprtju plošče.
- Vir resnice za izbiro je FreeCAD (`Gui.Selection`): brskalnik pošlje klik, obarva pa šele to, kar FreeCAD javi.
- Posnetek geometrije (od 2026-10-07) ima **predpomnilnik po objektih** (`_PREDPOMNILNIK`, ključ: oblika prek povezanega objekta /
  otrok skupine, lega, barve, oznaka; vnos je že serializiran JSON). Ob preklopu dokumenta ali ponovnem izračunu se teselirajo le
  spremenjeni objekti (soba: 6 s -> 0,3 s). Oblika se ne kopira (`copy()` izgubi mrežo); točke se prestavijo z `getGlobalPlacement`.
  Skupine (`App::DocumentObjectGroup`) niso v posnetku (njihov `Shape` je le sestav otrok, ki so v posnetku vsak zase). Ob preklopu
  dokumenta se posnetek zgradi takoj (brez zamika 300 ms). Dnevnik: `posnetek N: X objektov (Y iz predpomnilnika), kB, s`.
  Od 2026-10-09: `_geometrija` najprej zmreži celo obliko naenkrat (`oblika.tessellate` = vzporedni BRepMesh), ploskve nato
  mrežo le preberejo (po ploskvah je OCC tekel na enem jedru, 1,5x počasneje); prostornine teles v drevesu so v predpomnilniku
  `drevo._PROSTORNINE` (sestav s 70 telesi 1,5 s ob vsakem posnetku); **ogrevanje** (`Stanje.ogrej`): ko 3 s ni zahtev iz brskalnika,
  strežnik posnetke vseh odprtih dokumentov (sestavi najprej) pripravi vnaprej, po en mrežen objekt na obhod. 140 dokumentov
  ~3 min in ~300 MB; preklop na sestav nato 0,03–0,4 s namesto do 1 min ob prvem obisku.
- Pogled (3D) se vodi kot v SolidWorksu (lasten nadzor `nadzor` v `index.html`, ne OrbitControls): srednji gumb vrti
  prosto okoli središča modela (ko je ves v pogledu), sicer okoli točke na vidni geometriji blizu sredine zaslona
  (kot SolidWorks; vijolična oznaka med vlekom, da povečan detajl ne odleti), ali okoli točke, ki jo določi klik srednjega na model; Ctrl/Shift/Alt + srednji = premik,
  povečava, sukanje; kolešček naprej oddalji (`OBRNI_KOLESCEK`), proti kazalcu; levi gumb samo izbira. Projekcija je privzeto
  **pravokotna** kot v SolidWorksu (gumb Perspektiva v vrstici pogledov ali v meniju na preslednico, stanje v `localStorage`):
  lega pogleda živi v perspektivni `camera`, pravokotna kamera se pred izrisom in žarki uskladi z njo (`kameraPogleda()`),
  višina okna = razdalja do cilja × tan(fov/2), zato povečava, premik in prileganje delujejo enako v obeh načinih. Tipke: puščice 15°,
  Shift 90°, Alt sukanje, Ctrl premik, Ctrl+1..7 ali 1..7 standardni pogledi (Ctrl+številke brskalnik pogosto vzame
  sam), 8 pravokotno na izbrano ploskev, F, Z, Shift+Z, preslednica meni pogledov. Isti pogledi so tudi gumbi v zgornjem desnem kotu
  pogleda (`#pogledi`, trenutni pogled je poudarjen; v skici je vrstica skrita). Skica ostaja na `ortoControls`.
- **Videz modela kot v Fusionu** (od 2026-10-09, `index.html`, razdelek »3D pogled«): okolje `RoomEnvironment` prek `PMREMGenerator`
  (`scene.environment`, zavrteno za 90° okoli X, ker je svet Z-gor; jakost 0,35), `NeutralToneMapping`, ozadje navpični preliv
  (`scene.backgroundNode`, TSL `screenUV`; sličice ga za čas izrisa izklopijo), glavna luč 2,2 + šibka od zadaj, material satenast
  (kovinskost 0,15, hrapavost 0,42, `polygonOffset`), robovi temno sivi `0x353a42`. Mreža tal (`nastaviMrezo`) je četrtino polmera
  modela pod njegovim dnom in se postavi ob vsakem `uporabiRazstavitev` (nov posnetek, razstavitev), ne le ob prileganju (F). **Senčenje v kotih** (GTAO, `verigaIzrisa`):
  `RenderPipeline` na kamero (perspektivna, pravokotna; skica brez), predprehod normal in globine vidi samo ploskve modela (plast 2,
  `PLAST_SENCENJA`; mreža in robovi bi sicer dobili temne obrobe), zakritost pomnoži celoten izris (`mocSencenja`), polmer = 6 %
  vidne višine. `builtinAOContext` ne uporabljaj: predprehod se gnezdi v glavnem prehodu, si z njim deli seznam izrisa in ob plasteh
  pade (`renderList[i] undefined`). Gumb Senčenje v vrstici pogledov, tipka O, stanje `localStorage.sencenje`.
  Vgrajeni brskalniki vseh sej si delijo 6 povezav na gostitelja: ko jih zasedejo zavihki na `127.0.0.1:3020` (SSE), stran obvisi
  na »Povezujem«; odpri `http://localhost:3020/`. Zajem slike platna: `drawImage` platna WebGPU v `requestAnimationFrame`.
- **Razstavitev (explode)** (od 2026-10-09): gumb Razstavi in drsnik v vrstici pogledov, tipka E, meni na preslednico. Samo prikaz:
  vsak objekt posnetka (`skupina.position`) se odmakne od središča modela sorazmerno z oddaljenostjo središča svojega okvirja
  (`uporabiRazstavitev`, največ 1,5-krat); povezava na podsestav je en objekt in se premakne v celoti. V skici in med izrisom
  sličic je model sestavljen (`izrisiVir` razstavitev izklopi le v sinhronem delu do `render`). Ob preklopu dokumenta se ponastavi.
- **Videz kosov (materiali)** (od 2026-10-09, `lastno/splet/videz.py`): FreeCAD hrani videz kot klasični Coin material
  (`ViewObject.ShapeAppearance`: Diffuse/Specular/Shininess), brskalnik riše PBR. Ploskev posnetka nosi poleg barve še
  kovinskost, hrapavost, zrnatost in vzorec (indeksi 7–10; brez njih privzeto 0,15 / 0,42 / 0 / 0; vzorec 1 = les: letnice
  in pore v TSL iz koordinat modela, vlakna vzdolž X). Vir: (1) lastna prednastavitev =
  lastnost `Videz` na kosu (`VIDEZI`: pločevina, nerjavna, pocinkana, aluminij, krom, barvano, plastika, guma, folija = sijajni vinil, les-hrast), ob
  nastavitvi se zapiše tudi ShapeAppearance, izvirnik v skrito `VidezIzvirni` (»privzeto« ga vrne); (2) videz iz
  FreeCAD-ove knjižnice (Std_SetAppearance: Steel, Chrome ...) se prepozna po vrednostih (`KNJIZNICA_PBR`); (3) sicer
  satenast. **Sestav**: povezava na podsestav je en objekt posnetka, njene ploskve gredo po vrsti `getSubObjects()`
  (le vidni elementi, `isElementVisible`), zato `listi()` sestavi videz po kosih (prej je cel podsestav dobil eno barvo).
  Kovinske ploskve (kovinskost >= 0,5) imajo v brskalniku svoj material z okoljem ×3,2 (skupine geometrije), ker je
  okolje (0,35) za kovino pretemno. `POST /videz {dejanje: seznam | nastavi (ime, videz) | plocevina (shrani)}`; desni klik
  v drevesu -> ◐ Videz. »plocevina« poišče kose (`je_plocevina`: Vrsta, Debelina, SheetMetal; folije ne) v aktivnem
  dokumentu in vseh povezanih datotekah, nerjavno/aluminij izbere po `MaterialSW`. Vroča zamenjava funkcij v tekočem
  strežniku (brez ponovnega zagona): ast iz `streznik.py` -> `exec` v `sys.modules["streznik"].__dict__`, metode s `setattr`
  na razred; `_PREDPOMNILNIK.clear()` sproži ponovno teselacijo vseh ~140 dokumentov (minute), zato ga ne prazni brez potrebe.
- Ukazi v brskalniku so tisti iz orodnih vrstic okolij `DELOVNA_OKOLJA` (Snovanje delov, Skica, Del, od 2026-10-08 Pločevina =
  dodatek SheetMetal `SMWorkbench`, če je nameščen; znanje v `lastno/raziskava/plocevina.md`) in `HITRI_DOSTOP`.
  Od 2026-10-09 so v brskalniku **vsa** nameščena okolja (Sestav, TechDraw, Draft, BIM, FEM, CAM, Mesh ... in dodatki, ki
  jih seznam ne pozna, na koncu; brez `NoneWorkbench`, `TestWorkbench`). Ob zagonu se naložijo le `ZACETNA_OKOLJA`, ostala ob
  prvem kliku (`nalozeno: false` -> `POST /okolje` -> `preveri_okolje` opazi novo naloženo okolje, `__Workbench__` na ročaju,
  zgradi ukaze znova in odda dogodek `ukazi`). Vidni zavihki so `GLAVNI_ZAVIHKI`, ostala okolja so v meniju »Več ▾« (dejavno dobi
  zavihek). Ukazi, ki so le v menijih okolja (Inspection nima orodne vrstice), so na koncu traku kot skupine »<meni> (meni)«
  (`_zajemi_menije` ob aktivaciji, ker se menijska vrstica zgradi ob preklopu okolja; meni Pomoč in ukazi `Std_` izpuščeni);
  stanje »na voljo« se preverja vsakih 500 ms (`isActive`). Pri skritem oknu FreeCAD ne osvežuje omogočenosti dejanj
  (`MainWindow::_updateActions` le pri vidnem oknu), zato `_sprozi_ukaz` dejanje omogoči sam, če `isActive()` vrne True.
  **Ne dodajaj `Gui.addDocumentObserver` s `slotChangedObject`**: FreeCAD ta signal odda že iz konstruktorja ViewProviderja,
  opazovalec takrat ustvari Python ovoj osnovnega razreda in objekti Part potem nimajo `DiffuseColor` (SheetMetal Make Wall
  pade). Spremembe videza strežnik preverja vsako sekundo (`_videz_kljuc`).
- **Kabli** (od 2026-10-09): dodatek Cables v0.3.7 (`CablesWorkbench`, git klon v `%APPDATA%/FreeCAD/v1-1/Mod/Cables`, paket
  `freecad.cables`), zavihek »Kabli«. Iz skripte: `wireFlex.make_wireflex([(link, "VertexN"), ...])` (točke pripete na oglišča kosov
  v istem dokumentu, sledijo premiku), `archCable.makeCable(baseobj=pot, gauge=1.5)`, nato `recompute`. Prazna oblika kabla ob prvem preračunu je bila
  napaka dodatka pri ravni poti tipa BSpline (dve točki), zraven je ob vsakem preračunu kopičil telesa: lastna popravka
  v klonu dodatka, zapis in patch v `lastno/kabli/` (po posodobitvi dodatka uveljavi znova). Preizkušeno 2026-10-09:
  ravna, ukrivljena in lomljena pot, večžilni profil, premik kosov v sestavu, shrani in odpri. Brez ponovnega zagona: `sys.path` + `freecad.__path__` dopolni z mapo dodatka, `import freecad.cables.init_gui`.
  Urejanje točk (Cables_Edit) potrebuje 3D okno FreeCAD-a.
- **Električni priključki kosov** (od 2026-10-09, `Oblak/3D modeliranje/Photobox Slim A/Skripte/prikljucki_kosov.py`): vsak
  elektronski kos nosi na glavnem objektu lastnost `Prikljucki` (vrstice `ime | vrsta | x y z | dx dy dz | oznaka | opis`,
  koordinate v okviru vsebnika) in pri App::Part še točke `Part::Vertex` `Prikljucek_<ime>` (konec kabla se pripne nanje, točka
  sledi premiku kosa); gol Part::Feature (Kinter, plošča TV) dobi le lastnost, kabel se pripne na najbližje oglišče.
  Točka priključka je na **dnu luknje za vodnik** (Shelly 4,7 mm, Mean Well 4 mm globoko), ne na površini: kabel gre naravnost
  noter, goli konec (`StrippedWireLength`, ena vrednost za oba konca = manjša globina − 0,5) ostane v luknji, izhod iz kosa
  (`_izhod`) se začne šele nad površino (`Plosca.globina`: pot vzdolž smeri do roba okvirja telesa). Po spremembi kataloga
  **preračunaj nosilce** (DIN RAIL - Shely …) in sestave, sicer `getSubObject` vrne staro točko (2026-10-09).
  Nosilci »DIN RAIL - Shely (…)« so 2026-10-09 razpuščeni (`Skripte/razpusti_nosilce_shelly.py`): plošče imajo neposredni
  povezavi `Shelly<Oznaka>` + `Nastavek<Oznaka>` na standardni Shelly in Nastavek Shelly DIN; stari napajalniki
  »ELEKTRO - Napajalnik (…)« niso več v uporabi (datoteke ostajajo v Kupljeni deli).
  `elektro_kabli.prikljucki(povezava)` zbere lastne in podedovane priključke (nosilec Shelly -> vgrajeni Shelly, sestav spon ->
  elementi vrste, ključ `<oznaka>[i]/A`) z `getSubObject(pot, retType=3)`; `Plosca.povezi(ime, (kos, "L"), (kos2, "N"))` napelje
  vodnik s smerjo in vrsto iz priključka. Mesta na kupljenih ploščah so ocena iz geometrije (zapis v katalogu).
- **Tiskanje (plošča Tiskaj v zavihku)** (od 2026-10-09, plan `TISKANJE-PLAN.md`): nadzorna plošča tiskalnikov `3D print/tiskaj`
  (lasten program, vrata 3021, kamere 3026) je v glavi strani 3. stopnja risanja »Tiskanje« (od 2026-10-10 skupina `#stopnje` levo v glavi:
  1 Oblikovanje → 2 Strojno risanje (`#gumbStrojno`, FreeCAD; dejavna, ko ni odprt noben okvir) → 3 Tiskanje; `osveziStopnjo()`, v 1. in 3.
  stopnji razred `body.stopnjaZunaj` skrije hitri dostop, okolja in trak) (`#gumbTiskanje`, zunaj drsečega `#zavihki`, da je
  viden tudi v ozkem oknu): okvir `<iframe>` na `http://<gostitelj>:3021/` čez 3D pogled (`#tiskanje`; izris pogleda se medtem ustavi);
  klik na okolje ga zapre. Strežnik FreeCAD-a je le posrednik na niti strežnika (`_tiskaj_klic`, `http.client`, brez FreeCAD API-ja):
  `GET /tiskaj/stanje` (pomnjeno 2 s: tece, vrata, mapa, skrčeni tiskalniki, vrsta, vhod_mapa) za **čipe tiskalnikov** v vrstici stanja
  (`#tiskalnikiCipi`, vsakih 5 s, klik odpre zavihek); `POST /tiskaj/zazeni` (plošča ne teče → gumb Zaženi: `tiskaj_zazeni` požene sistemski
  `pythonw streznik.py --brez-brskalnika` kot odklopljen proces brez PYTHONHOME/PYTHONPATH, ki preživi Izhod FreeCAD-a);
  `POST /tiskaj/natisni {dokument, ime, imena}` = **Natisni** iz desnega klika v drevesu (`natisniVozel`, `imena` = `imenaZaIzris` vozla):
  glavna nit (`_tiskaj_natisni`) izvozi `Part.getShape(obj).exportStep` v vhodno mapo plošče (`mape.vhod` tekoče plošče, sicer njen
  `config.json` → `vhod_mapa`, privzeto `Desktop/STEPI`; zapis v `.delno`, nato `os.replace`; objekt z več telesi → `_1`, `_2`; ime = oznaka
  kosa, ista datoteka = nova različica), nato nit strežnika plošči javi `POST /api/vhod/rocno {datoteke}`, da je **samodejna priprava**
  (v plošči privzeto vklopljena: 75 %, podpore, črna, v vrsto) ne nareže sama; če plošča ne teče, oznaka počaka v `TISKAJ_ROCNO_CAKA` do
  njenega zagona. Stran nato odpre zavihek in okvirju pošlje `postMessage {dejanje: 'pripravi', datoteke}` (ob preklopu zavihka še
  `skrit`/`viden`; okvir ob nalaganju javi `{vir: 'tiskaj', dejanje: 'pripravljen'}`, do takrat sporočila čakajo v `tiskanje.cakajoce`);
  plošča odpre Vhod in okno Pripravi (tiskalnik, predal, orientacijo, polnilo potrdi uporabnik; tisk se nikoli ne zažene sam).
  `ZAZENI-SPLET.bat` ploščo zažene, če ne teče (podprogram `:tiskaj`). Mapa plošče: `TISKAJ_MAPA` (`_najdi_tiskaj`: ob repozitoriju
  `3D print/tiskaj` ali `3D tisk/3D print/tiskaj`; prepis `SPLET_TISKAJ_MAPA`, vrata `SPLET_TISKAJ_VRATA`). 2026-10-09 vroče zamenjano v
  tekoči strežnik (nove funkcije + `Stanje._izvedi`, `Zahteva.do_GET`/`do_POST`). Skripta strani je modul: v konzoli brskalnika
  `tiskanje` ni spremenljivka strani, ampak element `#tiskanje`.
- **Oblikovanje in render (Blender)** (od 2026-10-10, plan `OBLIKOVANJE-PLAN.md`, mapa `lastno/oblikovanje/`): Blender 5.2 (Program Files,
  `upodabljanje.najdi_blender` vzame najnovejšega; prepis `SPLET_BLENDER`) je drugi motor za proste, organske oblike. **Strežnik Oblikovanja**
  `streznik_blender.py` teče v Blenderju brez okna (`blender -b --factory-startup --python streznik_blender.py -- --vrata 3030`), enako pravilo niti
  kot spletni FreeCAD (nit HTTP ne kliče bpy; vrsta, zanka na glavni niti), 1 enota = 1 mm. Stran `oblikovanje.html` (three.js WebGL) je v spletnem
  FreeCAD-u zavihek »◆ Oblikovanje« (`#gumbOblikovanje`, okvir kot Tiskanje); ob prvem odprtju strežnik FreeCAD-a Blender zažene sam
  (`POST /oblikovanje/zazeni`, `GET /oblikovanje/stanje`), proces preživi Izhod FreeCAD-a. Ustavi ga `POST /izhod` na 3030 (z žetonom).
  **AI/skripte**: `python lastno/oblikovanje/izvedi.py skripta.py` (ali `-c "koda"`; žeton in vrata iz `%LOCALAPPDATA%/FreeCAD-splet/oblikovanje.json`),
  v imenskem prostoru `bpy, bmesh, np, Vector, Matrix, math, C, D` in pomočniki `dodaj_obliko(vrsta, velikost, lega)` (kocka = gladka kletka,
  krogla, valj, torus, stozec, kaplja), `gladko(obj)`, `material(ime, barva sRGB, kovinskost, hrapavost)`, `pocisti()`. Datoteke `.blend` in STL
  (`Izvoz/`) gredo v `Oblak/3D modeliranje/Oblikovanje` (`SPLET_OBLIKOVANJE_MAPA`). Posnetek mreže: točke po (oglišče, normala), skupine po materialih.
  **Render** (`upodabljanje.py` + `render.py`): vsak render je ločen proces Blenderja (vrsta, en naenkrat), vir je posnetek `/model` aktivnega
  dokumenta FreeCAD-a ali kopija `.blend` iz Oblikovanja; scena se normira na polmer 1, studio (tri luči + Blenderjevo vgrajeno okolje), tla lovijo le
  senco, ozadje (preliv, belo, temno) se doda z numpy. Okno `render-plosca.js` je skupno obema stranema (gumb s fotoaparatom v vrstici pogledov
  FreeCAD-a, gumb Render v Oblikovanju); kamera = trenutni pogled (tudi pravokotna in razstavitev). `POST /render`, `GET /render/stanje|slika|seznam`,
  `POST /render/ustavi` na obeh strežnikih. Video 360° = PNG sličice + ffmpeg (winget Gyan.FFmpeg). Slika gre še v `Renderji/` ob datoteki
  (v bazi standardnih delov `_Renderji/`, da je knjižnica ne pokaže kot kategorijo), delovne datoteke v `%LOCALAPPDATA%/FreeCAD-splet/renderji/<id>/`
  (`dnevnik.txt`). **OptiX** v Blenderju 5.2 z gonilnikom NVIDIA 566.03 ne dela (`OPTIX_ERROR_INTERNAL_COMPILER_ERROR`): prvi neuspeh zapiše
  `renderji/brez-optix.txt` in render teče s CUDA (7 dni, nato znova poskusi OptiX). Barve: `Khronos PBR Neutral` (AgX razbarva barve FreeCAD-a).
  **Igrišče (faza 3, od 2026-10-10)**: `igrisce.py` (ideje in različice, parametrična oblika, pogledi za AI) in `ai_oblikovalec.py` (Claude v
  zavihku). Ideja = `Oblikovanje/Ideje/<ime>/` z `ideja.json`, `R01.blend`…, `R01.png` (sličico izriše stran iz svojega pogleda, `POST /slicica`),
  `pogovor.json` (sporočila API, **samo dodajanje**: bloki odgovora se vrnejo nespremenjeni), `prikaz.json` (koraki za stran), `pogledi/`.
  Zadnja ideja se ob zagonu odpre sama (`FreeCAD-splet/oblikovanje-zadnja.json`). Parametrična oblika: besedilo `oblika.py` v .blend z
  `zgradi(p)` + lastnost scene `parametri` (JSON drsnikov); objekti v zbirki »Oblika« se ob drsniku zgradijo znova (`POST /ukaz {dejanje:
  parameter, vrednosti}`). AI: `claude-opus-5-5`, pretakanje, adaptivno razmišljanje s povzetkom (prikazan v klepetu), effort `medium`
  (pri `high` je prvi odgovor razmišljal > 5 min in povezava je padla), `fallbacks: "default"`, ponovitev ob prekinjeni povezavi; orodja
  `nastavi_obliko`, `izvedi_kodo`, `poglej` (Workbench, 4 pravokotni pogledi v sliki 2 × 2, ~1 s), `preberi_obliko`; tečejo na glavni niti
  (`na_glavni`). Na koncu odgovora, ki je spremenil sceno, nastane različica (vir AI). SDK `anthropic` je za Python Blenderja (3.13) nameščen s
  `pip --target` v `%LOCALAPPDATA%/FreeCAD-splet/python-blender`; ključ `ANTHROPIC_API_KEY` iz okolja, `FreeCAD-splet/kljuci.env` ali `.env`
  plošče Tiskaj (nikoli v izpis). **Odpri v Blenderju** (okno Blenderja je dovoljeno, odločitev uporabnika 2026-10-10; nameščenega FreeCAD-a
  z oknom še vedno ne odpiraj): scena gre v `<ideja>/_v_blenderju.blend`, okno Blenderja jo odpre, ob shranjevanju (sprememba časa datoteke)
  strežnik datoteko naloži kot novo različico (vir Blender). Poti: `GET /ideje`, `/ideja`, `/ideja/slicica?ideja=&r=`, `/ai/stanje?od=`,
  `/ai/slika?ime=`; `POST /ai {sporocilo, slike}`, `/ai/ustavi`, `/ukaz` (nova-ideja, odpri-idejo, shrani-razlicico, odpri-razlicico,
  uredi-razlicico, parameter, odpri-v-blenderju, izvozi-za-tisk). **3D natisni** (gumb v Oblikovanju, od 2026-10-10): Blender izvozi STL
  vidnih objektov v `%LOCALAPPDATA%/FreeCAD-splet/tisk/<ideja>.stl`, okvir pošlje oknu FreeCAD-a `postMessage {vir: 'oblikovanje',
  dejanje: 'natisni', pot}`, stran pokliče `POST /tiskaj/datoteka {pot}` (`tiskaj_datoteka`: le datoteke iz te mape, kopija v vhod
  plošče prek `.delno`, oznaka za ročno pripravo) in odpre zavihek Tiskanje z oknom Pripravi. Regularni izrazi v `oblikovanje.html`: pri popravkih iz Pythona pazi, da `\n` ne postane
  pravi prelom (stran se potem sploh ne zažene, 2026-10-10).
- **Lega za tisk** (od 2026-10-10, `lastno/splet/tisk_lega.py`, samo numpy): desni klik v drevesu -> ⊥ Lega za tisk. `POST /tisk/lega
  {dokument, imena, kot_previsa}`: glavna nit le zmreži kose (`_tisk_mreze`; kosi kot pri Natisni, `_kosi_za_tisk`: objekt z več telesi =
  več kosov, mreža v koordinatah STEP-a), iskanje teče na niti strežnika (`tisk_lega_kosov`, ~1,5 s za 50k trikotnikov). Preizkusi ~450
  smeri (krogla, osi, -normale največjih ravnih ploskev); hitra ocena podpor = projicirani previs × višina do mize, za ~10 najboljših
  natančno z rastrom (podpora pade do prve ploskve kosa pod previsom). Ocena (`_ocena`, ~cm³ podpor): podpore + previsi + višina +
  kazen 10 za kos brez ravne ploskve na mizi + kazen vitkosti (težišče/√stik). Kandidat nosi `gor` (STEP), `gor_pogled` (globalno,
  prek `getGlobalPlacement`) in `rotacija` (3x3 po vrsticah, `gor` -> +Z; preverjeno: po zasuku iste podpore). Stran obarva izbrani kos
  z `materialPrevisov` (TSL, uniforme `legaU`; modro miza, rdeče previs, rumeno do 10° pod pragom) in nariše prosojno mizo; »Natisni v
  tej legi« pošlje plošči `rotacije {datoteka: zasuk}` v sporočilu `pripravi` (tiskaj `modalPripravi(pot, null, lega)`). Samostojni
  `.pixi/.../python.exe` brez `Library/bin` v PATH obvisi pri množenju matrik numpy (BLAS DLL); v strežniku in s PATH dela.
- **Knjižnica standardnih delov** (od 2026-10-09, gumb ▦ Knjižnica v glavi stranskega stolpca): okno `#knjiznica` z mrežo
  kartic po kategorijah (mape baze, sličice prek `/slicica`, iskanje). `GET /knjiznica` (`zgradi_knjiznico`, nit strežnika,
  brez FreeCAD API-ja; izpušča mape `_*`, `.*`, `DXF`), `POST /knjiznica {dejanje: vstavi | odpri, pot, dokument}`
  (`_knjiznica_dejanje` na glavni niti): kos odpre (skrito) in ga kot `App::Link` (sestav iz baze v sestav:
  `Assembly::AssemblyLink`) doda v `Assembly::AssemblyObject` ciljnega dokumenta, sicer v koren; ciljni dokument je ime ali
  oznaka iz zahteve (brskalnik pošlje `stanje.dokument` = oznaka), **ne** `App.ActiveDocument` — drugo sejo, ki medtem
  preklopi dokument, vstavljanje ne sme zadeti (2026-10-09 je kos po pomoti pristal v »Elektro TV - A«). Ime povezave je
  ASCII (`newObject` z ne-ASCII imenom pade, #12164), oznaka = oznaka kosa. `baza.tarca` korene išče po `InList` znotraj
  dokumenta: `RootObjects` je za kos, na katerega kaže povezava iz drugega odprtega dokumenta, prazen.
- **Elektro kosi, parametrični** (od 2026-10-09, `lastno/elektro/lastna_elektro.py`, v `Mod` stičišče `lastna_elektro`):
  `Kanal` (kabelski kanal z režami in pokrovom, izhodišče spodnji vogal, dolžina +X) in `DinLetev` (TS35, X vzdolž letve,
  Z = 0 vrh letve, telo v −Z kot napajalniki Mean Well). Kosa v bazi `Standardni deli/Elektro/ELEKTRO - Kanal 25x40` in
  `ELEKTRO - DIN letev TS35` gradi `Standardni deli/_Skripte/elektro_parametricni.py` (prek `izvedi.py`; `PREPISI = True`
  prepiše obstoječa). Lastnosti ne poimenuj `Debelina` (baza po njej prepozna pločevino). Obstoječe spone v bazi so
  poenostavljeni kvadri iz SolidWorksa (8 mm korak), ne modeli proizvajalca.
- **Pločevina** (od 2026-10-08): znanje `lastno/raziskava/plocevina.md`; dodatek SheetMetal in networkx v `%APPDATA%\FreeCAD1-1`.
  Lastna parametrična objekta `lastno/plocevina/lastna_plocevina.py` (`TeloVPlocevino`, `Razgrnitev`) ploskve in robove
  poiščeta geometrijsko ob vsakem preračunu; SheetMetal objekti s shranjenimi imeni (`Face4`, `Edge14`) se ob spremembi mer
  pod posnetimi robovi pokvarijo (`missing element reference`). Mapa je v `Mod` povezana s stičiščem `lastna_plocevina`
  (README v mapi). Zgled: `Oblak/3D modeliranje/Betonski podstavek/` (mere na objektu »Mere (uredi tukaj)«).
  Razgrnitev je v dokumentu dela privzeto skrita (`Visibility = False`; uporabnik je ne želi videti ob kosu).
  STEP iz »Solid to Sheet Metal«: nekaj ploskev OCC zapiše, bralnik pa izpusti (odprta lupina) — pred izvozom jih pretvori v
  NURBS (`izvozi_step.py` v projektu); krog zapis-branje STEP v procesu spletnega FreeCAD-a sproži Access violation, zato v FreeCADCmd.
- **SolidWorks -> FreeCAD** (2026-10-08, zgled `Oblak/3D modeliranje/Photobox Slim/Skripte/`): SolidWorks prek COM s Pythonom
  (pywin32, `win32com.client.dynamic`; pozna vezava metodo brez argumentov pokliče že ob branju atributa). VBScript ne zna
  brati polj objektov (`GetChildren`, telesa), PowerShell s SolidWorksovim COM ne dela. Odpiraj z `GetOpenDocSpec` +
  `OpenDoc7` (`ReadOnly`, `Silent`), izvoz `SaveAs3(pot.step, 0, 1)`. Izvoz razgrnitev (`ExportToDWG2`) pri odprtem celem
  sestavu je SolidWorks pripeljal do »out of memory« — dele izvažaj posamič (odpri, izvozi, zapri). Navidezni deli imajo
  začasno pot, ki se spremeni ob vsakem zagonu. `Component2.Transform2.ArrayData`: globalna lega glede na koren, metri,
  vrstični vektor (p' = p R + t). Gradnja z ImportGui v ločenem primerku spletnega FreeCAD-a (vrata 3031, ločen
  LOCALAPPDATA); povezava na drug dokument zahteva, da je sestav že shranjen. Primerek s ~140 dokumenti se ob Izhodu lahko
  obesi (Access violation) — preveri, da se je končal, preden ga zaženeš znova.
  **Mate -> spoji** (od 2026-10-09, `Skripte/sw_mate_geometrija.py` + `mate_v_spoje.py` v projektu): geometrija referenc iz
  `IMateEntity2.EntityParams` (točka, smer, polmera; koordinate sestava, metri; `ReferenceType` 3 = ravnina, 4 = valj).
  Spoj iz skripte: najprej `Offset1`/`Offset2` (in `Distance`), **šele nato** `Reference1`/`Reference2` — sprememba odmika
  ob nastavljenih referencah sproži `Joint.onChanged` -> `preSolve`, ki kos premakne, preden je drugi odmik nastavljen.
  Gibljiv podsestav: `Assembly::AssemblyLink` (`LinkedObject`, `Placement` stare povezave, `recompute`, nato `Rigid = False`);
  kopira kose in spoje podsestava vase, spoji nadrejenega sestava se sklicujejo na kopije kosov. Podsestav, ki je v SolidWorksu
  gibljiv, ima samostojno drugačne lege kot v nadrejenem sestavu: geometrijo mat preslikaj po kosih, ne z eno preslikavo.
  **V spletnem strežniku ne poganjaj Boolovih operacij v zanki** (`common` pločevinastih lupin): glavna nit obvisi za več deset
  minut, strežnik ne sprejema povezav (ERR_CONNECTION_REFUSED). Za trke uporabi oglišča in obsege.
- **Shranjevanje v strežniku** (popravljeno 2026-10-08): `FileInfo::isWritable` odpre datoteko brez deljenja; če jo kdo drži
  odprto (tudi isti proces), FreeCAD zavrne shranjevanje z »file is marked as read-only«. Strežnik je pri branju vrste
  dokumenta (`_lastnosti_fcstd`) puščal odprt tok `z.open("Document.xml")` v `ET.iterparse` -> drugo shranjevanje istega
  dokumenta iz brskalnika ni uspelo. Tokove iz zipa vedno zapiraj z `with`. Kdo drži datoteko: Restart Manager (`RmGetList`).
  Shranjevanje prek `App.Document.save()/saveAs()` v GUI ne počisti oznake »neshranjeno« (to naredi le `Gui::Document::save`):
  po shranjevanju iz skripte nastavi `Gui.getDocument(ime).Modified = False`.
- **Telesa pod drevesom** (od 2026-10-08): posnetek drevesa nosi `telesa` (koreni drevesa s trdno obliko, `drevo._telesa`);
  stran pokaže razdelek »Telesa (N)« pod drevesom, ko jih je več kot eno (številka, ime = Label, število ločenih teles, cm³).
  Imena teles: »<kos> – <stanje>« (npr. »Podstavek – upognjen«, »Podstavek – razgrnitev«).
- **Povezave na druge datoteke v drevesu** (od 2026-10-08): vozel `App::Link` na objekt v drugem dokumentu nosi `povezava`
  {dokument, sestav}; gumb ↗ Odpri (dvojni klik, desni klik) odpre ta podsestav ali del (`drevo._odpri_povezano`: delno
  naložen dokument — `Document.Partial` — se naloži v celoti z `restore()`, nato postane dejaven). Seznam odprtih
  dokumentov je razdeljen: zgoraj Sestavi (N), spodaj Deli (N).
- **Izrisi kosov in razporeditev** (od 2026-10-08): vsak vozel drevesa z geometrijo v pogledu ima 40 px izometrični izris samo
  tega kosa (`izrisiIzometrijo(ime, velikost, zunanja)`; vozel brez lastne geometrije — sestav, App::Part, skupina — izriše
  vse svoje vidne potomce z geometrijo skupaj, `imenaZaIzris`; izrisi gredo po vrsti, predpomnilnik po dokumentu, imenu in velikosti
  mreže); prehod z miško čez vrstico kos v pogledu obarva oranžno (`osvetli`). Dokumenti brez sličice v seznamu odprtih se
  izrišejo v ozadju brez preklopa: `GET /posnetek?ime=` (glavna nit zgradi geometrijo dokumenta) -> ločena skupina scene ->
  `POST /slicica`. Stranski stolpec (dokumenti in drevo) sega čez celo višino levo; glava in pogled sta v `#desno`.
- **Zgradba sestava** (od 2026-10-09): gumb ☰ Zgradba v glavi stranskega stolpca (aktivni dokument) in ☰ pri vsakem sestavu v
  seznamu odpre okno z drevesno shemo od leve proti desni (`GET /zgradba?ime=` -> `_zgradba_dokumenta`: sledi App::Link čez
  datoteke, enake cilje združi s količino, vrsta iz lastnosti Vrsta). Klik na kartico odpre sestav ali del; ▸/▾ veja. Med urejanjem značilnosti je objekt v predogledu vključen v posnetek, čeprav je `Visibility` še False.
- **Spoji (mate) na kosih** (od 2026-10-09): ob izbiri spoja sestava (klik v drevesu) `posodobi_izbiro` doda vnosu izbire
  `spoj` [{objekt, elementi, tocke}] (`_reference_spoja`): podpot iz `Reference1/2` (npr. `Link003.Link002.Face9`) se razreši z
  `obj.getSubObject`, indeks v `obj.Shape` (= posnetek) najde `isPartner` (več primerkov istega kosa loči težišče); predpomnilnik
  `_REFERENCE_SPOJEV`. GroundedJoint označi cel kos. Brskalnik (`oznaciSpoje`) prvo referenco obarva modro, drugo vijolično in ju
  nariše še prosojno čez model (stični ploskvi se prekrivata ali sta skriti v sestavu).
- **Baza standardnih delov** (od 2026-10-09, `lastno/splet/baza.py`, `POST /standardni {dejanje: podatki|oznaci|odznaci, ime |
  dokument, kategorija}`, brskalnik počaka na `{ok, sporocilo}`): uporabnik sam označi kos (dokument dela ali sestava) kot standardni
  z desnim klikom v drevesu. Oznaka je lastnost `Vrsta` (»standardni del« / »standardni sestav«) na glavnem objektu (`tarca`).
  Označen kos se **premakne** (`os.replace`, nato `saveAs`, brez .FCBak) v `Oblak/3D modeliranje/Standardni deli/<kategorija>/`
  (prepis `SPLET_BAZA`, `SPLET_MODELIRANJE`); s kosom gresta STEP in `DXF/<ime>.dxf`. Z `novo_ime` (od 2026-10-10) se kos ob
  premiku preimenuje (datoteka, STEP in oznaka dokumenta). Proizvajalci in njihovi kontakti: `Standardni deli/_Proizvajalci/proizvajalci.md`,
  katalogi v `<kategorija>/_katalogi/`, na kosu lastnosti `Proizvajalec`, `Model`, `Katalog` (skupina Kos). Pred premikom se odprejo vsi FCStd iz 3D
  modeliranja, katerih `<XLink file=...>` v Document.xml kaže na kos (`kdo_uporablja`), delno naloženi se naložijo v celoti
  (delnega ni mogoče shraniti). FreeCAD ob `saveAs` dela sam popravi poti v odprtih sestavih (DocInfo::slotSaveDocument); ti se
  shranijo, kar je odprto le za to, se zapre. Ob premiku **sestava** njegove odhodne povezave obdržijo staro relativno pot:
  `_osvezi_povezave` jih nastavi znova (None, nato ista vrednost). Enak kos z istim imenom v bazi (telesa, ploskve, prostornina,
  površina, lokalna škatla) -> sestavi se preusmerijo nanj, drugačen -> zavrnitev. »Ni standardni« vrne kos iz baze v projekt, ki ga
  uporablja (Deli/Ostali, Deli/Pločevina, Sestavi); če ga uporablja več projektov ali sestav v bazi, ostane. Med premikom
  `STANJE.tiho_shranjevanje` utiša vprašanje »Kaj si spremenil?«. Drevo nosi `standardni {standardni, vBazi, sestav}` (značka STD).
- **Število kosov (konfiguracija)** (od 2026-10-09, `drevo._nastavi_kosov`, `POST /drevo {dejanje: kosov, ime, stevilo}`): v bazi je
  en kos (zgled: spone za DIN letev `Standardni deli/Elektro/ELEKTRO - Spona zemlja|faza|nula`, lastnost `Korak` = razmik 8 mm),
  sestav ga vstavi kot vrsto n kosov vzdolž osi X kosa (desni klik v drevesu -> Število kosov, značka ×n). Vrsta je povezava z
  elementi (`ElementCount`, `ShowElement = True`); **sestav zahteva ničelno lego take povezave** (`ensureIdentityPlacements` ob
  preračunu, s `ShowElement = False` kose vrže v izhodišče), lego nosi vsak `LinkElement`. Kos s spoji (razen pritrditve) zavrne.
- Skica v brskalniku (`POST /skica`, dogodek `skica`): `nova` (ravnina XY/XZ/YZ ali ploskev modela: okno Nova skica ne pokriva pogleda, ploskev se klikne med odprtim oknom; odmik, obrni, v telesu),
  `odpri`, `zapri`, `crta` (s `spoji1`/`spoji2` za sovpadanje), `pravokotnik` (4 črte + sovpadanja + vodoravno/navpično),
  `krog`, `tocka`, `premakni` (movePoint, reševalnik), `izbrisi`, `mera` (Distance/Radius), `omejitev`, `gradbena`.
  Vse v transakcijah (Razveljavi dela). FreeCAD-ov način urejanja skice se ne uporablja; brskalnik riše skico sam
  (pravokotna kamera, pripenjanje na točke, vlečenje točk), posnetek skice ne vključuje skice v urejanju.
  Pripenjanje na model (kot v SolidWorksu): pri Črti, Pravokotniku, Krogu in Točki se kazalec pripne na krajišča,
  razpolovišča, središča in kvadrante robov modela ali na poljubno točko roba (zelena oznaka z imenom roba). Ob kliku
  strežnik rob doda kot zunanjo geometrijo (`addExternal`, GeoId -3 ...) in točko veže z Coincident / Symmetric /
  PointOnObject. Posnetek modela nosi `robInfo` (analitika robov), posnetek skice `zunanji`. Skrite robove (za ploskvami)
  stran izloči z žarkom. Rob objekta zunaj telesa v skici telesa ni mogoč: točka nastane brez vezave (zapis v dnevnik).
  Orodja skice v brskalniku nosijo FreeCAD-ove ikone (`IKONE_SKICE` v strežniku, `Gui.getIcon`, slovar `skica` v `/ukazi`).
  Brskalnik prestreže ukaze Nov očrt / Edit Sketch / Leave Sketch ter Izboklino in Ugrez iz izbrane skice
  (`POST /znacilnost`, dolžina se vpraša v brskalniku). Urejanje skice, ki ga začne FreeCAD sam, strežnik prekine
  (`resetEdit`) in skico odpre v brskalniku.
- Stranski meni (od 2026-10-07, levo od pogleda, širina 520 px, **dva stolpca**: levo odprti dokumenti, desno drevo dokumenta;
  gumb ◀ ga skrije, ▶ Dokumenti in drevo pokaže; stanje v `localStorage`). Levi stolpec:
  samo razdelek Odprti dokumenti (aktivni poudarjen, `*` ob neshranjenih, × zapre; brskalnik vpraša, če so spremembe).
  Razdelka Projekti (datoteke FCStd iz `%USERPROFILE%\Oblak\3D modeliranje`, okoljska `SPLET_PROJEKTI`) in Oblak · različice
  sta 2026-10-07 odstranjena iz prikaza (strežnik `skupine` še pošilja, koda `vnosDatoteke`/`razdelekOblaka` ostaja neuporabljena);
  razdelek Nedavne datoteke je bil odstranjen isti dan. Klik preklopi na odprti dokument. Strežnik: `GET /projekti`, dogodek `projekti` (vsaki 2 s le ob spremembi,
  takoj ob dogodkih dokumenta), `POST /projekt {dejanje: odpri|aktiviraj|zapri, pot|ime}`. Neshranjene spremembe
  pozna le `Gui.getDocument(ime).Modified` (`App.Document` te lastnosti nima).
  Vsak vnos nosi sličico modela (render, ki ga stran izriše iz svojega 3D pogleda in pošlje s `POST /slicica`; strežnik
  jo hrani v `%LOCALAPPDATA%\FreeCAD-splet\slicice`, streže `GET /slicica?pot=`). Render (`izrisiSlicico`): izometrija,
  pravokotna kamera, prilegana po projiciranih ogliščih mrež (ne po krogli), prozorno ozadje, 192 px iz dvakrat večjega izrisa
  (glajenje), brez mreže, osi in izbire; `cilj.texture.colorSpace = SRGBColorSpace`, WebGPU vrne vrstice s korakom 256 bajtov.
  FreeCAD-ova vgrajena sličica iz FCStd je le rezerva in le, če jo `_uporabna_slicica` (Pillow) oceni kot uporabno: iz skritega
  okna nastane prazna ali sivo odrezana (vsebina ob robu), take se ne strežejo; prazen render strežnik zavrne (400) in ga ne hrani.
  Datoteke, shranjene iz skritega okna, imajo pogosto `Thumbnail.png` z **0 bajti**: ta ni uporabna (do 2026-10-09 je napaka pri
  branju veljala za »uporabno«, zato stran zanje ni izrisala sličice). Če se sličica v brskalniku ne naloži, jo stran izriše sama.
  Brez sličice stran pokaže ikono kocke (`IKONA_KOCKE`; črtkana = dokument še ni shranjen)
  in oznako vrste **Sestav** / **Del** (`vrsta` v `/projekti`: `_vrsta_iz_tipov` po tipih objektov, za datoteke iz
  `Document.xml` v FCStd, za odprte dokumente iz `TypeId`; sestav = Assembly, App::Link ali več App::Part, del = telesa).
  Ikona zavihka: `/favicon.ico` (pravi ICO 16–64 px, `favicon.ico`, narejen s Pillow iz `ikona.png`) in `/ikona.png` (64 px, iz
  `ikona.svg` prek Qt brez zaslona); v `<head>` s parametrom `?v=N` (brskalniki ikono trdovratno predpomnijo, ob zamenjavi
  dvigni N). SVG se v `<head>` ne navaja (okno aplikacije Claude in nekateri brskalniki ga ne prikažejo).
- **Videz seznama odprtih dokumentov** (od 2026-10-09, samo `index.html`, levi stolpec v slogu drevesa): glava `#dokumentiGlava`
  (deli sloge z `#drevoGlava`) s številom in iskanjem po imenu (Enter preklopi na prvi zadetek, Esc počisti), skupini Sestavi/Deli s
  števcem, vrstica `vnosOdprtega`: sličica z značko vrste (`okvirVnosa`), čipi (`cipVnosa`: vrsta, Neshranjeno namesto `*`, različica,
  zaklep), ikonski gumbi (`gumbVnosa`: različice, zgradba, zapri) plavajo čez desni rob le ob miški, da imenu ne jemljejo širine.
- **Sodobna podoba** (od 2026-10-09, CSS v `index.html`): barve, sence in zaobljenost so žetoni v `:root` (`--poudarek` #2563eb,
  `--poudarekMehko`, `--crta`, `--crtaMocna`, `--besedilo2/3`, `--lebdenje`, `--senca1/2`, `--obroc`, `--steklo`); novih barv ne piši v
  posamezna pravila. Zavihki okolij so podčrtani, `#pogledi`, `#namig` in `#stranskiPokazi` so steklene plavajoče ploščice, vsa okna
  (obrazec, različice, zgradba, nova skica, standardni del) dobijo skupno površino in gumbe iz bloka »Skupni sodobni videz« na koncu sloga.
  Več sej hkrati na `index.html`: samo ciljni Edit, nikoli zapis cele datoteke. Vgrajeni brskalniki vseh sej si delijo 6 povezav na
  gostitelja (vsak zavihek drži SSE `/events`); če stran obvisi pri »Povezujem«, odpri `http://localhost:3020/` namesto `127.0.0.1`.
- **Trak in vrstica stanja** (od 2026-10-09, `index.html`): vsaka orodna vrstica okolja je plošča z napisom spodaj (`.orodna` >
  `.vsebina` + `.napisOrodne`; kratka slovenska imena v `NASLOVI_ORODNIH`, sicer naslov brez predpone okolja). Orodne vrstice iz menijev
  (`meni: true`) niso na traku, ampak v enem gumbu »Ostali ukazi ▾« (`odpriMeniMenijskih`, razdeljeno po menijih). Ob premalo prostora
  `zgostiTrak` zgošča plošče od najširše naprej (le prvi gumb skupine velik), ne vsega traku. Zavihki okolij so slovenski
  (`LASTNI_NASLOVI` v strežniku = vsa `DELOVNA_OKOLJA`; FreeCAD-ov prevod jih pušča v angleščini). `#hud` je v vrstici stanja
  `#statusna` pod pogledom (levo dokument in izbira, desno tehnični podatki), ne več v glavi.
- **Videz drevesa** (od 2026-10-09, samo `index.html`): lastne SVG ikone po vrsti (`POTI_IKON`, `opisVozla`; FreeCAD-ova ikona le
  za neznane vrste), spoji kot »A → B« s čipom vrste iz `JointType` (`VRSTE_SPOJEV`; pripona » · vrsta« iz oznake gre v čip),
  skupina Spoji na koncu sestava pokaže le spoje, ki niso pod nobenim kosom, in izgine, če takih ni (želja uporabnika
  2026-10-09; `podKosom` v `otrociVozla`), vsak spoj je pod obema kosoma, ki ju povezuje (vozel spoja nosi `deli`
  iz `drevo._deli_spoja`: Reference1/2 ali ObjectToGround; pod kosom so spoji drobni čipi v eni vrsti, ki se prelomi (`spojnicaKosa`: ikona vrste v barvi vrste + ime drugega kosa, vrsta v namigu; čip je `.vozel`, zato izbira, tipkovnica in meni delujejo enako; želja uporabnika 2026-10-09, da je drevo čim krajše), ob miški se osvetlita oba;
  vrstice imajo zato ključ po poti `data-kljuc`, po katerem gre tudi tipkovnica), iskanje v glavi drevesa (zadetki in predniki, veje razprte), Razpri/Strni vse,
  tipkovnica pri fokusu na drevesu (↑↓ ←→ Home End, Enter uredi, preslednica vidnost; ostale tipke gredo pogledu), dejanja
  (uredi/odpri, oko) ob miški. Širina stranskega menija in seznama dokumentov se vleče (`.locilnik`, `localStorage`
  `sirinaStranski`/`sirinaDokumentov`, dvojni klik vrne privzeto).
- Drevo dokumenta (od 2026-10-07, `lastno/splet/drevo.py`, desni stolpec stranskega menija): objekti kot v FreeCAD-ovem
  drevesu (`ViewObject.claimChildren`, koreni so nezahtevani objekti), z ikono, vidnostjo (oko -> `POST /drevo
  {dejanje: vidnost, ime, vidno}`) in izbiro (klik -> `/select`, Ctrl doda). Razdelek Lastnosti pod drevesom je
  2026-10-09 na željo uporabnika odstranjen iz strani; strežnik lastnosti vozlov še pošilja (stran iz njih bere vrsto spoja)
  in `POST /drevo {dejanje: lastnost, ime, lastnost, vrednost}` še deluje. Posnetek `/model` nosi ključ `drevo`
  (koreni, vozli); brez njega stran javi, da je strežnik starejši. Razprti vozli so v `localStorage` po dokumentu. Urejanje iz drevesa (od 2026-10-08): gumb ✎ v vrstici (napis Uredi ob miški in na izbrani vrstici), dvojni klik, desni klik -> Uredi -> `POST /drevo {dejanje: uredi, ime}` (`drevo._uredi`): skica se odpre v urejevalniku skic v brskalniku, sicer `ViewObject.doubleClicked()` kot v FreeCAD-ovem drevesu (značilnost odpre opravilo -> obrazec desno, telo ali App::Part postane dejavno); med odprtim urejanjem strežnik drugo zavrne z dogodkom `obvestilo {sporocilo, slabo}`. Zajem seznamov v obrazcih: `QAbstractListModel.columnCount` je v PySide zaseben, šteje se kot en stolpec. Prikaz skice (od 2026-10-08): skica se riše nad modelom (materiali `NAD`: depthTest/depthWrite false, renderOrder), črte skice so debele (`LineSegments2` + `THREE.Line2NodeMaterial` iz addons/lines/webgpu, rezerva tanke črte), črna = v celoti določena, modra = ne (posnetek skice nosi `dolocena` = `sk.FullyConstrained`). Kote (`narisiMere`): DistanceX/Y zložene nad/pod oz. levo/desno od obsega skice s pomožnimi črtami in puščicami, Distance vzporedno, Radius/Diameter z vodilom; klik na koto odpre vnos na mestu (Enter ali klik drugam potrdi, Esc prekliče) -> `POST /skica {vrsta: nastaviMero, id, vrednost}` (`setDatum`, kot v °). Vlečenje kote (`zacniVlecenjeKote`, premik nad 4 px; brez premika je klik) jo premakne in shrani lego v omejitev kot FreeCAD (`POST /skica {vrsta: polozajMere, id, razmik, polozaj}` -> `setLabelDistance`/`setLabelPosition`, brez preračuna): razdalje: kotirna črta odmaknjena za LabelDistance po normali (-dir.y, dir.x) od druge točke, napis za LabelPosition vzdolž dir od sredine; polmer/premer: LabelPosition = kot vodila, LabelDistance = napis od kroga navzven. Privzeti vrednosti (10 in 0, pri polmeru 10 in 10) pomenita samodejno razporeditev okrog skice. `prilagodiPogledSkice` pusti prostor za kote. Skripte skic (npr. `nosilec_telo.py`) kotirajo obrise in odvečne omejitve pobrišejo po `RedundantConstraints`.
- Različice iz oblaka (od 2026-10-07, PDM korak 2, `lastno/splet/oblak.py`, plan `PDM-PLAN.md`): ob odprtem dokumentu
  iz mape odjemalca oblaka (privzeto iz `%APPDATA%\Oblak\nastavitve.json`: `folder`, `api`; prepis `SPLET_OBLAK_MAPA`,
  `SPLET_OBLAK_API`) je gumb ⟲, ki odpre ploščo z različicami: prijava v oblak (strežnik se prijavi kot **lastna**
  naprava »FreeCAD (splet)« — žetona odjemalca za Windows ne uporabljamo, ker bi oblak spremembe štel za njegove in jih
  odjemalec ne bi prenesel; seja v `%LOCALAPPDATA%/FreeCAD-splet/oblak.json`), seznam (`GET /oblak/zgodovina?pot=`),
  Odpri (`POST /oblak/odpri {pot, rev}`: prenos v `%LOCALAPPDATA%/FreeCAD-splet/razlicice/` in odprtje kot
  »ime · različica N«, oznaka »ogled različice«; Label se ne nastavlja, ker bi dokument označil kot spremenjen), Povrni
  (`POST /oblak/obnovi {pot, rev}`: nova revizija v oblaku; strežnik nato do 3 min opazuje lokalno datoteko, ki jo
  zamenja odjemalec oblaka, odprt dokument brez neshranjenih sprememb osveži in pošlje dogodek `oblak`). Klici v oblak
  tečejo na niti strežnika (brez FreeCAD API-ja), odpiranje in osvežitev prek vrste (`projekt`: `odpri-razlicico`,
  `osvezi`). Lokalna pot -> prostor: `Osebno/...` osebni prostor, `<skupina>/<prostor>/...`, `<prostor>/...`.
  Preizkusni primerek: `SPLET_VRATA=3031` (3029 pogosto zaseda drug primerek) z ločenim `LOCALAPPDATA`, da ne povozi
  `povezava.json` glavnega primerka; `cmd /c` iz Git Basha piši kot `//c` ali uporabi PowerShell `Start-Process`.
  Korak 3 (komentar, stanja, oznake): po shranjevanju datoteke iz mape oblaka (`slotFinishSaveDocument` v
  `OpazovalecDokumenta`) strežnik odda dogodek `oblak` vrste `shranjeno`, brskalnik vpraša »Kaj si spremenil?« in pošlje
  `POST /oblak/komentar {pot, komentar}`; ker datoteko v oblak pošlje odjemalec oblaka, `oblak.py` komentar pripne
  reviziji z enakim `content_hash` (sha256 nad sha256 kosov po 4 MiB) takoj ali v ozadju do 3 min. `POST /oblak/revizija
  {pot, rev, komentar?, stanje?}` nastavi komentar ali stanje (osnutek, v_pregledu, izdano; izdaja dodeli oznako).
  `Document.save()` na datoteki, ki je bila ob odpiranju samo za branje, javi »read-only« tudi po odstranitvi atributa
  (uporabi `saveAs` na isto pot); tik po pisanju lahko Windows datoteko za hip zaklene (ponovi po 2 s).
  Korak 4 (zaklepi): `zgradi_projekte` za vsak odprt dokument iz mape oblaka pokliče `OBLAK.zaklep_dokumenta` (iz
  predpomnilnika; ob prvem klicu sproži samodejni `POST /v1/zakleni` v ozadju), `slotDeletedDocument` zaklep sprosti,
  `izhod` in `aboutToQuit` pokličeta `odkleni_vse` (rok 5 s). Zaklep pripada uporabniku, zato odjemalec oblaka na istem
  računalniku datoteko še vedno pošlje; tuj zaklep pomeni 409 `locked` pri commitu drugega uporabnika. Poti:
  `GET /oblak/zaklep?pot=`, `POST /oblak/zakleni|odkleni|prevzemi {pot}`; sprememba zaklepa v ozadju pošlje
  `("projekt", {"dejanje": "osvezi-seznam"})` v vrsto glavne niti, da se seznam odprtih dokumentov znova zgradi.
  Korak 5 (reference, kosovnica): bere jih oblak iz `Document.xml` (`packages/api/src/fcstd.ts`), FreeCAD le prikaže
  (`GET /oblak/reference?pot=` → `razdelekReferenc` na dnu plošče z različicami; poti povezanih datotek se preslikajo
  nazaj v lokalne, klik jih odpre). Odpiranje sestava s povezavami (XLink) v FreeCAD-u samodejno odpre tudi povezane
  dokumente — vsi dobijo zaklep in ga ob izhodu sprostijo.
- Obrazci (od 2026-10-07): **vsa** okna FreeCAD-a gredo v brskalnik, okno FreeCAD-a se ne pokaže. Filter dogodkov na
  aplikaciji vsako novo okno (pogovor, sporočilo, izbira datoteke) ob prikazu naredi nevidno (prosojnost 0, zunaj zaslona,
  brez fokusa tipkovnice; skriti ga ne sme, ker `hide()` konča modalni pogovor). Vsakih 250 ms `_zajemi_obrazec` prebere
  okno, ki čaka (modalno, nevidno nemodalno ali podokno Opravila, `Gui::TaskView::TaskView`), v JSON po postavitvah
  (oznake, vnosi, številska polja z enotami, spustni seznami, kljukice, gumbi, seznami, zavihki, skupine) in ob
  spremembi pošlje dogodek `obrazec`; brskalnik ga izriše v plošči desno (ne pokriva pogleda, da se lahko izbirajo robovi).
  `POST /obrazec {kljuc, id, dejanje, vrednost}` vpiše vrednost v pravi gradnik; kliki gredo prek Qt vrste dogodkov.
  Kliki iz vrste tečejo **mimo modalnosti**, zato (od 2026-10-09): oznaka okna je številka v lastnosti Qt `_spletOkno` (`_kljuc_okna`; `id()` ovoja se
  ponovi pri naslednjem oknu iste vrste), ponovljen klik na isti gumb v 1,5 s se zavrne, dejanje se izvede le, če je okno še aktivno modalno
  (`_obrazec_se_caka`); brskalnik gumba 1,5 s ne pošlje znova. Brez tega je dvojni klik na »Počisti« v Obnovitvi dokumentov sprožil obnovo.
  `QFileDialog` ima svoj obrazec (mapa, vsebina, filter, ime); zato strežnik med delovanjem vklopi
  `Preferences/Dialog/DontUseNativeDialog` in ga ob izhodu vrne (nastavitev je skupna z nameščenim FreeCAD-om).
  Gumb »Odpri v FreeCAD-u« v obrazcu je rezerva, če kakšnega gradnika obrazec ne zna prikazati.
- **Skripte v FreeCAD-u brez novega okna:** `FreeCAD.exe skripta.py` vedno odpre okno; ne uporabljaj ga za pomožne skripte.
  Od 2026-10-07 zagon **nameščenega** `C:\Program Files\FreeCAD 1.1\bin\FreeCAD.exe` (z oknom) in odpiranje `.FCStd` prek
  povezave datotek v vseh sejah zavrne kavelj `~/.claude/hooks/blokiraj-freecad-okno.py` (pravilo v `~/.claude/CLAUDE.md`);
  `FreeCADCmd.exe` in lastna gradnja iz `.pixi/` nista prizadeta.
  Če spletni strežnik teče, kodo poženi v njem: `.pixi/envs/default/python.exe lastno/splet/izvedi.py skripta.py`
  (ali `-c "koda"`; vrne izpis in spremenljivko `rezultat`; vrata in žeton bere iz `%LOCALAPPDATA%/FreeCAD-splet/povezava.json`).
  Brez strežnika uporabi `FreeCADCmd.exe` (brez okna). Poti v Python nizih piši kot `r"C:\..."` ali s `/`
  (`"C:\Users"` je napaka zaradi `\U`, skripta se sploh ne zažene, FreeCAD pa obvisi z odprtim oknom).
- Vgrajeni brskalnik aplikacije Claude: gumbe klikaj prek `find` in `ref` (v zgoščenem traku so napisi skriti, zato raje
  `javascript_tool` s `querySelector('.gumb[data-ime=...]').click()`); klike po platnu daj v koordinatah posnetka zaslona
  (orodje jih preslika). `window.prompt` za preizkus povozi v JS.
- Preverjanje: `curl http://127.0.0.1:3020/stanje`, stran (napis v kotu: dokument, izbira, izris WebGPU ali WebGL 2).
  Vgrajeni brskalnik aplikacije Claude klika v CSS slikovnih pikah strani, ne v merilu posnetka zaslona.
- **Slike iz skritega FreeCAD-a:** `saveImage` deluje le za dokument, ki je nastal v tekočem primerku (`newDocument` ali skripta); dokument, odprt z `openDocument`, da prazno sliko (pogled brez velikosti). Za slike regala ga zgradi v dokumentu sobe (`soba_folija.py`) in skrij ostale kose, ali izberi objekte in `ViewSelection` + `ZoomOut`. Modeli so **zunaj repozitorija**, v Oblaku: `C:\Users\Uporabnik\Oblak\3D modeliranje\<Projekt>\` (od 2026-10-07; prej `lastno/modeli`). Vsak projekt ima datoteke FCStd/STEP/slike v korenu, skripte v podmapi `Skripte/` (izhod pišejo v mapo projekta, eno raven nad sabo) in `PREBERI.txt`. Zalogovnik folije: `Skripte/police_folija.py` v `FreeCADCmd` z `__file__` (gole oblike, DXF, kosovnica), `Skripte/zalogovnik_telo.py` (od 2026-10-07: isti kosi kot **telesa PartDesign s skicami**, žepi, zaokrožitvami, Part::Mirroring in kovice kot vrtenine prek App::Link; uvozi `police_folija.py` kot knjižnico z `SAMO_KNJIZNICA`, prostornine preveri proti golim oblikam; poganjaj prek `izvedi.py`, da dobi barve), `Skripte/soba_folija.py` v tekočem FreeCAD-u prek `izvedi.py` (brez `__file__` uporabi pot v Oblaku; zalogovnika v sobi sta App::Link na kose iz `zalogovnik.FCStd`). Past skic iz skript: skicirnik loke vodi le v nasprotni smeri urinega kazalca, zato lok podaj s središčem in kotoma (ne s tremi točkami), sicer sovpadanja potegnejo sosednje črte na napačno krajišče. Spletni posnetek povezavo (App::Link) riše prek posredovane `Shape` z lego povezave (brez lege vsebnikov; `getGlobalPlacement` povezava nima), zato povezave ne dajaj v vsebnik z lego.
- **Dvojniki po obnovi** (od 2026-10-08): FreeCAD-ova Obnova dokumentov ob zagonu odpre kopijo vsakega dokumenta iz vsakega nasilno končanega primerka in ne preveri, ali je ista datoteka že odprta (dva ubita primerka = isti dokument dvakrat). Strežnik zato 1,5 s po zadnjem novem dokumentu (ko se nič ne nalaga in ni modalnega okna) pokliče `_zapri_dvojnike`: od dokumentov z isto datoteko obdrži tistega z najnovejšim `LastModifiedDate`, ostale shrani s `saveCopy` v `%LOCALAPPDATA%/FreeCAD-splet/dvojniki` in zapre; nedotaknjene vzorčne dokumente »Preizkus« (`_je_vzorec`) zapre, ko je odprt kakšen drug dokument. Strežnik ustavljaj z gumbom Izhod (`POST /izhod`), ne z ubijanjem procesa.
- Če `povezava.json` manjka, strežnik pa teče (`/stanje` odgovarja), žeton piše v strani (`ZETON = '...'` v `GET /`); datoteko obnovi ročno (`vrata`, `zeton`, `pid` iz `tasklist`).
- Veja `ukazna-vrstica`: ustavljeno delo na C++ ukazni vrstici v slogu SolidWorksa; ne razvijaj naprej brez naročila.

## Način dela

- Vsaka sprememba na svoji veji iz `moje-spremembe`; po preverjeni gradnji združi nazaj. Commit sporočila v slovenščini.
- Push samo na `origin` (fork). Nikoli ne potiskaj na `upstream`.
- Posodobitev z uradnim FreeCAD-om: `git fetch upstream`, nato `git merge upstream/releases/FreeCAD-1-1` v `moje-spremembe`.
- Kje je kaj: `src/Base` osnove, `src/App` dokument in objekti, `src/Gui` uporabniški vmesnik (glavno okno
  `src/Gui/MainWindow.cpp`), `src/Main` ime programa, ikona, splash (`MainGui.cpp`), `src/Mod/<Ime>` delovne mize
  (C++ v `App/` in `Gui/`, Python ob njih; Python del ne potrebuje prevajanja).
- Uradna navodila: https://freecad.github.io/DevelopersHandbook/ (gradnja, slog kode, prispevanje).
