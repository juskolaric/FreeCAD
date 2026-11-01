# Pločevina (sheet metal): teorija, pravila konstruiranja in FreeCAD SheetMetal

Stanje: 8. 10. 2026. Namen: znanje, s katerim začnemo modelirati dele iz pločevine (laserski razrez + upogib na
upogibni stiskalnici / abkantu) v FreeCAD-u in v spletnem pogledu. Viri so na koncu vsakega poglavja.
**Številke se med viri razlikujejo** — vse so izhodišče; zavezujoče vrednosti (polmer, K, odbitek) da delavnica,
ki bo dele upogibala. Kar ni potrjeno v viru, je označeno **[nepotrjeno]**.

Izrazi: pločevina (sheet), debelina T, notranji polmer upogiba R, kot upogiba A, nevtralna os, K-faktor,
dodatek za upogib BA (bend allowance), odbitek upogiba BD (bend deduction), zunanji odmik OSSB (outside setback),
navidezni ostri rob (virtual sharp), razvita oblika / razgrnitev (flat pattern), prirobnica (flange),
zavihek (hem), razbremenilni izrez (bend relief), vogalni izrez (corner relief), matrica V (V-die), pestič (punch).

---

## 1. Kako deluje upogib

### 1.1 Nevtralna os in K-faktor
Pri upogibu se notranja stran stisne, zunanja raztegne. Plast vmes, ki ohrani dolžino, je **nevtralna os**. Ni na
sredini debeline: pomakne se proti notranjosti upogiba, bolj ko je upogib oster (majhen R/T).

- **K = t / T** (t = razdalja od notranje površine do nevtralne osi). V praksi 0,25–0,50; 0,5 = sredina, velja za
  velike polmere (R > ~3T).
- **Y-faktor** (Creo) = K·π/2; privzeti Y = 0,5 ustreza K ≈ 0,318.
- **ANSI in DIN K se razlikujeta:** DIN meri glede na T/2, zato **K_ANSI = k_DIN / 2**. FreeCAD SheetMetal interno
  uporablja ANSI.

Tipične vrednosti K (zračni upogib, V = 6–8T):

| Material | K |
|---|---|
| Konstrukcijsko jeklo (S235, DC01) | 0,44 (najpogostejši privzetek) |
| Nerjavno 304 (1.4301) | 0,45 |
| Mehak aluminij (3003, 5052) | 0,38–0,42 |
| Trd aluminij (6061-T6) | 0,42–0,45 |
| Baker, medenina | 0,35–0,40 |

Po načinu upogiba in R/T (mehak / srednji / trd material):

| Način | R = 0–1T | R = 1–3T | R > 3T |
|---|---|---|---|
| Zračni upogib | 0,33 / 0,38 / 0,40 | 0,40 / 0,43 / 0,45 | 0,50 |
| Upogib do dna (bottoming) | 0,42 / 0,44 / 0,46 | 0,46 / 0,47 / 0,48 | 0,50 |
| Kovanje (coining) | 0,38 / 0,41 / 0,44 | 0,44 / 0,46 / 0,47 | 0,50 |

Najzanesljivejši K je izmerjen: upogni 3 preizkusne kose, izmeri razvito dolžino in kraka, K izračunaj nazaj.

### 1.2 Trije načini upogibanja
- **Zračni upogib** (danes skoraj vedno): pestič potisne pločevino v matrico V, ne do dna. Kot določa globina hoda,
  zato en komplet orodja naredi vse kote. **Notranji polmer določa odprtina matrice** (~16 % V pri jeklu), ne polmer
  pestiča. Največ povratnega vzmetenja, najmanjša sila.
- **Do dna:** pločevina se prisloni na stene matrice; manj vzmetenja, sila ~2–3× [nepotrjeno].
- **Kovanje:** pestič vtisne polmer; vzmetenja skoraj ni, sila ~5–10× [nepotrjeno]; redko.

### 1.3 Formule
A = kot upogiba v stopinjah (90° za kotnik), R = notranji polmer, T = debelina.

- **Dodatek za upogib** (lok nevtralne osi): **BA = A · π/180 · (R + K·T)**
- **Zunanji odmik** (od tangente do navideznega ostrega roba): **OSSB = tan(A/2) · (R + T)**; pri 90° = R + T
- **Odbitek upogiba:** **BD = 2·OSSB − BA**
- **Razvita dolžina:** iz zunanjih mer **L = Σ zunanjih mer − Σ BD**, ali iz ravnih delov **L = Σ ravnih delov + Σ BA**

Na risbi mora biti jasno, ali je mera do zunanje strani, notranje strani ali do navideznega ostrega roba. Pri kotih
≠ 90° se zunanje mere nanašajo na navidezni ostri rob.

### 1.4 Primer
Kotnik, S235, T = 2 mm, R = 2 mm, zunanje mere 50 × 30 mm, 90°, K = 0,44:
- OSSB = tan45° · (2 + 2) = 4,00 mm
- BA = 1,5708 · (2 + 0,88) = 4,524 mm
- BD = 8,00 − 4,524 = 3,476 mm
- **L = 50 + 30 − 3,476 = 76,52 mm** (preverba: 46 + 26 + 4,524 = 76,52 ✓)

S K = 0,33 je L = 76,18 mm: 0,35 mm razlike na upogib, na škatli s 4 upogibi ~1,4 mm. **Zato K da delavnica.**

### 1.5 DIN 6935 (nemška metoda z izravnalno vrednostjo v)
L = a + b + … + Σv (zunanje mere krakov plus izravnava v, običajno negativna). Faktor (DIN):
**k = 0,65 + 0,5 · lg(R/T)** za R/T ≤ 5, sicer k = 1. Za R/T = 1 je k = 0,65 → K_ANSI ≈ 0,325.
Formula za v [nepotrjeno, preveri v standardu], β = kot med krakoma: za 0° < β ≤ 90°
v = π·(180−β)/180 · (R + T·k/2) − 2(R + T). Primer zgoraj (k = 0,65): v = −3,84 mm → L = 76,16 mm.
Metodi sta matematično enakovredni; DIN K le predpiše iz R/T. Tabele: DIN 6935 Beiblatt 1 in 2 (plačljivo).
Lastne tabele delavnice (BD po materialu, debelini, matrici) imajo prednost pred obema.

Viri: toolgrit.com/guides/sheet-metal-bending-guide, durmapress.com (k-factor, bend deduction, minimum bend radius,
V-die, tonnage), calculate.co.nz/bend-allowance-calculator.php, fabcon.com/articles/?p=127,
support.ptc.com (Creo: About_Bend_Allowance_and_Developed_Length, SheetMetal_adm_allow),
help.isdgroup.com (HiCAD Zuschlagverfahren), din.de (DIN 6935 Beiblatt), cris.fau.de/publications/366848483.

---

## 2. Najmanjši polmer, smer valjanja, povratno vzmetenje

| Material | Najmanjši notranji R (90°, prečno na valjanje) |
|---|---|
| Konstrukcijsko jeklo (S235, DC01) | 0,5–1T |
| Nerjavno 304 | 1–2T |
| Al 5052-H32 | 0,8–1T (**prva izbira za upogibane Al dele**) |
| Al 6061-T6 | ≥ 2–3T (v praksi 3–4T; zunanja vlakna pokajo) |
| Baker (pol trd) | 0,7–1T |
| Medenina (pol trda) | 1–1,5T |

