# Toplotna analiza boxa na soncu — pregled odprtokodnih orodij (14. 10. 2026)

**Vprašanje:** koliko se segreje notranjost Photobox Slim (701 × 770 × 2063 mm, pločevina 1,5 mm, steklo in pleksi
spredaj, v notranjosti TV, PC z napajalnikom, tiskalnik, Mikrotik, LED, že vgrajena klima »Klima Basi ohišje«),
ko stoji na soncu (Biograd, Opatija, Zlatibor …), in kakšno hlajenje (W) je treba, da ostane pod mejo naprav.

## Kaj je že na tem računalniku

- **FreeCAD 1.1 FEM s CalculiX-om** (`ccx.exe` v pixi okolju, mreža Netgen). Toplotni robni pogoji so že v tej
  gradnji: površinski tok (DFlux), konvekcija (FILM), sevanje (RADIATE, od 1.1 tudi sevanje med ploskvami — cavity),
  toplotni vir v telesu (W), začetna temperatura, časovni potek obremenitve (amplitude). Dovolj za 3D prevajanje.
- Zapisovalnik za **Elmer** je v kodi, Elmer sam **ni** nameščen.
- Python v pixi: numpy, scipy. Ni: pvlib, ht, gmsh, OpenFOAM, EnergyPlus, ParaView, Elmer, WSL Ubuntu (Docker ne dela).
- Model boxa: `Oblak/3D modeliranje/Photobox Slim/Slim A.FCStd` (301 teles, pločevina z debelinami).

## Orodja (vsa odprtokodna)

| Orodje | Kaj zmore | Sonce | Hlajenje / zrak | Windows | Ocena za nas |
|---|---|---|---|---|---|
| **Python bilanca: pvlib + ht + scipy** | box kot 1–5 toplotnih vozlišč (plašč, zrak, PC, zaslon); urni izračun temperature in potrebne hladilne moči | pvlib: sončno sevanje na vsako ploskev po uri, TMY podatki (PVGIS) za vsako lokacijo | ht: koeficienti konvekcije, sevanje v nebo; ventilator/klima kot odvzem W | pip | **1. korak.** Dan dela, takoj odgovor »koliko stopinj, koliko W«. Treba umeriti z meritvijo. |
| **EnergyPlus** (+ `eppy` / `pyenergyplus`) | box kot ena cona s 6 stenami, steklo, notranji dobitki, »Ideal Loads« vrne urno hladilno moč za celo leto | da, iz vremenske datoteke EPW (Rijeka, Zadar, Beograd, Ljubljana) | da: ventilacija, infiltracija, idealno hlajenje → velikost klime | namestitveni paket | **2. korak.** Narejen za stavbe, dela tudi za 1 m³ cono. Letni profil, ure nad 35/40 °C. |
| **FreeCAD FEM + CalculiX** | 3D prevajanje v pločevini, steklu, zaslonu; stacionarno in tranzientno; vroče točke | ročno: absorbirano sevanje α·G kot DFlux na osončene ploskve | konvekcija FILM na zunanjih in notranjih ploskvah; zraka ne premika (notranji zrak le kot telo z efektivno prevodnostjo) | **že nameščeno** | **3. korak.** Porazdelitev temperature, zaslon za steklom, kaj greje najbolj. Brez CFD. |
| **Elmer FEM** | kot CalculiX + sklopljen tok zraka (Navier-Stokes) + toplota + sevanje z view faktorji | ročno kot zgoraj | naravna konvekcija v 3D je zahtevna za konvergenco | namestitveni paket, FreeCAD ga poganja | Rezerva, če CalculiX ne zadošča; ne pred OpenFOAM-om. |
| **OpenFOAM** (+ CfdOF v FreeCAD-u) | CFD: naravna konvekcija, ventilatorji, rešetke, `chtMultiRegionFoam` (pločevina + zrak), `solarLoad` (sonce po datumu/uri, senčenje) | da, vgrajen model sonca | da, najbolj natančno | BlueCFD 2024-1, MinGW paket openfoam.com (CfdOF le 2212) ali WSL Ubuntu | **4. korak, samo če 1–3 ne zadostujejo.** CfdOF zna le buoyant tok, brez CHT in sevanja → primer urejaš ročno. Največ dela. |
| **OpenModelica + Buildings** | dinamični model z regulacijo (klima vklop/izklop, ventilator), cikli | iz vremenske datoteke | da, s krmiljenjem | namestitveni paket | Neobvezno; za simulacijo delovanja klime čez dan. |
| CalculiX + gmsh + ParaView (brez GUI) | isto kot FreeCAD FEM, skriptirano | ročno | ne | pip/paketi | Le če hočemo samodejne serije brez FreeCAD-a. |
| Code_Aster, SU2, FEniCSx | zmorejo, a brez prednosti | ročno | SU2 CHT | težavno | Ne priporočam. |
| Radiance (Ladybug / Honeybee) | senčenje od sosednjih objektov, dreves | da | ne | pip | Samo, če je lokacija delno v senci. |

## Podatki, ki jih potrebujemo (uporabnik / delavnica)

- Barva in površina pločevine (bela α ≈ 0,2–0,3, temna 0,8+; prah ali folija) — največji vpliv.
- Moči naprav: PC + napajalnik, TV, tiskalnik (mirovanje / tisk), Mikrotik, LED obroči, POS.
- Obstoječa klima: model in hladilna moč (W), kje jemlje in kam odvaja zrak; rešetke in odprtine v plašču.
- Lokacije in orientacija sprednje stene; ali stoji na asfaltu, travi, pod streho.
- Meritve iz pravih boxov za umeritev: temperatura v notranjosti čez vroč dan (Shelly z dodatkom za temperaturo ali
  USB logger). Vending App že spremlja temperaturo kamere (`camera-temp-watch`) — to je prvi vir.

## Predlagani koraki

1. **Bilančni model** (pvlib + ht, skripta v `Oblak/3D modeliranje/Photobox Slim/Skripte/`): najhujši dan (julij,
   Biograd), notranja temperatura brez hlajenja in potrebna moč hlajenja za cilj 35 °C; tri barve pločevine.
2. **EnergyPlus** z EPW za 3 lokacije: urni profil čez leto, ure nad mejo, velikost klime.
3. **FreeCAD FEM** na poenostavljenem plašču Slim A: porazdelitev, vroče točke (zaslon, tiskalnik).
4. Umeritev z meritvijo iz boxa; **OpenFOAM** šele, če vprašanje postane »kam z rešetko in ventilatorjem«.

## Namestitev (ko se odločimo)

```powershell
.pixi\envs\default\python.exe -m pip install pvlib ht            # korak 1
# korak 2: EnergyPlus namestitveni paket (energyplus.net), pip install eppy; EPW iz climate.onebuilding.org
# korak 4: WSL Ubuntu + openfoam.com v2412 ali BlueCFD Core 2024-1; v FreeCAD-u dodatek CfdOF
```

Viri: FreeCAD wiki FEM ConstraintHeatflux (1.0/1.1), CfdOF README, OpenFOAM API `solarLoad`, pvlib, ht, EnergyPlus
Engineering Reference, LBNL Modelica Buildings.
