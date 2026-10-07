# Onshape (PTC) — popis funkcij po uradni dokumentaciji

Stanje: 7. 10. 2026. Viri: Onshape Help (cad.onshape.com/help), onshape.com (features, pricing, changelog, blog), FsDoc, onshape-public.github.io (REST API), Glassworks API Explorer. Vse točke so preverjene na navedenih straneh; kjer stran ni bila dosegljiva ali je bil podatek le posreden, je to označeno. Oznake paketov: **Free / Standard / Pro / Ent**; če ni oznake, je funkcija v vseh paketih.

---

## 0. Osnovni pojmi

- **Dokument (Document)** — vsebnik za vse zavihke; ni datotek, vsaka sprememba se shrani samodejno kot inkrement.
- **Zavihki (Tabs)** — Part Studio, Assembly, Drawing, Feature Studio, Variable Studio, Render Studio, PCB Studio, CAM Studio, Material Library, uvožene datoteke (CAD, PDF, slike, video, CSV, JSON …), mape (do 10 ravni), aplikacijski zavihki iz App Stora.
- **Workspace / Version / Branch / Microversion** — delovni prostor (urejanje), nespremenljiva verzija, veja, mikroverzija (vsaka posamezna sprememba).
- **Part Studio** — večtelesno okolje z eno parametrično zgodovino (več delov v enem Part Studiu).
- **Posodobitve** vsake 3 tedne, brez namestitve.

---

## 1. Skica (Sketch)

### 1.1 Risalna orodja
- **Črta (Line)** — segmenti, L; Shift+A preklop črta/tangentni lok.
- **Pravokotnik iz vogala (Corner rectangle)** — G.
- **Pravokotnik iz središča (Center point rectangle)** — R.
- **Krog iz središča (Center point circle)** — C.
- **Krog skozi 3 točke (3 point circle)**.
- **Tangentni lok (Tangent arc)**.
- **Lok skozi 3 točke (3 point arc)** — A.
- **Elipsa (Ellipse)** — središče, glavna in stranska polos.
- **Stožernica (Conic)** — start, konec, kontrolna točka, rho (<0,5 elipsa, =0,5 parabola, >0,5 hiperbola).
- **Zlepek (Spline)** — interpolacijski zlepek skozi točke, lahko zaprt.
- **Bezier** — krivulja prek kontrolnega poligona, do stopnje 15, ne zaprt.
- **Točka zlepka (Spline point)** — doda kontrolno točko na zlepek/Bezier.
- **Utor (Slot)** — utor okoli izbranih krivulj (črte, loki, zlepki, verige, zaprti profili); širina = premer.
- **Včrtan mnogokotnik (Inscribed polygon)** / **Očrtan mnogokotnik (Circumscribed polygon)** — pravilni mnogokotnik 3–50 stranic s konstrukcijsko krožnico.
- **Točka (Point)** — Shift+S.
- **Besedilo (Text)** — do 250 znakov, pisave, krepko/ležeče, zrcaljenje, izrazi s spremenljivkami (npr. `roundToPrecision(#L/in,3) ~ "in"`); izbočljivo in omejljivo.
- **Vstavi sliko (Insert image)** — PNG/JPEG/GIF/BMP iz dokumenta, drugih dokumentov ali knjižnice; prva dimenzija skalira sliko; prosojnost ohranjena.
- **Vstavi DXF/DWG (Insert DXF or DWG)** — enote, »use file origin«, prva dimenzija skalira celoto.
- **Konstrukcija (Construction)** — Q; preklop entitet v referenčne.

### 1.2 Urejanje skice
- **Obreži (Trim)** — M, do prvega presečišča.
- **Podaljšaj (Extend)** — X, do prvega presečišča ali do klika.
- **Razdeli (Split)** — razdeli odprto/zaprto krivuljo v točkah (ohrani stopnjo in kontrolne točke).
- **Odmik (Offset)** — O, posamezna krivulja ali veriga, smer, negativna razdalja.
- **Zrcali (Mirror)** — odboj entitet prek črte.
- **Linearni vzorec skice (Linear sketch pattern)** — 1 ali 2 smeri, število, razdalja, kot; prikaže le prvih 10 pri >10.
- **Krožni vzorec skice (Circular sketch pattern)** — okoli točke/osi/Mate connectorja, odprt/zaprt (360°).
- **Zaokrožitev skice (Sketch fillet)** — Shift+F; doda »virtual sharp«.
- **Posnetje skice (Sketch chamfer)** — razdalja, vogal ali dve stranici.
- **Uporabi / projiciraj (Use / Project-Convert)** — U; projekcija robov in **silhuetnih robov** (valj, stožec, torus, krogla, izbočene ploskve).
- **Presečišče (Intersection)** — projekcija presečišča ploskve z ravnino skice.
- **Transformiraj skico (Transform sketch)** — premik, vrtenje, skaliranje, kopiranje, pripenjanje; deluje tudi na slike, besedilo, DWG/DXF.
- **Ovij (Wrap)** — v dokumentaciji pod Sketch: ovije skico/ploskev na valj ali stožec; nova/dodaj/odvzemi/presek, debelina, »Trim to target«, sidrne točke, kot, U/V zamik.

### 1.3 Omejitve (Constraints)
Sovpadanje (**Coincident**, I), koncentričnost (**Concentric**, Shift+O), vzporednost (**Parallel**, B), tangentnost (**Tangent**, T), vodoravno (**Horizontal**, H), navpično (**Vertical**, V), pravokotnost (**Perpendicular**, Shift+L), enakost (**Equal**, E), sredina (**Midpoint**, Shift+M), normala (**Normal**, Shift+K), prebod (**Pierce**, Shift+G; sovpadanje z entitetami zunaj ravnine skice), simetrija (**Symmetric**, Shift+Q; prek črte/ravnine/roba), fiksiraj (**Fix**, Shift+J), ukrivljenost (**Curvature**, Shift+U; G2 med zlepki). Samodejne: **Quadrant** (elipsa), **Use** (povezava s projicirano geometrijo), **Intersection**.
- **Upravitelj omejitev (Constraint Manager)** — filtriranje, analiza, popravljanje.
- Barve: modra = premalo omejeno, črna = polno omejeno, rdeča = napaka.

### 1.4 Dimenzije (Dimension, D)
Dolžina črte, razdalja med vzporednima črtama, diagonala/neposredna razdalja, vodoravna/navpična razdalja med točkami, premer, polmer, kot, dolžina loka, osna (centerline) dimenzija med krogi in konstrukcijsko črto, dimenzije zlepka, razdalja do ravnine. Vodilne/vodene (**Driving/Driven**), negativne vrednosti za obračanje, izrazi in `#spremenljivke`, tolerance na dimenzijah (glej §9).

### 1.5 Sklepanje (Automatic inferencing)
Vodoravno/navpično glede na izhodišče in entitete, sredina, vzporednost, sovpadanje, tangentnost; Shift med vlečenjem zatre sklepanje; prikaz pikčastih vodil in ikon.

### 1.6 Krivuljna orodja (dostopna iz skice/Part Studia)
Vijačnica (**Helix**), 3D prilegajoči zlepek (**3D fit spline**), projicirana krivulja (**Projected curve**), mostna krivulja (**Bridging curve**), sestavljena krivulja (**Composite curve**), presečna krivulja (**Intersection curve**), obreži krivuljo (**Trim curve**), izoklina (**Isocline**), odmaknjena krivulja (**Offset curve**), izoparametrična krivulja (**Isoparametric curve**), uredi krivuljo (**Edit curve**: poenostavitev, dvig stopnje, premik kontrolnih vozlišč, planarizacija), trasirna krivulja (**Routing curve**: zlepek/polilinija z radiji, točke iz vozlišč/krivulj/CSV, XYZ odmiki, ciljna dolžina, zaprta, odvodi, segmentni način; tabela trasirnih krivulj).

---

## 2. Part Studio (modeliranje delov)

