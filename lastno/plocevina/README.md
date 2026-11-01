# Lastna pločevina (`lastna_plocevina.py`)

Parametrična objekta za pločevino nad dodatkom SheetMetal (shaise), ki ne hranita imen ploskev in robov in se zato ne
pokvarita, ko se mere osnovnega telesa spremenijo (FreeCAD 1.x sledenje topologiji pri posnetih robovih izgubi sklice,
npr. `missing element reference … ?Edge14`).

| Objekt | Kaj naredi |
|---|---|
| `TeloVPlocevino(obj, telo)` | Telo -> pločevina (SheetMetal »Solid to Sheet Metal«). Odstrani ravne ploskve na dnu, razreže vse nevodoravne robove; vodoravni robovi postanejo upogibi. Lastnosti `Debelina`, `Polmer`, `Navznoter`. |
| `Razgrnitev(obj, kos)` | Razgrnitev (SheetMetal V2) z največje ravne ploskve navzgor. Lastnosti `KFaktor`, `Standard` (ANSI/DIN). |
| `PrenovaPlocevine(obj, izvirnik)` | Uvožen kos v novo debelino in polmer (`prenovi_plocevino`). Lastnosti `Debelina`, `Polmer`, `Obrni`. |
| `obris_za_laser(oblika)` | Zanke zgornje ploskve razgrnitve, poravnane na XY v izhodišče — za DXF brez upogibnih črt. |

Vsi trije objekti imajo `Material` (seznam iz tabele) in `Samodejno`: polmer in K se vzameta iz tabele materiala
(`plocevina_materiali.py`, odločitev 29. 10. 2026) ob vsaki spremembi materiala ali debeline; stari kosi ob odprtju dobijo
`Samodejno = False`, da se jim polmer ne spremeni. Vrednost delavnice vpiši ročno in `Samodejno` izklopi.

**`plocevina_materiali.py`** — parametri upogiba po materialu in debelini (Amada, katalog AFH 2024; `raziskava/plocevina.md` §3a):
`odprtina_v(T)` (6 T do 3 mm, 8 T do 8 mm …), `polmer(material, T)` (delež V, zaokrožen na 0,5, ≥ najmanjši za material),
`k_faktor`, `k_tabela`, `parametri(material, T, v=None, r=None)` (slovar V, R, K, KTabela, krak, sila, klin),
`opis(material, T)` (vrstica za pogovor) in `mere_plocevine(mere, material, T)`, ki na objekt »Mere« kosa vpiše
Debelina, Polmer, KFaktor, KTabela, Material, OdprtinaV, Klin. `najdi("inox")` prepozna material po delu imena.
Ključi: `Jeklo S235 / DC01`, `Nerjavno 1.4301`, `Al 5754-H22`, `Al 6082-T6`, `Baker / medenina`.

**`oznaci_dxf.py`** — laserska oznaka kosov (odločitev 30. 10. 2026): vsak DXF razgrnitve dobi v sloju `GRAVURA` vgravirano
kodo `SA-07 POKROV ZGORAJ AL2` (koda, ime brez šumnikov, material+debelina; krajše različice, če ni prostora, višina 6 → 3 mm) na
najgloblji točki razgrnitve (najdlje od rezov in lukenj, praviloma osnovna ploskev). Sistemski Python (ezdxf + shapely), ne pixi:
`python oznaci_dxf.py "<mapa DXF po materialih>" --izhod "<mapa>" --predpona SA --seznam "<Seznam kosov za razrez.csv>"`;
izhod je kopija map z oznakami in `Oznake kosov.csv` (koda ↔ kos). Obris v sloju `REZ` ostane nedotaknjen; premajhni kosi
(< ~20 mm) ostanejo brez oznake in so v CSV označeni.

Uporaba: `doc.addObject("Part::FeaturePython", "Plocevina")`, nato `lastna_plocevina.TeloVPlocevino(obj, telo)`;
v GUI še `obj.ViewObject.Proxy = 0`. Zgled: `Oblak/3D modeliranje/Betonski podstavek/Skripte/betonski_podstavek.py`.

## Namestitev

Modul mora biti na poti Pythona, ko FreeCAD odpre dokument, sicer se objekta ne preračunata (obdržita shranjeno obliko).
Mapa je z uporabniškimi dodatki povezana s stičiščem (en izvor, repozitorij):

```powershell
New-Item -ItemType Junction -Path "$env:APPDATA\FreeCAD\v1-1\Mod\lastna_plocevina" -Target "<repo>\lastno\plocevina"
```

Potreben je tudi dodatek SheetMetal in networkx (`lastno/raziskava/plocevina.md`, §7.1).

## Dokumentacija krivljenja (30. 10. 2026)

Za vsak kos iz pločevine list za krivilca (PDF A4 ležeče) — razgrnitev z upogibnimi črtami U1…Un (kot, smer gor/dol, R), slika
upognjenega kosa, tabela upogibov (prislon = krak v razgrnitvi, zunanja mera kraka), zaporedje korakov z orodjem (klin, matrica V,
sila) in opozorili (kratek krak, visok krak, povratni krak, velik R, zvit del). Pravila: `raziskava/plocevina.md` §3b, besedilo
prve strani `navodila_krivilcu.md`.

1. `FreeCADCmd.exe izvlecek_upogibov.py` (brez argumentov; poti sta v skripti) → `Razrez …/Upogibi/upogibi.json` + STL kosov:
   razgrne vsak objekt `Razgrnitev` (parametrična različica ima prednost), vrne obris, upogibne črte, kot, smer, R, globino v drevesu
   upogibov (povratni kraki) in dolžino kraka v razgrnitvi.
2. `python oznaci_dxf.py DXF --izhod "DXF oznaceni" --seznam "Seznam kosov za razrez.csv"` → kode SA-xx in gravura (potezna pisava
   Hershey Sans iz Inkscapea, sloj GRAVURA).
3. `python dokumentacija_krivljenja.py "<Razrez mapa>"` → `Dokumentacija krivljenja/SA-xx <kos>.pdf`, skupni PDF z navodili,
   `Zaporedja krivljenja.csv`, PNG predogledi v `slike/`.

Zaporedje je predlog po pravilih (najgloblji prej, krajši prej, iste smeri skupaj); krivilec ga potrdi. Trkov orodja program ne simulira.
