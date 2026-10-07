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
  Naslov `http://127.0.0.1:3020/` (vrata po `Photolandia-Apps/ports.json`). Okolje: `SPLET_VRATA`, `SPLET_BRSKALNIK=0` ne odpre brskalnika,
  `SPLET_OKNO=vidno` pusti okno FreeCAD-a vidno (privzeto je **skrito**: skripta ga skrije takoj ob zagonu, pokaže ga sama,
  ko FreeCAD potrebuje vnos (modalno okno, opravilo, urejanje skice), in ga po koncu spet skrije; gumba v brskalniku:
  Pokaži/Skrij FreeCAD in Izhod). Možnost `--hidden` FreeCAD-a ni uporabna: po skripti se program konča.
  Zaprtje okna z X konča program, ko ni več odprtih vprašanj (`setQuitOnLastWindowClosed(False)` + filter dogodkov).
  Vrata 3021 zaseda tuj program (python.exe); za testni primerek uporabi `SPLET_VRATA=3029`.
- Pravilo niti: nit strežnika **nikoli** ne kliče FreeCAD API-ja. Bere le posnetek (bajti JSON), zahteve daje v vrsto,
  ki jo obdela glavna nit (QTimer 50 ms; brez okna zanka). Posnetek se zgradi ob spremembi dokumenta z zamikom 300 ms.
- Končne točke: `GET /` stran, `GET /model` posnetek, `GET /ukazi` seznam ukazov (okolja, orodne vrstice, skupine, ikone),
  `GET /events` SSE (`model`, `izbira`, `aktivni`, `okolje`), `GET /stanje`, `POST /select {objekt, element, dodaj}`,
  `POST /ukaz {ime, indeks}` (sproži QAction prek Qt vrste dogodkov), `POST /okolje {ime}` (Gui.activateWorkbench),
  `POST /okno {prikazi}`, `POST /izhod` (zapre dokumente brez shranjevanja in konča), `POST /python {koda}`. Vsak POST potrebuje glavo `X-Zeton` (žeton nastane ob
  zagonu in je vpisan v stran), da tuja spletna stran v brskalniku ne more poganjati kode v FreeCAD-u.
- Vir resnice za izbiro je FreeCAD (`Gui.Selection`): brskalnik pošlje klik, obarva pa šele to, kar FreeCAD javi.
- Ukazi v brskalniku so tisti iz orodnih vrstic okolij `DELOVNA_OKOLJA` (Snovanje delov, Skica, Del) in `HITRI_DOSTOP`;
  stanje »na voljo« se preverja vsakih 500 ms (`isActive`). Okna z nastavitvami ukaza (dolžina izbokline ...) se še odpirajo
  v FreeCAD-u. Med urejanjem značilnosti je objekt v predogledu vključen v posnetek, čeprav je `Visibility` še False.
- Skica v brskalniku (`POST /skica`, dogodek `skica`): `nova` (ravnina XY/XZ/YZ ali ploskev modela: okno Nova skica ne pokriva pogleda, ploskev se klikne med odprtim oknom; odmik, obrni, v telesu),
  `odpri`, `zapri`, `crta` (s `spoji1`/`spoji2` za sovpadanje), `pravokotnik` (4 črte + sovpadanja + vodoravno/navpično),
  `krog`, `tocka`, `premakni` (movePoint, reševalnik), `izbrisi`, `mera` (Distance/Radius), `omejitev`, `gradbena`.
  Vse v transakcijah (Razveljavi dela). FreeCAD-ov način urejanja skice se ne uporablja; brskalnik riše skico sam
  (pravokotna kamera, pripenjanje na točke, vlečenje točk), posnetek skice ne vključuje skice v urejanju.
  Brskalnik prestreže ukaze Nov očrt / Edit Sketch / Leave Sketch ter Izboklino in Ugrez iz izbrane skice
  (`POST /znacilnost`, dolžina se vpraša v brskalniku). Ostala okna z nastavitvami so še v FreeCAD-u.
- Vgrajeni brskalnik aplikacije Claude: gumbe klikaj prek `find` in `ref` (v zgoščenem traku so napisi skriti, zato raje
  `javascript_tool` s `querySelector('.gumb[data-ime=...]').click()`); klike po platnu daj v koordinatah posnetka zaslona
  (orodje jih preslika). `window.prompt` za preizkus povozi v JS.
- Preverjanje: `curl http://127.0.0.1:3020/stanje`, stran (napis v kotu: dokument, izbira, izris WebGPU ali WebGL 2).
  Vgrajeni brskalnik aplikacije Claude klika v CSS slikovnih pikah strani, ne v merilu posnetka zaslona.
- Veja `ukazna-vrstica`: ustavljeno delo na C++ ukazni vrstici v slogu SolidWorksa; ne razvijaj naprej brez naročila.

## Način dela

- Vsaka sprememba na svoji veji iz `moje-spremembe`; po preverjeni gradnji združi nazaj. Commit sporočila v slovenščini.
- Push samo na `origin` (fork). Nikoli ne potiskaj na `upstream`.
- Posodobitev z uradnim FreeCAD-om: `git fetch upstream`, nato `git merge upstream/releases/FreeCAD-1-1` v `moje-spremembe`.
- Kje je kaj: `src/Base` osnove, `src/App` dokument in objekti, `src/Gui` uporabniški vmesnik (glavno okno
  `src/Gui/MainWindow.cpp`), `src/Main` ime programa, ikona, splash (`MainGui.cpp`), `src/Mod/<Ime>` delovne mize
  (C++ v `App/` in `Gui/`, Python ob njih; Python del ne potrebuje prevajanja).
- Uradna navodila: https://freecad.github.io/DevelopersHandbook/ (gradnja, slog kode, prispevanje).
