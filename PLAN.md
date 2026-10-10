# Plan: lastna kopija FreeCAD-a

Stanje 2026-09-29. Odločitve: osnova je veja `releases/FreeCAD-1-1` (nameščen je FreeCAD 1.1.3, veja je pri 1.1.4),
mapa `Desktop/Apps/FreeCAD`, javen fork `juskolaric/FreeCAD`.
**Smer od 2026-09-29 (pot 1): FreeCAD je motor, uporabniški vmesnik in grafika nastajata v brskalniku.**
Različice modelov (PDM nad lastnim oblakom): ločen plan `PDM-PLAN.md` (7. 10. 2026).
Prosto oblikovanje (Blender) in render: ločen plan `OBLIKOVANJE-PLAN.md` (10. 10. 2026, predlog).
Program kot MCP strežnik (AI z dostopom do vseh funkcij): ločen plan `MCP-PLAN.md` (10. 10. 2026, koraki 1–5 narejeni).

## Kaj je nastalo

- Fork uradnega repozitorija na GitHubu (`origin`), uradni FreeCAD kot `upstream`.
- Lokalni klon s podmoduli, delovna veja `moje-spremembe` nad `releases/FreeCAD-1-1`.
  Veja `ukazna-vrstica`: ustavljeno delo na ukazni vrstici v slogu SolidWorksa (C++), glej korak 7.
- Orodja: VS Build Tools 2022 s C++ (MSVC 14.44, Windows SDK 10.0.26100), pixi 0.81, git z vklopljenimi dolgimi potmi.
- Vpis v koren `Apps` (`.gitignore`, `CLAUDE.md`, `README.md`, pravilo za Cursor), odprte naloge v `Apps/TODO.md`,
  vrata 3020 v `Photolandia-Apps/ports.json`.
- `lastno/splet`: dokaz koncepta spletnega pogleda (strežnik v FreeCAD-u in stran s three.js/WebGPU).

## Koraki

1. [x] Odločitve (veja, mapa, GitHub)
2. [x] Orodja (C++ workload v Build Tools, pixi)
3. [x] Kopija (fork, klon, upstream, delovna veja, navodila `CLAUDE.md`)
4. [x] Prva gradnja 2026-09-29: `configure-release` 1 min, `build-release` 6756 korakov v 31 min brez napak, `install-release` 10 s
5. [x] Dokaz zanke 2026-09-29: oznaka »[lastna gradnja]« v naslovu okna (`src/Gui/MainWindow.cpp`); sprememba, gradnja (29 s), namestitev (30 s) in preverjanje z `lastno/preveri-naslov.py`
6. [x] Način dela zapisan v `CLAUDE.md`: veja na spremembo, gradnja le spremenjenega, občasni `git fetch upstream`
7. [x] Ukazna vrstica v slogu SolidWorksa (C++, `src/Gui/RibbonBar.*`): v1 prevedena in preverjena v Part Designu, v2 napisana in neprevedena; **ustavljeno 2026-09-29** na željo uporabnika, ostaja na veji `ukazna-vrstica`
8. [x] Dokaz koncepta spletnega pogleda 2026-09-29: model iz FreeCAD-a v brskalniku (three.js 0.186, WebGPU s preklopom na WebGL 2), izbira ploskev in robov v obe smeri, samodejna osvežitev ob spremembi modela, ukazi Python prek žetona; preverjeno v vgrajenem brskalniku
9a. [x] Okno FreeCAD-a skrito 2026-09-29: teče v ozadju, pokaže se samo, ko potrebuje vnos, gumba Pokaži/Skrij in Izhod v brskalniku; ukazi se sprožijo prek Qt vrste dogodkov, zato strežnik odgovarja tudi med modalnimi okni
9. [x] Ukazna vrstica v brskalniku 2026-09-29: vsi ukazi okolij Snovanje delov (28), Skica (52) in Del (34) ter hitri dostop, po zavihkih in skupinah kot v SolidWorksu (veliki in majhni gumbi, zgoščeni način, spustni meniji skupin, namigi, ikone iz FreeCAD-a), stanje »na voljo« v živo, klik izvede ukaz v FreeCAD-u (okno z nastavitvami se odpre v FreeCAD-u), zavihek Skica se pokaže sam med urejanjem skice; preverjeno: Kocka, Izboklina iz izbrane skice
10. [~] Pregledovalnik: drevo objektov in lastnosti v brskalniku (narejeno 2026-10-07: `lastno/splet/drevo.py`, stranski meni), več dokumentov, binarni prenos geometrije namesto JSON, robovi z debelino, boljše senčenje (okolje, sence)
11. [~] Okna z nastavitvami ukazov v brskalniku: Izboklina in Ugrez iz izbrane skice 2026-09-29 (dolžina, smer); ostali ukazi še v FreeCAD-u
12. [x] Urejevalnik skic v brskalniku, 1. različica 2026-09-29: nova skica na ravnini ali izbrani ploskvi (spletno okno), pravokotna kamera, črta in lomljena črta, pravokotnik, krog, točka, pripenjanje na točke s sovpadanjem, vlečenje točk z reševalnikom, mera (dolžina, polmer), gradbena, brisanje, napisi mer; preverjeno: ploskev → skica → pravokotnik + krog → zapri → izboklina, vse brez okna FreeCAD-a
13. [ ] Ločen repozitorij za spletni vmesnik (Next.js po vzoru ostalih programov); FreeCAD ostane motor s strežniškim delom v tej mapi

