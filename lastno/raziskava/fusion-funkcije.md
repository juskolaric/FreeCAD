# Autodesk Fusion (prej Fusion 360) — popis funkcij po uradni dokumentaciji

Stanje: 7. 10. 2026. Viri: Fusion Help (help.autodesk.com/cloudhelp/ENU/Fusion-*), autodesk.com (features, extensions, personal, sistemske zahteve, blog 2025/2026), APS (Autodesk Platform Services), help ADSKMCP. Strani `autodesk.com` so bile prebrane prek brskalnika (WebFetch vrača 403). Kjer je vir le iskalni izvleček ali sekundarni vir, je označeno. Nekaj referenčnih strani Electronics (ECD-*) vrača 404; to področje je popisano iz dosegljivih strani in uradnih povzetkov.

Oznake: **[ME]** Manufacturing Extension (prej Machining; vsebuje nekdanji Additive Build in Nesting & Fabrication), **[SE]** Simulation Extension (vsebuje nekdanji Generative Design Extension), **[DE]** Design Extension (prej Product Design Extension), **[MG]** Manage Extension / Fusion Manage, **[SI]** Signal Integrity Extension (ni več v prodaji), **[tokeni]** porabi Flex tokene, **[ne osebna]** ni v brezplačni različici za osebno rabo.

---

## 0. Arhitektura, delovna okolja in splošno

- **Delovna okolja (Workspaces)**: Design, Generative Design, Render, Animation, Simulation, Manufacture, Drawing, Electronics (Electronics Design + Electronics Library). Preklop s Ctrl+[ / Ctrl+].
- **Zavihki v Design**: Sketch (kontekstualni), Solid, Surface, Mesh, Form (kontekstualno okolje), Sheet Metal, Plastic (**[DE]**), Utilities; v vsakem zavihku paneli Create / Modify / Assemble / Construct / Inspect / Insert / Select.
- **Načina modeliranja**: parametrični (Timeline zajema zgodovino, »Capture Design History«) in direktni (brez zgodovine); preklop kadarkoli; privzeti način v preferencah.
- **Intent-driven design (preview 2025)**: ob začetku izbereš Part / Assembly / Hybrid design.
- **Oblačna arhitektura**: lokalni program (Windows, macOS) + podatki v oblaku (hubi/projekti); polna različica **Fusion v brskalniku** (komercialne/izobraževalne naročnine; dodatkov ni mogoče namestiti); Fusion web client za upravljanje podatkov; mobilna aplikacija (iOS/Android: pregled, komentarji, markupi, brez modeliranja); offline način s predpomnjenjem.

---

## 1. Skica (Sketch)

### 1.1 Ustvarjanje skice in vrste geometrije
- **Create Sketch** — nova skica na ravnini XY/YZ/ZX ali ravni ploskvi; **Edit Sketch**, **Finish Sketch**, **Finish with AutoConstrain** (**[ne osebna]**), **Redefine sketch plane**, **Copy sketch**, **Export sketch as DXF**.
- Vrste geometrije: Sketch Geometry (polna modra), **Construction** (črtkana oranžna), **Centerline** (os za revolve/simetrijo), Projection (vijolična, asociativna), Fixed (zelena), Constrained (črna). Profili: odprti / zaprti.
- **3D Sketch** (preklop v paleti): geometrija kjerkoli v prostoru; 3D manipulator (ravnina, osi, rotacijski ročaj). Podprta orodja v 3D: Line, Arc, Spline, Rectangle, Circle, Ellipse, Point, Text, Conic Curve.

### 1.2 Risalna orodja (Sketch > Create)
- **Line** — zaporedje povezanih črt in lokov (klik-vlek za tangentni lok, zapiranje profila s klikom na začetek).
- **Midpoint Line** — črta, simetrična glede na izbrano središče.
- **Rectangle**: **2-Point Rectangle**, **3-Point Rectangle**, **Center Rectangle**.
- **Circle**: **Center Diameter Circle**, **2-Point Circle**, **3-Point Circle**, **2-Tangent Circle**, **3-Tangent Circle**.
- **Arc**: **3-Point Arc**, **Center Point Arc**, **Tangent Arc**.
- **Polygon**: **Circumscribed Polygon**, **Inscribed Polygon**, **Edge Polygon**.
- **Ellipse** — središče, prva os, točka na elipsi.
- **Slot**: **Center to Center Slot**, **Overall Slot**, **Center Point Slot**, **3 Point Arc Slot**, **Center Point Arc Slot**.
- **Spline**: **Fit Point Spline** (skozi točke), **Control Point Spline** (kontrolni poligon).
- **Conic Curve** — konika iz dveh krajišč, vrha in vrednosti Rho (elipsa/parabola/hiperbola).
- **Point** — skicirna točka.
- **Text** — besedilo v okvirju (merljivo, omejljivo) ali **Text on Path**; izrazi in besedilni parametri; uporabno za Emboss/Extrude.
- **Mirror** — zrcalna kopija skicirnih krivulj (doda omejitev Symmetry).
- **Circular Pattern**, **Rectangular Pattern** — vzorci v skici (posamezne kopije je mogoče izključiti).
- **Project / Include**: **Project** (projekcija robov/ploskev/točk/teles na ravnino, s Projection Link), **Intersect**, **Include 3D Geometry**, **Project To Surface**, **Intersection Curve** (3D krivulja iz dveh skic), **Isoparametric Curve** (UV krivulje s ploskve; novo 2026), **Spun Profile** (zavrteni profil telesa okoli osi).
- **Create Mesh Section Sketch** (zavihek Mesh) — presečna črta ravnine z mrežo; za reverzno inženirstvo.
- **Sketch Dimension** — linearne, poravnane, kotne, radij, premer; **Driving** vs **Driven** (Toggle Driven), nanašanje na parametre/izraze.

### 1.3 Omejitve (Sketch > Constraints)
Horizontal/Vertical, Coincident, Tangent, Equal, Parallel, Perpendicular, Fix/UnFix, Midpoint, Concentric, Collinear, Symmetry, Curvature (G2). 3D skica ima lastno referenco podprtih omejitev.
- **AutoConstrain** (AI, 2025): generira več variant omejitev in mer (vijolično), drsnik gostote, »Generate more«, »Start Over«, nastavitev datuma (Set Datum, AutoConstrain From Datum), možnost »Modify Geometry« (popravi majhne vrzeli, nenatančne kote, skoraj-tangentne loke s tolerancami), **Finish with AutoConstrain**.