- **Smer valjanja:** upogib **prečno** na smer valjanja dopušča manjši polmer; vzdolž povečaj R za 50–100 %, sicer
  zunanjost poka. Pri ostrih upogibih smer valjanja označi na risbi in v DXF.
- **Povratno vzmetenje** (springback): po razbremenitvi se upogib malo odpre; raste z R/T in trdnostjo. Okvirno
  jeklo 1–2°, nerjavno 2–4°, aluminij 1,5–5° [okvirno]. Delavnica ga izravna s preupogibom (orodja 85–88° ali 30°,
  CNC korekcija kota). **V CAD-u modeliraj končni kot** — vzmetenje ni stvar modela.

Viri: durmapress.com/minimum-bend-radius…, oshcut.com/materialdetails (5052-H32, 6061-T6),
thefabricator.com (how-to-predict-an-air-formed-inside-bend-radius, springback-and-springforward,
bend-allowance-and-springback-in-air-bending), fabcon.com/articles/?p=1518.

---

## 3. Upogibna stiskalnica (zračni upogib)

- **Odprtina matrice V ≈ 8T** (6–8T za tanko, 10–12T za debelo, nerjavno, visokotrdna jekla).
- **Notranji polmer ≈ delež V:** hladno valjano jeklo 15–17 % (≈ **0,16·V**), toplo valjano 14–16 %, nerjavno
  304 20–22 %, Al 5052 10–15 %. Primer: 2 mm jekla v V16 → R ≈ 2,5 mm. **V model vpiši polmer, ki ga matrica
  res naredi**, ne 0 in ne samodejno 1T.
- **Najmanjša dolžina prirobnice ≈ 0,7·V** (sicer pločevina zdrsne v matrico). Jeklo 90°:

  | T [mm] | 1 | 1,5 | 2 | 2,5 |
  |---|---|---|---|---|
  | V [mm] | 8 | 12 | 16 | 20 |
  | min. prirobnica [mm] | 5,5 | 8,5 | 11 | 14 |

  Krajše le s posebnim orodjem ali z daljšo prirobnico, ki se nato odreže.
- **Sila:** P [kN] = 650 · T² · L / V (T in V v mm, L v m; jeklo). Faktorji: nerjavno ×1,4–1,6, 6061-T6 ×1,0–1,3,
  5052 ×0,5. Primer: 2 mm, V16, 1 m → 162,5 kN ≈ 16,5 t.
- **Orodja:** ravni pestič, »labodji vrat« (gooseneck, za profile U s povratno prirobnico), ostrokotni 30°
  (preupogib in prvi korak zavihka). Matrice: V, več V, ostrokotne, ploščate (za zavihke), Z (odmik).
- **Zavihek:** dva koraka — ostri upogib 30°, nato stisk (zaprt) ali na distančnik (odprt).
- **Z-upogib / odmik (jog):** dva nasprotna upogiba blizu; če je vmesni del krajši od najmanjše prirobnice, je
  potrebno posebno orodje Z, ki naredi oba v enem hodu.
- **Zaporedje upogibov:** profili U in škatle trčijo ob pestič in bat; okvirno globina U ≤ ~2× širina dna
  [nepotrjeno]. Preveri z delavnico.

Viri: durmapress.com (V-die opening, V-die chart, tonnage chart), wilatooling.com (v-opening, bending-short-flanges),
thefabricator.com (dissecting-bend-deductions-and-die-openings, minimum flange lengths, why-tonnage-matters,
how-an-air-bend-turns-sharp, design-for-the-press-brake), protolabs.com/resources/blog/bend-relief.

### 3a. Izbira parametrov po materialu in debelini (Amada, 29. 10. 2026) — **pravilo za vsak kos**

**Vsakič, ko rišeš kos iz pločevine, najprej določi material in debelino; iz njiju sledijo odprtina V, notranji polmer R
in K.** Ne ugibaj polmera in ne prepisuj K iz prejšnjega kosa. Koda: `lastno/plocevina/plocevina_materiali.py`
(`parametri(material, T)`, `opis(material, T)`, `mere_plocevine(mere, material, T)`); lastna objekta pločevine imata
lastnosti `Material` in `Samodejno` (polmer in K iz tabele ob spremembi materiala ali debeline; vrednost delavnice vpiši
ročno in `Samodejno` izklopi). Katalogi Amada (upogibna orodja AFH 2024, štancna orodja) so v
`Standardni deli/_Proizvajalci/Amada/`; proizvajalec je vpisan v `_Proizvajalci/proizvajalci.md`.

**Odprtina matrice** (Amada, tabela sil pri prostem krivljenju, str. 74 kataloga): **V = 6 T** do 3 mm, **8 T** od 3 do 8 mm,
10 T od 8 do 12 mm, 12 T nad 12 mm; zaokroži na standardno odprtino (4, 6, 7, 8, 10, 12, 14, 16, 18, 20, 25, 32, 40, 50, 63, 80 …).

**Notranji polmer na delu** ga pri prostem krivljenju naredi matrica, ne klin: **R ≈ 0,16 V** jeklo, **≈ 0,20 V** nerjavno,
**≈ 0,14 V** aluminij; v modelu zaokrožen navzgor na 0,5 mm in nikoli pod najmanjšim polmerom materiala (jeklo 0,8 T, nerjavno
in Al 5754 1 T, Al 6082-T6 3 T). Amadina tabela (`ir` v vrstici V): V8 → 1,3, V10 → 1,6, V12 → 2, V16 → 2,6, V20 → 3,3,
V25 → 4, V32 → 5, V40 → 6,5, V50 → 8 (jeklo; nerjavno ≈ 20 % več).

**Klin** (pestič) je oster: **R0,6** je pri Amadi privzeti radij skoraj vseh klinov (H120: 804, 847, 820, 817, 846, 841, 840,
814, 831; H90: 704, 747, 720, 717, 746, 713, 731; H160: 904, 947, 914), na voljo še R0,2, R0,52, R0,8, R1,5, R2, R3, R4, R5,
R6; večji radiji (R7–R50) so vložki v držalu, ne za običajne kose. Klin ne sme biti ostrejši od ~0,63 T (zareže pločevino):
do 3 mm R0,6/R0,8, 3–4,5 mm R3 (standardni 804/904), nad 4,5 mm R5/R6 (ravna 803/603, 1000 kN/m; labodji vrat 450–500 kN/m
pri debelem nerjavnem ne zdrži).