### 2.1 Osnovne značilnosti
- **Izboklina (Extrude)** — solid/surface/thin; New/Add/Remove/Intersect; končni pogoji Blind, Symmetric, Up to next, Up to face, Up to part, Up to vertex, Through all; odmik, nagib (draft), druga smer, začetni odmik, merge scope, tanke stene (mid plane, dve debelini). Shift+E.
- **Vrtenje (Revolve)** — Full, Blind (+symmetric), Up to face/part/vertex/next, druga smer, odmik, os (črta, rob, cilindrični rob, Mate connector), thin, surface. Shift+W.
- **Potiskanje (Sweep)** — profil + pot; Profile control: None, Keep profile orientation, Lock profile faces, Lock profile direction; **Twist** (turns/angle/pitch, opposite direction, extend to full path), **Scale**, thin (mid plane, trim ends), surface, merge scope.
- **Prehod (Loft)** — profili (regije, ploskve, robovi, točke), vodilne krivulje, srednjica (**Path**), pogoji: Normal to profile, Tangent to profile, Match tangent, Match curvature, Normal direction, Tangent direction (z magnitudo); **Connections** (match vertices), Trim profiles/guides, Show isocurves, solid/surface/thin.
- **Odebeli (Thicken)** — ploskev → solid; New/Add/Remove/Intersect, mid plane, dve debelini, keep tools.
- **Zapri (Enclose)** — zapre volumen iz ploskev/solidov/ravnin.
- **Zaokrožitev (Fillet)** — konstantna, **asimetrična**, **spremenljiva** (točke na robovih, gladek prehod), **delna (Partial)**, prerezi Circular/**Conic (rho)**/**Curvature**, tangent propagation, Allow edge overflow, Smooth fillet corners, Keep edges, **Full round fillet**. Shift+F.
- **Posnetje (Chamfer)** — Equal distance, Two distances, Distance and angle; merjenje Offset/Tangent; direction overrides; tangent propagation.
- **Nagib (Draft)** — Neutral plane ali Parting line (one-sided/symmetric/two-sided), pull direction, tangent propagation, reapply fillets, drsnik primerjave.
- **Nagib telesa (Body draft)** — nagib celotnega telesa.
- **Lupina (Shell)** — odstranjene ploskve, debelina, **Hollow** (brez odprtine), navznoter/navzven.
- **Rebro (Rib)** — sketch srednjice, debelina, Normal/Parallel to sketch plane, draft, Extend profiles, merge.
- **Luknja (Hole)** — Simple, Counterbore, Countersink, **Tapped** (straight tap, straight pipe tap, tapered pipe tap, kozmetični navoji), **Clearance** (Close/Free/Normal/Loose), **PEM®** (self-clinching nuts, standoffs, studs); start from part/sketch plane/selected plane; Blind/Up to next/Up to entity/Through all; vrh 118°/135°/flat/custom; tolerance; samodejno poimenovanje; edina luknja, ki jo Hole callout v risbi prepozna.
- **Zunanji navoj (External thread)** — ANSI (TPI) / ISO (pitch), kozmetičen, Blind/Up to next, posnetje in izrez (undercut).
- **Boolean** — Union, Subtract (z **Offset**: offset all / faces to offset, razdalja, smer, reapply fillet), Intersect; Keep tools; deluje tudi na ploskvah.
- **Razdeli (Split)** — Split part (ravnina, Mate connector, ploskev, face) in Split face (tudi krivulje s projekcijo); Keep tools, Trim to face boundaries, Keep both sides.
- **Transformiraj (Transform)** — Translate by line/distance/XYZ, Transform by Mate connectors, Rotate, Copy in place, **Scale** (enakomerno/neenakomerno); Copy part.
- **Izbriši del (Delete part)** — izbriše telo (tudi razpusti composite).
- **Zrcali (Mirror)** — Part/Feature/Face; ravnina ali Mate connector; Reapply features; New/Add/Remove/Intersect.
- **Linearni vzorec (Linear pattern)** — Part/Feature/Face; 2 smeri, Centered, Skip instances, Reapply features, merge scope, booleani.
- **Krožni vzorec (Circular pattern)** — os, kot, enakomeren razmik, centered, skip, reapply.
- **Vzorec po krivulji (Curve pattern)** — vzdolž skicirnih krivulj/robov; Equal spacing/Distance; orientacija Tangent to curve / Normal to face / Locked; skip, reapply.

### 2.2 Neposredno urejanje
- **Premakni ploskev (Move face)** — Offset, Translate (Blind/Up to entity), Rotate; Reapply fillet.
- **Izbriši ploskev (Delete face)** — Heal / Cap / Leave open; odstrani sosednje zaokrožitve.
- **Zamenjaj ploskev (Replace face)** — obreže ali podaljša ploskev do nove.
- **Spremeni zaokrožitev (Modify fillet)** — spremeni polmer ali odstrani; Reapply fillet; Create selection pomoč.
- **Premakni mejo (Move boundary)** — razširi/obreže ploskev po robovih.

### 2.3 Ploskovno modeliranje (Surfacing)
- **Mejna ploskev (Boundary surface)** — U in V krivulje, pogoji None/Normal to profile/Tangent to profile/Match tangent/Match curvature/Normal direction/Tangent direction z magnitudo; isocurves; merge.
- **Zapolni (Fill)** — ploskev iz mej z robnimi pogoji.
- **Vodena ploskev (Ruled surface)** — Normal, Tangent, Aligned with direction, Angled from direction.
- **Odmaknjena ploskev (Offset surface)** — odmik ali kopija (0).
- **Omejena ploskev (Constrained surface)** — ploskev skozi točke/mesh znotraj tolerance.
- **Medsebojno obrezovanje (Mutual trim)**, **Face blend** (dve strani, propagacija Tangent/Adjacent/Custom, **hold lines** tangent/conic, cliff edges, radius/width, rolling ball/swept profile, trim Walls/Short/Long/No trim), Thicken, Enclose, Move boundary, Delete/Replace face (glej zgoraj), **Flatten surface** (razgrnitev v analizah).
- **Analize**: Curve/surface analysis (ukrivljenostni glavniki, kontrolne mreže), Zebra stripes, Curvature color map, Dihedral analysis, Connection analysis (G0–G3), Deviation analysis, Reflection analysis, Draft analysis, Thickness analysis, Interference detection, Flatten surface.

### 2.4 Pločevina (Sheet metal) — vse v enem načinu, sočasno zloženo in razgrnjeno
- **Sheet metal model** — začetki: **Convert** (obda obstoječi del), **Extrude** (iz krivulj, tudi loki/zlepki → valjane stene), **Thicken**; parametri: debelina, polmer upogiba, **K-factor / Bend allowance / Bend deduction**, clearance, minimal gap, flip.
- **Flange (prirobnica)**, **Hem (rob)** (Straight/Rolled/Teardrop), **Tab (jeziček)** (tudi most med prirobnicama), **Bend (upogib po črti)**, **Jog (dvojni upogib S/Z)**, **Form (oblikovni element)** iz knjižnice, **Loft (pločevinski prehod)**, **Make joint** (presečišče sten → bend ali rip), **Joint/Modify joint**, **Corner** (tip vogala, relief scale), **Bend relief** (Rectangle-scaled, Obround-scaled, Tear), **Corner break** (fillet/chamfer), **Finish sheet metal model**.
- Reliefi vogalov: Square-sized, Rectangle-scaled, Round-sized, Round-scaled, Closed, Simple.
- **Sheet metal table and flat view** — tabela upogibov in rezov (pretvorbe bend↔rip, tip stika Edge/Butt, urejanje polmera, K-factor), razgrnjeni vzorec, skiciranje na razgrnjenem, **izvoz DXF/DWG** (bend centerlines, tangent lines, sketches, splines).
- **Knjižnica oblik (Sheet metal form library)**: Bridge lance, Circle emboss, Circle extrusion, Circle knockout, Countersink, Lance, Louver, Slot emboss, Slot extrusion; lastne oblike prek **Tag** + konfiguracijske spremenljivke `thickness`.