**Naslednji korak:** drevo objektov z lastnostmi (korak 10) ali nadaljevanje skice (loki, omejitve, kote, simetrija) in okna ostalih ukazov (zaokrožitev, vrtenina ...).

## Zgradba spletnega pogleda (dokaz koncepta)

- `lastno/splet/streznik.py` teče v FreeCAD-u (z oknom ali brez): HTTP strežnik v niti na `127.0.0.1:3020` bere le
  pripravljen posnetek geometrije, zahteve odloži v vrsto, obdela jih glavna nit (časovnik 50 ms). Posnetek se zgradi
  ob spremembi dokumenta (opazovalci dokumenta, pogleda in izbire) z zamikom 300 ms: teselirane ploskve z oznakami
  `Face{n}`, diskretizirani robovi `Edge{n}`, barve iz `ShapeAppearance`.
- `lastno/splet/index.html`: three.js z WebGPU, izbira z žarkom (ploskve in robovi), dogodki SSE `/events`
  (`model`, `izbira`, `aktivni`, `okolje`), izbira `POST /select`, ukazi `POST /ukaz`, okolje `POST /okolje`, Python `POST /python`;
  POST zahteva žeton, vpisan v stran. Seznam ukazov `GET /ukazi` nastane iz orodnih vrstic okolij (prevedena imena, namigi,
  ikone kot PNG, podukazi skupin); ob zagonu strežnik enkrat aktivira okolja Snovanje delov, Skica in Del, da ukazi obstajajo.
- Vir resnice za izbiro je FreeCAD: brskalnik pošlje klik, FreeCAD izbere, opazovalec izbire jo vrne vsem odjemalcem.
- Zagon: `lastno/splet/ZAZENI-SPLET.bat` (FreeCAD s strežnikom in brskalnik) ali `FreeCAD.exe lastno/splet/streznik.py`.

## Kje se kaj spreminja

- `src/Base` osnovne knjižnice, `src/App` dokument in objekti, `src/Gui` uporabniški vmesnik,
  `src/Main` zagon in identiteta programa (ime, ikona, splash).
- `src/Mod/<Ime>` delovne mize: C++ v `App/` in `Gui/`, Python ob njih. Python del ne potrebuje prevajanja.
- `CMakeLists.txt`, `cMake/`, `CMakePresets.json`, `pixi.toml` gradnja in okolje.
- `lastno/` lastne skripte in spletni pogled (Python in HTML, brez prevajanja).

## Ocene

| Postavka | Vrednost |
|---|---|
| Izvorna koda z zgodovino | 2,9 GB |
| pixi okolje (`.pixi/`) | 9,7 GB |
| Mapa `build/` po gradnji | 3,9 GB |
| Prva gradnja Release (20 niti) | 31 min |
| Ponovna gradnja po majhni spremembi | pod 1 min, namestitev 30 s |
| Posnetek vzorčnega modela za brskalnik | 52 kB, 2 objekta, 1500 trikotnikov |