### 1.4 Urejanje (Sketch > Modify)
Fillet, Chamfer (**Equal Distance**, **Distance And Angle**, **Two Distance**), Trim, Extend, Break, Sketch Scale, Offset (eno-/dvostransko, ujemanje topologije), Blend Curve (tangentna/krivinska povezava), Move/Copy (tudi izven ravnine pri 3D skici), Change Parameters.

### 1.5 Sketch Palette in sklepanje (inference)
Feature Options, Linetype (Construction/Centerline), Look At, Sketch Grid, Snap, Slice (prerez modela na ravnini skice), Show Profile, Show Points, Show Dimensions, Show Constraints, Show Projected Geometries, 3D Sketch. Objektni snapi/sklepanje prikažejo simbole med premikanjem kazalca.

---

## 2. Design — Solid

### 2.1 Create
- **New Component**; **Create Sketch**; **Create Form** (vstop v T-Spline okolje); **Create Base Feature** (direktno urejanje znotraj parametričnega načina); **Create PCB** (asociativna PCB iz skice).
- **Extrude** (tip, razdalja, kot nagiba, tanke stene), **Revolve**, **Sweep** (vodila/ploskve), **Loft** (vodila, osrednja črta, točkovno ujemanje), **Rib**, **Web**, **Emboss** (dvig/vdolbina profila na ploskvi), **Hole** (Simple / Counterbore / Countersink; navojne, tip konice, globina, premer, kot; po standardih), **Thread** (notranji/zunanji, kozmetični ali modelirani; dolžina, zamik, tip, velikost, oznaka, razred; **Threads Library**, **Manage Threads Library**).
- Primitivi: **Box, Cylinder, Sphere, Torus, Coil, Pipe** (Join/Cut/Intersect/New Body/New Component).
- **Pattern**: **Rectangular Pattern**, **Circular Pattern**, **Pattern on Path**, **Geometric Pattern** **[DE]** (gradienti velikosti/porazdelitve po ploskvi); **Mirror** (ploskve, telesa, značilnosti, komponente, konstrukcijska geometrija).
- **Thicken** (ploskve v telo), **Boundary Fill** (celice iz teles/ploskev/ravnin → nova telesa).
- **Automated Modeling** (AI, naročnina/študent): poveže 2+ ploskev z generiranimi telesi (Smooth/Sharp, telesa, ki se jim izogne, drsnik volumna; rezultat kot Form/Base/Boundary Fill/Combine).
- **Derive** → glej Insert Derive.
- Plastic (**[DE]**, zavihek Plastic): **Boss**, **Snap Fit**, **Lip** (Lip / Groove / Lip And Groove), **Rest**; **Plastic Rules** (material, debelina, knjižnica pravil); nagib/smer izvleka/radiji na Web in Rib.

### 2.2 Modify
Press Pull, Fillet (tudi Full Round, Rule Fillet; **asimetrični radij** 2025), Chamfer, Shell (navznoter/navzven/obojestransko), Draft (fiksni / parting line), Scale, Combine (Join/Cut/Intersect; mesh-assisted fallback), Offset Face, Replace Face, Split Face, Split Body, Silhouette Split, Move/Copy, Align, Delete, **Simplify > Remove Features / Remove Faces**, Physical Material, Appearance, Manage Materials, **Change Parameters**, Compute All; **Volumetric Lattice** **[DE]**; **Organic mesh conversion** **[DE]**.

### 2.3 Construct
**UCS** (uporabniški koordinatni sistem). Ravnine: Offset Plane, Plane At Angle, Tangent Plane, Midplane, **Perpendicular Plane**, Plane Through Two Edges, Plane Through Three Points, Plane Along Path. Osi: Axis Through Cylinder/Cone/Torus, Axis Perpendicular To Face, Axis Through Two Planes, Axis Through Two Points, Axis Through Edge. Točke: Point At Vertex, Point Through Two Edges, Point Through Three Planes, Point At Center Of Circle/Sphere/Torus, Point At Edge And Plane, Point Along Path. (Roadmap 2026: vzorčenje ravnin, snap točke.)

### 2.4 Inspect
Measure, Section Analysis, Interference, Center of Mass, Curvature Comb Analysis, Curvature Map Analysis (Gaussian / Principal Min / Max), Zebra Analysis, Isocurve Analysis, Draft Analysis, Accessibility Analysis, Minimum Radius Analysis, Environment Map Analysis, **Fastener Stack Analysis** (Assembly/Hybrid), Display Component Colors, Display Mesh Face Groups, **Find Similar Components** (AI, **[DE]**), **Design Advice** **[DE]** (DFM pregled proti standardom).

### 2.5 Insert
Insert Component (zunanja referenca), **Insert Fastener** (vijaki/matice/podložke/kovice), Insert Derive (asociativno povezane značilnosti/telesa iz drugega dizajna), Decal, Canvas (slika s kalibracijo), Insert SVG, Insert DXF (ena skica ali po slojih), Insert McMaster-Carr Component (SAT/STEP), Insert Mesh (STL/OBJ/3MF), **Insert a Manufacturer Part** (400+ katalogov), **Insert TraceParts Supplier Components**.

### 2.6 Select
Načini: Window, Freeform, Paint, Adjacent Faces. Orodja: Select By Name, Select By Boundary, Select By Size, Invert Selection, Seed And Boundary, Select All Occurrences, Select Similar Occurrences, Isolate, Unisolate. Prioritete: Body / Face / Edge / Component. Filtri: Select Through, Bodies, Body Edges/Faces/Vertices, Canvas, Components, Custom Graphics, Decal, Dimension, Features, Joint Origins, Joints, Mesh Bodies/Face Groups/Faces, Sketch Curves/Constraint/Points/Profiles, T-Spline Body, Text, Work Geometry, Generative/Simulation Attributes, Simulation Model Tags.

