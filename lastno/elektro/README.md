# Lastni elektro kosi (`lastna_elektro.py`)

Parametrična objekta za bazo standardnih delov (`Oblak/3D modeliranje/Standardni deli/Elektro/`). Oblika se zgradi
iz kvadrov ob vsakem preračunu, zato sprememba mer nikoli ne pokvari sklicev na ploskve ali robove.

| Objekt | Kaj naredi | Glavne lastnosti |
|---|---|---|
| `Kanal` | Kabelski kanal z režami (prsti) in pokrovom; izhodišče spodnji vogal, dolžina +X, širina +Y, višina +Z. | `Dolzina`, `Sirina`, `Visina` (s pokrovom), `DebelinaStene`, `SirinaReze`, `KorakRez`, `DnoReze`, `PremerLuknje`, `DolzinaLuknje`, `KorakLukenj`, `Pokrov`, `DebelinaPokrova`, `JezicekPokrova` |
| `DinLetev` | Letev DIN TS35 (EN 60715) z montažnimi režami; X vzdolž letve, Y čez širino, Z = 0 vrh letve, telo v −Z (kot napajalniki Mean Well v bazi). | `Dolzina`, `Sirina`, `Visina` (7,5 / 15), `SirinaDna`, `DebelinaPlocevine`, `Reze`, `SirinaReze`, `DolzinaReze`, `KorakRez` |

Uporaba: `lastna_elektro.nov_kanal(doc)` / `lastna_elektro.nova_letev(doc)`, nato nastavi lastnosti in `doc.recompute()`.
Kosa v bazi: `ELEKTRO - Kanal 25x40.FCStd` in `ELEKTRO - DIN letev TS35.FCStd` (gradi `Standardni deli/_Skripte/elektro_parametricni.py`).
V sestavu, ki ju uporablja, se dolžina nastavi na povezanem objektu (v datoteki kosa) — kos v bazi je en, dolžine
po sestavih pa se razlikujejo: za vsako drugo dolžino shrani kopijo kosa z dolžino v imenu.

## Namestitev

Modul mora biti na poti Pythona, ko FreeCAD odpre dokument, sicer se objekta ne preračunata (obdržita shranjeno obliko).

```powershell
New-Item -ItemType Junction -Path "$env:APPDATA\FreeCAD\v1-1\Mod\lastna_elektro" -Target "<repo>\lastno\elektro"
```
