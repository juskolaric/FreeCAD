# -*- coding: utf-8 -*-
"""Zunanja oblika, 1. korak (teče v FreeCADCmd, brez okna): iz shranjenega strojnega sestava izvozi grobo mrežo
vseh vidnih kosov. Kliče ga zunanja_oblika.py; parametri so v okoljskih spremenljivkah:
    ZO_RECEPT   pot do recepta (JSON, glej zunanja_oblika.py)
    ZO_IZHOD    pot izhodne datoteke .npz (+ .json z imeni skupin in odtisom)

Poenostavitev že tu: kosi, manjši od `najmanjsi_kos`, odpadejo; ravnim ploskvam se zaprejo luknje, manjše od
`najmanjsa_luknja` (perforacija, izvrtine, reže), da v Blenderju ostane gladka plošča. Vsak trikotnik nosi številko
izvorne ploskve (za izločanje skritih ploskev) in številko skupine (vrhnji kos sestava).
"""
import hashlib
import json
import os
import re
import sys
import time

import numpy as np

import FreeCAD as App
import Part


def _ravna(ploskev):
    """Ravna ploskev, tudi če je po uvozu iz STEP zapisana kot B-zlepek."""
    if ploskev.Surface.TypeId == "Part::GeomPlane":
        return True
    try:
        return ploskev.findPlane() is not None
    except Exception:  # noqa: BLE001
        return False


def _telesa(o, oblika):
    """(ime kosa v podsestavu, telo) za vrhnji kos sestava; ime je prazno, če vrhnji kos ni podsestav. Imena kosov
    omogočajo material po kosu (recept: "Prikazovalnik/Veliki")."""
    izid = []
    cilj = getattr(o, "LinkedObject", None) or o
    otroci = [c for c in getattr(cilj, "Group", []) if c.TypeId not in ("App::Origin", "Assembly::JointGroup")]
    if otroci and o.TypeId == "App::Link":
        m = o.Placement.toMatrix()
        try:
            for c in otroci:
                if not getattr(c, "Visibility", True):
                    continue
                s = Part.getShape(c)
                if s.isNull():
                    continue
                podime = re.sub(r"-\d+$", "", c.Label)
                izid += [(podime, t) for t in s.transformed(m).Solids]
        except Exception:  # noqa: BLE001
            izid = []
    if not izid or len(izid) != len(oblika.Solids):     # neznana zgradba: celota brez imen kosov
        return [("", t) for t in oblika.Solids]
    return izid