### 2.7 Timeline in parametri
- Timeline: vsaka značilnost, urejanje, preurejanje, supresija, Compute All, Roll back marker.
- **Parameters**: user parameters in model parameters; izrazi z aritmetičnimi in logičnimi operatorji, funkcija `if`, matematične/trigonometrijske funkcije, konstante; **besedilni parametri** (2025); priljubljene, filtriranje, razvrščanje, uvoz/izvoz CSV, samodejni preračun z možnostjo zaustavitve.

### 2.8 Konfiguracije (Configurations) **[ne osebna]**
Konfiguracijska tabela (dodaj/aktiviraj/preimenuj/podvoji/izbriši/razvrsti; zavihka Parameters in Properties); konfigurabilni vidiki: User Parameters, Feature Parameters, lastnosti Joint/Thread/Hole, **Suppression**, **Visibility**, Physical Material, Appearance, Sheet Metal Rules, Plastic Rules, Properties (Part Number, Description); **Theme Tables**; konfigurabilne sestave, konfigurirane zamenjave komponent; **Configuration Rules** **[DE]** (vizualni pravilnik brez kode); konfiguracije v Render, Animation, Simulation, Drawing (Configuration Table), Manage; API za konfiguracije.

### 2.9 Sestavljanje (Assemble)
New Component, **Joint**, **As-Built Joint**, **Joint Origin**, **Rigid Group**, **Drive Joints**, **Motion Link** (razmerje med sklepi), **Enable Contact Sets / Disable All Contact / Enable All Contact / New Contact Set**, **Motion Study**, **Constraints** (novo 2025: več relacij v enem ukazu, tip **Center** med dvema ploskvama).
- Tipi sklepov: Rigid, Revolute, Slider, Cylindrical, Pin-Slot, Planar, Ball. Postavitev izhodišča: Simple / Between Two Faces / Two Edge Intersection; poravnava (kot, odmik X/Y/Z, Flip); **Joint limits** (min/max/rest).
- Edit In Place (urejanje zunanje komponente v kontekstu), Ground, Capture Position, Revert Position, zunanje reference.

---

## 3. Design — Surface, Form, Mesh, Sheet Metal, Plastic, Utilities, Generative Design

### 3.1 Surface
Create: **Patch**, Extrude, Revolve, Sweep, Loft, **Ruled**, **Offset**, primitivi, vzorci/zrcaljenje. Modify: Press Pull, Fillet, Chamfer, **Trim**, **Untrim**, **Extend**, **Stitch**, **Unstitch**, **Merge**, **Reverse Normal**, Scale, Split Face, Split Body (+ standardni Modify ukazi).

### 3.2 Form (T-Splines)
- Create: Box, Plane, Cylinder, Sphere, Torus, **Quadball**, Pipe, **Face**; iz skic: Extrude, Revolve, Sweep, Loft (razmik Curvature/Uniform, kontinuiteta).
- Modify (25 orodij): Edit Form, Edit By Curve, Insert Edge, Subdivide, Insert Point, Merge Edge, Bridge, Fill Hole (star/reduced star/collapse), Erase and Fill, Weld Vertices, UnWeld Edges, Crease, UnCrease, Bevel Edge, Slide Edge, Smooth, Cylindrify, Pull, Flatten, Straighten, Match, Interpolate, Thicken, Freeze, Unfreeze.
- Symmetry: Mirror – Internal, Circular – Internal, Mirror – Duplicate, Circular – Duplicate, Clear Symmetry, Isolate Symmetry.
- Utilities: Display Mode (Box / Control Frame / Smooth), Repair Body, Make Uniform, Convert (BRep↔T-Spline, Quad mesh→T-Spline), Enable Better Performance.

### 3.3 Mesh
- Create: Insert Mesh (STL/OBJ/3MF), **Tessellate** (solid/surface → mesh), Create Mesh Section Sketch.
- Prepare: **Repair**, **Generate Face Groups**, **Combine Face Groups**, Create Face Group (direktni način).
- Modify: **Direct Edit**, Remesh, Reduce, Plane Cut, Shell, Combine, Smooth, Reverse Normal, Erase And Fill, Mesh Align, **Texture Extrude** (slika → relief), Separate, Move/Copy, Scale Mesh, Delete, **Convert Mesh** (v solid/surface; organske mreže **[DE]**), Physical Material, Appearance, Change Parameters, Compute All. Direktno urejanje: Expand To Face Group, Expand To Connected, Grow/Shrink Selection, Invert.

### 3.4 Sheet Metal
- Komponenta pločevine s **Sheet Metal Rule** (debelina, radij upogiba, K-faktor, relief; knjižnica pravil; deljenje med ekipami — roadmap 2026).
- Create: New Component, **Flange** (Base Flange iz zaprtega profila, Edge Flange, Contour Flange iz odprtega profila; stran materiala One Side/Other Side/Symmetric), **Bend** (upogib ravnega dela vzdolž črt), **Create Flat Pattern** (ločena predstavitev z lastno časovnico), **Convert To Sheet Metal**.
- Modify: **Unfold** / **Refold** (začasno razgrnjenje za značilnosti čez upogibe), **Sheet Metal Rules**, standardna Modify orodja; izvoz razgrnitve DXF/DWG/SAT; bend table in bend identifier v risbi; CAM 2D Profile za laser/vodni curek/plazmo; nesting **[ME]**.

### 3.5 Plastic **[DE]**
Plastic Rules, Boss, Snap Fit, Lip, Rest, Geometric Pattern, Volumetric Lattice, Design Advice, nagib/radiji na Web/Rib.

### 3.6 Utilities
- **Add-Ins**: **Scripts and Add-Ins** (ustvari/uredi/zaženi/ustavi/odpravljanje napak; Python in C++ predloge), **Design and Make Marketplace** (prej Fusion App Store).
- **Make**: **3D Print** (telo → mreža → STL ali 3D-tiskalni program), 3D Printing Essentials dodatek.
- **Manage Threads Library**, **Manage Materials**, preference (API: Fusion MCP Server vklop, vrata 27182).

