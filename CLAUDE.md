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
- Vir resnice za izbiro je FreeCAD (`Gui.Selection`): brskalnik pošlje klik, obarva pa šele to, kar FreeCAD javi.
- Posnetek geometrije (od 2026-10-07) ima **predpomnilnik po objektih** (`_PREDPOMNILNIK`, ključ: oblika prek povezanega objekta /
  otrok skupine, lega, barve, oznaka; vnos je že serializiran JSON). Ob preklopu dokumenta ali ponovnem izračunu se teselirajo le
  spremenjeni objekti (soba: 6 s -> 0,3 s). Oblika se ne kopira (`copy()` izgubi mrežo); točke se prestavijo z `getGlobalPlacement`.
  Skupine (`App::DocumentObjectGroup`) niso v posnetku (njihov `Shape` je le sestav otrok, ki so v posnetku vsak zase). Ob preklopu
  dokumenta se posnetek zgradi takoj (brez zamika 300 ms). Dnevnik: `posnetek N: X objektov (Y iz predpomnilnika), kB, s`.
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
- Ukazi v brskalniku so tisti iz orodnih vrstic okolij `DELOVNA_OKOLJA` (Snovanje delov, Skica, Del, od 2026-10-08 Pločevina =
  dodatek SheetMetal `SMWorkbench`, če je nameščen; znanje v `lastno/raziskava/plocevina.md`) in `HITRI_DOSTOP`;
  stanje »na voljo« se preverja vsakih 500 ms (`isActive`). Pri skritem oknu FreeCAD ne osvežuje omogočenosti dejanj
  (`MainWindow::_updateActions` le pri vidnem oknu), zato `_sprozi_ukaz` dejanje omogoči sam, če `isActive()` vrne True.
  **Ne dodajaj `Gui.addDocumentObserver` s `slotChangedObject`**: FreeCAD ta signal odda že iz konstruktorja ViewProviderja,
  opazovalec takrat ustvari Python ovoj osnovnega razreda in objekti Part potem nimajo `DiffuseColor` (SheetMetal Make Wall
  pade). Spremembe videza strežnik preverja vsako sekundo (`_videz_kljuc`).
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
  tega kosa (`izrisiIzometrijo(ime, velikost, zunanja)`, izrisi gredo po vrsti, predpomnilnik po dokumentu, imenu in velikosti
  mreže); prehod z miško čez vrstico kos v pogledu obarva oranžno (`osvetli`). Dokumenti brez sličice v seznamu odprtih se
  izrišejo v ozadju brez preklopa: `GET /posnetek?ime=` (glavna nit zgradi geometrijo dokumenta) -> ločena skupina scene ->
  `POST /slicica`. Stranski stolpec (dokumenti in drevo) sega čez celo višino levo; glava in pogled sta v `#desno`.
- **Zgradba sestava** (od 2026-10-09): gumb ☰ Zgradba v glavi stranskega stolpca (aktivni dokument) in ☰ pri vsakem sestavu v
  seznamu odpre okno z drevesno shemo od leve proti desni (`GET /zgradba?ime=` -> `_zgradba_dokumenta`: sledi App::Link čez
  datoteke, enake cilje združi s količino, vrsta iz lastnosti Vrsta). Klik na kartico odpre sestav ali del; ▸/▾ veja. Med urejanjem značilnosti je objekt v predogledu vključen v posnetek, čeprav je `Visibility` še False.
- **Baza standardnih delov** (od 2026-10-09, `lastno/splet/baza.py`, `POST /standardni {dejanje: podatki|oznaci|odznaci, ime |
  dokument, kategorija}`, brskalnik počaka na `{ok, sporocilo}`): uporabnik sam označi kos (dokument dela ali sestava) kot standardni
  z desnim klikom v drevesu. Oznaka je lastnost `Vrsta` (»standardni del« / »standardni sestav«) na glavnem objektu (`tarca`).
  Označen kos se **premakne** (`os.replace`, nato `saveAs`, brez .FCBak) v `Oblak/3D modeliranje/Standardni deli/<kategorija>/`
  (prepis `SPLET_BAZA`, `SPLET_MODELIRANJE`); s kosom gresta STEP in `DXF/<ime>.dxf`. Pred premikom se odprejo vsi FCStd iz 3D
  modeliranja, katerih `<XLink file=...>` v Document.xml kaže na kos (`kdo_uporablja`), delno naloženi se naložijo v celoti
  (delnega ni mogoče shraniti). FreeCAD ob `saveAs` dela sam popravi poti v odprtih sestavih (DocInfo::slotSaveDocument); ti se
  shranijo, kar je odprto le za to, se zapre. Ob premiku **sestava** njegove odhodne povezave obdržijo staro relativno pot:
  `_osvezi_povezave` jih nastavi znova (None, nato ista vrednost). Enak kos z istim imenom v bazi (telesa, ploskve, prostornina,
  površina, lokalna škatla) -> sestavi se preusmerijo nanj, drugačen -> zavrnitev. »Ni standardni« vrne kos iz baze v projekt, ki ga
  uporablja (Deli/Ostali, Deli/Pločevina, Sestavi); če ga uporablja več projektov ali sestav v bazi, ostane. Med premikom
  `STANJE.tiho_shranjevanje` utiša vprašanje »Kaj si spremenil?«. Drevo nosi `standardni {standardni, vBazi, sestav}` (značka STD).
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
  Brez sličice stran pokaže ikono kocke (`IKONA_KOCKE`; črtkana = dokument še ni shranjen)
  in oznako vrste **Sestav** / **Del** (`vrsta` v `/projekti`: `_vrsta_iz_tipov` po tipih objektov, za datoteke iz
  `Document.xml` v FCStd, za odprte dokumente iz `TypeId`; sestav = Assembly, App::Link ali več App::Part, del = telesa).
  Ikona zavihka: `/favicon.ico` (pravi ICO 16–64 px, `favicon.ico`, narejen s Pillow iz `ikona.png`) in `/ikona.png` (64 px, iz
  `ikona.svg` prek Qt brez zaslona); v `<head>` s parametrom `?v=N` (brskalniki ikono trdovratno predpomnijo, ob zamenjavi
  dvigni N). SVG se v `<head>` ne navaja (okno aplikacije Claude in nekateri brskalniki ga ne prikažejo).
