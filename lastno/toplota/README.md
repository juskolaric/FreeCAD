# Toplota — toplotna simulacija boxa (5. stopnja spletnega FreeCAD-a)

Plan in ozadje: `../../TOPLOTNA-ANALIZA-PLAN.md`. Pravila in pasti: razdelek »Toplota« v `../../CLAUDE.md`.

| Datoteka | Vloga |
|---|---|
| `bilanca.py` | bilančni model (pvlib + ht + scipy): vreme PVGIS TMY, sonce po ploskvah, vozlišča plašč/zrak/masa; `izracun(mapa, nast, obseg)` |
| `model_mke.py` | iz odprtega sestava zgradi poenostavljeno kopijo za MKE (bloki, Boolean Fragments, analiza CalculiX) — glavna nit FreeCAD-a |
| `mke_zagon.py` | FreeCADCmd v ozadju: mreža Gmsh (pip `gmsh`), lasten zapis `.inp` (nabori po težiščih elementov, klima kot izmenjevalnik), CalculiX, rezultati po območjih, slike, `polje.json`; mapa prek `TOPLOTA_MKE_MAPA` |
| `toplota3d.html` | 3D pregledovalnik polja temperatur (three.js): `GET /toplota/3d?mapa=`, bere `mke/polje.json` prek `/toplota/datoteka` |
| `toplota.html` | stran zavihka (okvir), streže jo `GET /toplota` iz `../splet/toplota.py` |

Podatki projekta: `Oblak/3D modeliranje/<Projekt>/Toplota/` (`nastavitve.json` je vhod, ostalo so rezultati). Zagon bilance iz ukazne vrstice:
`<Projekt>/Skripte/toplota_bilanca.py` (pixi python, PATH z `.pixi/envs/default/Library/bin`).