### 3.7 Generative Design (v **[SE]** neomejeno; sicer **[tokeni]**)
- Paneli: Study, Edit Model (Obstacle/Preserve/Starting geometrija, bolt-hole preserve), Design Space, Design Conditions (omejitve, obremenitve), Design Criteria (cilj: minimiziraj maso / maksimiraj togost; omejitve: varnostni faktor, ciljna masa, pomik), Materials, Generate (pre-check, oblačno generiranje), Explore (filtri, grafi, vizualna podobnost z ML), Select, Inspect.
- Metode izdelave: Unrestricted, Additive (smeri X+/Y+/Z+), Milling (2.5-, 3-, 5-osno), 2-Axis Cutting, Casting (debelina, enakomernost, nagib); costing (ocena stroškov glede na količino); rezultati kot urejljiva nativna geometrija (Form/Mesh).

---

## 4. Manufacture (CAM)

### 4.1 Postavitve, stroji, orodja
- **Setup**: tipi Milling, Turning / Mill-Turn, Cutting, Additive; izbira stroja iz **Machine Library**, WCS (več WCS odmikov), Stock (modeli surovca, bounding solid), Model/Fixtures, Program Name/Comment; **Manufacturing Model** (ločen model za CAM).
- **Machine definitions / Machine Library** (Fusion, My Machines, Document, Recent), **Machine Builder** (kinematika, modeli strojev), **Machine Simulation** (trki, singularnosti, multi-axis feedrate, retract/reconfigure), **Post Library** (cam.autodesk.com/hsmposts, `.cps`, **Post Processor Editor**, feedrate tables), **NC Program** (izbira operacij, post, izhod G-kode), **Setup Sheet** (HTML/Excel), **Machining time**, **Toolpath data**, **CAM Task Manager**, **Parameter defaults / templates / expressions**, Compare & Edit.
- **Tool Library**: Fusion Library, Vendor libraries, Hub/Cloud/Local/Document knjižnice; tipi Milling, Turning, Cutting (vodni curek, laser, plazma), Touch Probes, Holders; **Cutting data / presets**, 2D/3D predogled orodja, izrazi, form mill, uvoz/izvoz.
- **Simulate** (surovec, trki, **GPU stock simulation** na Windows od 2025, simulacija s strojem), **Actions > Generate / Simulate / Post Process / Setup Sheet**.

### 4.2 Strategije (iz API `OperationStrategyTypes` + strani strategij)
- **2D rezkanje**: Face, 2D Adaptive Clearing, 2D Pocket, 2D Contour, Slot, Trace, Thread (navojno rezkanje), Bore, Circular, Engrave, **2D Chamfer**.
- **3D rezkanje**: Adaptive Clearing, Pocket Clearing, Parallel, Contour, Ramp, Horizontal, Pencil, Scallop, Spiral, Radial, Morphed Spiral, Project(ion), Flow, Morph, **Steep and Shallow** **[ME]**, **Rest Finishing**, **Corner** **[ME]**, **Deburr** **[ME]**, **3+2 Clearing** **[ME]**, multi-axis možnosti v 3D poteh (nagib orodja), Machine Over Holes and Pockets.
- **Večosno** **[ME]**: Swarf, Advanced Swarf, Multi-Axis Contour, Multi-Axis Morph, Multi-Axis Flow, **Rotary** (Rotary Finishing, Rotary Pocket), Multi-Axis Clearing, blade/turbine strategije, samodejno izogibanje trkom, tool-axis kontrole.
- **Vrtanje**: Drilling (vrtanje, povrtavanje, vrezovanje navojev, canned cycles), **Hole Recognition** **[ME]** (samodejne operacije spot/drill/counterbore/bore/tap/ream, delne luknje, več ravnin; **Hole Template Editor** 2025).
- **Struženje**: Turning Profile (OD/ID/Face, grobo/fino), Turning Groove, Single Groove, Turning Face, Turning Part (odrez), Turning Thread (standardne definicije 2025), Turning Chamfer, **Turning Trace** (2025), Stock Transfer (prenos med vretenoma), smer vretena na operacijo, mill-turn.
- **Toolpath Modifications** **[ME]**: Trim, Delete Passes/Segments, Replace Tool, Move Entry/Start Points, Leads and Links — brez ponovnega izračuna.
- **Probing / inšpekcija**: **Probe WCS**, **Probe Geometry** **[ME]**, **Inspect Surface** **[ME]**, **Part Alignment** in **Live Part Alignment** **[ME]**, **Manual Inspection**, PMI for inspection, inspection results & reports; **Machine Connect** (prenos NC kode, monitoring strojev — ločen izdelek).
- **Fabrication**: **2D Profile** (laser/vodni curek/plazma), **Nesting** **[ME]**: Nest Study (Create/Generate/Edit, Component Sources, več plošč, več materialov, primerjava).
- **Additive**: Additive Setup (FFF, SLA/DLP, MJF, SLS, MPBF, eBeam, binder jetting, DED **[ME]**), Print Settings Library, Platform/Build Volume, No Build Zone, **Arrange** (3D arrange, **True Shape** vokselsko gnezdenje, ročno razvrščanje, zaznavanje dvojnikov), **Automatic Orientation**, **Supports** (Volume, Solid Volume, Bar, Solid Bar, Lattice, Polyline, Surround Volume by Polyline, Down-Oriented Point Bar, Edge with Bar, Edge with Polyline, Cluster Contour with Polyline, Medial Axis with Polyline, Base Plate, Setter), simulacija procesa (kovinski tisk), generiranje poti/slice, izvoz G-kode/3MF, setup iz G-kode; knjižnica strojev (Ultimaker, EOS, Renishaw …).
- **Automatizacija**: Automated toolpath / AI strategije (Autodesk Assistant v Manufacture), **System Automation Modeler** (vizualni node-based potek, roadmap 2026), hole-making avtomatizacija, templates, PMI authoring **[DE]/[ME]**.
- **CAM API** (adsk.cam): setupi, operacije, generiranje poti, post, setup sheet, parametri, tool library.

---

## 5. Drawing

