# -*- coding: utf-8 -*-
"""Možnosti (konfiguracije) Oblikovanja: deli modela, ki jih vklopiš ali izklopiš s kljukico na strani.

Lastnost scene »moznosti« (JSON seznam):
    [{"id": "mizica_nabiralnik", "oznaka": "Mizica in nabiralnik", "vklop": true,
      "ob_vklopu": ["Mizica", "Nabiralnik"],             # zbirke, vidne ko je možnost vklopljena
      "ob_izklopu": ["Steber desno brez nabiralnika"]}]  # zbirke, vidne ko je izklopljena
Vidnost velja za pogled in render (hide_set + hide_render). Ker je v sceni, gre v vsako različico.
Ukaz (POST /ukaz): {"dejanje": "moznost", "id": ..., "vklop": true|false}
"""

import json

import bpy

LASTNOST = "moznosti"


def seznam():
    try:
        return json.loads(bpy.context.scene.get(LASTNOST, "") or "[]")
    except (TypeError, ValueError):
        return []


def shrani(s):
    bpy.context.scene[LASTNOST] = json.dumps(s, ensure_ascii=False)


def stanje():
    s = seznam()
    return s or None


def _vidnost_zbirke(ime, vidno):
    z = bpy.data.collections.get(ime)
    if z is None:
        return 0
    objekti = list(z.all_objects)
    for o in objekti:
        o.hide_render = not vidno
    # hide_set v eni zanki čez veliko objektov 8. 11. 2026 ni prijel pri vseh (5 od 30 je ostalo vidnih); ponovi do stanja
    for _ in range(4):
        ostali = [o for o in objekti if o.hide_get() == vidno]
        if not ostali:
            break
        for o in ostali:
            try:
                o.hide_set(not vidno)
            except RuntimeError:      # objekt ni v plasti pogleda
                pass
        bpy.context.view_layer.update()
    return len(objekti)


def uveljavi(m):
    for ime in m.get("ob_vklopu", []):
        _vidnost_zbirke(ime, bool(m["vklop"]))
    for ime in m.get("ob_izklopu", []):
        _vidnost_zbirke(ime, not m["vklop"])


def dodaj(id_, oznaka, ob_vklopu, ob_izklopu, vklop=True):
    s = [m for m in seznam() if m["id"] != id_]
    stari = next((m for m in seznam() if m["id"] == id_), None)
    m = {"id": id_, "oznaka": oznaka, "vklop": stari["vklop"] if stari else vklop,
         "ob_vklopu": list(ob_vklopu), "ob_izklopu": list(ob_izklopu)}
    s.append(m)
    shrani(s)
    uveljavi(m)
    return m


def ukaz(u):
    if u.get("dejanje") != "moznost":
        return None
    s = seznam()
    m = next((x for x in s if x["id"] == u.get("id")), None)
    if m is None:
        return {"ok": False, "sporocilo": "Ni možnosti %r." % u.get("id")}
    m["vklop"] = bool(u.get("vklop"))
    shrani(s)
    uveljavi(m)
    return {"ok": True, "id": m["id"], "vklop": m["vklop"]}
