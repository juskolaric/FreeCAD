# Plan: lastna kopija FreeCAD-a

Stanje 2026-09-29. Odločitve: osnova je veja `releases/FreeCAD-1-1` (nameščen je FreeCAD 1.1.3, veja je pri 1.1.4),
mapa `Desktop/Apps/FreeCAD`, javen fork `juskolaric/FreeCAD`.

## Kaj je nastalo

- Fork uradnega repozitorija na GitHubu (`origin`), uradni FreeCAD kot `upstream`.
- Lokalni klon s podmoduli, delovna veja `moje-spremembe` nad `releases/FreeCAD-1-1`.
- Orodja: VS Build Tools 2022 s C++ (MSVC 14.44, Windows SDK 10.0.26100), pixi 0.81, git z vklopljenimi dolgimi potmi.
- Vpis v koren `Apps` (`.gitignore`, `CLAUDE.md`, `README.md`, pravilo za Cursor), odprte naloge v `Apps/TODO.md`.

## Koraki

1. [x] Odločitve (veja, mapa, GitHub)
2. [x] Orodja (C++ workload v Build Tools, pixi)
3. [x] Kopija (fork, klon, upstream, delovna veja, navodila `CLAUDE.md`)
4. [x] Prva gradnja 2026-09-29: `configure-release` 1 min, `build-release` 6756 korakov v 31 min brez napak, `install-release` 10 s
5. [x] Dokaz zanke 2026-09-29: oznaka »[lastna gradnja]« v naslovu okna (`src/Gui/MainWindow.cpp`); sprememba, gradnja (29 s), namestitev (30 s) in preverjanje z `lastno/preveri-naslov.py`
6. [x] Način dela zapisan v `CLAUDE.md`: veja na spremembo, gradnja le spremenjenega, občasni `git fetch upstream`

**Naslednji korak:** odločitev uporabnika, kaj v programu spremeniti najprej.

## Kje se kaj spreminja

- `src/Base` osnovne knjižnice, `src/App` dokument in objekti, `src/Gui` uporabniški vmesnik,
  `src/Main` zagon in identiteta programa (ime, ikona, splash).
- `src/Mod/<Ime>` delovne mize: C++ v `App/` in `Gui/`, Python ob njih. Python del ne potrebuje prevajanja.
- `CMakeLists.txt`, `cMake/`, `CMakePresets.json`, `pixi.toml` gradnja in okolje.

## Ocene

| Postavka | Vrednost |
|---|---|
| Izvorna koda z zgodovino | 2,9 GB |
| pixi okolje (`.pixi/`) | 9,7 GB |
| Mapa `build/` po gradnji | 3,9 GB |
| Prva gradnja Release (20 niti) | 31 min |
| Ponovna gradnja po majhni spremembi | pod 1 min, namestitev 30 s |
