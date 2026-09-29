# FreeCAD — lastna kopija (navodila za Claude Code)

Fork uradnega FreeCAD-a: `origin` = `juskolaric/FreeCAD` (**javen** repozitorij), `upstream` = `FreeCAD/FreeCAD`.
Osnova je veja `releases/FreeCAD-1-1` (nameščen FreeCAD v Program Files je 1.1.3, veja je pri 1.1.4), delo poteka
na veji `moje-spremembe`. Samostojen projekt v `Desktop/Apps`; ni del Photolandie, veljajo pa splošna pravila iz
`Apps/CLAUDE.md` (slovenščina, ne briši podatkov, zaključni povzetki v naravnem jeziku, odprte naloge v
`Apps/TODO.md` pod »FreeCAD«). Plan in stanje: `PLAN.md`.

## Gradnja (pixi, Windows)

Orodja: VS Build Tools 2022 z »Desktop development with C++« (MSVC 14.44, Windows SDK 10.0.26100) in pixi
(`C:\Users\Uporabnik\AppData\Local\pixi\bin\pixi.exe`; v terminalih, odprtih po namestitvi, je `pixi` v PATH).
Vse knjižnice (Qt 6.8, OCCT 7.8, Python 3.11, Boost, Coin3D …) prinese pixi v `.pixi/` (približno 9 GB);
sistem ostane nedotaknjen.

Vedno gradi **Release**. Privzeti `pixi run configure` / `build` / `freecad` na tej veji pomenijo **debug**; ne uporabljaj jih.

```powershell
pixi run configure-release   # enkrat: posodobi podmodule, pripravi build/release (Ninja, preset conda-windows-release)
pixi run build-release       # prevajanje; prvič 30–90 min, potem le spremenjene datoteke
pixi run install-release     # kopira v .pixi/envs/default/Library (od tam se na Windows zaganja)
pixi run freecad-release     # install-release + zagon .pixi/envs/default/Library/bin/FreeCAD.exe
```

- Prevedeni program zaganjaj **samo** prek `pixi run freecad-release` ali iz `pixi shell` (sicer manjkajo DLL-ji).
- `build/` in `.pixi/` sta izven gita. **Ne briši ju** brez naročila: polna gradnja traja do uro in pol.
- Dnevniki gradnje gredo v `build/` (npr. `build/build-release.log`), ne v koren repozitorija.
- Preverjanje spremembe: prevedi, namesti, zaženi in preveri v oknu. Konzolna različica:
  `.pixi\envs\default\Library\bin\FreeCADCmd.exe --version`.
- Nastavitve uporabnika si prevedeni program deli z nameščenim 1.1.x (`%APPDATA%\FreeCAD\v1-1`), ker je `ExeName`
  isti (`src/Main/MainGui.cpp`). Sprememba imena bi premaknila tudi mapo nastavitev.

## Način dela

- Vsaka sprememba na svoji veji iz `moje-spremembe`; po preverjeni gradnji združi nazaj. Commit sporočila v slovenščini.
- Push samo na `origin` (fork). Nikoli ne potiskaj na `upstream`.
- Posodobitev z uradnim FreeCAD-om: `git fetch upstream`, nato `git merge upstream/releases/FreeCAD-1-1` v `moje-spremembe`.
- Kje je kaj: `src/Base` osnove, `src/App` dokument in objekti, `src/Gui` uporabniški vmesnik (glavno okno
  `src/Gui/MainWindow.cpp`), `src/Main` ime programa, ikona, splash (`MainGui.cpp`), `src/Mod/<Ime>` delovne mize
  (C++ v `App/` in `Gui/`, Python ob njih; Python del ne potrebuje prevajanja).
- Uradna navodila: https://freecad.github.io/DevelopersHandbook/ (gradnja, slog kode, prispevanje).
