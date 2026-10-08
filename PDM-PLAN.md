# PDM za modele FreeCAD — plan (7. 10. 2026)

Cilj: vsaka sprememba modela je shranjena kot različica, vidna in obnovljiva; baza in trezor sta v lastnem
oblaku (`Apps/oblak`), vmesnik v FreeCAD-ovem spletnem pogledu (`lastno/splet`) in v spletnem vmesniku oblaka.

## Kako delujejo sistemi PDM (preverjeno 7. 10. 2026)

- **Trezor** (vault): ena shramba na strežniku, lokalno je le delovna kopija. Uporabnik datoteko *vzame* (check-out),
  ureja in *vrne* (check-in); medtem je njen lastnik samo on, drugi vidijo, kdo jo ima in od kdaj.
- **Različice in revizije** sta dve plasti: *različica* (1, 2, 3 …) nastane samodejno ob vsakem vračanju v trezor,
  *revizija* (A, B, C ali 01, 02) je zavesten mejnik, ki ga datoteka dobi ob prehodu stanja (osnutek → v pregledu → izdano).
  Zgodovina kaže vse različice, revizije so označene; vsako različico je mogoče dobiti nazaj.
- **Reference**: sestav ve, katere datoteke vsebuje (Vsebuje), del ve, kje je uporabljen (Kje je uporabljeno); iz tega
  je kosovnica. Ob prevzemu stare različice sestava pridejo zraven prave različice delov.
- **Podatkovna kartica**: metapodatki ob datoteki (številka dela, naziv, material, revizija, stanje) za iskanje in sezname.

## Kaj za FreeCAD že obstaja

- **Ondsel Lens**: podjetje zaprto novembra 2024, strežnik je odprtokoden (`FreeCAD/Ondsel-Server`: Node, MongoDB,
  Keycloak, Docker), FreeCAD Project Association ga s posebno donacijo preoblikuje, testni strežnik `lens.freecad.org`,
  od junija 2025 projekt NLnet za tesnejšo integracijo. Model: delovni prostor → datoteka → različice s komentarjem,
  aktivna različica. Za nas pretežak (lastna baza Mongo, Keycloak), ne gre v naš oblak; model pa je dober zgled.
- **CADBase**: gostovana platforma z workbenchem (komponenta → modifikacija → nabor datotek), ročno nalaganje, brez zaklepanja.
- **Git z razpakiranim FCStd** (fcinfo, zippey): deluje za razvijalce, ne za delo brez gita.
- **Naš oblak že ima trezor z različicami**: vsaka shranjena datoteka je nova vrstica `revisions` (kosi po SHA-256,
  prenos točno določene revizije z `GET /v1/download?rev=`), dnevnik sprememb, prostori s člani in pravicami,
  odjemalci Windows/macOS/iOS. Stare revizije se ne brišejo. **Manjka**: seznam različic datoteke (API in vmesnik),
  obnova stare različice, komentarji, zaklepanje, revizijske oznake in stanja, reference med datotekami FCStd, metapodatki.

## Odločitev

PDM zgradimo nad lastnim oblakom: baza in bajti so že tam, FreeCAD samo bere zgodovino in piše metapodatke.
Lensa ne prevzamemo. Mapa `Oblak/3D modeliranje` ostane delovna kopija, ki jo sinhronizira odjemalec oblaka.

## Predpogoj

Oblak zdaj teče **samo lokalno** (Worker na tem računalniku, Postgres 5438); objava na internet čaka na tri korake,
ki jih lahko naredi le lastnik računa (Neon, `wrangler login` s paketom Workers Paid, žeton R2 — glej `Apps/TODO.md`,
razdelek oblak). Koraka 1 in 2 spodaj delujeta že lokalno; da bodo različice res »v oblaku« in dosegljive z drugih
računalnikov, je treba oblak objaviti. V oblaku vsebina ni šifrirana (odprta točka iz pregleda 2026-09-16).

## Koraki (vsak je svoja manjša naloga)

1. [x] **Zgodovina v oblaku** _(narejeno 7. 10. 2026)_. API `GET /v1/zgodovina?path=` (različice z datumom, napravo,
   uporabnikom, velikostjo, oznako obnove) in `POST /v1/obnovi {rev}` (obnova = nova revizija s staro vsebino, v dnevnik
   kot `upsert`, nič se ne briše); `POST /v1/content/link` in `GET /v1/content` sprejmeta `rev`. Spletni vmesnik oblaka:
   v meniju datoteke »Zgodovina različic« s seznamom, gumboma Prenesi in Obnovi. Migracija `0004_zgodovina.sql`
   (`revisions.restored_from`). Preizkusi v `test/splet.test.mjs` (6 novih), `pnpm test:splet` 30 ok, `test:protokol` 28 ok.