| Material, T | V | R v modelu | K (R/T → K) | najkrajši krak | sila/m | klin |
|---|---|---|---|---|---|---|
| Al 5754-H22, 2 mm | 12 | **2** | 0,40 (1:0,40; 3:0,50) | 8,5 mm | ≈ 12 t | 86°/88° R0,6 |
| nerjavno 1.4301, 1,4 mm | 8 | **2** | 0,44 (1:0,43; 3:0,47) | 5,5 mm | ≈ 24 t | R0,6 |
| nerjavno, 4 mm | 32 | **6,5** | 0,44 | 22 mm | ≈ 50 t | 86° R3 |
| nerjavno, 5 mm | 40 | **8** | 0,44 | 28 mm | ≈ 62 t | 60° R5/R6 |
| nerjavno, 6 mm | 50 | **10** | 0,44 | 35 mm | ≈ 72 t | 60° R5/R6 |
| DC01, 1,5 mm | 10 | **2** | 0,43 (1:0,42; 3:0,46) | 7 mm | ≈ 15 t | R0,6 |
| DC01, 2 mm | 12 | **2** | 0,42 | 8,5 mm | ≈ 22 t | R0,6/R0,8 |
| S235, 3 mm | 18 | **3** | 0,42 | 12,5 mm | ≈ 33 t | R0,8 |
| Al 6082-T6, 2 mm | 12 | **6** (3 T, sicer poka) | 0,45 | 8,5 mm | ≈ 18 t | R0,6 |

**K-faktor** se iz R/T vzame iz dvovrstične tabele materiala (SheetMetal V2 interpolira pravilno le med dvema vrsticama):
jeklo 1:0,42 · 3:0,46; nerjavno 1:0,43 · 3:0,47; Al 5754 1:0,40 · 3:0,50; Al 6082-T6 1:0,42 · 3:0,45; baker/medenina
1:0,36 · 3:0,42. Isti K gre v `Razgrnitev.KTabela` in v `Mere.KTabela` kosov, narisanih s SheetMetal.

**Ostri upogibi R0,8 v modelu** (zalogovnik folije, betonski podstavek, 7.–8. 10. 2026) so bili izbrani zaradi cene; pri prostem
krivljenju 1,5–2 mm jekla pa matrica V10/V12 naredi R ≈ 1,6–2 mm, ne 0,8 — pri naslednji prenovi teh kosov vzemi R iz tabele.
Nerjavno se krivi s klini 86°/88° (vzmetenje 2–4°); Al 6082-T6 (trd) poka pri R < 3 T, zato za krivljenje jemlji 5754.

Viri: Amada, Bending tools catalogue AFH 2024 (`Catalog_AFH_EN_2024.pdf`, str. 11–25 klini, 74 tabela sil), thefabricator.com
(predicting-the-radius-without-test-bending, what-makes-an-air-bend-sharp), wilatooling.com (tip-radius, v-opening).

---

### 3b. Postopek krivljenja: zaporedje upogibov, orodja, prislon (30. 10. 2026) — **za dokumentacijo kosa**

Vsak kos iz pločevine dobi **list za krivilca** (`lastno/plocevina/dokumentacija_krivljenja.py` iz `izvlecek_upogibov.py`):
razgrnitev z upogibnimi črtami U1…Un (kot, smer gor/dol, R), sliko upognjenega kosa, tabelo upogibov in zaporedje korakov z
orodjem in prislonom. Kos nosi lasersko oznako (sloj GRAVURA, `oznaci_dxf.py`); **pogled na razgrnitev je s strani gravure**,
»gor« pomeni, da se krak dvigne proti gledalcu (proti gravuri), »dol« stran od nje.

**Orodje (iz tabele materiala, §3a):** matrica 1V z odprtino V = 6 T (do 3 mm) oz. 8 T (3–8 mm) → Al 5754 2 mm: **V12**, jeklo
3 mm: **V18/V20**, 4 mm: **V32**, 8 mm: **V63**. Klin za 90° kot pri zračnem krivljenju **88° R0,6** (Amada 804 standard, H120)
— 88° zaradi vzmetenja (Al 5754 1–2°, nerjavno 2–4°), kot se doseže z globino; pri 3–4,5 mm klin R3 (804 R3), nad 4,5 mm
R5/R6 60° (803/603, 1000 kN/m). **Labodji vrat 847** (gooseneck) vedno, kadar je na kosu že upognjen povratni krak ali
zaprt profil (U, škatla z notranjimi kraki) — 847 nosi 500 kN/m, tanki 846 350 kN/m. Visoki kraki (> ~100 mm) rabijo klin
H160 ali ozko matrico, sicer krak trči v stroj/orodje. Sila: Amada tabela str. 74 (Al 5754 2 mm V12 ≈ 120 kN/m, jeklo 3 mm V20
≈ 330 kN/m, 4 mm V32 ≈ 400 kN/m, 8 mm V63 ≈ 800 kN/m) × dolžina upogiba.

**Zaporedje (pravila, povzeto po Amada AFH 2024 str. 6–7, 70, Bystronic, Mate, thefabricator):**
1. **Od znotraj navzven / najprej najgloblji**: povratni (notranji) kraki in zavihki pred krakom, na katerem sedijo — ko je
   zunanji krak upognjen, notranjega klin ne doseže več. Globina v drevesu upogibov pada po korakih.
2. **Krajši kraki pred daljšimi** na isti globini; pri škatli najprej oba kratka nasprotna kraka, nato dolga.
3. **Čim manj obračanj**: upogibi iste smeri (gor/dol) skupaj, menjava smeri pomeni obrat kosa — zapisan je v koraku.
4. **Prislon** vedno na raven, dolg rob (nikoli na že upognjen kratek krak ali na lok); mera prislona je razdalja od upogibne
   črte do roba kraka **v razgrnitvi** (CNC si BA kompenzira sam); za kontrolo je zraven zunanja mera kraka po krivljenju.
5. **Preveri trk** pred vsakim korakom: že upognjeni kraki proti klinu, držalu in čeljusti; pri U-profilu širine < 2 × višine
   kraka klin ne gre ven — rabi labodji vrat ali drug red. Nekratki kot (< 90° ali > 90°) naj ne bo zadnji, ki se prislanja.
6. **Najkrajši krak** ≥ 0,7 V (Al 2 mm: 8,5 mm); krajši krak zdrsne v matrico → ožja matrica (V8) ali konstrukcijska sprememba.
7. **Isti R in isti kot** na vseh upogibih = ena nastavitev; prvi kos izmeri (kot, mera), popravi globino, šele nato serija.
8. Stopenjsko krivljenje (Amada »stage bending«): več orodnih postaj v eni mizi, kos se prime enkrat — če ima delavnica AFH.

Smer valjanja: pri Al 5754-H22 in jeklu 2–4 mm upogibi R ≥ T niso občutljivi; pri R < T upogibaj prečno na valjanje.
Viri: Amada AFH 2024 (str. 6–7 stage bending, 12–13 klini 804/847/820/817/846, 64 min. krak, 70 U/beading), Bystronic
whitepaper (simuliraj zaporedje), Mate (povratni kraki trčijo v klin), 247TailorSteel (prislon), gwklaser (kratek krak).

---

## 4. Pravila konstruiranja (DFM)