### 2.5 Okvirji (Frames)
- **Frame** — potiskana telesa po poti z istim profilom; vogali Miter/Butt/Coped butt/None, **Corner override**, poravnava profila (Tag točke).
- **Frame trim**, **Gusset (ojačitev)**, **End cap (zaključek)**, **Cut list (kosovnica rezov)** — odprt composite + tabela, column overrides.
- **Knjižnica profilov**: ISO, ANSI (palice/cevi), 8020 (serije 10–45), AISC (C, HP, L, M, MC, MT, pipe, rect, round, S, square, ST, W, WT), AS (hladno oblikovani in vroče valjani), les (inch/metric); lastni profili prek **Tag**.
- Samo v brskalniku (ne v mobilnih aplikacijah).

### 2.6 Referenčna geometrija, povezave, spremenljivke, konfiguracije
- **Ravnina (Plane)** — Offset, Plane point, Line angle, Point normal, Three point, Mid plane, Curve point, **Tangent**; Flip normal. (Samostojnega »Axis«/»Point« ukaza ni; osi dajo robovi, cilindri, Mate connectorji; točke skica.)
- **Mate connector (Part Studio)** — On entity / Between entities; izhodišče, skicirne entitete; realign/flip osi, odmiki, vrtenje; ponovno uporaben v vseh sestavih.
- **Variable** — tipi Length, Angle, Number, **Any** (tudi FeatureScript vrednosti: boolean, map, array, string, funkcija); Assigned, **Measured**, **From table (CSV)**, on-the-fly; `#ime`, polja, preimenovanje z razširjanjem.
- **Variable table / Variable Studio** — tabela spremenljivk v Part Studiu in Assemblyju; Variable Studio kot zavihek, vstavljiv iz drugih dokumentov (read-only), **konfigurabilen**, revizionabilen.
- **Query variable** — parametrična izbira: ročne izbire, po značilnosti, po kriterijih (konveksnost, zaokrožitve, vzporednost), union/subtract/intersect, Evaluate on use, filtri tipa.
- **Konfiguracije (Configurations)** — vhodi **List**, **Checkbox**, **Configuration variable** (Length/Angle/Integer/Real/Text); konfigurirajo parametre, zatiranje, izbire, lastnosti delov, videz, materiale, besedilo skice, mate-e, instance, vzorce, tolerance; **Configured properties** (samodejne številke delov Pro/Ent); **Visibility conditions**; filtriranje, kopiranje/lepljenje iz preglednic, privzete vrednosti, izključitve; **Release configurations**.
- **Derived (izpeljano)** — Part Studios, deli, ploskve, krivulje, skice, ravnine, aktivni pločevinski modeli, Mate connectorji; iz workspace/version/drugih dokumentov; izbira konfiguracije; poravnava na Mate connector; enosmerno.
- **Composite part (sestavljeni del)** — Closed (porabi telesa) / Open; en zapis v BOM; dissolve z Delete part.
- **Tag** — profil okvirja, pločevinska oblika (Add/Subtract deli), **PCB luknje** (plated/non-plated, namen, komponenta).
- **Decal (nalepka)** — PNG/JPG/GIF/BMP do 4096×4096 na ravne/valjaste ploskve; kot, U/V, realign, velikost, prosojnost.
- **Flex PCB model / Finish flex PCB model** — Convert/Extrude/Thicken, bend/rip, razgrnjeni vzorec; za rigid-flex izvoz IDX.
- **Custom features (FeatureScript)** — gumb »Add custom features« iz drugih dokumentov/verzij, posodabljanje prek Reference manager; objava kot »Published FeatureScript«.
- **Tabele v Part Studiu**: Inspection table (MBD), Hole table, Sheet metal table, Cut list, Configuration tables, Variable table, Routing curve table, **Custom tables** (FeatureScript).
- **Materiali** — knjižnica 400+ (Ceramic 8, Composite 9, Earth 1, Glass 1, Metal 150+, Plastic 25, Rubber 6, Wood 24), gostota, Poissonovo število, Youngov modul, meja plastičnosti, natezna/tlačna trdnost; lastne knjižnice iz CSV (Material Library zavihek), deljenje. Knjižnice materialov v tabeli cen: Pro/Ent.
- **Videz (Appearance)** — barva RGB/hex, prosojnost 0–1, barve po ploskvah, privzeta rotacija 8 barv, custom colors; Appearance panel.
- **Mixed modeling (mesh + B-rep)** — uvoz STL/OBJ/glTF/3MF/Rhino/Parasolid mesh; na mesh: Delete face, Rib, Shell, Enclose, Boolean, Split, Offset surface, Move face, Hole, Mate connector, projekcija točk v skico, ravnine iz vozlišč; Constrained surface za rekonstrukcijo.
- **MBD (Model-Based Definition)** — Pro/Ent: 3D dimenzije (skice, značilnosti, luknje, osne razdalje, min/max cilindrov, debeline), GD&T okvirji, datumi, varilni simboli, note; Inspection table (filtri, CSV); validacija (rdeče ob manjkajočih referencah/neujemanju); izvoz v STEP AP242.
- **Seznam značilnosti (Features list)** — rollback vrstica, preurejanje z vlečenjem, suppress, **Dynamic suppression** (logični izrazi), mape, komentarji, časi regeneracije, filtri `:part :type :name :errors :warnings :folder :variable :suppressed :hidden :shown`, Show dependencies, Pause regeneration, Roll to here.
- **Seznam delov (Parts list)** — deli, ploskve, meshi, composite, krivulje; material, videz, lastnosti, hide/isolate/transparent, center mase, drawing, export, release.

---

## 3. Sestavi (Assembly)

### 3.1 Vstavljanje in struktura
- **Insert** — iz trenutnega/drugih dokumentov (verzije, revizije), **Standard content**; filtri skice/ploskve/deli/composite/flat pattern; iskanje po lastnostih; konfiguracije; vstavi del, ves Part Studio, **rigid Part Studio**, podsestav; I.
- **Instances list** — mape, hide/show/isolate/transparent, Fix/Unfix, Suppress, Dynamic suppression, Replace instances, Move to new subassembly, Edit in context, Change to version, Where used, Check interference, Create drawing, Export, Add mate connector to origin, Instance properties (reference designators); filtri `:part :assembly :mate :matelimits :item :folder :errors :warnings :suppressed :hidden :shown`.
- **Replace instance** — zamenja eno ali vse instance, ponovno uporabi mate-e, iskanje po lastnostih.
- **Updating references** — opozorilo (modro) ob novih verzijah, izbirno posodabljanje.
- **Group (skupina)** — zamrzne relativne položaje (brez DOF).
- **Triad manipulator** — vlečenje/vrtenje po oseh, pripenjanje na Mate connectorje, številčni vnos.

### 3.2 Mate-i (vsi definirani z Mate connectorji, razen Tangent)
**Fastened** (0 DOF, M), **Revolute** (Rz), **Slider** (Tz), **Planar** (Tx, Ty, Rz), **Cylindrical** (Tz, Rz), **Pin slot**, **Ball** (3 R), **Parallel**, **Tangent** (brez connectorjev; tangent propagation, flip; samo swept faces), **Width** (centriranje med vzporednima ploskvama).
- Možnosti: **Offset** (X/Y/Z, rotacija), **Limits** (min/max), **Animate** (start/end, koraki, Single/Reciprocate, ~60 korakov/s; vozi ostale mate-e in relacije), **Solve**, Flip primary axis (A), Reorient secondary axis (Q), Suppress, Apply limit position, Reset, Copy/Paste z mate-i, **Simulation connection** (za simulacijo).
- **Mate connector (Assembly)** — eksplicitni/implicitni, inferenčne točke (vogali, središča lokov, sredine robov, težišča, konci cilindrov …), Shift zaklep sklepanja, K preklop vidnosti.
- **Snap mode** (Shift+S) — vlečenje connectorja na connector ustvari mate; Ctrl cikla connectorje.
- **Show mates mode** (H) — hover prikaže mate-e instance; J prikaže vse mate-e.
- **Fix** — zaklep položaja.

### 3.3 Relacije (Relations)
**Gear** (razmerje, reverse), **Rack and pinion**, **Screw** (vrtenje↔pomik v cylindrical mate), **Linear** (konstantno razmerje pomikov).