- Drevo dokumenta (od 2026-10-07, `lastno/splet/drevo.py`, desni stolpec stranskega menija): objekti kot v FreeCAD-ovem
  drevesu (`ViewObject.claimChildren`, koreni so nezahtevani objekti), z ikono, vidnostjo (krogec ● / ○ -> `POST /drevo
  {dejanje: vidnost, ime, vidno}`) in izbiro (klik -> `/select`, Ctrl doda). Pod drevesom so urejljive lastnosti edinega
  izbranega objekta (dolžine, koti, števila, besedila, kljukice, naštevanja, lega `x; y; z`; Enter potrdi, Esc prekliče ->
  `POST /drevo {dejanje: lastnost, ime, lastnost, vrednost}`, nato `recompute`). Posnetek `/model` nosi ključ `drevo`
  (koreni, vozli); brez njega stran javi, da je strežnik starejši. Razprti vozli so v `localStorage` po dokumentu. Urejanje iz drevesa (od 2026-10-08): gumb ✎ v vrstici (napis Uredi ob miški in na izbrani vrstici), dvojni klik, desni klik -> Uredi ali gumb ✎ Uredi nad lastnostmi -> `POST /drevo {dejanje: uredi, ime}` (`drevo._uredi`): skica se odpre v urejevalniku skic v brskalniku, sicer `ViewObject.doubleClicked()` kot v FreeCAD-ovem drevesu (značilnost odpre opravilo -> obrazec desno, telo ali App::Part postane dejavno); med odprtim urejanjem strežnik drugo zavrne z dogodkom `obvestilo {sporocilo, slabo}`. Zajem seznamov v obrazcih: `QAbstractListModel.columnCount` je v PySide zaseben, šteje se kot en stolpec. Prikaz skice (od 2026-10-08): skica se riše nad modelom (materiali `NAD`: depthTest/depthWrite false, renderOrder), črte skice so debele (`LineSegments2` + `THREE.Line2NodeMaterial` iz addons/lines/webgpu, rezerva tanke črte), črna = v celoti določena, modra = ne (posnetek skice nosi `dolocena` = `sk.FullyConstrained`). Kote (`narisiMere`): DistanceX/Y zložene nad/pod oz. levo/desno od obsega skice s pomožnimi črtami in puščicami, Distance vzporedno, Radius/Diameter z vodilom; klik na koto odpre vnos na mestu (Enter ali klik drugam potrdi, Esc prekliče) -> `POST /skica {vrsta: nastaviMero, id, vrednost}` (`setDatum`, kot v °). Vlečenje kote (`zacniVlecenjeKote`, premik nad 4 px; brez premika je klik) jo premakne in shrani lego v omejitev kot FreeCAD (`POST /skica {vrsta: polozajMere, id, razmik, polozaj}` -> `setLabelDistance`/`setLabelPosition`, brez preračuna): razdalje: kotirna črta odmaknjena za LabelDistance po normali (-dir.y, dir.x) od druge točke, napis za LabelPosition vzdolž dir od sredine; polmer/premer: LabelPosition = kot vodila, LabelDistance = napis od kroga navzven. Privzeti vrednosti (10 in 0, pri polmeru 10 in 10) pomenita samodejno razporeditev okrog skice. `prilagodiPogledSkice` pusti prostor za kote. Skripte skic (npr. `nosilec_telo.py`) kotirajo obrise in odvečne omejitve pobrišejo po `RedundantConstraints`.
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
