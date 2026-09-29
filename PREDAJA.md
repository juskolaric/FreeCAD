# Predaja projekta: lastna kopija FreeCAD-a z vmesnikom v brskalniku

Stanje: **29. september 2026**. Lastnik: Jus Kolarič (GitHub `juskolaric`). Napisano za človeka (in njegov
Claude Code), ki prevzame delo na drugem računalniku. Vse, kar je tu, je preverjeno na Windows 11.

---

## 1. Kaj je to in kam gre

- **Lastna kopija FreeCAD-a** (fork uradnega repozitorija), ki jo spreminjamo po svoje. Osnova je uradna
  veja `releases/FreeCAD-1-1` (različica 1.1.4). Program se prevede sam na računalniku.
- **Smer od 29. 9. 2026:** FreeCAD je samo motor (geometrija, reševalnik skic, ukazi), **uporabniški vmesnik
  in grafika nastajata v brskalniku** (three.js, WebGPU). Okno namiznega FreeCAD-a je skrito in se pokaže
  le, kadar kak ukaz še potrebuje vnos v njem.
- Cilj: delo na modelu v celoti v brskalniku, po vzoru SolidWorksa (zavihki z ukazi, skica, značilnosti).

Kaj že deluje v brskalniku: prikaz modela z izbiro ploskev in robov (v obe smeri s FreeCAD-om), samodejna
osvežitev ob spremembi, vsi ukazi okolij Part Design, Sketcher in Part v ukazni vrstici, nova skica (ravnina
ali izbrana ploskev), risanje skice (črta, pravokotnik, krog, točka, mera, gradbena, brisanje, vlečenje
točk z reševalnikom), izboklina in ugrez iz skice. Kaj je še v oknu FreeCAD-a: okna z nastavitvami
ostalih ukazov (zaokrožitev, vrtenina, vzorci ...), loki in ročne omejitve v skici, drevo modela.

## 2. Repozitoriji in veje

| Kaj | Kje |
|---|---|
| Fork (javen) | https://github.com/juskolaric/FreeCAD, `origin` |
| Uradni FreeCAD | https://github.com/FreeCAD/FreeCAD, `upstream` |
| Delovna veja (vse naše delo) | `moje-spremembe` (privzeta veja forka na GitHubu) |
| Osnova | `releases/FreeCAD-1-1` (sinhronizacija: `git fetch upstream`, `git merge upstream/releases/FreeCAD-1-1`) |
| Ustavljeno delo | `ukazna-vrstica`: ukazna vrstica v slogu SolidWorksa v C++ (nadomestila jo je spletna); ne nadaljuj brez naročila |
| Zgodovina korakov | `splet-pogled`, `splet-ukazi` (združeni v `moje-spremembe`) |

Kaj je našega v drevesu (vse ostalo je uradni FreeCAD):

| Pot | Vsebina |
|---|---|
| `PREDAJA.md`, `PLAN.md`, `CLAUDE.md` | ta predaja, plan s stanjem in odločitvami, pravila za Claude Code |
| `POSTAVI.bat` | postavitev novega računalnika (orodja, podmoduli, gradnja) |
| `ZAZENI.bat` | prevede spremenjeno, namesti in zažene namizni FreeCAD |
| `lastno/splet/streznik.py` | strežnik v FreeCAD-u: HTTP, dogodki, geometrija, ukazi, skica |
| `lastno/splet/index.html` | stran: 3D pogled, ukazna vrstica, urejevalnik skice |
| `lastno/splet/ZAZENI-SPLET.bat` | zažene FreeCAD s strežnikom (skrito okno) in odpre brskalnik |
| `lastno/preveri-naslov.py` | hitri preizkus, da prevedeni program teče |
| `src/Gui/MainWindow.cpp` | edina sprememba v C++: oznaka »[lastna gradnja]« v naslovu okna |

## 3. Postavitev na novem računalniku (Windows)

Potrebno: Windows 10/11 x64, internet (prenos ~15 GB), ~40 GB prostora, 16 GB RAM (bolje več), čas
1 do 2 uri (večinoma prenos in prevajanje). Poti brez presledkov in kratke (npr. `C:\Users\<ime>\Desktop\Apps\FreeCAD`).

1. Namesti git (`winget install Git.Git`) in kloniraj fork s podmoduli:
   ```
   git clone --recurse-submodules -b moje-spremembe https://github.com/juskolaric/FreeCAD.git FreeCAD
   cd FreeCAD
   git remote add upstream https://github.com/FreeCAD/FreeCAD.git
   ```