### 3.4 Vzorci in podvajanje
**Assembly linear pattern** (do 3 smeri, equal spacing, centered, skupine), **Assembly circular pattern** (os, kot, equal spacing), **Assembly mirror** (Transform vs. **Derived** za zrcalne dele, tabela strategije, samodejne verzije), **Replicate** (najde enako geometrijo, kot je mate-ano seme, in ustvari kopije z mate-i; scope faces/edges; dissolve).

### 3.5 Prikaz in položaji
**Exploded views** (koraki translacije/rotacije, specify direction/axis, explode lines po geometriji, v risbah, samo desktop), **Named positions** (shranjene vrednosti DOF in transformi; apply/update/duplicate), **Display states** (vidnost delov/mate-ov, v risbah), **Lock/follow position to** za podsestave, grafično izločanje majhnih delov.

### 3.6 Kontekst
**Modeling in context** (konteksti = posnetki sestava, več kontekstov za isti sestav v različnih položajih, ročni **Update context**, preimenovanje, primarna instanca, follow named position), **Create Part Studio in context**; samo verzijske/workspace reference (ne revizijske).

### 3.7 Standardna vsebina (Standard content)
Vijaki, matice, podložke, zatiči, vskočniki, O-obroči, distančniki, moznik; standardi **ANSI, DIN, ISO, NAS, PEM®, SAE**; **auto-size** iz izbranega roba/valja; skladi (stacking); urejanje metapodatkov (Pro/Ent polno).