def main():
    with open(os.environ["ZO_RECEPT"], encoding="utf-8") as f:
        recept = json.load(f)
    izhod = os.environ["ZO_IZHOD"]
    mapa = os.path.dirname(os.path.dirname(os.path.abspath(os.environ["ZO_RECEPT"])))
    pot = os.path.join(mapa, recept["sestav"])
    izpusti = set(recept.get("izpusti", []))
    najm_kos = float(recept.get("najmanjsi_kos", 40))
    najm_luknja = float(recept.get("najmanjsa_luknja", 60))
    odstop = float(recept.get("odstop", 0.3))
    najm_ploskev = float(recept.get("najmanjsa_ploskev", 12))

    t0 = time.time()
    doc = App.openDocument(pot)
    print("odprto v %.1f s: %s" % (time.time() - t0, pot), flush=True)
    sestav = next((o for o in doc.Objects if o.TypeId == "Assembly::AssemblyObject"), None)
    vrhnji = list(sestav.Group) if sestav else list(doc.RootObjects)

    tocke, trikotniki, ploskev_tri, skupina_tri, telo_tri = [], [], [], [], []
    st_teles = 0
    kosi, kos_tri, nalepka_tri = [], [], []
    nalepke = set(recept.get("nalepke", []))
    nalepka_debelina = float(recept.get("nalepka_debelina", 1.5))
    skupine, st_tock, st_ploskev, zaprtih = [], 0, 0, 0
    for o in vrhnji:
        if o.TypeId in ("App::Origin", "Assembly::JointGroup") or not getattr(o, "Visibility", True):
            continue
        ime = re.sub(r"-\d+$", "", o.Label)
        if ime in izpusti:
            continue
        try:
            oblika = Part.getShape(o)
        except Exception as e:  # noqa: BLE001
            print("! %s: %s" % (o.Label, e), flush=True)
            continue
        if oblika.isNull():
            continue
        if ime not in skupine:
            skupine.append(ime)
        sid = skupine.index(ime)
        for podime, telo in _telesa(o, oblika):
            if telo.BoundBox.DiagonalLength < najm_kos:
                continue
            st_teles += 1
            kos = ime + "/" + podime if podime else ime
            b = telo.BoundBox
            nalepka = kos in nalepke and min(b.XLength, b.YLength, b.ZLength) <= nalepka_debelina
            if nalepka:                 # tanko telo na pločevini = nalepka: svoj objekt, ne zakriva pločevine
                kos += "/nalepka"
                if "Nalepke" not in skupine:
                    skupine.append("Nalepke")
            gid = skupine.index("Nalepke") if nalepka else sid
            if kos not in kosi:
                kosi.append(kos)
            kid = kosi.index(kos)
            for ploskev in telo.Faces:
                p = ploskev
                obrni = ploskev.Orientation == "Reversed"
                try:
                    if ploskev.BoundBox.DiagonalLength < najm_ploskev:
                        continue
                    if len(ploskev.Wires) > 1 and _ravna(ploskev):
                        zunanja = ploskev.OuterWire
                        velike = [w for w in ploskev.Wires
                                  if not w.isSame(zunanja) and w.BoundBox.DiagonalLength >= najm_luknja]
                        if len(velike) + 1 < len(ploskev.Wires):
                            p = Part.makeFace([zunanja] + velike, "Part::FaceMakerBullseye")
                            obrni = False
                            zaprtih += 1
                    v, t = p.tessellate(odstop)
                except Exception:  # noqa: BLE001
                    try:
                        v, t = ploskev.tessellate(odstop)
                    except Exception:  # noqa: BLE001
                        continue
                if not t:
                    continue
                tocke.extend((a.x, a.y, a.z) for a in v)
                for a, b, c in t:
                    trikotniki.append((a + st_tock, c + st_tock, b + st_tock) if obrni else (a + st_tock, b + st_tock, c + st_tock))
                ploskev_tri.extend([st_ploskev] * len(t))
                skupina_tri.extend([gid] * len(t))
                nalepka_tri.extend([nalepka] * len(t))
                telo_tri.extend([st_teles] * len(t))
                kos_tri.extend([kid] * len(t))
                st_tock += len(v)
                st_ploskev += 1
        print("%-28s teles %3d, skupaj trikotnikov %d" % (ime, len(oblika.Solids), len(trikotniki)), flush=True)

    V = np.asarray(tocke, dtype=np.float32)
    T = np.asarray(trikotniki, dtype=np.int32)
    odtis = hashlib.sha1(np.round(V, 1).tobytes() + T.tobytes()).hexdigest()[:16]
    np.savez_compressed(izhod, tocke=V, trikotniki=T, ploskev=np.asarray(ploskev_tri, dtype=np.int32),
                        skupina=np.asarray(skupina_tri, dtype=np.int16), telo=np.asarray(telo_tri, dtype=np.int32),
                        kos=np.asarray(kos_tri, dtype=np.int32), nalepka=np.asarray(nalepka_tri, dtype=bool))
    okvir = [[float(x) for x in V.min(axis=0)], [float(x) for x in V.max(axis=0)]] if len(V) else []
    with open(os.path.splitext(izhod)[0] + ".json", "w", encoding="utf-8") as f:
        json.dump({"skupine": skupine, "kosi": kosi, "odtis": odtis, "sestav": pot, "sestav_mtime": os.path.getmtime(pot),
                   "trikotnikov": int(len(T)), "ploskev": st_ploskev, "zaprtih_ploskev": zaprtih, "okvir": okvir},
                  f, ensure_ascii=False, indent=1)
    print("KONEC izvoza: %d trikotnikov, %d ploskev, odtis %s, %.1f s" % (len(T), st_ploskev, odtis, time.time() - t0), flush=True)


try:
    main()
except Exception:  # noqa: BLE001
    import traceback
    traceback.print_exc()
    sys.stdout.flush()
    os._exit(1)
os._exit(0)
