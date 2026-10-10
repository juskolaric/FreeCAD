# -*- coding: utf-8 -*-
"""Orodja MCP v tekoči spletni FreeCAD brez ponovnega zagona (vroča zamenjava). Teče V strežniku:

    .pixi/envs/default/python.exe lastno/splet/izvedi.py lastno/mcp/namesti_v_tekoci.py

Naloži (ali znova naloži) mcp_orodja.py in pomocnik.py, ju poveže s strežnikom in iz streznik.py na disku zamenja metode, ki
orodja kličejo: Stanje._izvedi (ukaz "mcp"), Zahteva.do_GET (/mcp/orodja, /mcp/vir) in Zahteva.do_POST
(/mcp/orodje, /mcp/odgovor, /pomocnik). Pred zamenjavo preveri, da nove metode ne kličejo imen, ki jih tekoči strežnik nima
(sprememba druge seje, ki še ni naložena); takrat ne zamenja ničesar in imena izpiše.
Stran v brskalniku (index.html) se bere ob vsakem nalaganju: zavihek je treba le osvežiti (F5).
"""
import ast
import builtins
import importlib
import os
import sys
import textwrap

S = sys.modules.get("streznik") or sys.modules.get("__main__")
pot = os.path.join(getattr(S, "MAPA", ""), "streznik.py")
with open(pot, encoding="utf-8") as f:
    izvor = f.read()
vrstice = izvor.splitlines(True)
drevo = ast.parse(izvor)

ZAMENJAJ = {"Stanje": ["_izvedi"], "Zahteva": ["do_GET", "do_POST"]}


def imena_kode(koda):
    imena = set(koda.co_names)
    for k in koda.co_consts:
        if hasattr(k, "co_names"):
            imena |= imena_kode(k)
    return imena


nove, manjka = {}, set()
for vozel in drevo.body:
    if isinstance(vozel, ast.ClassDef) and vozel.name in ZAMENJAJ:
        for m in vozel.body:
            if isinstance(m, ast.FunctionDef) and m.name in ZAMENJAJ[vozel.name]:
                besedilo = textwrap.dedent("".join(vrstice[m.lineno - 1:m.end_lineno]))
                koda = compile(besedilo, pot, "exec")
                ns = {}
                exec(koda, S.__dict__, ns)
                nove[(vozel.name, m.name)] = ns[m.name]
                fn_koda = ns[m.name].__code__
                for ime in imena_kode(fn_koda):
                    if ime not in S.__dict__ and not hasattr(builtins, ime) and ime not in ("mcp_orodja", "pomocnik"):
                        manjka.add(ime)

# imena atributov (obj.ime) so tudi v co_names: preverjamo le tista, ki bi bila globalna imena modula
manjka = {i for i in manjka if i in {n.name for n in drevo.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
          or i in {t.id for n in drevo.body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)}}
if manjka:
    print("NE ZAMENJAM: nove metode kličejo imena, ki jih tekoči strežnik nima (ponovni zagon ali naloži tudi te):",
          ", ".join(sorted(manjka)))
    rezultat = {"ok": False, "manjka": sorted(manjka)}
else:
    if "mcp_orodja" in sys.modules:
        mcp_orodja = importlib.reload(sys.modules["mcp_orodja"])
    else:
        import mcp_orodja  # noqa: F401
    S.mcp_orodja = mcp_orodja
    mcp_orodja.povezi(S)
    if "pomocnik" in sys.modules:
        pomocnik = importlib.reload(sys.modules["pomocnik"])
    else:
        import pomocnik  # noqa: F401
    S.pomocnik = pomocnik
    for (razred, ime), fn in nove.items():
        setattr(getattr(S, razred), ime, fn)
    print("Zamenjano: %s; orodij MCP: %d; katalog %s" % (
        ", ".join("%s.%s" % k for k in nove), len(mcp_orodja.ORODJA), mcp_orodja.katalog()["verzija"]))
    rezultat = {"ok": True, "orodij": len(mcp_orodja.ORODJA)}