| Pravilo | Tipična vrednost |
|---|---|
| Luknja do upogiba (od tangente) | ≥ 2T + R (konzervativno 2,5T + R); utori dlje |
| Značilnost do osi upogiba | ≥ V/2, sicer se deformira; znotraj tega pasu simetrično |
| Luknja do roba | ≥ 1,5–2T |
| Najmanjši premer luknje | ≥ T (štancanje; nerjavno 1,5–2T); laser do ~0,5–1T [nepotrjeno] |
| Mostiček med luknjami, širina utora | ≥ T |
| Razbremenilni izrez upogiba — širina | ≥ T (nekateri ≥ 0,5T) |
| Razbremenilni izrez — globina | **R + T + 0,5 mm** čez upogib |
| Vogalni izrez (srečata se dva upogiba) | okrogel (Ø ≈ 2T ali več), kvadraten ali solza |
| Najmanjša prirobnica | ≈ 0,7·V ali 2,5T + R do 4T (tabela delavnice) |
| Grezilo | do roba ≥ 4T, do upogiba ≥ 3T, med grezili ≥ 8T, globina ≤ 0,6T |
| Luknja ob zvitku (curl) | ≥ polmer zvitka + T |
| Oblikovane značilnosti (žaluzije, reliefi) | nagib ≥ 5°, razmik ≥ T, od upogiba ≥ 3T + R [nepotrjeno] |
| Isti polmer na vseh upogibih | ena nastavitev orodja — ceneje |
| Toleranca kota upogiba | ±1° |

**Razbremenilni izrez** je potreben le, kjer se material nadaljuje na obeh straneh konca upogiba (upogib ne gre
do roba); brez njega se material natrga in vogal izboči.

**Standardne debeline (EU, mm):** hladno valjano 0,5 · 0,6 · 0,7 · 0,8 · 1,0 · 1,2(5) · 1,5 · 2,0 · 2,5 · 3,0;
toplo valjano 3 · 4 · 5 · 6 · 8 · 10 · 12 · 15 · 20; aluminij pogosto 1 · 1,5 · 2 · 3 · 4 · 5. Ameriški »gauge«
ni enak med materiali — debelino vedno piši v mm s standardom (npr. »DC01, 1,5 mm, EN 10131«).

**Tolerance:**
- Laserski razrez: ISO 9013; praktično ±0,1 mm do 3 mm, ±0,2–0,3 mm debelejše.
- Splošne: **ISO 2768-mK** na risbi. Razred m, dolžine: 0,5–6 ±0,1 · 6–30 ±0,2 · 30–120 ±0,3 · 120–400 ±0,5 ·
  400–1000 ±0,8 · 1000–2000 ±1,2 mm. Koti m: ±1° do 10 mm, ±30′ 10–50 mm, ±20′ 50–120 mm (za upogibe pogosto
  nerealno). Nemška alternativa za pločevino: DIN 6930-2.
- Upognjene mere: ±0,2–0,5 mm na upogib, **seštevajo se** prek verige upogibov; ±1° na dolgi prirobnici da veliko
  napako na koncu. Kritične mere kotiraj znotraj enega segmenta, ne čez več upogibov.

Viri: fabcon.com/articles (?p=127, 479, 544, 1449, 1518), sendcutsend.com/blog (avoid-deformation, ultimate guide to
bending), mate.com (special-application-success-tips), xometry.com/blog/understanding-sheet-metal-tolerances,
protolabs.com (bend-relief, 8-ways-to-improve-sheet-metal-parts).

---

## 5. Postopki izdelave

| Postopek | Obseg | Opombe |
|---|---|---|
| Vlakenski laser | jeklo do ~20–25 mm, nerjavno 15–20+, Al 15+ (odvisno od moči); rez 0,1–0,3 mm | najpogostejši, brez orodja, ISO 9013 |
| Plazma | 1–50 mm, ±0,5–1 mm, poševen rob | debeli konstrukcijski deli |
| Vodni curek | vsak material, brez toplotne cone, ±0,1–0,2 mm | počasnejši |
| Revolverska štanca | do ~6 mm; luknje + **oblike** (žaluzije, reliefi, izvlečene luknje, grezila, navoji) | poceni pri serijah; luknja ≥ T |
| Upogibna stiskalnica | poglavja 1–3 | CNC zadnji prislon, ±1° |
| Valjanje | valji, stožci | |
| Globoki vlek, štancanje | velike serije | draga orodja, druga pravila |
| Spajanje | varjenje (MIG/TIG, točkovno, lasersko), kovice, clinching, **vtisni vezni elementi** (PEM matice, vijaki, distančniki) | |

**Vtisni elementi PEM:** luknja točne mere (+0,08 mm), pločevina ≤ HRB 70 (ne za kaljeno nerjavno). Vsaka oznaka
ima svojo najmanjšo debelino in razdaljo do roba (npr. BS-M6-1: pločevina ≥ 1,4 mm, luknja 8,75 mm, os–rob
≥ 8,6 mm; M4: luknja 5,41 mm, rob 6,9 mm). Vedno po katalogu za točno oznako; vgradnja po prašnem lakiranju.

### Kaj delavnica (laser + abkant) potrebuje od nas
1. **DXF razgrnitve** 1 : 1 v mm: samo zaprte konture, upogibne črte v **ločenem sloju** (ali sploh ne), brez
   napisov v sloju rezanja, brez podvojenih črt.
2. **STEP upognjenega dela** (mnoge delavnice razgrnitev izračunajo same s svojimi BD tabelami).
3. **PDF risba:** material in standard (npr. »1.4301, 2B, 1,5 mm«), debelina, notranji polmer, uporabljeni K ali
   BD, koti in smer (gor/dol), kritične mere s tolerancami, smer valjanja (ostri upogibi, brušene/vidne površine),
   stran zaščitne folije, površinska obdelava (prašni lak ~60–120 µm na stran — upoštevaj pri ujemih), vezni
   elementi (oznake PEM in stran vgradnje).
4. **Tabela upogibov** (zaporedje, kot, polmer, smer), če jo zahtevajo.
5. Količina in rok.

**Najprej pridobi tabelo upogibov delavnice** (material, T, V, R, K ali BD) in jo vpiši v predlogo.

Viri: catalog.pemnet.com (BS-M6-1), sendcutsend.com/?p=50432, soliddna.com (Solid Edge bend tables),
support.sw.siemens.com (Gagetable).

---

## 6. Pogoste značilnosti

- **Prirobnica** (flange): osnovni upogib ob robu.
- **Zavihki (hem):** zaprt 180° brez reže (le tanka duktilna pločevina, jeklo do ~1,5–2 mm; ne Al T6, ne debelo
  nerjavno); odprt z režo ≥ 1T (1,5–2T); solza (teardrop) z notranjim Ø ≥ 1T (2–3T varneje), za manj duktilne
  materiale; zvit (rolled) Ø 2–3T. Dolžina zavihka ≥ ~4T.
- **Odmik (jog, Z):** dva nasprotna upogiba za stopnico T (prekrivni spoj) ali več.
- **Žaluzije (louver):** prezračevanje, štanca; nagib ≥ 5°, razmik ≥ T, od upogiba ≥ 3T + R.
- **Zarezni jeziček (lance):** rez in upogib na treh straneh — prisloni, kljuke, vzmetni jezički.
- **Reliefi, rebra (emboss, bead):** ojačitev z lokalnim vlekom; globina ≤ 3T, nagib ≥ 5° [nepotrjeno].
  Diagonalno rebro čez upogib (gusset) močno poveča togost kotnika.
