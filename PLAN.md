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
4. [ ] Prva gradnja: `pixi run configure-release`, `pixi run build-release`, `pixi run install-release`
5. [ ] Dokaz zanke: oznaka »lastna gradnja« v naslovu okna, prevedeno, nameščeno in preverjeno v oknu
6. [ ] Način dela naprej: veja na spremembo, gradnja le spremenjenega, občasni `git fetch upstream`

## Kje se kaj spreminja

- `src/Base` osnovne knjižnice, `src/App` dokument in objekti, `src/Gui` uporabniški vmesnik,
  `src/Main` zagon in identiteta programa (ime, ikona, splash).
- `src/Mod/<Ime>` delovne mize: C++ v `App/` in `Gui/`, Python ob njih. Python del ne potrebuje prevajanja.
- `CMakeLists.txt`, `cMake/`, `CMakePresets.json`, `pixi.toml` gradnja in okolje.

## Ocene

| Postavka | Vrednost |
|---|---|
| Izvorna koda z zgodovino | 2,9 GB |
| pixi okolje (`.pixi/`) | približno 9 GB |
| Prva gradnja Release | 30 do 90 min |
| Ponovna gradnja po majhni spremembi | 1 do 5 min |