2. Zaženi `POSTAVI.bat`. Namesti pixi (upravljalnik okolja, prinese Qt, OpenCASCADE, Python ... v mapo
   `.pixi/`, sistem ostane nedotaknjen) in Visual Studio Build Tools 2022 z delovno obremenitvijo »Desktop
   development with C++« (skrbniška potrditev), nato prevede in namesti program. Z `POSTAVI.bat --brez-gradnje`
   samo preveri orodja.
3. Zagon: `ZAZENI.bat` (namizni FreeCAD) ali `lastno\splet\ZAZENI-SPLET.bat` (brskalnik, http://127.0.0.1:3020/).
   Brskalnik: Chrome, Edge, Firefox ali Safari z WebGPU (2026 vsi), sicer samodejno WebGL 2.

Ročno, brez skripte: `pixi run configure-release`, `pixi run build-release`, `pixi run install-release`
(ne uporabljaj `configure`/`build`/`freecad` brez pripone: na tej veji pomenijo debug). Linux in macOS:
`pixi.toml` ju podpira, naše skripte `.bat` pa ne; strežnik in stran sta prenosljiva (Python, HTML).

GitHub: za push potrebuješ pravice do forka (`gh auth login`) ali svoj fork.

## 4. Zagon in vsakdanje delo

- `ZAZENI.bat`: gradnja spremenjenega → namestitev → zagon namiznega FreeCAD-a. Če FreeCAD iz te mape že
  teče, se ustavi (namestitev ne more prepisati knjižnic).
- `lastno\splet\ZAZENI-SPLET.bat`: FreeCAD s strežnikom in skritim oknom, odpre brskalnik. Če strežnik že
  teče, samo odpre brskalnik. Konzola teče minimizirano.
- Okoljske spremenljivke strežnika: `SPLET_VRATA` (privzeto 3020), `SPLET_BRSKALNIK=0` (ne odpre
  brskalnika), `SPLET_OKNO=vidno` (okno FreeCAD-a ostane vidno).
- V brskalniku: hitri dostop (nov, odpri, shrani, razveljavi, uveljavi, preračunaj, prilagodi pogled), zavihki
  Part Design / Sketcher / Part z vsemi ukazi, gumba »Pokaži/Skrij FreeCAD« in »Izhod«. Rumena pasica pove,
  kadar FreeCAD potrebuje vnos v svojem oknu (okno se takrat pokaže samo, po koncu se skrije).
- Tok izdelave dela: klik na ploskev → »Nov očrt« (spletno okno: ploskev ali ravnina) → risanje → »Zapri
  skico« → z izbrano skico »Izboklina« ali »Ugrez« (dolžina v brskalniku).

## 5. Zgradba

### 5.1 Prevajanje FreeCAD-a
- pixi (`pixi.toml`, `pixi.lock`) prinese vse knjižnice v `.pixi/envs/default/` (~10 GB). Gradnja je Ninja
  + MSVC prek CMake presetov (`CMakePresets.json`, `conda-windows-release`), mapa `build/release/` (~4 GB).
  Namestitev kopira v `.pixi/envs/default/Library/` (od tam se program zaganja, ker so tam DLL-ji).
- Prva gradnja 31 min na 20 nitih; po majhni spremembi v C++ pod 1 min + 30 s namestitve. Spremembe v
  Pythonu in HTML (`lastno/`) ne potrebujejo prevajanja, le ponovni zagon FreeCAD-a (strežnik se naloži ob
  zagonu; `index.html` se bere ob vsakem klicu, torej zadošča osvežitev strani).
- Opozorilo pixi o starem formatu `pixi.lock` (v6) ignoriraj; ne poganjaj `pixi lock`, da se datoteka ne
  razide z uradnim repozitorijem.

### 5.2 Strežnik v FreeCAD-u (`lastno/splet/streznik.py`)
- Zažene se kot skripta ob štartu FreeCAD-a. HTTP strežnik (standardna knjižnica, brez odvisnosti) teče v
  svoji niti in **FreeCAD-ovega API-ja nikoli ne kliče sam**: streže pripravljene posnetke (bajti JSON),
  zahteve pa odloži v vrsto. Glavna nit (Qt časovnik vsakih 50 ms) vrsto obdela, ob spremembi dokumenta
  (opazovalci) zgradi nov posnetek geometrije (zamik 300 ms) in vsakih 500 ms preveri stanje ukazov, aktivno
  okolje, urejanje, modalna okna in opravila.
- Dogodki v brskalnik prek Server-Sent Events (`GET /events`): `zeton`, `model`, `izbira`, `aktivni`,
  `okolje`, `skica`. Brskalnik → strežnik: `POST /select`, `/ukaz`, `/okolje`, `/okno`, `/izhod`, `/skica`,
  `/znacilnost`, `/python`. Vsak POST potrebuje glavo `X-Zeton` (žeton nastane ob zagonu, stran ga dobi ob
  vsaki povezavi), da tuja spletna stran ne more poganjati kode v FreeCAD-u. Strežnik posluša samo na 127.0.0.1.
- Posnetek geometrije: za vsak viden objekt z obliko teselirane ploskve (`Face{n}`) in diskretizirani robovi
  (`Edge{n}`), barve iz `ShapeAppearance`. Izhodišče telesa (osi, ravnine) je izpuščeno, objekt v urejanju
  (predogled) je vključen, skica v urejanju v brskalniku pa izpuščena (brskalnik jo riše sam).
- Ukazi se sprožijo kot klik na gumb orodne vrstice prek Qt-jeve vrste dogodkov (`QMetaObject.invokeMethod`
  → `QAction.trigger`), ne z `Gui.runCommand`: tako modalno okno ukaza ne zadrži Python GIL-a in strežnik
  odgovarja tudi med njim.
- Skica: geometrija in omejitve prek Python API-ja skice (`addGeometry`, `addConstraint`, `movePoint`,
  `delGeometries`, `solve`) v transakcijah (Razveljavi dela). FreeCAD-ov način urejanja skice se ne uporablja.
- Okno: skrito ob zagonu (`--hidden` ni uporaben, ker se FreeCAD z njim po skripti konča),
  `setQuitOnLastWindowClosed(False)`, samodejni prikaz ob potrebnem vnosu, zapiranje z X konča program.

### 5.3 Stran (`lastno/splet/index.html`)
- Ena datoteka, brez gradnje: three.js 0.186 prek CDN (jsdelivr, import map), `WebGPURenderer` s
  samodejnim preklopom na WebGL 2. Brez interneta stran ne dela (CDN); za delo brez omrežja bi bilo treba
  three.js shraniti lokalno.
- Deli: glava (hitri dostop, zavihki, gumba, HUD), trak z ukazi (skupine iz orodnih vrstic, veliki in majhni
  gumbi, zgoščeni način ob ozkem oknu, spustni meniji, namigi), 3D pogled (izbira z žarkom), način skice
  (pravokotna kamera, mreža, pripenjanje na točke, predogled, napisi mer), spletna okna (nova skica), pasica.

## 6. Kako razvijati in preverjati

- Spremembe v `lastno/`: zapri FreeCAD (gumb Izhod) in zaženi `ZAZENI-SPLET.bat`. Za preizkus vzporedno z
  delujočim primerkom zaženi drugega na drugih vratih: `set SPLET_VRATA=3029` in `set SPLET_BRSKALNIK=0`
  pred zagonom (3021 na razvojnem računalniku zaseda drug program).
- Preverjanje brez brskalnika: `curl http://127.0.0.1:3020/stanje`, `/ukazi`, `/model`; POST z žetonom iz
  strani (`curl http://127.0.0.1:3020/ | grep ZETON`). `POST /python {"koda": "..."}` izvede Python na
  glavni niti (za diagnostiko; koda naj piše v datoteko, ker izpis ne pride nazaj).
- Dnevnik FreeCAD-a: izpis v konzoli (`[splet] ...`), pri zagonu iz terminala tudi v datoteko, če ga preusmeriš.
- Spremembe v C++: uredi, `ZAZENI.bat` (ali `pixi run build-release` + `install-release`), preveri v oknu ali
  z `lastno/preveri-naslov.py`.
- Claude Code: pravila v `CLAUDE.md` (slovenščina, veje, kaj ne delati). Vgrajeni brskalnik aplikacije Claude
  zna odpreti stran na 127.0.0.1, klika po koordinatah posnetka zaslona, gumbe v zgoščenem traku najlaže
  sproži prek `javascript_tool` (`document.querySelector('.gumb[data-ime="PartDesign_Pad"]').click()`).

## 7. Pasti, ki so nas že stale časa

1. Zavihek, odprt pred ponovnim zagonom FreeCAD-a, je imel star žeton: kliki so bili tiho zavrnjeni.
   Rešeno (žeton prek dogodka `zeton`), a če stran ne kaže ukazov, jo osveži (F5).
2. Dva FreeCAD-a na istih vratih: Windows dovoli dvojno vezavo, zahteve pridejo do napačnega. Rešeno
   (`allow_reuse_address=False`, zaganjalnik ob tekočem strežniku le odpre brskalnik).
3. Modalno okno ukaza (npr. izbira ravnine), zagnano z `Gui.runCommand` iz Pythona, zamrzne strežnik
   (GIL). Rešeno s sprožitvijo prek Qt vrste dogodkov; ne vračaj se na `runCommand`.
4. `FreeCAD --hidden` po izvedbi skripte konča program; okno skrije skripta.
5. Namestitev (`install-release`) ne uspe, dokler teče FreeCAD iz te mape (knjižnice so zaklenjene).
6. `ViewFit` in podobni ukazi pogleda javijo napako, ko je okno skrito; niso potrebni.
7. Skica ali značilnost med urejanjem ima `Visibility=False`; posnetek zato posebej vključi objekt v urejanju.
8. Vgrajeni brskalnik aplikacije Claude: `find` vrne skrite napise gumbov v zgoščenem traku (klik ne uspe);
   uporabi JS. Dolge poti (nad 250 znakov) Windows brez vklopa dolgih poti ne prenese; git ima `core.longpaths`.
9. `pixi.toml` na tej veji privzeto pomeni debug (`configure` = `configure-debug`); vedno `-release`.
10. Dva skripta (Bash in PowerShell) v Claude Code različno obravnavata poševnice nazaj; pri pisanju datotek
    raje uporabi orodje Write.

## 8. Stanje in odprte naloge (29. 9. 2026)

Narejeno: fork in gradnja; oznaka v naslovu okna; spletni pogled z izbiro in osvežitvijo; ukazna vrstica z vsemi
ukazi treh okolij; skrito okno; skica v brskalniku (1. različica); izboklina/ugrez iz skice; predaja.

Odprto (predlog vrstnega reda):
1. Drevo objektov z lastnostmi v brskalniku (imena, vidnost, izbira, urejanje vrednosti).
2. Okna z nastavitvami ostalih ukazov v brskalniku (zaokrožitev, posnemanje, vrtenina, luknja, vzorci ...),
   dokler ni več potrebe po oknu FreeCAD-a.
3. Skica: loki, ročne omejitve (kot, enakost, simetrija, tangentnost), urejanje vrednosti mer, prikaz
   stopnje določenosti, izbira več elementov, kopiranje.
4. Binarni prenos geometrije (namesto JSON) za velike modele, robovi z debelino, senčenje z okoljem.
5. Ločen repozitorij za spletni vmesnik (npr. Next.js, kot ostali programi lastnika), FreeCAD ostane motor.
6. three.js lokalno (delo brez interneta), paket za namestitev na drug računalnik brez prevajanja (kopija
   `.pixi/envs/default` je prenosljiva samo na isto pot).

## 9. Dnevnik odločitev

| Datum | Odločitev |
|---|---|
| 2026-09-29 | Osnova veja `releases/FreeCAD-1-1` (stabilna, enaka nameščeni 1.1.x), ne `main` (26.3, velik skok knjižnic). |
| 2026-09-29 | Javen fork `juskolaric/FreeCAD`; LGPL zavezuje k objavi kode le ob razdeljevanju programa. |
| 2026-09-29 | Gradnja s pixi (brez LibPacka), samo Release. |
| 2026-09-29 | Ukazna vrstica v slogu SolidWorksa najprej v C++ (veja `ukazna-vrstica`), nato ustavljena v prid spletnega vmesnika. |
| 2026-09-29 | Pot 1: FreeCAD kot motor, vmesnik in grafika v brskalniku (three.js, WebGPU), FreeCAD Ribbon (GPLv3) zavrnjen. |
| 2026-09-29 | Okno FreeCAD-a skrito, pokaže se le ob potrebnem vnosu; delo v brskalniku. |
| 2026-09-29 | Skica se ureja v brskalniku prek Python API-ja skice, brez FreeCAD-ovega načina urejanja. |