- **Zvitek (curl):** zavit rob za varnost in togost, zunanji R ≥ 2T.
- **Izvlečena luknja z navojem:** ovratnik za več navojev v tanki pločevini (vsaj 2–3 navoji).
- **Grezila:** oblikovana ali strojno izdelana; globina ≤ 0,6T.
- **Jeziček in utor (tab & slot, samopozicioniranje pred varjenjem):** širina jezička 3–5T, zračnost 0,1–0,15 mm
  na stran, zaobljeni vogali utora, utori ≥ 1,5T od tangente upogiba, reža za var ≤ 0,5 mm.
- **Mikrospoji (laserski mostički):** ≥ 1 mm široki, vsaj 2 na prirobnico, zunaj pasu matrice.
- **Zapiranje vogalov škatle:** odprt (reža 0,1–1 mm ali večji vogalni izrez; poceni), sočelni (butt, za varjenje),
  prekrivni (overlap/underlap, za točkovno varjenje, kovice, tesnost). Reža po načinu spajanja: laser ~0,1–0,2 mm,
  MIG 0,5–1 mm [nepotrjeno].

Viri: fractory.com/sheet-metal-hemming, sendcutsend.com (tab-and-slot, odd flange shapes), fictiv.com (tabs and
slots), pcbway.com (welded sheet metal guidelines), help.solidworks.com (closed corners), help.autodesk.com
(Inventor corner seam), support.ptc.com (Creo corner seams).

---

## 7. FreeCAD: delovna miza SheetMetal

**Jedro FreeCAD-a nima razgrnjevalnika pločevine** (ne PartDesign, ne BIM, ne TechDraw). Standard je dodatek
**SheetMetal** (Shai Seger, `github.com/shaise/FreeCAD_SheetMetal`, LGPL). Stanje 30. 9. 2026: različica 0.8.24,
dela s FreeCAD 1.x (upošteva novo poimenovanje topologije). **Nameščen 8. 10. 2026** (commit a1cf212, 0.8.24) v
`%APPDATA%\FreeCAD1-1\Mod\sheetmetal`, networkx 3.6.1 v `AdditionalPythonPackages\py311`; velja za nameščeni
FreeCAD 1.1 in lastno gradnjo (oba Python 3.11). Posodobitev: `git -C "%APPDATA%\FreeCAD1-1\Mod\sheetmetal" pull`.

### 7.1 Namestitev
- Orodja → Addon Manager → »SheetMetal Workbench«, ali ročno:
  `git clone https://github.com/shaise/FreeCAD_SheetMetal "%APPDATA%\FreeCAD\v1-1\Mod\sheetmetal"`.
  Mapo si delita nameščeni 1.1 in lastna gradnja (isti `v1-1`).
- Odvisnost **networkx** (≥ 3.4.2) za novi razgrnjevalnik V2; brez nje se uporabi stari V1 (z opozorilom).
  Nameščeni FreeCAD 1.1 je nima. Addon Manager jo namesti v `%APPDATA%\FreeCAD\v1-1\AdditionalPythonPackages\py311`
  (ročno: `pip install --target <ta mapa> networkx`). `FreeCADInit.py` doda mapo Mod in to mapo v `sys.path`
  tudi v `FreeCADCmd`, zato `import SheetMetalCmd` dela brez okna.
- Nastavitve: `BaseApp/Preferences/Mod/SheetMetal` (privzeti polmer, kot, K, BendType …) — **veljajo tudi v
  skriptah**, ker jih konstruktor vsakega objekta naloži. Lastnosti zato nastavi **po** konstrukciji.
  `UseOldUnfolder` vsili V1.

### 7.2 Orodja

| Ukaz | Razred (modul) | Kaj naredi |
|---|---|---|
| Add Base Shape | `SheetMetalBaseShapeCmd.SMBaseShape` | parametrični začetni del: Flat, L, U, Tub (korito), Hat, Box |
| Make Base Wall | `SheetMetalBaseCmd.SMBaseBend(obj, skica)` | **zaprta skica** → plošča debeline `Thickness`; **odprta skica** → profil z zaobljenimi vogali (`Radius`), izvlečen za `Length`. `BendSide` Outside/Inside/Middle, `MidPlane`, `Reverse` |
| Solid to Sheet Metal | `SheetMetalFromSolid.SMFromSolid` | pretvori telo/lupino (tudi uvoženo škatlo) v pločevino; izbrane ploskve odstrani, robove naredi v upogibe |
| Make Wall (prirobnica) | `SheetMetalCmd.SMBendWall(obj, osnova, ["EdgeN"])` | upogne prirobnico na izbranem **robu** (ukaz v GUI je na voljo le, ko so izbrani samo robovi; skripta sprejme tudi ploskev debeline); glej 7.3 |
| Hem | `SheetMetalHem.SMHem` | zavihek: Flat, Open, Teardrop, Rolled |
| Extend Face / Extend by Sketch | `SheetMetalExtendCmd.SMExtrudeWall` | podaljša steno ob ploskvi debeline; skica za obris |
| Fold on Line | `SheetMetalFoldCmd.SMFoldWall` | upogne ravno ploskev po črti iz skice (`radius`, `angle`, `Position`) — tako se naredi tudi odmik Z |
| Unfold | `SheetMetalUnfoldCmd.SMUnfold(obj, del, ["FaceN"])` | parametrična razgrnitev z izbrane ravne ploskve, skice za DXF/SVG |
| Corner Relief | `SheetMetalCornerReliefCmd.SMCornerRelief` | vogalni izrez, kjer se srečata dva upogiba: Circle, Square, Weld, lastna skica |
| Make Relief → Junction → Bend | `SheetMetalRelief`, `SheetMetalJunction`, `SheetMetalBend` | pretvorba telesa konstantne debeline (npr. PartDesign Pad + Thickness): izrezi v ogliščih, razrez robov z režo, ostri robovi → valjasti upogibi |
| Sketch on Sheet | `SketchOnSheetMetalCmd.SMSketchOnSheet` | izrez po skici, ki se ovije čez upogibe |
| Extruded Cutout | `ExtrudedCutout.ExtrudedCutout` | izrez skozi pločevino po skici |
| Forming in Wall | `SheetMetalFormingCmd.SMBendWall` | vtis orodja (relief, žaluzija) — **po tem dela ni več mogoče razgrniti** |

Ni posebnih ukazov za odmik (jog), rebro čez upogib (gusset) in tabelo upogibov (le tabela K, glej 7.4).

### 7.3 Make Wall — lastnosti
- `radius` (notranji), `length`, `angle` (90°), `invert`, `gap1`/`gap2` (reža na koncih), `extend1`/`extend2`.
- `BendType`: **Material Outside** (privzeto; plošča ostane, prirobnica zunaj), Material Inside, Thickness Outside,
  Offset.
- `LengthSpec`: **Leg** (od tangente upogiba), **Outer Sharp** (do zunanjega navideznega ostrega roba — ko so mere
  na risbi zunanje), Inner Sharp, Tangential.
