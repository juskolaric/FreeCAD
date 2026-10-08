# Kaj je sestav (assembly) in kaj so deli (parts)

Razlaga pojmov, ki jih uporabljata `onshape-funkcije.md` in `fusion-funkcije.md`, in kako jim ustreza FreeCAD.
Stanje 7. 10. 2026. Za primerjavo je dodan SolidWorks, ker je naš vzor za vmesnik.

## 1. Pojma na kratko

- **Del (part)** je en kos, kot pride iz izdelave: ena pločevina, en vijak, en odlitek. Ima svojo geometrijo
  (telo), svojo zgodovino značilnosti (skica → izboklina → luknje → zaokrožitve), material, maso in številko
  v kosovnici. Del se oblikuje sam zase, v svojem koordinatnem sistemu.
- **Sestav (assembly)** je skupina delov in podsestavov, postavljenih drug ob drugega. Sestav **nima lastne
  geometrije**; nosi samo **instance** delov (isti del lahko nastopa večkrat, npr. 30 enakih kovic), njihove
  **položaje** in **vezi** med njimi (mate / joint / spoj): »ta ploskev leži na tej«, »ta os sovpada s to«.
  Reševalnik iz vezi izračuna položaje; kar ni vezano, se da premikati (prostostne stopnje, DOF).
  Sestav lahko vsebuje **podsestave** (sestav v sestavu), zato nastane drevo: izdelek → sklopi → deli.
- **Telo (body)** je najmanjša enota geometrije: en zvezni kos snovi (solid). Del ima praviloma eno telo,
  večtelesni del pa več (npr. pred združitvijo ali odlitek z vložkom).
- **Kosovnica (BOM)** se dela iz sestava: našteje dele, koliko instanc vsakega in njihove lastnosti.
- **Risbe** se delajo iz obojega: iz dela (izdelavna risba kosa) in iz sestava (montažna risba, razstavljeni
  pogled, pozicijske oznake, kosovnica).

Pravilo palca: **če gre v izdelavo kot en kos, je del; če se sestavi iz kosov, je sestav.**

## 2. Kako to vidi vsak program

| | Del | Sestav | Vezi | Posebnost |
|---|---|---|---|---|
| **SolidWorks** | datoteka `.sldprt`, eno ali več teles | datoteka `.sldasm`, kaže na datoteke delov in podsestavov | mates (Coincident, Concentric, Distance, Angle, Parallel, Tangent, mehanski …) | stroga ločitev del / sestav; urejanje dela v kontekstu sestava; risba `.slddrw` iz obeh |
| **Onshape** | **Part Studio** je zavihek z **več deli** v eni zgodovini značilnosti; del nastane, ko značilnost ustvari novo telo (»New«) | zavihek **Assembly**: Insert vstavi del, cel Part Studio ali podsestav kot instance | mate-i prek **Mate connectorjev** (Fastened, Revolute, Slider, Planar, Cylindrical, Pin slot, Ball, Parallel, Tangent, Width) + relacije (zobniki, vijak …) | deli, ki se morajo ujemati (pokrov in ohišje), se modelirajo skupaj v istem Part Studiu; sestav je ločen zavihek v istem dokumentu |
| **Fusion** | **Component** (komponenta) s svojimi telesi, skicami in izhodiščem; en dizajn ima lahko eno komponento (= del) ali drevo komponent | isti dizajn: koren je komponenta, podkomponente so deli ali podsestavi; **Insert Component** doda zunanji dizajn kot referenco | **Joints** (Rigid, Revolute, Slider, Cylindrical, Pin-Slot, Planar, Ball), As-Built Joint, Rigid Group, Ground, Motion Link | del in sestav sta v **isti datoteki**; »intent-driven design« (2025) ob začetku vpraša Part / Assembly / Hybrid; telo (Body) brez komponente je samo geometrija brez položaja in kosovnice |
| **FreeCAD 1.0+** | **Body** (`PartDesign::Body`, eno telo z zgodovino značilnosti) ali vsebnik **Part** (`App::Part`, več teles z enim položajem) | **Assembly** (`Assembly::AssemblyObject`, okolje Assembly od 1.0): vsebuje **povezave** (`App::Link`) na dele iz istega ali drugega dokumenta, skupino **Joints**, kosovnice in razstavljene poglede | **Joint** (Fixed, Revolute, Cylindrical, Slider, Ball, Distance, Parallel, Perpendicular, Angle, RackPinion, Screw, Gears, Belt) + **Grounded** za sidranje | del in sestav sta lahko v isti datoteki `.FCStd` ali v ločenih (Link čez datoteke); podsestav = Assembly v Assemblyju |

Prevod pojmov, ki ga uporabljamo v slovenskih opisih: part = **del**, body = **telo**, assembly = **sestav**,
subassembly = **podsestav**, instance = **instanca** (ali ponovitev), mate / joint = **vez** (ali spoj),
Part Studio ostane Part Studio, component = **komponenta**.