- **Ustvarjanje**: From Design / From Animation; Automatic ali Manual; Full Assembly / Visible Only / Select; Folded Model / Flat Pattern; nova risba ali list; predloge (`.f2t`, **placeholder views & tables**); standardi **ASME**, **ISO**; enote in/mm; velikosti listov; Structure First Level / All Levels.
- **Create (pogledi)**: Base View, Projected View, Section View, Detail View, **Break View**, Create Sketch (risalna skica: Line, 2-Point Rectangle, Center Radius Circle, 3-Point Arc, Leader, Text, Move/Rotate/Copy/Trim/Extend/Offset/Delete, Measure, omejitve). Modify: Move, Rotate, Delete; Drawing View dialog (Shaded/Visible Edges/Hidden Edges, tangentni robovi, merilo, orientacija).
- **Geometry**: Center Line, Center Mark, Center Mark Pattern, Edge Extension.
- **Dimensions**: Dimension (pametna), Ordinate, Linear, Aligned, Angular, Radius, Diameter, Baseline, Chain, Dimension Break; **Auto Dimension** (Baseline, Chain, Ordinate, Overall, Symmetric …, drsnik gostote); **Tidy Up**; luknje: Dimension ali Hole and Thread Note.
- **Text**: Text, Leader. **Symbols** (GD&T): Surface Texture, Feature Control Frame, Datum Identifier. **Insert**: Image.
- **Tables**: Table (Automatic, Custom Table, Parts List — First/All Levels, Auto Balloon; **Bend Table**; **Hole Table**; **Configuration Table**; **Revision History**), Balloon (Standard / Patent), Bend Identifier, Renumber, Align Balloon.
- **Drawing Automation** (AI): samodejni listi (Main/Sub-Assembly, Animation, Component, Folded Model, Flat Pattern; Single Iso / Orthogonal), parts list in bend table, auto dimensions, center marks/lines, **Detect and Omit Fasteners** (AI), izključitev komponent, shranjevanje v predlogo; Save As z risbami (2025); PCB risbe (2025); **tracked changes** **[MG]**.
- **Export**: PDF, DWG, Sheet as DXF, CSV (tabele).

---

## 6. Render, Animation, Simulation

### 6.1 Render
Setup: **Appearance** (knjižnica; Opaque, Transparent, Metal, Layered, Wood; Material Editor, bump/teksture), **Scene Settings** (okolje/osvetlitev, ozadje, kamera: goriščnica, ekspozicija, globinska ostrina, tla/odsevi), **Decal**, **Texture Map Controls**. **In-canvas render** (nastavitve, **Capture Image**). **Render** (lokalno ali v oblaku **[tokeni]**), **Rendering Gallery**, render konfiguracij. **AI rendering** prek Autodesk Assistant (GPT-image-1, 20 slik/mesec komercialno; izvoz v PowerPoint — 2025/26).

### 6.2 Animation
**Storyboard** (več storyboardov na konfiguracijo), **Transform**: Transform Components, Restore Home, Auto Explode: One Level, Auto Explode: All Levels, Manual Explode, Show/Hide (fade), Appearance; **Expose Trails**; **Annotation**: Create Callout; **View** (kamera kot akcija); **Publish Video** (AVI Windows / MP4 macOS); risba iz animacije.

### 6.3 Simulation
- Toolbar: Study (New Study), **Simplify** (Remove Features, Remove Faces, Replace with Primitives), Materials, Constraints (Fixed, Pin, Frictionless, Prescribed Displacement …), Loads (Force, Moment, Pressure, Hydrostatic, Gravity, Bearing, Remote, Point Mass …; toplotne: Temperature, Convection, Internal Heat, Radiation), Contacts (samodejni/ročni, self-contact), Display, Solve (Pre-Check, Generate Mesh, Solve lokalno ali v oblaku **[tokeni]**), Manage (mesh, adaptive mesh refinement, local mesh controls, load cases), Inspect (probe, measure), Results, **Compare** (do 4 študije).
- Tipi študij: **Static Stress** (v osnovnem Fusionu). **[SE]**: Modal Frequencies, Thermal (Steady State), Thermal Stress, Structural Buckling, Nonlinear Static Stress, Quasistatic Event Simulation, Dynamic Event Simulation, Shape Optimization, **Electronics Cooling**, **Injection Molding Simulation**, Generative Design.

---

## 7. Electronics (naslednik EAGLE)

- Delovna okolja: **Electronics Design** (Schematic, 2D PCB, 3D PCB — dokumenti `.fsch/.fbrd`) in **Electronics Library** (`.flbr`).
- **Schematic**: Place Components, Net, Name, Label, Bus, Junction, Supply/Power symbols, Attributes, ERC, več listov (osebna 2; komercialna do 999), variants, **BOM** (živ pogled, izvoz Excel/CSV/TXT).
- **2D PCB**: Route (Manual, Multi Route, Differential-Pair, Quick Route, Meander/dolžinsko usklajevanje), **Autorouter**, Ripup/Unroute, Via (blind/buried), Polygon pour, **Layer Stack Manager** (osebna 4 signalni sloji, komercialna 64), neomejena površina plošče, **Design Rules / DRC** (clearance, copper width, via drill; obsegi In Net Classes/In Signal/Is Signal/In Diff Pair/In Named Group; `.edru`), Design Blocks, ULP/Eagle združljivost, Insert DXF/DWG.
- **3D PCB / ECAD-MCAD**: **Create PCB** iz skice, **Push to 2D PCB**, **Push to 3D PCB**, pull-based sinhronizacija (2025), 3D paketi komponent, umestitev v mehansko sestavo.
- **Library**: Library Manager (hub / javne / zasebne; iskanje komponent 2025), Component = Symbol + Package (Footprint + 3D model), uvoz knjižnic (EAGLE `.lbr`, library.io), managed libraries.
- **Manufacturing outputs**: **CAM Processor** (Gerber RS-274X, Excellon, **ODB++**, BOM, Pick and Place); izvoz v EAGLE 9.6.2; PCB risbe v Drawing.
- **Simulacija**: SPICE; **Signal Integrity** **[SI]** (impedanca, zakasnitev, crosstalk; Ansys; **ni več v prodaji**); **Electronics Cooling** **[SE]**.
- **Electronics API** (`adsk.electron`, Python/C++, preview, samo branje).

---

## 8. Podatki in sodelovanje