- Razbremenitev: `reliefType` Rectangle/Round, `reliefw` (0,8), `reliefd` (1,0), `UseReliefFactor`, `ReliefFactor`.
- `AutoMiter` (privzeto vklopljen, `minGap` 0,2) — sosednje prirobnice se same zajerejo.
- `miterangle1`/`2`, `Sketch` (profil → več sten v eni značilnosti), `Perforate` (perforiran upogib).
- `kfactor` na steni vpliva le na predogled (`unfold`), vogalne izreze in Sketch on Sheet — **razgrnitev uporablja
  K iz objekta Unfold**.
- Debelino zazna sama iz izbrane ploskve.

### 7.4 K-faktor v SheetMetal
- Interno **ANSI**; DIN vnos se razpolovi. Razgrnitev: BA = (R + K·T)·kot.
- `SMUnfold.KFactor` (privzeto 0,4), `KFactorStandard` (ansi/din), ali `MaterialSheet` = preglednica, npr.
  `material_jeklo`: A1 `Radius / Thickness`, B1 `K-factor (ANSI)`, nato vrstice R/T → K (npr. 1 → 0,38; 3 → 0,43;
  99 → 0,5). Pod prvo vrstico velja prva vrednost, nad zadnjo zadnja.
- **Možna napaka v V2** (`BendAllowanceCalculator.get_k_factor`): zanka se ne premakne naprej, zato pri tabelah z
  več kot dvema vrsticama interpolira le med prvima dvema. Do preverbe uporabljaj dvovrstične tabele ali en K na
  debelino/polmer.

### 7.5 Skripte brez okna (FreeCADCmd ali `izvedi.py`)
Vsi razredi značilnosti in geometrijske funkcije delujejo brez GUI (pogledi, okna opravil in `Gui.addCommand` so
za `FreeCAD.GuiUp`). Datoteka, zgrajena brez okna, nima pogledov SheetMetal (splošne ikone, brez dvoklika); prek
našega spletnega strežnika (`izvedi.py`) GUI teče, zato dobi prave.

Pasti:
1. Izvoz DXF prek `SMUnfold` odpre pogovorno okno — brez okna kliči `importDXF.export([...], pot)` neposredno.
2. `SheetMetalNewUnfolder.getUnfoldSketches` brez zaščite piše v `ViewObject` (`SeparateSketchLayers`,
   `ShowBendAngles` = privzeto) → v FreeCADCmd verjetno AttributeError. Brez okna: `GenerateSketch = False` in
   razgrnitev prek neposrednih funkcij (spodaj).
3. Brez ločenih slojev je v skici razgrnitve tudi upogibna črta — **laser bi jo rezal**. Za laser izvozi le obris
   in luknje.
4. Potreben je aktivni dokument: `FreeCAD.setActiveDocument(doc.Name)`.
5. Ploskve izbiraj geometrijsko (normala, središče), ne s stalno številko `FaceN` (poimenovanje topologije).

Primer (**preizkušen 8. 10. 2026 v `FreeCADCmd`** nameščenega 1.1: plošča 100 × 60 × 2, prirobnica 25 mm, R 2, K 0,42 →
razgrnitev 129,461 × 60 mm = 100 + BA 4,461 + 25, točno po formuli; DXF ima le zaprt obris v sloju objekta, brez
upogibnih črt, dolgi robovi so razdeljeni na meji upogiba v 3 kolinearne odseke; STEP in parametrični `Unfold` z
`GenerateSketch = False` delujeta, sporoči »Using V2 unfolding system«. Kot koren vzemi največjo ravno ploskev):

```python
import FreeCAD, Part, importDXF
from FreeCAD import Vector as V
import SheetMetalBaseCmd, SheetMetalCmd, SheetMetalUnfoldCmd

doc = FreeCAD.newDocument("Nosilec"); FreeCAD.setActiveDocument(doc.Name)

sk = doc.addObject("Sketcher::SketchObject", "Osnova")          # zaprta skica -> plošča
pts = [V(0,0,0), V(100,0,0), V(100,60,0), V(0,60,0)]
for i in range(4):
    sk.addGeometry(Part.LineSegment(pts[i], pts[(i+1) % 4]))
doc.recompute()

base = doc.addObject("Part::FeaturePython", "Plosca")
SheetMetalBaseCmd.SMBaseBend(base, sk)
base.Thickness = 2.0; base.Radius = 2.0
doc.recompute()

def stranska(obj, pogoj):                                       # ploskev debeline, izbrana geometrijsko
    for i, f in enumerate(obj.Shape.Faces, 1):
        if f.Surface.TypeId == "Part::GeomPlane" and abs(f.normalAt(0, 0).z) < 1e-6 and pogoj(f):
            return f"Face{i}"

stena = doc.addObject("Part::FeaturePython", "Prirobnica")
SheetMetalCmd.SMBendWall(stena, base, [stranska(base, lambda f: f.CenterOfMass.x > 99)])
stena.radius = 2.0; stena.length = 25.0; stena.angle = 90
stena.BendType = "Material Outside"; stena.LengthSpec = "Leg"
doc.recompute()

# razgrnitev neposredno (V2, potrebuje networkx)
from SheetMetalNewUnfolder import BendAllowanceCalculator, getUnfold, SketchExtraction
bac = BendAllowanceCalculator.from_single_value(0.42, "ansi")
koren, ravno, pregibi, normala, info = getUnfold(bac, stena, "Face1")   # Face1 = poljubna ravna ploskev
zunanji, notranji, luknje = SketchExtraction.extract_manually(ravno, normala)
M = SketchExtraction.move_to_origin(zunanji, koren)
rez = doc.addObject("Part::Feature", "Rez")
rez.Shape = Part.makeCompound([zunanji, *notranji, *luknje]).transformed(M)
importDXF.export([rez], r"C:\pot\nosilec_rez.dxf")      # laser: samo obris in luknje
Part.export([stena], r"C:\pot\nosilec.step")            # upognjen del za delavnico
# brez networkx: SheetMetalUnfolder.getUnfold({1: 0.42}, stena, "Face1", "ansi")
```

Upogibne črte (`pregibi`) vrne `getUnfold` v izvornem koordinatnem sistemu; ob prvi uporabi vizualno preveri, ali
se ujemajo z obrisom.

### 7.6 Omejitve razgrnitve
- Debelina mora biti konstantna, ravne ploskve prave ravnine, upogibi pravi valji (ne B-zlepki — nekateri CAD-i jih
  tako izvozijo v STEP; poskusi Refine ali modeliraj znova).
- Ravne ploskve brez šivov in razdelilnih črt (`removeSplitter()` / Refine).
- Izrezi čez upogib ali vogal upogiba pogosto podrejo razgrnitev; luknje ≥ ~2T od tangente.
- Stene, ki se dotikajo (reža 0), se zlijejo in jih ni mogoče razgrniti → `gap1`/`gap2` > 0, `AutoMiter`, Junction.
- Uvožen STEP: le čisto telo; zaobljeni robovi čez debelino ali posnetja pokvarijo konstantno debelino.
- Preizkus: razvita dolžina prvega dela proti ročnemu izračunu (poglavje 1.3) ali `tools/calc-unfold.py` v repu
  dodatka.

