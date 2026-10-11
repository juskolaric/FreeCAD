# Popravki dodatka Cables (v0.3.7)

Dodatek Cables je git klon v `%APPDATA%/FreeCAD/v1-1/Mod/Cables`. Lastni popravki so v
`cables-0.3.7-popravki.patch` (komentarji »lastni popravek« v kodi). Po posodobitvi dodatka
(`git pull`) jih uveljavi znova:

```bash
cd "$APPDATA/FreeCAD/v1-1/Mod/Cables" && git apply "<pot do repozitorija>/lastno/kabli/cables-0.3.7-popravki.patch"
```

1. `wireFlex.execute_bspline`: ravna pot tipa BSpline (npr. samo dve točki, privzeto `BSpline_K`)
   se zgradi kot daljica. Krivulja iz `getBSpline_K` ima enotske tangente, OCC čez ravno tako krivuljo
   ne zna povleči cevi (`BRepFill_Sweep::BuildEdge`, »Cevi ni mogoče izdelati«), kabel ostane prazen
   (`BRepCheck_Analyzer::Init() - NULL shape` v skripti, ki obliko preveri).
2. `ArchCable.execute`: ko `ArchPipe` cevi ne izdela, pusti `obj.Shape` nespremenjen. Prej je staro
   obliko vzel za glavno telo in ji dodal nova izolirana konca: z vsakim preračunom dve telesi več,
   kabel je segal čez končno točko. Popravek vrne tudi `Placement`, `Additions`, `Subtractions`.

Opozorilo »Link(s) ... go out of the allowed scope 'Line' ... reside within 'Assembly'« je le
opozorilo (pot v korenu dokumenta, kosi v sestavu): pot vseeno sledi ogliščem kosov.
Napake »AttachEngine3D: subshape not found LineNNN.Vertex« ob ustvarjanju večžilnega kabla
(s profilom) so prehodne (`makeCable` preračuna pred potjo); po prvem preračunu izginejo.

Vroča zamenjava v tekočem strežniku: `importlib.reload` modulov `freecad.cables.wireFlex` in
`archCable`, `obj.Proxy.__class__ = <nov razred>` in nato **`obj.Proxy = obj.Proxy`** (FreeCAD si ob
nastavitvi Proxy zapomni metode starega razreda; brez tega `super()` v `onChanged` pade s TypeError).
