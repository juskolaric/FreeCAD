# Raziskava: Onshape, Autodesk Fusion in pločevina

Popis funkcij obeh programov po uradni dokumentaciji, stanje 7. 10. 2026. Namen: vedeti, kaj ponujata vodilna
CAD programa, ko gradimo spletni vmesnik nad FreeCAD-om (`lastno/splet`, PLAN.md korak 8 naprej).

| Datoteka | Vsebina |
|---|---|
| `onshape-funkcije.md` | Onshape (PTC): skica, Part Studio, sestavi, risbe, Render/PCB/CAM studii, AI, PDM, uvoz/izvoz, FeatureScript in REST API, vmesnik, arhitektura spletnega CAD-a, paketi |
| `fusion-funkcije.md` | Autodesk Fusion: skica, Solid/Surface/Form/Mesh/Sheet Metal/Plastic, Generative Design, CAM, risbe, Render/Animation/Simulation, Electronics, podatki, uvoz/izvoz, API in MCP, AI, vmesnik, paketi |
| `plocevina.md` | Pločevina: upogib, K-faktor, formule razgrnitve, DIN 6935, najmanjši polmeri, abkant, pravila konstruiranja, tolerance, kaj potrebuje delavnica; FreeCAD delovna miza SheetMetal (orodja, lastnosti, K-tabele, skripte brez okna, omejitve) |
| `sestav-in-deli.md` | Kaj je del, telo in sestav; kako to vidijo SolidWorks, Onshape, Fusion in FreeCAD (Body, Part, Assembly, Link, Joint); kaj to pomeni za spletni pogled |

Vsaka datoteka ima na koncu seznam prebranih virov in opombo, kateri deli niso bili dosegljivi.

## Kaj je pomembno za naš spletni pogled

- **Onshape je najbližji vzor naši smeri.** Jedro (Parasolid in reševalnik D-Cubed) teče na strežniku, brskalnik
  samo izrisuje trikotnike prek WebGL in pošilja izbire. Pri nas je FreeCAD (OCCT in reševalnik skic) strežnik,
  brskalnik pa riše s three.js. Razlika: Onshape hrani le spremembe v bazi, mi delamo z datotekami FCStd.
- **Skica**: oba imata bistveno več kot naša 1. različica. Ta ima črto, pravokotnik, krog, točko, gradbeno
  geometrijo, mere (dolžina, X/Y, polmer, premer) in omejitve vodoravno, navpično, sovpadanje, točka na robu
  in sredina roba. Manjkajo nam predvsem loki (3 točke, tangentni, središčni), elipsa, utor, mnogokotnik, zlepek,
  besedilo, obreži/podaljšaj/razdeli, odmik, zrcali, vzorci v skici, zaokrožitev in posnetje v skici,
  omejitve (vzporedno, pravokotno, tangentno, enako, simetrija prek črte, koncentrično, fiksiraj) in kotna mera.
  FreeCAD Sketcher večino tega že ima, zato gre večinoma za izpostavitev v brskalnik.
- **Značilnosti**: izboklina, vrtenje, potisk, prehod, zaokrožitev, posnetje, nagib, lupina, rebro, luknja z navojem,
  vzorci in zrcaljenje so v obeh osnova. V FreeCAD-u (PartDesign) obstajajo; pri nas so okna z nastavitvami
  narejena le za izboklino in ugrez.
- **Vmesnik**: oba imata drevo/seznam značilnosti z vrstico za povratek (rollback), seznam delov, merjenje,
  prerez (section view), vrste prikaza, izbiro z okvirjem in »izberi drugo« po globini. To je naš korak 10.
- **Spremenljivke in konfiguracije**: Onshape (Variable, Variable Studio, konfiguracije) in Fusion (Parameters,
  Configurations) ju imata v središču; v FreeCAD-u jima ustrezata preglednica (Spreadsheet) in izrazi.
- **Razširljivost z AI**: Fusion ima uradni lokalni strežnik MCP, ki v živi seji izvaja Python; Onshape ga
  napoveduje za FeatureScript. Naš `POST /python` z žetonom je enak vzorec.