2. [x] **Zgodovina v FreeCAD-u** _(narejeno 7. 10. 2026)_. `lastno/splet/oblak.py`: prijava v oblak kot lastna naprava
   »FreeCAD (splet)« (seja v `%LOCALAPPDATA%/FreeCAD-splet/oblak.json`; naslov API-ja in mapa iz nastavitev odjemalca
   za Windows, prepis `SPLET_OBLAK_API`, `SPLET_OBLAK_MAPA`), preslikava lokalne poti v prostor in pot v oblaku (Osebno,
   skupine, prostori), `GET /oblak/zgodovina`, `POST /oblak/odpri` (prenos različice v `razlicice/`, odpre se kot
   »ime · različica N« z oznako »ogled različice«), `POST /oblak/obnovi` (po obnovi strežnik čaka, da odjemalec oblaka
   zamenja lokalno datoteko, in odprt dokument brez neshranjenih sprememb osveži). Stran: gumb ⟲ ob odprtem dokumentu
   iz mape oblaka, plošča z različicami (prijava, Odpri, Povrni, Odjava), obvestila. Preizkušeno na ločenem primerku
   (vrata 3031) s preizkusnim računom: prijava, seznam, odpiranje različice, povrnitev, samodejna osvežitev.
   Levi stolpec stranskega menija od 7. 10. kaže le odprte dokumente (odločitev druge seje), zato so različice pri
   odprtih dokumentih, ne pri seznamu datotek.
