# freecad-mcp: spletni FreeCAD kot MCP strežnik

AI (Claude Code, Claude Desktop, Cursor) dobi orodja `mcp__freecad__*` za tekoči spletni FreeCAD
(`lastno/splet`, http://127.0.0.1:3020/): vidi stanje in model (slika, drevo, mere), požene katero koli funkcijo
(Python, ukaz okolja, končna točka strežnika, obrazec) in sam najde, kaj obstaja (`isci`). Plan: `MCP-PLAN.md`.

## Zgradba

- `lastno/splet/mcp_orodja.py` — možgani v FreeCAD-u: katalog orodij (opisi, sheme, oznake samo-branje /
  uničujoče), viri, predloge, izvedba. Strežnik: `GET /mcp/orodja`, `GET /mcp/vir?uri=`, `POST /mcp/orodje
  {ime, argumenti}` (žeton `X-Zeton`, seja `X-Seja`), `POST /mcp/odgovor` (stran v brskalniku odgovarja na zahteve
  orodij: slika pogleda, kamera, okno Pripravi).
- `freecad_mcp.py` (ta mapa) — most stdio brez odvisnosti. Orodja, viri in predloge pridejo s strežnika, zato novo
  orodje ne zahteva spremembe mostu. Lastni orodji mostu: `zazeni` (ZAZENI-SPLET.bat) in `freecadcmd` (ločen
  proces nameščenega FreeCADCmd, ko strežnik ne teče ali za krog zapis-branje STEP).

**Pomočnik v brskalniku** (`lastno/splet/pomocnik.py`, gumb ✦ Pomočnik) uporablja isti katalog brez mostu: zanka
Claude API teče v strežniku, stran kaže korake, slike in potrditve.

## Namestitev (enkrat, za vse projekte)

```bash
claude mcp add --scope user --transport stdio freecad -- "C:/Users/Uporabnik/AppData/Local/Programs/Python/Python311/python.exe" "C:/Users/Uporabnik/Desktop/Apps/FreeCAD/lastno/mcp/freecad_mcp.py"
```

**Namizna aplikacija Claude** (pogovor, Cowork): razširitev `freecad.mcpb` (dvojni klik ali Nastavitve → Razširitve →
namesti iz datoteke). Vsebuje le manifest in zaganjalnik `razsiritev/server/main.py`, ki požene ta most iz repozitorija
(pred in po selitvi v »3D tisk«), zato popravki mostu ne zahtevajo ponovne namestitve. Ponovna gradnja:
`npx --yes @anthropic-ai/mcpb pack lastno/mcp/razsiritev lastno/mcp/freecad.mcpb`. Vpis v `claude_desktop_config.json`
med delovanjem aplikacije ne obstane (aplikacija datoteko prepiše iz pomnilnika), zato `vpisi_v_claude_desktop.py
--cakaj` (pythonw, v ozadju) počaka na zaprtje aplikacije, strežnik vpiše in po ponovnem zagonu preveri, da vpis obstane
(dnevnik `%LOCALAPPDATA%/FreeCAD-splet/vpis-claude-desktop.log`). Uporabi eno od obeh poti, ne obeh (dvojna orodja).

**Skill `freecad`** (`skill/freecad/SKILL.md`): delovni postopki za orodja (prvi koraki, spremembe, okna ukazov, nov kos,
pločevina, sestav, pregled, tisk, render). Za Claude Code je nameščen v `~/.claude/skills/freecad/`; za namizno
aplikacijo `freecad-skill.zip` (Nastavitve → Zmožnosti → Skills → naloži). Po spremembi skill kopiraj znova. Isto
besedilo vrne tudi orodje `postopki` (in vir `freecad://postopki`), zato ga ima vsak odjemalec MCP brez nalaganja.

Nova seja Claude Code nato vidi orodja `mcp__freecad__*`, navodila strežnika (kratka pravila) pa so v njenem
sistemskem pozivu. Predloge so ukazi `/mcp__freecad__nov_kos`, `…__pregled`, `…__plocevina`, `…__sestav`,
`…__v_bazo`, `…__natisni_kos`; vir s pravili je `@freecad:freecad://pravila`.

## Orodja

| Orodje | Kaj naredi |
|---|---|
| `stanje` | aktivni dokument, neshranjeni, izbira, okolje, odprt obrazec, napaka, plošča tiskalnikov |
| `dokumenti` | seznam, aktiviraj, odpri, nov, zapri (le shranjenega), datoteke v Oblaku |
| `drevo` | drevo kot besedilo (prostornine, napake, povezave, spoji); `objekt` = vse lastnosti enega objekta |
| `slika` | izris modela iz smeri ali posnetek zaslona (prek strani v brskalniku; brez nje preprost izris iz mreže) |
| `izmeri` | okvir, prostornina, masa, ploskve in robovi, razdalja, kot, trki (`vsi`) |
| `python` | koda na glavni niti (transakcija, nove/odstranjene objekte, napake po preračunu); `datoteka` za skripte |
| `ukaz`, `obrazec`, `izberi` | ukazi okolij kot klik na gumb, okno ukaza (vpis, izbira, potrdi), izbira robov in ploskev |
| `isci` | ukazi, FreeCAD API, tipi objektov z lastnostmi, naši moduli, skripte projektov, končne točke, pravila |
| `razveljavi`, `shrani` | koraki nazaj in naprej; edino shranjevanje (s `komentar` za različico v oblaku) |
| `splet` | katera koli končna točka strežnika (videz, baza, knjižnica, skica, lega za tisk, oblak …) |
| `natisni`, `render`, `oblikovanje` | STEP v ploščo Tiskaj z oknom Pripravi; render Cycles; Python in slika v Blenderju |
| `opravilo`, `dnevnik`, `izhod` | dolgi klici, dnevnik strežnika in klicev, konec programa (le z izrecno potrditvijo) |
| `zazeni`, `freecadcmd` | (most) zagon spletnega FreeCAD-a; Python v ločenem FreeCADCmd |

Varovalke: `python` in `freecadcmd` brez `dovoli_pisanje` zavrneta kodo, ki shranjuje, zapira dokumente ali briše
datoteke; vsak `python` je ena transakcija (ob napaki se razveljavi sam); `izhod` zahteva `potrdi` in pri neshranjenih
dokumentih še `zavrzi_spremembe`; `splet` ne pusti `/izhod`, `/python` in posnetkov geometrije.

## Preizkus

```bash
python lastno/mcp/freecad_mcp.py test
python lastno/mcp/freecad_mcp.py call drevo '{"globina": 2}'
python lastno/mcp/preizkus_protokola.py
```

`call` slike shrani v začasno mapo in izpiše pot. Preizkusni primerek na drugih vratih: `FREECAD_MCP_POVEZAVA` = pot
do njegovega `povezava.json` (ločen `LOCALAPPDATA`), `FREECAD_MCP_ZAGON` = njegova zagonska skripta.

## Novo orodje

V `mcp_orodja.py` ena funkcija z dekoratorjem `@orodje(ime, opis, lastnosti, nit="glavna" | "streznik", ...)`.
Vroča zamenjava v tekoči strežnik (brez ponovnega zagona FreeCAD-a), npr. z orodjem `python`:

```python
import importlib, mcp_orodja
importlib.reload(mcp_orodja); mcp_orodja.povezi(S)
```

Most ob naslednjem klicu opazi novo verzijo kataloga in Claude Code javi `notifications/tools/list_changed`.