### 3.8 BOM, analize, tabele
- **Bill of Materials** (Pro/Ent) — Structured (top level/multi-level) in Flattened, številke postavk po vrstnem redu instanc, lokalno zatiranje / globalna izključitev, **non-geometric Items**, urejanje lastnosti v tabeli, CSV izvoz, predloge (Pro/Ent), generiranje številk delov, komentarji.
- **Assembly variable table / Variable Studio** v sestavu.
- **Interference detection** (iz Analysis tools ali »Check interference«): rdeč prikaz, seznam, include standard content, top level only.
- **Measure** ([ ), **Mass properties** (masa, volumen, površina, težišče, vztrajnostni momenti, override mass, varianca).
- **Assembly configurations**, konfigurirani mate-i in instance.

### 3.9 Simulacija (Onshape Simulation) — Pro/Ent, samo v sestavih
- **Linearna statična FEA** in **modalna analiza** (lastne frekvence; 5–15 ne-togih načinov + togi načini; frekvenca, pomik, energija). Brez termike/CFD.
- Tehnologija **TrueSOLID™** (Frustum), brez ročnega mreženja/odstranjevanja detajlov; adaptivno izpopolnjevanje v živo.
- Obremenitve: **Force, Moment, Bearing, Pressure, Acceleration, Angular velocity**; load regions; **Inertial relief**.
- Povezave: Mates and touching faces / Mates / Bond all touching faces; iz mate-ov.
- Rezultati: von Mises, signed von Mises, Safety factor, Max principal stress, Displacement; animacija deformacije, barvne lestvice, hover.
- **Asynchronous simulation** — v ozadju, do 50 zaporednih, 24 h, 64/128 GB instance, Results and history, spremenljivke in konfiguracije.
- Omejitve: nepodprti mate-i Tangent/Pin slot/Parallel/Width in vse relacije; <100 instanc, <10 000 kontaktnih parov; brez composite delov.

---

## 4. Risbe (Drawings)

### 4.1 Pogledi
Osnovni pogledi ob ustvarjanju (brez ali 4 standardni), **Projected** (P), **Auxiliary**, **Section** (vertical/horizontal/angular, jogged do 4 točk, partial, Blind/Up to entity depth, Show cut geometry only, Exclude from cut, flip, section-from-section), **Aligned section**, **Broken-out section**, **Detail** (circle/rect/spline/polygon, In line/Connected/Leader, clip to geometry), **Break**, **Crop**, **Flat pattern** (bend lines, bend notes), izometrični/dimetrični/trimetrični, **named views**, **exploded views / named positions / display states** v pogledu, merilo, rotacija, tangentni robovi (hidden/solid/phantom), render mode, view simplification, shaded views (nalepke), sketch appearances, pogledi konfiguracij, Show annotations from model (MBD), pin references.
- Kontekstni meni pogleda (43 možnosti): hidden lines, bend lines/notes, threads, faulty parts, part intersections, offset cut lines, sketches, centerlines, auto centermarks, parts, constraints, center of mass, line style, Align/Rotate views, Order, Move to sheet, Group, **Replicate annotations**, Edit hatch, Suppress alignment, Paste as table …

### 4.2 Dimenzije
**Dimension** (univerzalna), 2-point linear, Line-to-line, Point-to-line, Line-to-line angular, 3-point angular, Radial (Shift+R), Diameter (Shift+D), Arc length, Chamfer, **Ordinate** (X/Y skupine, ANSI/ISO), Max/Min (Ctrl+M), center marks ob dimenzioniranju, jogged extension lines, dual dimensions, tolerance (Symmetrical, Deviation, Limits, Min, Max, Basic, Fit), inspection frames, prekrivanje vrednosti (podčrtano).

### 4.3 Anotacije
**Note** (N; leaderji, simboli %%d %%c %%p, Unicode, polja lastnosti — ime, številka, revizija, datumi, Title 1–3, list, merilo, velikost, opis, vendor, material, masa; SHX/TrueType, krepko/ležeče/podčrtano, poravnave, seznami, ulomki, ravnilo, premik v title block/zone), **Callout/Balloon** (povezava z BOM/cut list/instance properties, stacked, add from BOM, oblike, polja okoli), **Geometric tolerance** (14 simbolov: Position, Concentricity, Symmetry, Parallelism, Perpendicularity, Angularity, Cylindricity, Flatness, Roundness, Straightness, Square, Profile of surface, Profile of line, Circular runout, Total runout; MMC/LMC/RFS, free state, tangent plane, projected zone, statistical, continuous feature, do 5 okvirjev, composite, All around/All over), **Datum** (datum targets Point/Circle/Rectangle/Custom), **Surface finish** (Basic / material removal required / prohibited, ISO variante, all around, oklepaji, lay direction, do 5 vrstic), **Weld symbol** (ANSI/ISO, groove tipi, fillet, plug/slot, seam, spot, stagger, symmetric, second fillet, all around, field flag), **Hole/Thread callout** (iz Hole/External thread; count types, fits ANSI/ISO), **Inspection items** (ročno/samodejno oštevilčenje, inspection table, CSV, Drawing definition list), **Revision callouts**, **Insert image**, **Center of mass**.

### 4.4 Skica in konstrukcija v risbi
Line, Center point circle, 3 point circle, Tangent arc, Corner/Center point rectangle, Spline, Spline point, Sketch point, Trim, **Hatch region**; omejitve Horizontal, Vertical, Coincident, Perpendicular, Parallel, Tangent; konstrukcija: 2 point centerline, Edge-to-edge centerline, 3 point / 2 point circle centerline, Centermark (single/circular/linear, bolt circle, patterns), Virtual sharp.

### 4.5 Tabele
**BOM** (Flattened, Structured top-level, Structured multi-level; override celic; razdelitev; predloge; anchor), **Hole table** (izvor, osi, vrstni red, izključitve), **Revision table** (samodejno iz release managementa, Linked/See sheet 1, pending modro), **Cut list table**, **Custom table** (title/header, merge, formati), **Inspection table**, »Paste as table« iz Excela/Sheets; kopiranje celic v Excel.

### 4.6 Listi, predloge, lastnosti, slogi
Več listov (dodaj, preuredi, dupliciraj, kopiraj med dokumenti, zone, velikosti do 1800″, merilo, border), **Templates** (ANSI/ISO/JIS, prvi/tretji kot, enote, decimalno ločilo; lastne iz DWT, iz DWG/DXF, uvoz SOLIDWORKS predlog), **Drawing properties** (Units and precision, Dimensions, Annotations, Views, Construction geometry, Formats, Tables, Inspection; shranljive kot predloge), **Styles** panel (dimenzije, anotacije, šrafure, skicirna geometrija), **Format painter**, **MBD status** (manjkajoče anotacije, suggested views), **Updating** (ročna posodobitev, dangling entities rdeče, verzijske/revizijske reference za hitrost), **Drawing constraints**, QR koda in URL risbe.

### 4.7 Uvoz/izvoz risb
Uvoz DWG (do 2018), DXF (2013/2018), DWT; izvoz **PDF** (barva/črno-belo/sivine, besedilo kot izbirno), **DWG/DXF** (R11–2018, enote, text vs. polylines, splines as polylines, z=0, off-sheet), **DWT**, **SVG, PNG, JPEG, CSV** (inspection); tiskanje; mobilno DXF/DWG/DWT/PDF.

---

## 5. Studii: Render, PCB, CAM, AI

### 5.1 Render Studio — Pro/Ent (+ **Render Studio Advanced** kot dodatna aplikacija)
- Oblačni **NVIDIA Iray**, brez GPU; scena = posnetek vstavljenih delov/sestavov, povezana (posodobitve); več scen v dokumentu; brez sočasnega urejanja.
- Orodna vrstica: Undo/Redo, Insert, **Render scene**, Transform, **Projector** (UV projekcija), Match scene properties, **Volume** (Adv), **Light** (Adv), Upgrade.
- **Appearance panel**: base color, diffuse roughness, metallic, reflection roughness/weight/anisotropy/rotation, transmission color/volume color/reference distance/roughness/weight, thin walled, IOR, Abbe, bumps; **Appearance library** (mape, favorites, funkcije: checker, bump, bitmap, sticker; uvoz PNG/JPG tekstur in bump map), **Appearance sets** (Adv), **AxF** (X-rite, Adv), **modifiers/functions**, **Light emission**.
- **Environment panel**: HDRI knjižnica/lastni HDRI, dome (infinite/hemisphere), intenziteta, rotacija, ground plane (odboj, hrapavost, sence), **Daylight** (lokacija, datum, ura), area lights Disc/Rectangle/Ring (Adv), gradient/solid.
- **Camera panel**: FOV 1–175° / goriščnica 1–2063 mm, clipping, položaj/rotacija, ozadje (barva/slika), **Depth of field** (f-število, lamele, fokus), ekspozicija (ISO/f-stop/shutter ali enostavna), toni (sence, svetlobe, nasičenost, color balance), vinjeta, tone mapping (Reinhard, Uncharted 2, ACES, PBR neutral), gama.
- **Render options**: ločljivosti (From view, 8K UHD, 2160, 1080, 720, NTSC, PAL, custom; razmerja), **JPEG/PNG/HDR/EXR**, kakovost Production/Medium/Preview/Custom (čas, vzorci, prag), odstranitev ozadja (alfa), **panoramic** in **stereo** (Adv), **appearance masks** (Adv); render v zavihek ali prenos; 2,1 MP standard / 100 MP Adv; named views, section view, SpaceMouse.

### 5.2 PCB Studio — Pro/Ent (tudi Educator Ent, Government)
- Uvoz **IDF 2.0/3.0, IDX 3.0/3.5/4.0, Eagle .brd v6+**, Creo hint.map; izvoz IDF 2.0/3.0 in **IDX 4.0** (Cadence Allegro); združljivost Altium Designer, P-CAD, Allegro, OrCAD, Eagle, Xpedition, PADS.
- **Altium 365** integracija (pull/push oblak-v-oblak).
- Sync to/from Onshape: obris plošče, cone rigid/flex, luknje (plated/non-plated s **PCB Data** tagi), keep-in/keep-out, stackup, komponente (No model / Automatic footprint / Custom Onshape part), BOM s cross-highlightom, suppress, library document in Components folder.
- **Rigid-flex** z upogibi, flat/folded konfiguracije (1.220).

### 5.3 CAM Studio — Pro/Ent (beta); **CAM Studio Advanced** (napovedan)
- CAM Studio: 2,5- in 3-osno; Advanced: 4, 3+2, 5 osi, struženje.
- Tok: Components (deli, vpenjala, surovec) → Jobs → **Machines** (Haas, Tormach, Brother, DMG Mori …) → Setups (WCS) → Tools (ball/end/bull/dove/lollipop/slot/taper/chamfer mill, drill, tap; holderji) → Toolpaths → Work planes.
- Strategije: 2-axis rough/profile/chamfer, 3-axis profile, 5-axis profile, Face, Trochoidal, Engrave; podvzorci Offset/Parallel/**Adaptive**; po robovih/ploskvah/telesih/luknjah.
- **Post processor** (enote, numeriranje blokov, loki, vijačnice, retracti, canned cycles: drilling, peck, threading, chip break); Generic Sinumerik/S840D ipd.
- **Back plot, Verify (odvzem materiala, gouge), Simulate (kinematika stroja, trki)**; izvoz G-kode (prenos / zavihek).
- Verzioniranje, branch/merge CAM poslov, sočasno delo.

### 5.4 AI (2025/2026)
- **AI Advisor** — vsi paketi razen Government; v Document panelu in Help; odgovarja iz Help, Learning Center, blogov; ocena 1–5 zvezdic; kumulativna seja.
- **Onshape Labs** (osebni opt-in; admin dovoljenje »Allow access to Onshape Labs«): **FeatureScript Co-Complete** (LLM dopolnjevanje v Feature Studiu), **Descriptive image search / AI-powered public document search** (opisi sličic), **AI Quick Render** (fotorealističen render iz viewporta in pozivov, v stranskem panelu, na Onshape strežnikih), **FeatureScript MCP Server** (napovedan), **NVIDIA Omniverse Publisher**, **AI agents and automation** (napovedano: troubleshooting, metapodatki, generiranje FeatureScripta, izvozi, popravki geometrije).
- **Replicate annotations (beta)** — strojno učenje prenese dimenzije/tolerance/razporeditev med pogledi risb.

---

## 6. Podatki in sodelovanje (PDM)

- **Versions and history** — verzije (ime, opis), samodejne verzije ob posodobitvah referenc, **veje (branch)** iz verzij, **merge** (Keep / Merge changes / Replace, po zavihkih; risbe in PCB le Keep/Replace; revert), **compare** (verzija/workspace: značilnosti, deli, Feature Studio koda zeleno/rdeče, tolerance), **restore**, obnova izbrisanih workspace-ov, iskanje po zgodovini (zavihek, tip, avtor, datum), filtri vej, **Workspace protections** (spremembe le prek vej), **View in repair / Replace reference** (popravilo zlomljenih referenc, propagacija).
- **Release management** (Pro; Ent prilagodljiv) — Release candidate (deli, sestavi, risbe, Variable Studio, datoteke; tudi iz več dokumentov), stanja In progress/Pending/Released/Rejected/Obsolete, approvers/observers, več nivojev, **custom workflows v JSON** (states, transitions SUBMIT/APPROVE/REJECT, actions: email, mark pending/released, obsolete, FeatureScript lastnosti), obsoletion workflow, revision schemes (alfabetski/numerični/custom), unreleased suffix, vodni žigi na risbah, pogoji preprečitve (napake, pending drawing updates, tasks), zahteva release notes, samodejno zastaranje prejšnjih revizij, release drafts, **Releasing a configuration**, revizijska zgodovina, cloniranje paketov, poročila.
- **Part numbers** — ročno, **sequential numbering schemes** (prefix, dolžina, start; Pro/Ent), Arena; pravila unikatnosti, propagacija v workspace; **Revision tools** (reset tipa številke).
- **Properties/metadata** — privzete (name, description, part number, revision, state, vendor, project, product line, title 1–3, material, UoM, mass, not revision managed, exclude from BOM), **custom properties** (Text, Boolean, Integer, Double, Date, List, User, Value with units; required, editable in workspace/version, **computed via FeatureScript**), **Categories** (hierarhične, scope, publish states), metadata overrides javnih delov, bulk urejanje na Documents page.
- **Items** (negeometrijski zapisi za BOM; CSV uvoz/izvoz; Pro/Ent »Bulk item management«).
- **Sharing** — Can edit / Can view + Copy, Export, Link document, Share/Reshare, Comment, Delete; posamezniki, **teams**, podjetje, **Public**, **link sharing** (brez prijave, opcijsko export), **Connections** (Ent–Ent), **guest users** (Ent), **light users** (Ent; view-only toolbar), transfer ownership; Free uporabniki zasebnih dokumentov ne morejo urejati.
- **Sodelovanje** — sočasno urejanje v istem zavihku, **Follow mode** (zavihek, kurzor, izbire, dialogi), **Comments** (vezani na geometrijo/značilnosti/dimenzije/MBD, @omembe, e-pošta, resolve), **Markups** (risanje po zaslonu kot priloga komentarja), **Tasks/Action items** (comment/general/release; Pro/Ent ustvarjanje; filtri), real-time obvestila, **Slack** integracija (komentarji, naloge, release-i, seznam dokumentov), **View-only mode** z lastno orodno vrstico (25 orodij: section, inspection, BOM, exploded, named positions, simulation, measure, mass, export, print …).
- **Documents page** — mape, **Projects** (Ent; permission schemes, project roles: Project Administrators, Managers, Engineers, Reviewers, Suppliers), **Labels**, filtri (All, Shared with me, Public, Teams, Recently opened, Trash 30/90 dni), **List view** in **Structure view** (Pro/Ent: hierarhija izdanih revizij, where used, revision history), **Advanced search** (tip, ime, opis, številka, stanje, revizija, kategorija, custom properties, workspace/version, wildcard), **Where used** (Pro/Ent), **Publications** (read-only paketi iz več dokumentov/verzij/revizij, notes v Markdownu, »view as viewer«), **Document notes** (Markdown), Details/Properties/Share/Analytics paneli, uvoz iz Google Drive/Dropbox/OneDrive, trash, default units per workspace, linking documents (verzijske reference, selektivno posodabljanje).
- **Enterprise** — SSO (Okta, OneLogin, PingOne, Microsoft Entra ID, ADFS, Google, ClassLink, custom SAML), 2FA, domain verification, company domain URL, **RBAC** (24 global permissions: admin, manage users/teams/aliases, invite guests, RBAC, permanently delete, analytics admin, create projects/releases/tasks, approve releases, App Store, public docs, items, workflows, link sharing, transfer out, sync to PLM, standard content metadata, workspace protection, import/export files, revision tools, Labs), teams, aliases, **Analytics** (Amazon QuickSight dashboardi: Action items, Audit, Documents, Permissions, Projects, Release, Resource, Users; scheduled reports; CSV/Excel), **IP audit trail** (kopije, izvozi, link-share, prenosi, neuspele prijave, lokacije), job queue, applications/developer settings, webhooks s podpisi (HMAC), ITAR/EAR podpora, Government okolje, Edu Enterprise (classes, assignments).
- **PLM** — **Onshape Arena Connection** (Ent): enosmerni sync delov/sestavov/BOM/risb v Arena Change (PDF, STEP, glTF, DXF), mapiranje kategorij/lastnosti; marketinška stran omenja tudi API povezavo z Windchill; ERP prek App Store (SharpSync, CADLink, Cideon → SAP, NetSuite, Odoo, Dynamics 365).

---

## 7. Uvoz / izvoz

**Uvoz delov**: Parasolid x_t/x_b v10–v38.1 (priporočeno), Parasolid mesh/mixed, ACIS .sat do 2023, STEP AP203/214/242, IGES do 5.3, CATIA V5 R7–R33/2026, SOLIDWORKS .sldprt 1999–2026, Inventor 9–2026, Pro/E 2000i–Creo 12, JT do 11, Rhino 2–8, STL, OBJ, NX (UG15–2512), Solid Edge 10–2026, glTF 2.0, 3MF, PVZ.
**Uvoz sestavov**: isto + SOLIDWORKS Pack&Go zip, Inventor .iam zip, Creo zip, NX zip, Solid Edge zip.
**Risbe**: DWG do 2018, DXF 2013/2018, DWT. **Ne-CAD**: PDF, MP4, PNG, JPG, SVG, GIF, TXT, MD, CSV, JSON (ogled); PY/JAVA/JS/MOV/DOC (shramba).
**Možnosti uvoza**: en dokument / razdeli v več dokumentov (>100 unikatnih delov) / združi v en Part Studio, Import appearances, Import material density, Y axis up, Create composite, Join adjacent surfaces, Allow faulty parts, IGES postprocessing, enote STL/OBJ; 4 GB na datoteko; posodobitev uvoza (Update); **LiDAR scan** (iOS, environment → GLB, object → OBJ).
**Izvoz delov/Part Studiev**: Parasolid v25–v37, Parasolid mesh/mixed, ACIS v5, STEP (MBD, barve, enote), IGES 5.3, STL (coarse/medium/fine/custom, text/binary, enote), JT, glTF/GLB (kompresija), Rhino, PVZ 8.0, 3MF, OBJ (+mtl). **Sestavi**: isto + **URDF**. Skice/ravne ploskve: DWG/DXF. Možnosti: ena/več datotek, hidden instances, Y up, export rules (`${partNumber}-${revision}`), cilj prenos / zavihek / e-pošta. **Risbe**: glej §4.7.
**Mesh orodja**: glej §2.6 Mixed modeling.

---

## 8. Razširljivost

- **FeatureScript** — jezik Onshapea za vse vgrajene značilnosti; **Feature Studio** (urejevalnik, commit Ctrl+S, outline, find usages/rename, iskanje regex); tipi značilnosti z anotacijami UI: Boolean, String, Enum, Length/Angle/Integer/Real/Anything, **Query** (filtri, max picks), **Reference** (Part Studio, slike, CSV), **Lookup table**, Array, Parameter groups; UIHint (OPPOSITE_DIRECTION, ALWAYS_HIDDEN, HORIZONTAL_ENUM, REMEMBER_PREVIOUS_VALUE, …); preconditions, manipulatorji, atributi, **custom tables**, **computed part properties**, imports med dokumenti, debugging; **Standardna knjižnica** (odprta koda): Modeling (geometry, geomOperations, primitives, sketch, query, evaluate, context, common), Math (vector, matrix, transform, coordSystem, units, box, nurbsUtils, splineUtils, surfaceGeometry …), Utilities (attributes, feature, manipulator, path, properties, table, tolerance, string, debug, holeUtils, patternUtils …), Features (vse: extrude, revolve, sweep, loft, fillet, chamfer, draft, shell, hole, boolean, splitpart, transformCopy, patterns, mirror, sheetMetal*, frame*, gusset, endcap, cutlist, decal, tag, wrap, routingCurve, helix, fitSpline, moveFace, deleteFace, replaceFace, faceBlend, fillSurface, bsurf, ruledSurface, offsetSurface, constrainedSurface, enclose, thicken, rib, externalThread, importDerived, importForeign, mateConnector, variable, queryVariable, pcbStart/End, compositePart …), 76 enum modulov. Objava kot javni FeatureScript; Co-Complete; MCP strežnik (napovedan).
- **REST API** — URL `/api/v{n}/{endpoint}/d/{did}/{w|v|m}/{id}/e/{eid}`; GET/POST/DELETE, JSON; **OAuth2** (obvezno za App Store) in **API keys** (HMAC); skupine v Glassworks: Accounts, Alias, APIApplications, AppAssociativeData, AppElement, Assembly, Billing, BlobElement, Comment, Company, Document, Drawing, Element, ExportRule, FeatureStudio, Folder, Insertable, Metadata, MetadataCategory, OpenApi, Part, PartNumber, PartStudio, Project, Property, PublicationItem, ReleasePackage, Revision, Sketch, Team, Thumbnail, Translation, User, Variables, Versions, Webhook, Workflow; FeatureScript evaluation prek API; **limiti** (letno: Ent 10 000/full user, Pro 5 000/user, Free/Standard/EDU 2 500/user; 429 za rate, 402 ob izčrpanju; javne App Store aplikacije ne štejejo).
- **Webhooks** — dogodki npr. `onshape.document.lifecycle.created`, `onshape.model.lifecycle.changed`, `onshape.model.lifecycle.createversion`, `onshape.document.lifecycle.statechange`, `onshape.model.translation.complete`, `onshape.comment.create`, `webhook.register/unregister/ping`; polni seznam v createWebhook Callbacks; collapseEvents; podpisi HMAC in basic auth (Ent nastavitve).
- **App extensions** — Element tab, Element right panel, Element/Tree/Document list context menu, Document list info panel, **Part number generator**; akcije GET/POST/open window; **client messaging** prek postMessage; **structured storage** (sub-elements, **JSON Tree** z merge/diff), associative data.
- **App Store** — integrirane oblačne / povezane namizne / povezane oblačne aplikacije; ocene, EULA; primeri: Luminary Cloud, SimScale (simulacije), Kiri:Moto (CAM/laser/3D tisk), SharpSync, CADLink, Cideon (ERP), Infinitive, Spokbee (konfiguratorji), CADENAS, TraceParts, 3DX (knjižnice delov), Altium 365.
- **Integracije računa**: Google Drive, Dropbox, OneDrive, Altium 365, Slack.

---

## 9. Uporabniški vmesnik

- **Izbira**: klik/preklop, Ctrl dodaj, Shift razpon, okvir L→D (v celoti) / D→L (dotik), Ctrl+okvir odstrani, Space počisti, sredine robov, **Select other** (`, cikla po globini), **Create selection** (Protrusion, Pocket, Hole, Fillets, Tangent connected, Bounded faces; robovi: tangent, loop/chain, equal length/radius, parallel; select patterns), Alt+klik skozi prosojno, filtri v dialogih.
- **Pogledi**: view cube, Shift+1…7, izometrični/dimetrični/trimetrični, perspektiva/ortografija, **Named views** (Shift+V; s section view), **Section view** (Shift+X; več ravnin, Mate connectorji, cilindri, exclude/include, N normalno), Shaded / Unshaded / Shaded without edges / Translucent, hidden edges, tangent edges, boundary edges, zoom fit/window/selection, rotacija s tipkami, **Appearance panel**, **Display states**, isolate (Shift+I), transparent (Shift+T), hide (Y), 3Dconnexion.
- **Analize** (meni spodaj desno): glej §2.3; **Measure** (razdalje center/min/max, premer, polmer, dolžina, površina, koti, XYZ, tangentni koti, ukrivljenost, obseg; enote; kopiranje), **Mass properties**, **Interference detection**.
- **Bližnjice**: celoten uradni seznam (General, Part Studio, Sketch, 3D view, Assembly, Feature Studio, Drawings) — ključne: S shortcut toolbar, Alt+C Search tools, Shift+/ seznam, Ctrl+Space zadnji zavihki, Alt+T Tab manager, Ctrl+M Mate connector, [ Measure, Enter/Shift+Enter potrditev (+nov dialog), Esc, Ctrl+Z/Y; prilagodljive bližnjice in orodne vrstice (drag&drop, tool sets).
- **Numerična polja**: enote mm/cm/m/in/ft/yd, deg/rad; + − * / ^ %, ceil floor round exp sqrt abs max min log log10, trig (v stopinjah), pi, polja `[..][i]`, ternarni `?:`, && ||, ulomki, vejica kot decimalka, `#spremenljivke`.
- **Tolerance options**: Default, No tolerance, Symmetrical, Deviation, Limits, Min, Max, Basic, Fit / Fit with tolerance / Fit (tolerance only) (ANSI/ISO, Clearance/Transition/Interference, hole/shaft class); natančnost 0–6; **Default tolerances library** (ISO 2768 c/f/m/v, Precision).
- **Drugo**: Triad manipulator, context menus (Show all, Zoom to, Isometric, View normal to, Roll to here, Add comment, Create drawing of sketch, Export DXF/DWG, Suppress …), **Performance panel** (regeneracija, grafika, dokument, sistem, povezava), graphics tessellation levels, Tab manager, dark mode, jeziki, Help/Explore Onshape/Learning Center, Print/Download image, Error indicators, Undo/Redo per uporabnik.
- **Mobilno (iOS/Android)**: polno skiciranje in modeliranje (extrude, revolve, sweep, shell, fillet, chamfer …), sestavi (insert, mates, connectors, fix), ogled risb, verzije/branching, komentarji, follow, measure/mass, precision selector, 3D rotate lock, view cube, izvoz; **AR View** (iOS: measure, section, vidnost, konfiguracije, shrani sliko), **Apple Vision Pro** (Onshape Vision: ogled iz iOS, brez urejanja), **LiDAR** (iPhone 12 Pro+/iPad Pro 2020+); omejeno: konfiguracije le izbira, exploded le ogled, Frames ne, Render Studio ne.

---

## 10. Posebnosti spletnega CAD-a

- **Arhitektura**: mikrostoritve na strežnikih — avtentikacija, modeling servers (seje v pomnilniku), geometry servers (**Parasolid** jedro in **D-Cubed** reševalnik, Siemens), interpretacija FeatureScripta, regeneracija, reševanje mate-ov, teselacija; baza namesto datotek, samo delte, nič se ne prepiše. Odjemalec: UI, izbira, **WebGL** izris trikotnikov (mobilno OpenGL ES); lasten renderer; **HTTPS/REST + WebSocket**. Regije: Oregon, Dublin, Tokio, Singapur, Sydney.
- **Zahteve**: WebGL obvezen (float framebuffer za prosojnost); brskalniki Chrome, Firefox, Safari (macOS), Edge, Opera (64-bit; IE ne); namenska grafična kartica ≥1 GB priporočena; RAM malo pomemben; pasovna širina majhna (kratka sporočila; »en video tok = ekipa«); 60 Hz; iOS 18+ (iPhone 8+), Android 8+ (OpenGL ES 2.0, priporočeno 3.0).
- **Omejitve**: brez delovanja brez interneta (ni offline načina v dokumentaciji); 4 GB na uvoženo datoteko; časovna omejitev regeneracije; <100 zavihkov/dokument priporočeno; grafično izločanje <2 px (5 000 teles) / <10 px; simulacija <100 instanc; render 2,1 MP (100 MP Adv); API letni limiti; sheet metal/frames v mobilnih ne; Enterprise dokumenti ne morejo biti javni; Free le javni dokumenti.
- **Varnost/IP**: audit trail, IP tracking, link sharing nadzor, RBAC, SSO/2FA, ITAR/EAR (Ent), Government okolje; AI Quick Render teče na Onshape strežnikih.

---

## 11. Cene in paketi (onshape.com/en/pricing, 10/2026)

| Paket | Cena | Ključne razlike |
|---|---|---|
| **Free** | 0 $ | le nekomercialno, le javni dokumenti (neomejeno), vsa CAD orodja, FeatureScript, API, App Store, AR, Publications, AI Advisor; brez Simulation/CAM/PCB/Render/MBD/BOM/Release/Where used |
| **Standard** | 1 500 $/uporabnik/leto | komercialno, zasebni dokumenti, admin orodja; brez Simulation/CAM/PCB/Render/MBD, brez BOM/Release/Where used/numbering/material libraries |
| **Professional** | 2 500 $/uporabnik/leto | + Simulation, CAM Studio, PCB Studio, Altium konektor, Render Studio, MBD, BOM, company ownership, material libraries, categories, Release management, Search & Where used, part numbering, items, IP audit trail, guided onboarding |
| **Enterprise** | po dogovoru | + prilagodljiv Release management, Arena, company domain URL, SSO, ITAR/EAR, RBAC, guest in light users, advanced provisioning, project reporting, Analytics & IP dashboard, priority support |
| Education / Startup / Discovery (6 mesecev Pro) | brezplačno | |

Dodatno plačljivo: **Render Studio Advanced**, **CAM Studio Advanced** (napovedan), dodatni API klici.

---

## Neverificirano / opombe
- Stran `onshape.com/en/features` in `/en/features/mobile`, `/en/product` vračajo 404; uporabljene so podstrani `/features/<tema>`.
- Mapa Sketch v Sitemap.xml ni vključena; orodja skice so potrjena prek posameznih strani in seznama bližnjic.
- »Windchill« je omenjen le na marketinški PDM strani, Help pozna le Arena povezavo.
- Guest users: iz Enterprise Settings – Users (povzetek iskanja), strani nisem odprl v celoti.

---

## Prebrani viri

**Onshape Help**
- https://cad.onshape.com/help/Content/home.htm · https://cad.onshape.com/help/Sitemap.xml
- Sketch: …/Content/Sketch/sketch_tools.htm, working_with_constraints.htm, dimension.htm, automatic_inferencing.htm, slot.htm, text.htm, use.htm, conic.htm, ellipse.htm, extend.htm, bezier.htm, sketch_fillet.htm, sketch_circular_pattern.htm, insert_dwg_or_dxf.htm; …/Content/sketch_basics.htm, sketch-image.htm, sketch-tools-offset.htm, sketch-tools-sketch-pattern.htm, transform-sketch.htm, sketch-tools.htm
- Part Studio: …/Content/PartStudio/part_studios.htm, feature_basics.htm, feature_tools.htm, features_and_parts_lists.htm, extrude.htm, revolve.htm, sweep.htm, loft.htm, fillet.htm, chamfer.htm, draft.htm, shell.htm, rib.htm, hole.htm, external_thread.htm, boolean.htm, split.htm, transform.htm, mirror.htm, linear_pattern.htm, curve_pattern.htm, move_face.htm, delete_face.htm, modify_fillet.htm, face_blend.htm, thicken.htm, ruled_surface.htm, boundary_surface.htm, surface_modeling.htm, helix.htm, routing_curve.htm, plane.htm, mate_connector.htm, variable.htm, variable_table.htm, query_variable.htm, configurations.htm, configured_properties.htm, part_studio_and_assembly_configurations.htm, managing_configurations.htm, visibility_conditions.htm, derived.htm, composite_part.htm, custom_tables.htm, mixed_modeling.htm, add_custom_features.htm, decal.htm, tag.htm, cut_list.htm, inspection_table.htm, customizing_part_materials.htm, customizing_appearances.htm, model_based_definition.htm, flex_pcb_model.htm, frame.htm, sheet_metal_model.htm, sheet_metal_table.htm, sheet_metal_form.htm, sheet_metal_jog.htm
- Assembly: …/Content/Assembly/assembly.htm, mates.htm, relations.htm, gear_relation.htm, tangent_mate.htm, assembly_mate_connector.htm, group.htm, snap_mode.htm, show_mates_mode.htm, insert_parts_and_assemblies.htm, instances_list.htm, replace_instance.htm, assembly_linear_pattern.htm, assembly_circular_pattern.htm, assembly_mirror.htm, replicate.htm, exploded_views.htm, named_positions.htm, display_states.htm, modeling_in_context.htm, standard_content.htm, bill_of_material.htm, working_with_the_bom_table.htm, assembly_variable_table.htm, simulation.htm, asynchronous_simulation.htm, modal_simulation.htm
- Drawing: …/Content/Drawing/drawings.htm, drawing_basics.htm, views.htm, view_context_menu.htm, drawing_section_view.htm, detail_view.htm, drawing_dimensions.htm, drawing_-_ordinate_dimension.htm, drawing_properties.htm, drawing_properties_-_dimensions.htm, note.htm, callout_balloon.htm, geometric_tolerance.htm, datum.htm, surface_finish.htm, weld_symbol.htm, hole_thread_callout.htm, inspection_item.htm, table.htm, bom_table.htm, drawing_hole_table.htm, revision_table.htm, cut_list_table.htm, drawing_sketch_tools.htm, drawing_construction_tools.htm, working_with_drawing_constraints.htm, sheets.htm, custom_drawing_templates.htm, styles.htm, mbd_status.htm, exporting_a_drawing.htm, importing_a_drawing.htm, updating_a_drawing.htm
- Studii: …/Content/RenderStudio/render_studios.htm, render_studio_basics.htm, render_studio_advanced.htm, render_studio_interface_toolbar.htm, …_appearance_panel.htm, …_appearances_library.htm, …_environment_panel.htm, …_camera_panel.htm, …_render_options.htm; …/Content/PCBStudio/pcb_studios.htm; …/Content/CAMStudio/cam_studios.htm; …/Content/FeatureStudio/feature_studios.htm
- Dokumenti/sodelovanje: …/Content/Document/document_management.htm, documents_page.htm, document_panel.htm, document_tabs.htm, document_notes.htm, versions_and_history.htm, merging.htm, compare.htm, repairing.htm, linking_documents.htm, advanced_search.htm, where_used.htm, structure_view.htm, workspace_protections.htm, publications.htm, doc_integrations.htm, importing_files.htm, working_with_imported_cad.htm; …/Content/Collaboration/sharing_and_collaboration.htm, share_documents.htm, comments_on_workspaces.htm, follow_mode.htm, view_only_mode.htm, using_the_view_only_toolbar.htm; …/Content/Release/release_management.htm, creating_a_customized_release_workflow.htm
- File: …/Content/File/supported_file_formats.htm, exporting_files.htm, importing_a_lidar_scan.htm
- Plans/Enterprise: …/Content/Plans/analytics.htm, audit_reports.htm, project_roles_and_permission_schemes.htm, understanding_teams.htm, enterprise_settings_numbering_schemes.htm, enterprise_settings_custom_properties.htm, enterprise_settings_categories.htm, enterprise_settings_release_management.htm, enterprise_settings_revision_tools.htm, enterprise_settings_task_management.htm, enterprise_settings_webhooks.htm, enterprise_settings_integrations.htm, enterprise_settings_authentication.htm, enterprise_settings_global_permissions.htm, enterprise_settings_items.htm, onshape_arena_connection.htm, plm_connections.htm, getting_started_as_a_light_user.htm, action_items.htm, my_account_preferences.htm, my_account_integrations.htm, export_rule_conventions.htm, managing_your_onshape_free_account.htm
- Library: …/Content/Library/onshape_standard_content_library.htm, onshape_frame_profiles_library.htm, onshape_material_library.htm, sheet_metal_form_library.htm, onshape_default_tolerances_library.htm
- Mobile: …/Content/Mobile/mobile_touch_interface_videos.htm, viewing_models_with_ar_view.htm, viewing_models_with_apple_vision_pro.htm
- Home/View: …/Content/Home/ai_advisor.htm, onshape_labs.htm, featurescript_co_complete.htm, descriptive_image_search.htm, app_store.htm, selection.htm, select_other.htm, create_selection.htm, search_tools.htm, user_interface_basics.htm, context_menus.htm, triad_manipulator.htm, numeric_fields.htm, tolerance_options.htm, properties_metadata.htm, hardware_and_graphics_performance_recommendations.htm, performance_considerations.htm, performance_panel.htm, graphics_area_display_data.htm, printing_part_studios_and_assemblies.htm, product_data_management.htm; …/Content/View/analysis_tools.htm, measure_tool.htm, mass_properties_tool.htm, named_views.htm, section_view.htm; …/Content/moving.htm, shortcut_keys.htm, webgl.htm

**FeatureScript**: https://cad.onshape.com/FsDoc/ · /FsDoc/library.html · /FsDoc/feature-types.html · /FsDoc/tables.html · /FsDoc/uispec.html

**API**: https://onshape-public.github.io/docs/ · /docs/api-intro/ · /docs/auth/ · /docs/auth/limits/ · /docs/app-dev/webhook/ · /docs/app-dev/extensions/ · /docs/app-dev/clientmessaging/ · /docs/app-dev/structuredstorage/ · https://cad.onshape.com/glassworks/explorer/

**onshape.com**: /en/pricing · /en/changelog · /en/features/parts-modeling · /en/features/assemblies · /en/features/drawings · /en/features/sheet-metal · /en/features/frames · /en/features/surfacing · /en/features/custom-features · /en/features/simulation · /en/features/cam-studio · /en/features/render-studio · /en/features/pcb-studio · /en/features/data-management · /en/app-integrations/applications · /en/blog/how-does-onshape-really-work · /en/blog/ai-artificial-intelligence-cloud-native-cad-pdm-platform

**Iskanja (WebSearch)** za potrditev: interference detection, animate mate, polygon/split/wrap/sketch tools, guest users, API limits, webhooks, Onshape Labs AI Quick Render, file size limits, arhitektura (develop3d, architosh).