- **Hubi** (team/personal; administratorji, vabila, skupine, vloge, združevanje hubov 2025), **Projekti**, **Mape/podmape** z dovoljenji, **Data Panel** (hubi/projekti/dizajni, iskanje, uvoz/nalaganje, knjižnice Assets: CAMPosts, materiali).
- **Fusion web client / Fusion Team**: upravljanje podatkov, dovoljenj, projektov; pregledovalnik (100+ formatov), **verzije** (Version History, promote, **Save vs Create Version**, **Milestones**, izbira verzije vezanega dizajna), **komentarji in markupi**, **Share** (javna povezava, geslo, dovoljenje prenosa, vgradnja), izvoz, lastnosti in BOM (20+ lastnosti, Parts Only pogled), aktivnost projekta.
- **Offline**: Cache designs/folders/projects (**Autodesk Fusion Cache**), offline način v namizni in mobilni aplikaciji.
- **Desktop Connector** (virtualni pogon, sinhronizacija), **Autodesk Drive**, **Vault** (Vault Connector ↔ Fusion Manage: sinhronizacija artiklov/BOM; AnyCAD z Inventorjem; Inventor kot »Fusion Connected Client« — AU 2026).
- **Fusion Manage** **[MG]** (PLM): Items, Lifecycle (Unreleased, Pre-Production, Production, Obsolete), Workflow & states, Revisions/Versions/Milestones, **Change Orders**, Change Requests, Problem Reports, Change Tasks, Quick Release, BOM management, samodejno številčenje, tracked changes v risbah, predloge procesov, agentni PLM (preview 2026).
- **Fusion Contributor** (prej Team Participant + Manage Participant; 250 USD/leto): pregled, markup, PLM vpogled. **Fusion Operations** (MES) kot ločen izdelek.
- **Varnost/administracija**: project admin, vloge Project Admin/Editor/Viewer, BYOS, audit trail.

---

## 9. Uvoz/izvoz in interoperabilnost

- **CAD aplikacije**: 123D (`.123dx`, uvoz), Alias (`.wire`, uvoz), Fusion (`.f3d`, `.f3z`), Inventor (`.ipt/.iam`, uvoz/izvoz), CATIA V5 **[ne osebna]**, Pro/E & Creo **[ne osebna]**, Rhino (`.3dm`) **[ne osebna]**, Siemens NX **[ne osebna]**, SketchUp (`.skp`, uvoz/izvoz), Solid Edge **[ne osebna]**, SolidWorks (`.sldprt/.sldasm`) **[ne osebna]** (risbe `.slddrw` ne).
- **Izmenjevalni**: IGES (uvoz; izvoz **[ne osebna]**), JT (uvoz), Parasolid (`.x_t/.x_b`) **[ne osebna]**, Pro/E Granite, Pro/E Neutral, SAT/SAB (do ACIS v7; izvoz **[ne osebna]**), SMT/SMB, STEP (uvoz/izvoz), TSM **[ne osebna]**.
- **Mreže**: 3MF, FBX, OBJ, SPD, STL, USDZ (uvoz/izvoz), SVG (uvoz).
- **Risbe/dokumentacija**: DWG (uvoz; izvoz iz Drawing), DXF (uvoz/izvoz skic, razgrnitev, risb), `.f2t` predloge, PDF, CSV.
- **Proizvodnja/elektronika**: `.cam360`, EAGLE `.sch/.brd/.lbr` **[ne osebna]**, `.fsch/.fbrd/.flbr`, Gerber/Excellon/ODB++, G-koda/NC, 3MF/G-koda aditivno.
- **Interoperabilnost**: AnyCAD (Inventor ↔ Fusion), Insert Derive, McMaster-Carr/TraceParts/Manufacturer parts, Cadence (PCB), SolidWorks sestavi z ohranjeno strukturo (roadmap 2026), mobilna aplikacija 100+ formatov.

---

## 10. Razširljivost

- **Fusion API** (namizna): Python in C++ (JavaScript opuščen), moduli `adsk.core`, `adsk.fusion` (skice, značilnosti, telesa, parametri, sklepi, konfiguracije, AutoConstrain, Render/Animation manager, risbe omejeno), `adsk.cam`, `adsk.electron` (preview); skripte in dodatki (debug v VS Code, predloge), ukazi/palete/UI, custom graphics, dogodki.
- **Design and Make Marketplace** (Fusion App Store) za dodatke.
- **Fusion Automation API** (APS, oblak): headless izvajanje Fusion skript, branje/analiza nativnih in tujih CAD datotek, ustvarjanje/spreminjanje dizajnov, sestavov, CAM setupov; **Fusion Data API / Manufacturing Data Model API** (GraphQL) za lastnosti, BOM, strukturo; Design Automation.
- **MCP strežniki** (2026): **Fusion MCP** (lokalni, vklop v Preferences > General > API, vrata 27182; orodja read/execute/update/electronics_read — izvajanje Pythona v živi seji, posnetki zaslona; uradni Claude Desktop konektor), **Fusion Data MCP** (projekti, mape, dovoljenja), **Fusion Compute MCP** (headless Fusion v oblaku: modeliranje, CAM, sestav, izvoz; beta), **Autodesk Product Help MCP**; Assistant Builder (2027).

---

## 11. AI funkcije (2024–2026)

- **Autodesk Assistant** (v Fusionu od 2025; GA na AU 2026): pomoč/podpora, prompt-to-API (Text-to-Command), izvajanje nalog v modelu, Design in Manufacturing poteki, generiranje strategij obdelave, **AI rendering**, PowerPoint, vabila sodelavcem; **mesečni Flex tokeni (beta)**: Personal 10, Students 10, Trial 10, Commercial 20.
- **AutoConstrain / ConstraintGen** (jan. 2025), **Automated Modeling**, **Drawing Automation** (jan. 2024; AI zaznavanje vijakov), **Find Similar Components** **[DE]**, **Design Advice** **[DE]**, GD z ML raziskovanjem rezultatov, **Automated toolpaths / hole-making automation**, **AutoTimeline** (parametrična zgodovina iz uvožene geometrije — AU 2026), **AutoAssemble** (AU 2026), **System (Automation) Modeler**, **neural CAD / text-to-editable-geometry** (v razvoju), **agentni PLM** v Fusion Manage, prompt-based BOM/property updates.

---

## 12. Uporabniški vmesnik in platforme