### 7.7 Alternative v jedru
- PartDesign Pad + Thickness → SheetMetal Relief → Junction → Bend → Unfold (uradno dokumentirana pot).
- PartDesign Pad debeline + Fillet (notranji R in zunanji R + T, koncentrična valja): pravilna 3D oblika, razgrnitev
  ročno ali s SheetMetal razgrnjevalnikom.

Viri: github.com/shaise/FreeCAD_SheetMetal (README, package.xml, InitGui.py, SheetMetalCmd.py, SheetMetalBaseCmd.py,
SheetMetalUnfoldCmd.py, SheetMetalNewUnfolder.py, SheetMetalUnfolder.py, SheetMetalKfactor.py, SheetMetalTools.py,
SheetMetalHem.py, SheetMetalFromSolid.py, …; prebrano iz klona 30. 9. 2026, commit a1cf212), wiki.freecad.org
SheetMetal_Workbench / SheetMetal_Unfold / SheetMetal_AddWall (prek zrcala github.com/FreeCAD/FreeCAD-documentation),
forum.freecad.org/viewtopic.php?t=60818, github.com/shaise/FreeCAD_SheetMetal/issues/54,
de.wikipedia.org/wiki/Biegeverkürzung, lokalno `src/App/FreeCADInit.py`.

---

## 8. Postopek za naše delo

1. **Material in debelina najprej** (3a): `python` → `import plocevina_materiali as pm; print(pm.opis("inox", 4))` da V, R, K,
   najkrajši krak, silo in klin; v skripti kosa `pm.mere_plocevine(mere, "Al 5754-H22", 2.0)` napolni objekt »Mere«
   (Debelina, Polmer, KFaktor, KTabela, Material, OdprtinaV, Klin), vsi upogibi in razgrnitev se vežejo nanj z izrazi.
   **Od delavnice** pridobi tabelo (material, debeline, matrice V, nastali R, K ali BD) in jo vpiši (`v=`, `r=`,
   `Samodejno` izklopi). En polmer na debelino.
2. **Model:** zaprta skica → Make Base Wall (ali Base Shape) → Make Wall na robovih (polmer, kot, `LengthSpec`
   po tem, kako je kotirana risba) → razbremenilni in vogalni izrezi → luknje (Extruded Cutout) stran od upogibov.
3. **Preveri DFM** (poglavje 4): prirobnica ≥ 0,7·V, luknje ≥ 2T + R od upogiba, izrez R + T + 0,5 mm, polmer ≥
   najmanjši za material.
4. **Unfold** z ravne ploskve, K iz tabele; preveri razvito dolžino proti ročnemu izračunu.
5. **Izvoz:** DXF samo obris + luknje (upogibne črte ločeno), STEP upognjenega dela, PDF risba (TechDraw) z
   materialom, debelino, R, K, koti, smerjo valjanja, ISO 2768-mK.