3. [x] **Komentar in revizijske oznake** _(narejeno 7. 10. 2026)_. Oblak: tabela `pdm_revizije` (komentar, stanje
   osnutek / v pregledu / izdano, oznaka), `POST /v1/revizija`; ob izdaji revizija dobi oznako A, B, C … (po Z sledi AA)
   in je ni več mogoče vrniti v osnutek; zgodovina in seznam datotek nosita komentar, stanje in oznako; commit in obnova
   sprejmeta komentar. **Odstop od plana:** izdaja datoteke *ne zaklene* (odjemalci sinhronizirajo mapo in bi ob
   zavrnjenem shranjevanju delali nasprotujoče kopije); nova shranjena različica po izdaji je samodejno osnutek
   naslednje revizije (»osnutek po A«). Zaklepanje je korak 4. FreeCAD: po shranjevanju datoteke iz mape oblaka
   (opazovalec `slotFinishSaveDocument`) brskalnik vpraša »Kaj si spremenil?«; ker datoteko v oblak pošlje odjemalec
   oblaka, strežnik komentar pripne reviziji z enakim vsebinskim hashem (sha256 nad sha256 kosov po 4 MiB) takoj ali ko
   pride (čakanje do 3 min, obvestilo). V plošči z različicami: komentar, oznaki izdano/v pregledu, izbira stanja z
   potrditvijo izdaje, gumb Komentar. Preizkušeno: API (36 preizkusov), FreeCAD na primerku 3031 (komentar, izdaja A,
   vprašanje ob shranjevanju, komentar pripet, ko je simulirani odjemalec poslal različico #4).
4. [x] **Zaklepanje (check-out)** _(narejeno 7. 10. 2026)_. Oblak: tabela `pdm_zaklepi` (uporabnik, naprava, od kdaj,
   opomba), `POST /v1/zakleni`, `POST /v1/odkleni` (`force` = prevzem), `GET /v1/zaklep`; zaklep v zgodovini in seznamu.
   Zaklep pripada **uporabniku** (ne napravi): FreeCAD in odjemalec oblaka na istem računalniku sta dve napravi, datoteko
   v oblak pošlje odjemalec, zato lastnikove naprave shranjujejo naprej; commit *drugega* uporabnika vrne 409 `locked`,
   jedro odjemalca to obravnava kot konflikt (nasprotujoča kopija, zaklenjena datoteka ostane). Jedro je spremenjeno
   v kodi (`engine.rs`), **nameščeni odjemalec za Windows še ni izdan na novo**. FreeCAD: odprt dokument iz mape oblaka
   se samodejno zaklene (ob prvem seznamu odprtih dokumentov, v ozadju), ob zaprtju dokumenta ali izhodu se zaklep
   sprosti; seznam odprtih dokumentov kaže »🔒 zaklenjeno zame« ali »🔒 ime« (rdeče, z opozorilom, da bodo shranjene
   spremembe nasprotujoča kopija); plošča z različicami ima vrstico zaklepa z gumbi Zakleni / Odkleni / Prevzemi.
   Preizkušeno: API (41 preizkusov), drugi uporabnik zaklene → commit prvega 409, FreeCAD pokaže tuj zaklep, Prevzemi,
   zaprtje dokumenta sprosti zaklep. Odprto: ni samodejnega poteka zaklepa (če FreeCAD pade, zaklep ostane; sprosti se
   ročno z Odkleni/Prevzemi).
5. [x] **Reference in kosovnica** _(narejeno 7. 10. 2026)_. Oblak ob vsaki novi reviziji datoteke FCStd v ozadju
   prebere `Document.xml` iz zipa (lasten bralnik zipa v Workerju, `fcstd.ts`) in zapiše `pdm_dokument` (objekti,
   kosovnica, napaka) in `pdm_reference` (zunanje povezave XLink s `stamp`); obnova prepiše podatke izvorne revizije.
   `GET /v1/reference`: Vsebuje (z opozorilom »v oblaku novejša kot ob shranjevanju«, ko je povezana datoteka
   spremenjena po času `stamp`), Kje je uporabljeno (datoteke, katerih trenutna revizija kaže sem; »sestav pozna
   starejše stanje«) in kosovnica. **Odstop od plana:** kosovnico računa oblak iz `Document.xml` (vidna telesa in
   deli po 1, povezave App::Link seštete po cilju; skice, značilnosti, pomožna geometrija, vsebniki in skriti objekti
   ne štejejo), ne FreeCAD v `Meta` — tako velja za vsako datoteko ne glede na to, kje je bila shranjena. Cilje v
   drugi datoteki pozna le po imenu objekta (oštevilčene Kovica, Kovica001 … združi brez pripone). FreeCAD in spletni
   vmesnik oblaka: razdelek Vsebuje / Kje je uporabljeno / Kosovnica na dnu plošče oz. zgodovine, klik odpre povezano
   datoteko (FreeCAD). Preizkušeno: 47 preizkusov API-ja (umetna FCStd z XLink, zastarelost, obnova, pokvarjen zip);
   pravi modeli: soba vsebuje zalogovnik (114 povezav), zalogovnik je uporabljen v sobi, kosovnica zalogovnika
   Kovica_stranica 30, Kovica_polica 10, kosi po 1. Omejitve: pri sestavu, ki kaže na povezave v drugi datoteki
   (soba → povezave kovic v zalogovniku), kosovnica šteje cilje po imenu, ne razreši verige do telesa.
6. **Podatkovna kartica.** Lastnosti dokumenta FreeCAD (Id = številka dela, Label, Company, Comment, Meta) urejljive
   v stranskem meniju in vidne v oblaku; iskanje po njih.
7. **Pozneje.** Razlika med različicama (objekti, lastnosti, prostornine kot izpis), slika predogleda ob reviziji,
   STEP izvoz izdane revizije, obnova sestava z usklajenimi različicami delov.

Vrstni red: 1 → 2 → 3 najprej (podatki že obstajajo, manjka le pogled), nato 4, 5, 6.

## Tehnične podrobnosti

- Oblak: `nodes.current_rev`, `revisions(node_id, size, content_hash, device_id, created_at)`, `journal`;
  `GET /v1/download?rev=`. Novo: `pdm_revizije(rev_id pk, komentar, oznaka, stanje, user_id, created_at)`,
  `pdm_zaklepi(node_id pk, user_id, device_id, since)`, `pdm_reference(rev_id, cilj_pot, stamp)`. Branje
  `Document.xml` iz FCStd (zip) zmore Worker sam, FreeCAD-a ne potrebuje. Pravilo »ne briši podatkov« velja.
- FreeCAD: zunanje povezave so v `Document.xml` kot `<XLink file="../zalogovnik.FCStd" stamp="…" name="…"/>`;
  lastnosti dokumenta `Id`, `Label`, `Company`, `Comment`, `CreatedBy`, `LastModifiedBy`, `Meta` (slovar).
  Shrani prestreže brskalnik (`Std_Save` → komentar → shranjevanje prek `POST /python`); oblak API s prijavo
  uporabnika v stranskem meniju; datoteko najde po poti znotraj mape `Oblak/3D modeliranje`.
- Odjemalec oblaka mora znati prenesti točno določeno revizijo na drugo pot (začasna mapa), ne čez delovno kopijo.