## 3. FreeCAD podrobneje (to je naš motor)

- `PartDesign::Body` — **en del z eno trdnino**. Značilnosti (Pad, Pocket, Fillet …) se nizajo v verigo; vsaka
  nova vzame rezultat prejšnje (Tip). Telo ima svoj izhodiščni sistem (Origin: 3 osi, 3 ravnine) in `Placement`.
  V Part Designu je to tisto, kar v SolidWorksu imenujemo del.
- `App::Part` — **vsebnik**: skupina objektov (teles, skic, pomožne geometrije) z enim skupnim `Placement`.
  Uporablja se za »del iz več teles« ali kot preprosta ročna sestava brez vezi (deli se postavijo z vpisom položaja).
- `Assembly::AssemblyObject` — **sestav** (okolje Assembly, od 1.0). Ukazi: Create Assembly, Insert Link (vstavi
  del ali podsestav kot `App::Link`), Insert New Part, Create Joint, Toggle Grounded, Solve, Create BoM,
  Exploded View, Export ASMT. Reševalnik je OndselSolver. V drevesu ima sestav skupine **Joints**,
  **Bills of Materials** in **Exploded Views**.
- `App::Link` — **instanca**: kazalec na obstoječi objekt z lastnim položajem; geometrija se ne podvaja,
  zato 30 kovic pomeni 30 povezav na eno kovico. `Assembly::AssemblyLink` je povezava na podsestav.
- Vez (`Joint`) je Python objekt (`src/Mod/Assembly/JointObject.py`) z dvema priključnima koordinatnima
  sistemoma (JCS 1 in 2, vsak na ploskvi/robu/vozlišču nekega dela) in vrsto vezi; dodatno odmik, kot,
  obrat, omejitve dolžine in kota.
- Starejši pristop brez okolja Assembly: deli kot `Part::Feature` z ročno nastavljenim `Placement` (brez vezi,
  brez reševalnika). Tako sta narejena naša modela `police_folija.py` in `soba_folija.py` (Oblak/3D modeliranje/Zalogovnik folije/Skripte):
  vsak kos pločevine je `Part::Feature`, kovice so ena sestavljena oblika (compound), »sestav« je dokument sam.
  Kosovnica se v skripti računa ročno. Pravi sestav bi imel vsak kos kot Body, vsako ponovitev kot Link
  in kovico kot en del s 30 povezavami.

## 4. Kaj to pomeni za spletni pogled (`lastno/splet`)

- Posnetek modela zdaj izpusti vsebnika `PartDesign::Body` in `App::Part` in pokaže njune vidne elemente
  (`_vidni_objekti` v `streznik.py`). Za sestave je treba enako obravnavati `Assembly::AssemblyObject` in
  **razrešiti `App::Link`**: geometrija je na povezanem objektu, položaj pa na povezavi (`LinkPlacement`;
  pri poljih `ElementCount` več položajev). Brez tega se vstavljeni deli v brskalniku ne pokažejo ali pa
  stojijo na mestu izvirnika.
- Drevo objektov (plan, korak 10) naj loči tri ravni: **sestav → instanca (del ali podsestav) → telo**, kot
  Onshapeov Instances list in Fusionov Browser. Enake instance istega dela naj kažejo na isti vir.
- Izbira: klik v brskalniku mora vrniti **pot** (sestav/povezava/telo/ploskev), ne le imena objekta, ker ista
  ploskev istega dela obstaja v vsaki instanci. FreeCAD-ova izbira to že podpira (`SubName` s potjo).
- Vezi: Onshape in Fusion ju ustvarjata z izbiro dveh točk na ploskvah (Mate connector / Joint origin) s
  sklepanjem (vogali, središča lokov, sredine robov). Naše pripenjanje v skici (krajišča, razpolovišča, središča,
  kvadranti) je isti mehanizem in se da ponovno uporabiti za vezi.
- Kosovnica: FreeCAD jo zna narediti (Create BoM) kot preglednico; v brskalniku je to tabela iz drevesa
  sestava, ne iz ročnega štetja kot v `police_folija.py`.

## Viri

- FreeCAD: izvorna koda `src/Mod/Assembly` (`CommandCreateAssembly.py`, `CommandInsertLink.py`,
  `CommandInsertNewPart.py`, `JointObject.py`, `UtilsAssembly.py`, `App/AssemblyObject.cpp`,
  `App/AssemblyLink.cpp`, `App/BomGroup.cpp`), primer `data/examples/AssemblyExample.FCStd`.
- Onshape in Fusion: strani, naštete na koncu `onshape-funkcije.md` (§3 Sestavi, Part Studio) in
  `fusion-funkcije.md` (§0, §2.9 Sestavljanje).
- SolidWorks: iz spomina, brez preverjanja dokumentacije (za potrebe primerjave izrazov).
