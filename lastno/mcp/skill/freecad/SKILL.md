---
name: freecad
description: Delo v spletnem FreeCAD-u prek orodij mcp__freecad__* (lastna gradnja FreeCAD 1.1, vmesnik v brskalniku na http://127.0.0.1:3020/). Uporabi, kadar uporabnik govori o 3D modelih, kosih, sestavih, skicah, pločevini, meritvah, trkih, STEP/STL, 3D tisku (Bambu P2S, plošča Tiskaj), renderju, Oblikovanju (Blender) ali o datotekah FCStd v Oblak/3D modeliranje, ali kadar prosi, naj kaj naredi, popravi, pregleda ali izmeri v FreeCAD-u.
---

# Spletni FreeCAD: kako ga upravljati

Uporabnik dela v brskalniku in ves čas vidi isti model kot ti. Okno FreeCAD-a je skrito. Odprtih je lahko več deset
njegovih dokumentov, zato vedno delaj na pravem dokumentu (argument `dokument`, v kodi `doc`) in ne na slepo na
`App.ActiveDocument`.

## Prvi koraki
1. `stanje`: aktivni dokument, neshranjeni, izbira, odprt obrazec. Če ne odgovori, `zazeni`.
2. `dokumenti` (seznam, odpri, aktiviraj, nov) in `drevo` (struktura; `objekt` = vse lastnosti, izrazi, napaka).
3. `slika` (izo, spredaj, zgoraj …) in `izmeri` (okvir, prostornina, razdalje, trki). Model poglej, preden kaj trdiš.
4. Ne veš imena ukaza ali funkcije: `isci` (vrsta ukaz, api, tip, modul, skripta, splet, pravilo). Ne ugibaj API-ja;
   `isci {"podrobno": "PartDesign::Pad"}` vrne vse lastnosti tipa, `{"podrobno": "Part.makeLoft"}` podpis in opis.

## Spremembe
- **Koda**: `python` (en klic = en korak za Razveljavi; ob napaki se klic razveljavi sam). Vrne izpis, `rezultat`,
  nove in odstranjene objekte ter napake po preračunu. Po vsaki spremembi oblike: `slika` + `izmeri`.
- **Ukaz z oknom** (Zaokrožitev, Posnetje, Make Wall …): `izberi` robove ali ploskve → `ukaz` → `obrazec` preberi →
  `vpisi` / `izberi` / `kljukica` po #id → `potrdi`. V kodi ne kliči `Gui.runCommand` za ukaze z oknom.
- **Obstoječ parametričen kos**: `drevo {"objekt": ...}` pokaže mere in izraze; spremeni lastnost v `python`
  (`obj.Length = 25; doc.recompute()`), nato preveri. Skripte projekta (`Skripte/` ob modelu) najde `isci` z vrsta
  skripta; poženeš jih s `python {"datoteka": pot}`.
- **Shranjevanje** samo z `shrani` in samo, ko uporabnik to želi; s `komentar` za datoteke v mapi Oblak (različica).
- **Razveljavi**: `razveljavi` (korakov 0 = seznam korakov).

## Postopki
- **Nov kos**: `dokumenti nov` → telo PartDesign → skice na ravninah izhodišča, popolnoma omejene (`sk.solve() == 0`,
  `sk.FullyConstrained`), loki s središčem in kotoma (ne s tremi točkami) → izbokline in ugrezi → mere na enem mestu.
- **Pločevina**: najprej preberi `lastno/raziskava/plocevina.md` v repozitoriju FreeCAD; lastna objekta TeloVPlocevino
  in Razgrnitev (`lastno/plocevina/lastna_plocevina.py`); lastnosti ne imenuj `Debelina`.
- **Sestav**: okolje Assembly (`ukaz {"okolje": "AssemblyWorkbench"}`), kosi kot App::Link na shranjene dokumente,
  spoji: najprej Offset1/Offset2, šele nato Reference1/Reference2. Trke preveri z `izmeri {"vsi": true}`.
- **Pregled**: `drevo` (⚠ napake), `izmeri vsi`, `slika` iz treh smeri; ničesar ne spreminjaj.
- **3D tisk**: okvir znotraj 256 × 256 × 256 mm (`izmeri`), lega brez podpor `splet POST /tisk/lega`, nato `natisni`
  (odpre okno Pripravi; tiskalnik, predal in polnilo potrdi uporabnik, tisk se ne zažene sam).
- **Render**: `render` (osnutek je hiter; `pogled zaslon` = uporabnikova kamera). **Proste oblike**: `oblikovanje`
  (Python v Blenderju, 1 enota = 1 mm, `slika: true`).
- **Videz, baza standardnih delov, knjižnica, oblak**: `splet` (`splet {"katalog": true}` našteje končne točke).
- **Brez strežnika** ali krog zapis-branje STEP (v strežniku lahko sesuje proces): `freecadcmd`.

## Ne
- Ne poganjaj Boolovih operacij (common, cut, fuse) v zankah čez veliko kosov: glavna nit obvisi za minute.
- Ne shranjuj, ne zapiraj dokumentov in ne briši datotek ali uporabnikovih objektov brez izrecne želje.
- `izhod` le na izrecno zahtevo. `dovoli_pisanje` le, če je uporabnik to izrecno dovolil.
- Imena objektov (Name) naj bodo ASCII, oznake (Label) so lahko slovenske. Poti v Pythonu: `r"C:\..."` ali `/`.
- Podrobna pravila in pasti: vir `freecad://pravila` ali `isci {"vrsta": "pravilo", "poizvedba": ...}`.

Odgovarjaj kratko v slovenščini: kaj si naredil, kaj vidiš na sliki, mere, predlog naslednjega koraka.
