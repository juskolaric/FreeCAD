# -*- coding: utf-8 -*-
"""Vroča zamenjava kode strežnika v tekočem spletnem FreeCAD-u (brez ponovnega zagona). Teče V strežniku:

    .pixi/envs/default/python.exe lastno/splet/izvedi.py lastno/splet/vroca_zamenjava.py
    (ali orodje MCP python {"datoteka": ...})

Iz streznik.py na disku prenese v tekoči modul `streznik`:
  - funkcije in prireditve na ravni modula iz seznama IMENA (nove ali spremenjene; obstoječe vrednosti prireditev,
    npr. množice, se ne prepišejo, če že obstajajo — stanje ostane),
  - metode razredov iz slovarja METODE (razred -> imena metod).
Pred zamenjavo preveri, da nove metode ne kličejo imen, ki jih tekoči strežnik nima (sprememba, ki še ni naložena):
takrat ne zamenja ničesar in imena izpiše. index.html se bere ob vsakem nalaganju strani: zavihek le osveži (F5).

Nastavitev: spremenljivki IMENA in METODE spodaj (privzeto: risbe TechDraw, 2026-10-12). Za druge spremembe ju prilagodi
ali nastavi pred klicem v globalnem prostoru (`IMENA = [...]`; `exec` skripte).
"""
import ast
import builtins
import os
import sys
import textwrap

IMENA = globals().get("IMENA") or ["IZVOZI_RISB", "_RISBE_ODPRTE", "_risba_dejanje"]
METODE = globals().get("METODE") or {"Stanje": ["_izvedi"], "Zahteva": ["do_GET", "do_POST"]}

S = sys.modules.get("streznik") or sys.modules.get("__main__")
pot = os.path.join(getattr(S, "MAPA", ""), "streznik.py")
with open(pot, encoding="utf-8") as f:
    izvor = f.read()
vrstice = izvor.splitlines(True)
drevo = ast.parse(izvor)


def imena_kode(koda):
    imena = set(koda.co_names)
    for k in koda.co_consts:
        if hasattr(k, "co_names"):
            imena |= imena_kode(k)
    return imena


def besedilo(vozel):
    return textwrap.dedent("".join(vrstice[vozel.lineno - 1:vozel.end_lineno]))


globalna = {n.name for n in drevo.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))} | {
    t.id for n in drevo.body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)}

nove_vrednosti, nove_metode, manjka = {}, {}, set()
for vozel in drevo.body:
    if isinstance(vozel, ast.FunctionDef) and vozel.name in IMENA:
        ns = {}
        exec(compile(besedilo(vozel), pot, "exec"), S.__dict__, ns)
        nove_vrednosti[vozel.name] = ns[vozel.name]
        for ime in imena_kode(ns[vozel.name].__code__):
            if ime not in S.__dict__ and not hasattr(builtins, ime) and ime in globalna and ime not in IMENA:
                manjka.add(ime)
    elif isinstance(vozel, ast.Assign):
        for t in vozel.targets:
            if isinstance(t, ast.Name) and t.id in IMENA and t.id not in S.__dict__:
                ns = {}
                exec(compile(besedilo(vozel), pot, "exec"), S.__dict__, ns)
                nove_vrednosti[t.id] = ns[t.id]
    elif isinstance(vozel, ast.ClassDef) and vozel.name in METODE:
        for m in vozel.body:
            if isinstance(m, ast.FunctionDef) and m.name in METODE[vozel.name]:
                ns = {}
                exec(compile(besedilo(m), pot, "exec"), S.__dict__, ns)
                nove_metode[(vozel.name, m.name)] = ns[m.name]
                for ime in imena_kode(ns[m.name].__code__):
                    if ime not in S.__dict__ and not hasattr(builtins, ime) and ime in globalna and ime not in IMENA:
                        manjka.add(ime)

if manjka:
    print("NE ZAMENJAM: nova koda kliče imena, ki jih tekoči strežnik nima (dodaj jih v IMENA ali ponovno zaženi):",
          ", ".join(sorted(manjka)))
    rezultat = {"ok": False, "manjka": sorted(manjka)}
else:
    for ime, vrednost in nove_vrednosti.items():
        setattr(S, ime, vrednost)
    for (razred, ime), fn in nove_metode.items():
        setattr(getattr(S, razred), ime, fn)
    print("Zamenjano: %s" % ", ".join(list(nove_vrednosti) + ["%s.%s" % k for k in nove_metode]))
    rezultat = {"ok": True, "vrednosti": list(nove_vrednosti), "metode": ["%s.%s" % k for k in nove_metode]}
