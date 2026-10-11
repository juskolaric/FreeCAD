# Načrt: Tiskanje v spletnem FreeCAD-u (združitev s ploščo Tiskaj)

Pripravljeno 2026-10-09. Izhodišče: dva programa v dveh zavihkih brskalnika — spletni FreeCAD
(`lastno/splet`, vrata 3020) in nadzorna plošča Tiskaj (`3D print/tiskaj`, vrata 3021, kamere 3026).
Danes gre kos iz FreeCAD-a na tiskalnik ročno: izvoz STEP v mapo STEPI, nato plošča.

**Cilj.** Eno okno: stran spletnega FreeCAD-a. Plošča za tiskanje je v njej zavihek, kos gre na
tiskalnik naravnost iz drevesa dokumenta, stanje tiskalnikov je ves čas vidno v vrstici stanja.

## Kako bo delovalo

1. **Zavihek »Tiskanje«** v glavi strani (ob zavihkih okolij). Klik zamenja 3D pogled s celotno
   ploščo Tiskaj (tiskalniki s kamerami, projekti, vhod, čakalna vrsta), vdelano kot okvir na njen
   naslov; plošča ostane svoj program in svoj proces. Če ne teče, zavihek pokaže »Plošča ne teče« z
   gumbom Zaženi, ki jo zažene v ozadju. Ob prehodu na drug zavihek plošča ugasne kamere.
2. **Natisni iz drevesa.** Desni klik na telo, kos ali sestav → »Natisni«: FreeCAD izvozi STEP
   (vsako telo svoja datoteka, ime = oznaka kosa) v vhodno mapo plošče, stran preklopi na zavihek
   Tiskanje in odpre okno Pripravi za to datoteko (tiskalnik, predal, orientacija, polnilo potrdi
   uporabnik). Samodejna priprava iz mape STEPI dela kot doslej.
3. **Stanje tiskalnikov v vrstici stanja**: čip za vsak tiskalnik (»P2S 1 · tiska 45 % · še 1 h 10 min«,
   »P2S 2 · prost«, oranžno »miza ni pospravljena«), osveženo vsakih 5 s; klik odpre zavihek Tiskanje.
4. **Skupen zagon.** `ZAZENI-SPLET.bat` zažene tudi ploščo, če še ne teče. Gumb Izhod v brskalniku
   plošče **ne** ustavi: čakalna vrsta in nadzor tiskalnikov tečeta naprej brez FreeCAD-a.
5. (kasneje) Pretvorba STEP → STL v plošči prek tekočega spletnega FreeCAD-a namesto `freecadcmd`
   (hitreje, brez zagona novega procesa); `freecadcmd` ostane rezerva.

**Kaj se ne spremeni.** Plošča na 3021 deluje tudi sama (brez FreeCAD-a) in ostane lasten repo
`juskolaric/3D-print`. Pot iz SolidWorksa (makro → STEPI) ostane. MQTT, ffmpeg in Bambu Studio ne
tečejo v procesu FreeCAD-a: sesutje FreeCAD-a ne sme ustaviti tiska.

## Koraki gradnje (vsak preverljiv posebej)

1. ✅ 2026-10-09 Zavihek Tiskanje z vdelano ploščo, zaznava »ne teče« + gumb Zaženi, ugašanje kamer ob skritju.
2. ✅ 2026-10-09 Natisni iz drevesa: izvoz STEP iz izbranega objekta, predaja plošči, odprto okno Pripravi.
   Preverjeno s preizkusno kocko: datoteka v STEPI, plošča jo zabeleži kot ročno (brez samodejnega rezanja), okno Pripravi se odpre.
3. ✅ 2026-10-09 Čipi tiskalnikov v vrstici stanja (prek posrednika v strežniku FreeCAD).
4. ✅ 2026-10-09 Skupen zagon v `ZAZENI-SPLET.bat`; zapis v `CLAUDE.md` obeh projektov (`ports.json` nespremenjen: vrata ostajajo).
5. Pretvorba STEP → STL v plošči prek tekočega spletnega FreeCAD-a (še odprto).

Potrjeno 2026-10-09 (uporabnik: iz programa za 3D modeliranje takoj tiskati in vse nadzirati znotraj programa).
Spremembe še niso commitane (delovno drevo obeh repozitorijev nosi tudi necommitano delo drugih sej).

## Odločitve (sprejete 2026-10-09)

- Gostitelj: spletni FreeCAD, plošča kot zavihek. Druga pot — 3D pogled v plošči — ne, ker je
  stran FreeCAD-a desetkrat večja in nosi skice, drevo, bazo, oblak.
- Vdelava: okvir na naslov plošče. Pogledi plošče, narisani na novo v slogu FreeCAD-a, šele
  kasneje, če bo okvir motil (dva sloga, dva nabora bližnjic).
- Natisni: vedno okno Pripravi (uporabnik potrdi tiskalnik, predal, orientacijo, polnilo); tiha samodejna
  priprava ostaja le za datoteke iz SolidWorksa (mapa STEPI).
- Izvoz: en STEP na kos (oznaka kosa); objekt z več telesi gre v več datotek (`_1`, `_2` …).

## Tehnične podrobnosti

Okvir `<iframe>` kaže neposredno na `http://127.0.0.1:3021/` (ne prek posrednika: absolutne poti
`/web/…`, `/api/…` v strani plošče bi se podrle, povezave do 3021 pa ne jemljejo 6 povezav do 3020).
Stran FreeCAD-a plošči sporoča z `postMessage` (`{dejanje: "pripravi", datoteka}`, `{dejanje: "skrit"}`),
plošča dobi poslušalca v `app.js` (odpre Vhod in `modalPripravi`, ugasne kamere kot ob skritem zavihku).
Stanje za čipe in Natisni gre prek strežnika FreeCAD (`GET /tiskaj/stanje`, `POST /tiskaj/natisni` z
žetonom; posrednik teče na niti strežnika z `http.client`, brez FreeCAD API-ja), da plošča ne potrebuje
CORS in tuja stran v brskalniku ne more klicati njenih ukazov. Izvoz STEP na glavni niti
(`Part.export` / `ImportGui.export` izbranih objektov, vsako telo posebej) v `vhod_mapa` iz
`config.json` plošče (privzeto `~/Desktop/STEPI`); vrata plošče iz `Photolandia-Apps/ports.json`.