6. Skripte modelov naj gredo v `Oblak\3D modeliranje\<Projekt>\Skripte\` kot pri drugih projektih; ploskve izbiraj
   geometrijsko.

**V spletnem pogledu** (od 8. 10. 2026): zavihek **Pločevina** z vsemi 18 ukazi dodatka (FreeCAD-ove ikone, angleška imena,
ker dodatek nima slovenskega prevoda). Preverjeno prek strežnika: skica → Make Base Wall (obrazec: debelina, polmer,
stran) → izbran rob → Make Wall (obrazec: dolžina, način dolžine, polmer, kot, lega) → izbrana največja ravna ploskev
→ Unfold (obrazec: K, ANSI/DIN, preglednica materiala, skica, DXF/SVG izvoz) — razgrnitev 129,398 mm pri K 0,4, točno
po formuli. Dve pasti, ki sta se pokazali in sta popravljeni v strežniku: (1) pri skritem oknu FreeCAD ne osvežuje
omogočenosti gumbov, zato `_sprozi_ukaz` dejanje omogoči sam, če `isActive()` vrne True; (2) Python opazovalec
pogleda (`Gui.addDocumentObserver` s `slotChangedObject`) je pokvaril vse objekte Part, nastale med delovanjem
strežnika (brez `DiffuseColor`; Make Wall je padel) — odstranjen, videz se preverja vsako sekundo.

**Kaj še ni preizkušeno:** primer iz 7.5 prek `izvedi.py` (z GUI, skice razgrnitve z ločenimi sloji), prikaz objektov SheetMetal v spletnem pogledu in drevesu, napaka interpolacije K v V2.

---

## 9. Izkušnje iz prvega kosa (betonski podstavek, 8. 10. 2026)

Prenos kosa iz SolidWorksa (`Oblak/3D modeliranje/Betonski podstavek/`): SLDPRT se prebere tako, da se SolidWorks
zažene prek COM brez okna (VBScript `GetOpenDocSpec` + `OpenDoc7` z `ReadOnly`, `SaveAs3` v STEP; PowerShell s
SolidWorksovim COM ne dela), mere se odčitajo iz STEP v FreeCADCmd. Kar se je pokazalo:

- **»Solid to Sheet Metal« (SMFromSolid)** je najhitrejša pot za škatle in korita: parametrično telo (PartDesign) ->
  odstrani dno, razreže navpične robove. Ravne ploskve ob prostih robovih obreže za 0,1 mm (reža na vogalih), tudi
  ob dnu — telo naredi 0,1 mm višje.
- **Shranjena imena ploskev in robov se ob spremembi mer pokvarijo** (posneti robovi, FreeCAD 1.x): zato
  `lastno/plocevina/lastna_plocevina.py` (`TeloVPlocevino`, `Razgrnitev`) izbiro poišče geometrijsko ob vsakem preračunu.
- **Mere na enem objektu** (`App::FeaturePython` z lastnostmi Length): spletni pogled jih pokaže kot urejljiva polja;
  skice, izboklina, posnetje in pločevina se nanje vežejo z izrazi (številke v izrazih z enoto: `- 40 mm`).
- **STEP**: nekaj ploskev iz pretvorbe bralnik izpusti (odprta lupina, čeprav je zapis MANIFOLD_SOLID_BREP); popravi
  jih pretvorba samo teh ploskev v NURBS (preizkus vsake ploskve z zapisom in branjem). Po izvozu vedno preberi STEP
  nazaj in preveri, da je zaprto telo.
- **DXF za laser** iz zgornje ploskve razgrnitve (zanke, poravnane na XY), brez upogibnih črt.
- **Preverjanje**: prostornina in prekrivanje z izvirnikom (`common`), raztegovanje na kopiji (več naborov mer in
  vrnitev na izvirne), slike iz STL z lastnim izrisovalnikom.

## Parametrično ohišje iz uvoženega (2026-10-29, Ohišje zadaj Slim A)

`Photobox Slim A/Deli/Pločevina/Ohišje zadaj Basi - parametrično.FCStd`, skripte v `Skripte/ohisje_parametricno/`:
- U profil: odprta skica = **zunanja** ploskev, `SMBaseBend` z `BendSide = "Outside"` (material navznoter), `Radius` = notranji
  polmer vogalov, `Length` = višina. `Inside` da material navzven (okvir +2T).
- Zavihka: `SMBendWall` na čelnih ploskvah debeline stranic, `BendType = "Material Inside"`, `LengthSpec = "Outer Sharp"`
  (zunanja mera zavihka), `gap1/gap2` skrajšata zavihek na koncih.
- **`ExtrudedCutout` je pri stotinah lukenj neuporaben**: za debelino primerja vsako ploskev z vsako (`distToShape`, O(n²)),
  vsak naslednji izrez je počasnejši (4 izrezi ~10 min na glavni niti). Namesto njega skica → `Part::Extrusion` (±5 mm po
  normali, `Solid`) → `Part::Cut`: 429 izrezov v 12 s. Skice stenam sledijo z izrazi na `.Placement.Base`.
- Izreze iz uvoženega kosa prenesi kot geometrijo skice (notranje zanke zunanje ploskve stene; dva polkroga → krog).
- Razgrnitev izvirnika je imela K 0,5 (ne privzeti 0,44): primerjaj K, preden iščeš razliko v geometriji.
- Zamenjava v sestavih brez preračuna: v dokumentu kosa povezava na nov kos v istem `App::Part`, izvirnik skrit (spoji
  sestavov kažejo na njegove ploskve in ostanejo veljavni).

## Prenova uvoženih kosov v drugo debelino in polmer (2026-10-29, Slim A → Al 5754-H22 2 mm, R 2)

`lastna_plocevina.prenovi_plocevino(oblika, debelina, polmer, obrni)` in objekt `PrenovaPlocevine` (parametri Debelina,
Polmer, Obrni; izvirnik ostane skrit, ker nanj kažejo spoji sestavov):
1. debelina iz para vzporednih velikih ploskev; upogibi = pari koaksialnih valjev r / r + T (stene lukenj izločene po
   osni dolžini ≤ 1,2 T, sicer povežejo obe strani); valji z r ≥ 10 T so zviti deli in ostanejo;
2. `defeaturing(upogibi)` → ostri kos; strani pločevine po sosednosti velikih ploskev; zunanja = več izbočenih robov
   (zviti deli: večji polmer);
3. postopek A: vsaka notranja ploskev posebej `makeOffsetShape(ΔT, fill=True)` + unija; zunanji ostri rob `makeFillet(R + T)`,
   nato obroč R … R + T (odebelitev valjaste ploskve navznoter) + unija. Postopek B (rezerva): lupina zunanje strani
   `makeOffsetShape(-T, join=2, fill=True)`. **Dvojno zaokroževanje (notranji R in zunanji R + T) OCC sestavi neveljavno**
   (»Self-intersecting wire«), lupina iz več ploskev s `fill` pogosto pade (»ThruSections failed«);
4. luknje zunanje strani se izrežejo na koncu skozi novo debelino (luknja ob upogibu sicer zmoti zaokroževanje).
Preverjanje: veljavnost, prostornina ≈ izvirnik · T_nova / T_stara, okvir nespremenjen (pri ravnih ploščah +ΔT).
Dopolnitve: dvojček velike ploskve mora ležati nasproti (prekrivanje projekcije), sicer se strani povežejo; ravne notranje
ploskve se odebelijo z izvlekom, ukrivljene z odmikom (preverjena prostornina); med upogibanjem so luknje zapolnjene;
pladnji (štirje upogibi z vogali) dobijo kvadratno vogalno razbremenitev R + T + 0,5, ker stara (za stari polmer) novega
zaokroževanja ne spusti skozi (`_vogalne_razbremenitve`). Videz: vsebnik kosa (App::Part) z lastnostjo Videz =
»pločevina« da lisasto strukturo tudi novemu kosu — aluminijastim nastavi `videz.nastavi_videz(vsebnik, "aluminij")`.
Izid 29. 10. (prvi krog): 19 od 25 kosov 1,5 mm; ne gre: posodici in stena klime z letvijo (strani niso ločljive), podstavek trda tla
in pokrovček betonskega podstavka (OCC), Betonski podstavek in Šild 2 (okvir se spremeni – napačna geometrija).
Razgrnitev: `KTabela` »1:0.40; 3:0.50« (Al 5754-H22, R/T); razgrnjevalnik pri nekaterih kosih pade z vseh ploskev
(»Two points are coincident«: Elektro levo, Elektro sredina).

## Zlivanje dveh uvoženih kosov v en kos (2026-10-09, ohišje klime Slim A)

- Stena in letev, ki se stikata v skupni ravnini, se zlijeta v eno telo (`fuse`), a `getUnfold` (SheetMetalNewUnfolder) iz
  zlitega telesa vrne neveljavno razgrnitev: reži v spodnji prirobnici stene se zlijeta z zunanjim robom (ne glede na izbrano
  izhodiščno ploskev). Kosa posamič se razgrneta brezhibno.
- Rešitev: vsak del razgrni posebej z izhodiščem v **isti ravnini** (ploskev z normalo +Z na skupni ravnini); `getUnfold` pusti
  izhodiščno ploskev na mestu, zato je unija ploskih razgrnitev pravilna razgrnitev celega kosa (preverjeno: ploščina = prostornina / T).
- Kjer upogib ene prirobnice konča ob drugi prirobnici, se konca dotikata in razgrnitev se tam raztrga: izreži sprostitev (2 mm reža
  čez upogib in prirobnico).

## Na novo narisani kosi z majhnim polmerom (2026-10-29, Slim A: mizica, posodica za slike, stena klime)

Kosi z notranjim R ≈ 0,3 se s prenovo ne dajo prenesti na R 2, zato so narisani znova kot SheetMetal (osnovna plošča iz zaprte skice
z mero-izrazi na objektu »Mere«, stene `SMBendWall`, luknje iz izvirnika s `izrezi_iz_izvirnika.py`: notranje žice ravnih ploskev →
skica → izvlek ±5 mm → odštevanje, vogali in posebni izrezi s skico in izvlekom). Pasti:
- **Jeziček, nižji od upogibnega pasu** (prirobnica le na delu roba, rob plošče ob njej nižje od R + T): »Material Inside« in »Thickness
  Outside« upogib razširita čez **ves** rob plošče (prirobnica od stopnice do stopnice). Deluje »Material Outside«: upogib je ves zunaj
  plošče, notranja ploskev prirobnice je za **polmer** nad robom plošče — rob plošče v skici postavi na zunanjo mero − T − R, ob straneh
  razbremenilni zarezi (širina 0,8, 1 mm pod začetkom upogiba).
- »Outer Sharp« stene na čelu druge stene: pri posodici je bila dolžina zunanja mera + T, pri steni klime točno zunanja mera — dolžino
  vedno preveri po okvirju.
- `SMBaseBend` iz zaprte skice: smer debeline ni vedno normala skice; preveri okvir in po potrebi `Reverse = True`.
- Okvir izvirnika je zaokrožen: ravnine za izreze vzemi iz `CenterOfMass` ploskve (-92,1829, ne -92,18), sicer filter s toleranco 1e-3 ne najde ničesar.
- Zaokrožitev v skici osnovne plošče lahko poravna sosednja stena; zaokroži jo raje kot izrez po steni.
