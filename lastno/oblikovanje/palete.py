# -*- coding: utf-8 -*-
"""Barvne palete Oblikovanja: isti model v različnih barvnih kombinacijah, izbira s klikom na strani.

Zgradba (vse je v sceni, zato gre v vsako različico in v vsako novo idejo, ki nastane iz nje):
  - Vloga je skupina delov z isto barvo (npr. »Deske«, »Robovi desk«, »Tramovi«). Vsaka vloga ima svoj material z lastnostjo
    »vloga« = id vloge; dele vlogi priredi skripta projekta (npr. Projekti/Podest/Skripte/vloge_barv.py).
  - Lastnost scene »palete« (JSON):
        {"vloge":   [{"id": "deske", "oznaka": "Deske"}, ...],
         "palete":  [{"ime": "Božič belo-rdeča", "barve": {"deske": "#e4e1d8", "robovi": "#9b1b1e", ...}}, ...],
         "aktivna": "Božič belo-rdeča"}
    Barva null (ali vloga brez barve) pomeni izvirni material (npr. les s teksturo).
  - Uporaba palete osnovni barvi Principled BSDF odklopi vir (teksturo lesa) in nastavi barvo; izvirni vir se zapomni v
    lastnosti materiala »paleta_izvor« in se ob barvi null priklopi nazaj. Barva materiala v pogledu (diffuse_color) se
    nastavi enako, zato se spremeni tudi ključ posnetka objekta (stran dobi nove barve, ne starih iz predpomnilnika).

Ukazi (POST /ukaz, dejanje):
  paleta            {ime}                     uporabi paleto
  paleta-barva      {vloga, barva}            spremeni barvo vloge v aktivni paleti (barva "#rrggbb" ali null)
  paleta-shrani     {ime}                     trenutne barve aktivne palete shrani kot novo paleto (ali prepiše isto ime)
  paleta-odstrani   {ime}                     odstrani paleto iz seznama (deli in materiali ostanejo)
"""

import json

import bpy

LASTNOST = "palete"


def _scena():
    return bpy.context.scene


def podatki():
    try:
        p = json.loads(_scena().get(LASTNOST, "") or "{}")
    except (TypeError, ValueError):
        p = {}
    p.setdefault("vloge", [])
    p.setdefault("palete", [])
    p.setdefault("aktivna", "")
    return p


def shrani(p):
    _scena()[LASTNOST] = json.dumps(p, ensure_ascii=False)


def stanje():
    """Za posnetek strani: None, če scena nima palet."""
    p = podatki()
    if not p["vloge"]:
        return None
    return p


def _hex_v_lin(h):
    h = h.lstrip("#")
    s = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    return [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in s]


def _principled(mat):
    if mat.node_tree is None:
        return None
    for n in mat.node_tree.nodes:
        if n.type == "BSDF_PRINCIPLED":
            return n
    return None


def material_vloge(vloga, oznaka=None, iz=None):
    """Material vloge (ustvari ga kot kopijo materiala `iz`, da ostane izvirni videz, npr. les)."""
    for m in bpy.data.materials:
        if m.get("vloga") == vloga:
            return m
    if iz is not None:
        m = iz.copy()
    else:
        m = bpy.data.materials.new("x")
        m.use_nodes = True
    m.name = "Vloga · " + (oznaka or vloga)
    m["vloga"] = vloga
    return m


def dodaj_vlogo(vloga, oznaka):
    p = podatki()
    if not any(v["id"] == vloga for v in p["vloge"]):
        p["vloge"].append({"id": vloga, "oznaka": oznaka})
        shrani(p)


def nastavi_barvo_materiala(mat, barva):
    """barva "#rrggbb" ali None (izvirni material)."""
    bs = _principled(mat)
    if "paleta_diffuse" not in mat:
        mat["paleta_diffuse"] = list(mat.diffuse_color)
    if bs is None:
        mat.diffuse_color = (*_hex_v_lin(barva), 1.0) if barva else tuple(mat["paleta_diffuse"])
        return
    vhod = bs.inputs["Base Color"]
    if "paleta_izvor" not in mat:
        if vhod.is_linked:
            l = vhod.links[0]
            mat["paleta_izvor"] = json.dumps({"vozlisce": l.from_node.name, "izhod": l.from_socket.identifier})
        else:
            mat["paleta_izvor"] = json.dumps({"barva": list(vhod.default_value)})
    izvor = json.loads(mat["paleta_izvor"])
    drevo = mat.node_tree
    for l in list(vhod.links):
        drevo.links.remove(l)
    if barva:
        lin = _hex_v_lin(barva)
        vhod.default_value = (*lin, 1.0)
        mat.diffuse_color = (*lin, 1.0)
        return
    if "vozlisce" in izvor and izvor["vozlisce"] in drevo.nodes:
        n = drevo.nodes[izvor["vozlisce"]]
        izhod = next((s for s in n.outputs if s.identifier == izvor["izhod"]), n.outputs[0])
        drevo.links.new(izhod, vhod)
    elif "barva" in izvor:
        vhod.default_value = izvor["barva"]
    mat.diffuse_color = tuple(mat["paleta_diffuse"])


def _aktivna(p):
    return next((x for x in p["palete"] if x["ime"] == p["aktivna"]), None)


def uporabi(ime):
    p = podatki()
    pal = next((x for x in p["palete"] if x["ime"] == ime), None)
    if pal is None:
        raise ValueError("Ni palete %r." % ime)
    for v in p["vloge"]:
        mat = material_vloge(v["id"], v["oznaka"])
        nastavi_barvo_materiala(mat, pal["barve"].get(v["id"]))
    p["aktivna"] = ime
    shrani(p)
    return {"ok": True, "aktivna": ime}


def ukaz(u):
    """Ukazi palet; None, če dejanje ni od palet."""
    d = u.get("dejanje", "")
    if not d.startswith("paleta"):
        return None
    p = podatki()
    if d == "paleta":
        return uporabi(u.get("ime", ""))
    if d == "paleta-barva":
        pal = _aktivna(p)
        if pal is None:
            return {"ok": False, "sporocilo": "Ni aktivne palete."}
        pal["barve"][u["vloga"]] = u.get("barva") or None
        shrani(p)
        return uporabi(pal["ime"])
    if d == "paleta-shrani":
        ime = (u.get("ime") or "").strip()
        if not ime:
            return {"ok": False, "sporocilo": "Paleta potrebuje ime."}
        akt = _aktivna(p)
        barve = dict(akt["barve"]) if akt else {}
        p["palete"] = [x for x in p["palete"] if x["ime"] != ime] + [{"ime": ime, "barve": barve}]
        p["aktivna"] = ime
        shrani(p)
        return {"ok": True, "aktivna": ime}
    if d == "paleta-odstrani":
        p["palete"] = [x for x in p["palete"] if x["ime"] != u.get("ime")]
        if p["aktivna"] == u.get("ime"):
            p["aktivna"] = ""
        shrani(p)
        return {"ok": True}
    return {"ok": False, "sporocilo": "neznano dejanje palet: %s" % d}