- **Application bar**: Home, Data Panel toggle, File, Save, Undo/Redo, zavihki dokumentov, New Design, Autodesk Assistant, Extensions (Purchase Manager), Job Status, Notification Center, Help, Profile.
- **Toolbar** (delovno okolje → zavihki → paneli; kontekstualni zavihki), **Browser** (komponente, telesa, skice, origin, sklepi, konstrukcija, vidnost), **Canvas**, **ViewCube**, **Marking Menu** (desni klik: kolo + overflow), **Navigation Bar** (Orbit Free/Constrained, Look At, Pan, Zoom, Fit/Zoom Window; **Display Settings**: Visual Style — Shaded, Shaded w/ Hidden Edges, Shaded w/ Visible Edges Only, Wireframe, Wireframe w/ Hidden Edges, Wireframe w/ Visible Edges Only; Environment — Theme, Photo Booth, River Rubicon, Dark Sky …; Graphics Preset Performance/Quality/Custom; Effects — Ambient Occlusion, Anti-Aliasing, Ground Reflection, sence, Transparency, NPR, Selection Effect; Camera — Orthographic/Perspective/Perspective with Ortho Faces; Object Visibility; Ground Plane Offset; Grid and Snaps; Viewports), **Timeline**, **Autodesk Assistant panel**, **Comments** panel, **Preferences** (teme dark/light, exposure slider 2025, enote, API).
- **Bližnjice**: sistemske, canvas selection (1 Window, 2 Freeform, 3 Paint), preklop okolij Ctrl+[ ], mesh/form izbira; podpora 3Dconnexion SpaceMouse, Wacom.
- **Platforme**: Windows 11, macOS (nativno Apple silicon), **Fusion v brskalniku** (HTML5: Chrome/Firefox/Safari/Edge; komercialna ali izobraževalna licenca; polni nabor orodij, brez dodatkov; min 2 GB RAM, 5/1,5 Mbps; Chromebook/Linux prek brskalnika), Fusion web client, **mobilna aplikacija** (iOS 13+/iPadOS, Android, Mac, Windows: pregled 100+ formatov, lastnosti, parts list, isolate/hide, komentarji, markupi, deljenje, offline), 11 jezikov + češčina.

---

## 13. Sistemske zahteve, paketi, cene (na kratko)

- **Windows**: Windows 11 23H2+; min x86-64 2 P-jedri/4 niti 3 GHz turbo, 8 GB RAM, 1 GB GPU DirectX 11, 1366×768, 8,5 GB; priporočeno 8+ jeder, 32 GB+, 8 GB+ GPU, 4K, 15 GB+ SSD.
- **macOS**: min macOS 14 Sonoma, Intel i5 ali M1, 4 GB; priporočeno macOS 15.7 / 26, M1 Max+, 16 GB+.
- **Brskalnik**: HTML5 brskalnik, 1366×768 (1920×1080 priporočeno).
- **Paketi (SRP, ZDA)**: **Fusion for personal use** (brezplačno; nekomercialno < 1000 USD/leto; 10 aktivnih dokumentov, omejen CAM (brez 3+2, mill-turn, probing, hitri pomiki/avtomatska menjava orodja), 2 lista/4 sloji PCB, omejena risba, omejeni formati, brez razširitev), **Startup** (150 USD/uporabnika za 3 leta), **Education** (brezplačno), **Autodesk Fusion** 85 USD/mesec, **680 USD/leto**, 2040 USD/3 leta, **Fusion for Manufacturing** 2040 USD/leto (z Manufacturing Extension), **Fusion for Design** 2190 USD/leto (Design + Simulation Extension + Fusion Manage), **Fusion Contributor** 250 USD/leto; razširitve posamezno: Manufacturing 1465 USD/leto, Simulation 1465 USD/leto, Manage 495 USD/leto; 14-dnevni preizkus razširitve, dnevni dostop s Flex tokeni; 30-dnevni preizkus.

---

## Viri (dejansko prebrani)

