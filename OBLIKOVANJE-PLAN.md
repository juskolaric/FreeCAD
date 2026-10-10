# Plan: prosto oblikovanje in render (Blender ob FreeCAD-u)

Stanje 2026-10-10: potrjeno (Blender 5.2, generiranje lokalno), fazi 2 in 4 narejeni. Cilj: v spletnem 3D programu se lahko z idejo **igramo** (organske, gladke,
»na oko« oblike, hitre različice, lep render). Ko je oblika všeč, jo **prestavimo na tehnično stran** (FreeCAD: mere,
stene, pritrdila, STEP, tisk). Isti vmesnik v brskalniku, dva motorja v ozadju.

## Stanje na tem računalniku

- Blender 5.2.2 LTS (posodobljen 2026-10-10 prek winget), teče v ozadju brez okna.
- Gonilnik NVIDIA 566.03 je za OptiX v Blenderju 5.2 prestar (jedro se ne prevede): render teče s CUDA (približno enako hitro).
  Po posodobitvi gonilnika (R570 ali novejši) se OptiX vklopi sam (preverba vsakih 7 dni).
- Grafična kartica RTX 4000 Ada (20 GB) z OptiX, 64 GB RAM: dovolj za hiter render Cycles in za lokalne AI modele, ki iz slike
  naredijo 3D obliko.

## Kako bo delovalo za uporabnika

1. **Ideja**: v novem zavihku »Oblikovanje« opišemo ali narišemo idejo (besedilo, skica, fotografija, obstoječ kos).
2. **Igranje**: AI (ali mi z drsniki) zgradi obliko. Vsak poskus je **različica** v galeriji s sličico; primerjava, zvezdica,
   vrnitev na prejšnjo. Drsniki pomenijo, da obliko preoblikujemo brez kode (debelina, zaobljenost, raztezanje, simetrija).
3. **Render**: gumb Render nariše fotorealistično sliko (studio, okolje, materiali iz našega Videza), tudi vrtenje okoli kosa.
4. **V tehniko**: izbrano različico prenesemo v FreeCAD in jo tam naredimo izdelljivo.

## Faze

1. [x] **Odločitve in Blender** (2026-10-10): Blender 5.2, generiranje oblik lokalno. Okno Blenderja je za ročno
   kiparjenje dovoljeno (gumb Odpri v Blenderju).
2. [x] **Blender kot drugi motor** (2026-10-10): Blender v ozadju s strežnikom po vzoru FreeCAD-ovega (vrsta ukazov, posnetek mreže, žeton).
   Brskalnik isti pogled riše iz Blenderja; zavihek Oblikovanje.
3. [x] **Igrišče** (2026-10-10): ideje z različicami (trak sličic, zvezdica, vir), klepet s Claudom v zavihku (gradi parametrično obliko, pogleda 4 poglede, popravi; skica ali fotografija kot priloga), drsniki iz parametrov oblike, Odpri v Blenderju (shranjeno v oknu se vrne kot različica). Prvotno: ideje in različice (galerija, sličice), AI zanka z izrisom slike (AI zgradi, pogleda, popravi), osnovni gradniki
   oblike: gladka kletka (SubD), zlivajoča se telesa (SDF/metaballi), cevi po krivulji, drsniki prek Geometry Nodes.
4. [x] **Render** (2026-10-10; slika, video, predloge osvetlitve in ozadja preverjeni; les in zrnatost iz Videza napisana, še nepreverjena): Cycles na grafični kartici, predloge studia (luči, ozadja, tla), materiali iz Videza, slika in vrtenje
   (video). Velja tudi za tehnične modele iz FreeCAD-a (izvoz v Blender), npr. Photobox za ponudbe.
5. [ ] **Oblika iz slike ali besedila**: lokalni model (Hunyuan3D / TRELLIS na RTX 4000) ali storitev v oblaku; rezultat je
   različica kot vse ostale.
6. [ ] **Most v tehniko** (glej spodaj): mreža kot referenca, prerezi v loft, SubD v gladke ploskve, ob koncu STEP in Natisni.
7. [ ] **Obratna smer**: tehnične kose (elektronika, nosilci) prenesemo v Oblikovanje kot ovire, okoli katerih rišemo ohišje.

## Most v tehniko: štiri poti, od najhitrejše do najčistejše

- **Za tisk takoj**: mreža (STL) gre naravnost v ploščo Tiskaj; FreeCAD ni potreben.
- **Referenca**: mreža v FreeCAD-u kot zamrznjena lupina; tehnične kose (pritrdila, luknje) rišemo ob njej in jih združimo.
- **Prerezi v loft**: iz mreže vzamemo prereze, FreeCAD jih poveže v gladko trdno telo; čist STEP, mere popravljive.
- **SubD v ploskve**: če je oblika zgrajena kot gladka kletka, se kletka pretvori v B-zlepke (kot T-zlepki v Fusionu).
  Najčistejše, a najzahtevnejše; šele, ko prve tri poti tečejo.
  Pri vseh poteh v FreeCAD-u sledijo: debelina stene, ojačitve, sedeži vijakov, razdelitev na kose za tisk.

## Tveganja

- Mreža ni trdno telo: luknje in prekrivanja popravi Blender (remesh) pred prenosom.
- Proste oblike nimajo točnih mer: dogovor, da mere določi šele tehnična stran.
- Velike mreže v brskalniku: prenos zmanjšane mreže, polna ostane v Blenderju.

## Tehnično (na kratko)

- Blender: `blender.exe -b --factory-startup --python strežnik.py`, skripta drži zanko na glavni niti (bpy ni nitno varen),
  HTTP v drugi niti, enako pravilo kot `lastno/splet/streznik.py`. Vrata iz `Photolandia-Apps/ports.json` (`vrata.mjs prosto`).
- Mapa `lastno/oblikovanje/`; projekti v `Oblak/3D modeliranje/<Projekt>/Oblikovanje/` (`.blend`, različice, renderji).
- Mreža v brskalnik: isti format posnetka kot iz FreeCAD-a (točke, trikotniki, normale), kasneje binarno.
- Render: Cycles, OptiX, razšumljanje OptiX/OIDN; hiter predogled EEVEE. HDRI okolja (Poly Haven) lokalno.
- Prenos v FreeCAD: OBJ/STL → `Mesh` (referenca) ali `MeshPart` prerezi → `Part.makeLoft`; SubD kletka → `Part.BSplineSurface`.
