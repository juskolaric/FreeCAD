# Lastna pločevina (`lastna_plocevina.py`)

Parametrična objekta za pločevino nad dodatkom SheetMetal (shaise), ki ne hranita imen ploskev in robov in se zato ne
pokvarita, ko se mere osnovnega telesa spremenijo (FreeCAD 1.x sledenje topologiji pri posnetih robovih izgubi sklice,
npr. `missing element reference … ?Edge14`).

| Objekt | Kaj naredi |
|---|---|
| `TeloVPlocevino(obj, telo)` | Telo -> pločevina (SheetMetal »Solid to Sheet Metal«). Odstrani ravne ploskve na dnu, razreže vse nevodoravne robove; vodoravni robovi postanejo upogibi. Lastnosti `Debelina`, `Polmer`, `Navznoter`. |
| `Razgrnitev(obj, kos)` | Razgrnitev (SheetMetal V2) z največje ravne ploskve navzgor. Lastnosti `KFaktor`, `Standard` (ANSI/DIN). |
| `obris_za_laser(oblika)` | Zanke zgornje ploskve razgrnitve, poravnane na XY v izhodišče — za DXF brez upogibnih črt. |

Uporaba: `doc.addObject("Part::FeaturePython", "Plocevina")`, nato `lastna_plocevina.TeloVPlocevino(obj, telo)`;
v GUI še `obj.ViewObject.Proxy = 0`. Zgled: `Oblak/3D modeliranje/Betonski podstavek/Skripte/betonski_podstavek.py`.

## Namestitev

Modul mora biti na poti Pythona, ko FreeCAD odpre dokument, sicer se objekta ne preračunata (obdržita shranjeno obliko).
Mapa je z uporabniškimi dodatki povezana s stičiščem (en izvor, repozitorij):

```powershell
New-Item -ItemType Junction -Path "$env:APPDATA\FreeCAD\v1-1\Mod\lastna_plocevina" -Target "<repo>\lastno\plocevina"
```

Potreben je tudi dodatek SheetMetal in networkx (`lastno/raziskava/plocevina.md`, §7.1).