Help (cloudhelp, `https://help.autodesk.com/cloudhelp/ENU/...`):
- https://help.autodesk.com/view/fusion360/ENU/ (kazalo)
- Fusion-GetStarted/files/GS-WORKSPACES.htm, GS-THE-FUSION-INTERFACE.htm, GS-NAVIGATION-BAR.htm, GS-SUBSCRIPTIONS-EXTENSIONS-TOKENS.htm, GS-HUBS-AND-PROJECTS.htm, GS-START-FUSION-AND-WEB-CLIENT.htm, LEARNINGPANEL.htm
- Fusion-Sketch/files/SKT-3D-SKETCH.htm, SKT-REF-3D-SKETCH-SUPPORTED-CMD.htm, SKT-SKETCH-CREATE-LINES/-RECTANGLES/-CIRCLES/-ARCS/-POLYGONS/-ELLIPSES/-SLOTS/-SPLINES/-CONIC-CURVES/-TEXT/-MIRRORS-PATTERNS/-PROJECT-INCLUDE/-DIMENSIONS.htm, SKT-CREATE-LINES.htm, SKT-CONSTRAINTS.htm, SKT-SKETCH-MODIFY-TOOLS.htm, SKT-AUTO-CONSTRAIN-CONCEPT.htm
- Fusion-Model/files/GUID-99E108D3-07E9-4FFA-AEF9-A97D3278ED91.htm (Solid overview), SLD-CREATE-SOLID-FROM-SKETCH.htm, SLD-CREATE-SOLID-PRIMITIVE.htm, SLD-MODIFY-SOLID-BODY.htm, SLD-HOLE-THREAD.htm, SLD-PATTERNS.htm, SLD-CONSTRUCT-TOOLS.htm, SLD-INSPECT-TOOLS.htm, SLD-INSERT-TOOLS.htm, SLD-MAKE-TOOLS.htm, SLD-ADD-IN-TOOLS.htm, SLD-SELECTION.htm, SLD-MODIFY-PARAMETERS.htm, SLD-AUTOMATED-MODELING.htm
- Fusion-Patch/files/GUID-B1A3AD96-A19E-4A7E-A5A3-27327A4E074B.htm, SFC-CREATE-SURFACE-FROM-SKETCH.htm, SFC-MODIFY-SURFACE.htm
- Fusion-Sculpt/files/FRM-CREATE-FORM-PRIMITIVE.htm, FRM-CREATE-TSPLINE-FROM-SKETCH.htm, FRM-MODIFY-TOOLS.htm, FRM-SYMMETRY-TOOLS.htm, FRM-UTILITIES.htm
- Fusion-Mesh/files/MESH-OVERVIEW.htm, MESH-CREATE-TOOLS.htm, MESH-PREPARE-TOOLS.htm, MESH-MODIFY-TOOLS.htm, MESH-DIRECT-EDIT.htm
- Fusion-Sheet-Metal/files/CREATE-SHEET-METAL-COMPONENT.htm, SM-COMPONENTS.htm, SM-UNFOLD-IN-SM.htm
- Fusion-Assemble/files/ASM-EDIT-IN-PLACE-SUPPORTED-COMMANDS.htm, ASM-CREATE-JOINT.htm, ASM-AS-BUILT-JOINT.htm, ASM-CONTACT-SETS.htm
- Fusion-Configurations/files/CFG-CONFIGURABLE-ASPECTS.htm, CFG-CONFIGURATIONS.htm
- Fusion-Extensions/files/EXT-PRODUCT-DESIGN.htm, EXT-SIMULATION.htm, EXT-MANUFACTURING.htm, EXT-SIGNAL-INTEGRITY.htm, EXT-WAYS-TO-ACCESS.htm
- Fusion-GenerativeDesign/files/GD-OVERVIEW.htm, GD-WORKSPACE-TOOLBAR.htm, GD-MFG-METHODS.htm, GD-DESIGN-CRITERIA.htm
- Fusion-CAM/files/GUID-BEC5DEA9-AC3E-4FA8-998E-4AE8CD0D0B1E.htm (Manufacture overview), GUID-C6CD4BE6-5130-4957-97BA-623832623F10.htm, MFG-CREATE-SETUP.htm, MFG-MACHINES.htm, MFG-POST-PROCESSING-OVERVIEW.htm, MFG-TOOL-LIBRARY-OVERVIEW.htm, MFG-TOOLPATH-MODIFY-OVERVIEW.htm, MFG-PROBING-OVERVIEW.htm, MFG-OVERVIEW-FABRICATION-OVERVIEW.htm, MFG-OVERVIEW-FABRICATION-WORKFLOW.htm, MFG-OVERVIEW-MILLING-OVERVIEW.htm, MFG-OVERVIEW-TURNING-OVERVIEW.htm, MFG-OVERVIEW-ADDITIVE-OVERVIEW.htm, MFG-AM-SETUPS.htm, MFG-AM-VOLUME-SUPPORTS.htm, LP-READ-IRONHOLERECOGNITION.htm, NST-STUDY.htm
- Fusion-360-API/files/cam_OperationStrategyTypes.htm, CAMIntroduction_UM.htm, ElectronicsIntro.htm
- Fusion-Drawing/files/DWG-REF-DRAWING-TAB.htm, DWG-REF-SKETCH-TAB.htm, DWG-REF-TABLE-DIALOG.htm, DWG-AUTO-DRAWING.htm, DWG-REF-AUTO-PREFERENCES.htm, DWG-CREATE-FROM-DESIGN.htm
- Fusion-Render/files/RND-RENDER-CLOUD-LOCAL.htm, RND-RENDER-IN-CANVAS.htm, RND-MATS-APPEARANCES.htm
- Fusion-Animate/files/ANI-TRANSFORM.htm, ANI-SHARING.htm, ANI-ANNOTATE.htm
- Fusion-Simulate/files/GUID-58159399-B08F-43BF-89E3-57AD489FF29C.htm, SIM-SETUP-TAB.htm, SIM-HOW-IT-WORKS.htm, SIM-MODIFY-COMMANDS.htm
- Fusion-ECAD/files/ECD-DESIGN-RULES.htm
- Fusion-Manage/files/MNG-KEY-CONCEPTS.htm
- Fusion-Designs/files/TPD-SUPPORTED-FILE-FORMATS.htm
- https://help.autodesk.com/view/ADSKMCP/ENU/ (MCP strežniki)

autodesk.com (prek brskalnika):
- https://www.autodesk.com/products/fusion-360/features
- https://www.autodesk.com/products/fusion-360/overview (compare preusmeri sem)
- https://www.autodesk.com/products/fusion-360/extensions
- https://www.autodesk.com/products/fusion-360/personal in /personal/compare
- https://www.autodesk.com/support/technical/article/caas/sfdcarticles/sfdcarticles/System-requirements-for-Autodesk-Fusion-360.html
- https://www.autodesk.com/shortcuts/fusion-360 (tabele se niso izpisale)
- https://www.autodesk.com/products/fusion-360/blog/fusion-roadmap-2026/
- https://www.autodesk.com/products/fusion-360/blog/autodesk-fusion-year-in-review-2025/
- https://www.autodesk.com/products/fusion-360/blog/changes-to-autodesk-assistant-in-autodesk-fusion-beginning-october-6th/
- https://www.autodesk.com/products/fusion-360/blog/build-your-own-fusion-add-ins-with-the-fusion-mcp/
- https://www.autodesk.com/products/fusion-360/blog/fusion-360-mobile-ios-android/
- https://www.autodesk.com/products/fusion-360/blog/autodesk-fusion-industry-cloud-for-manufacturing/
- https://aps.autodesk.com/automation-apis, https://aps.autodesk.com/developer/overview/autodesk-fusion-360-api, https://aps.autodesk.com/blog/au-2026-autodesk-building-ai-design-and-make
- https://adsknews.autodesk.com/en/news/autodesk-ai-strengthens-fusion-and-alias/, https://adsknews.autodesk.com/en/news/new-investments-in-fusion-bring-ai-powered-transformation-to-manufacturing/

Sekundarni viri (dopolnilno): engineering.com (Fusion MCP, AI features, AU 2026), Wikipedia (Autodesk Fusion), App Store (Autodesk Fusion), iskalni izvlečki za Fusion Contributor, Vault Connector, browser access FAQ, omejitev 10 dokumentov, cene, Fusion MCP orodja.

Vrzeli: podrobne referenčne strani Electronics (ECD-*) niso dosegljive (404); tabele bližnjic se niso izpisale; strani Render Scene Settings in Sheet Metal Flange reference vračajo 404 — ti deli so popisani iz drugih uradnih strani in povzetkov.
