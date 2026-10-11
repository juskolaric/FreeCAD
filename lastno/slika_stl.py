# -*- coding: utf-8 -*-
"""Preprost izris STL (ortografska projekcija, ploščato senčenje) brez FreeCAD-a: python slika_stl.py vhod.stl izhod.png smer"""
import struct, sys, numpy as np
from PIL import Image, ImageDraw

def beri_stl(pot):
    with open(pot, "rb") as f:
        podatki = f.read()
    if podatki[:5] == b"solid" and b"facet" in podatki[:300]:
        tocke = []
        for vrstica in podatki.decode("ascii", "ignore").splitlines():
            v = vrstica.split()
            if v and v[0] == "vertex":
                tocke.append([float(x) for x in v[1:4]])
        return np.array(tocke).reshape(-1, 3, 3)
    n = struct.unpack("<I", podatki[80:84])[0]
    a = np.frombuffer(podatki[84:84 + n * 50], dtype=np.dtype([("n", "<3f4"), ("v", "<9f4"), ("a", "<u2")]))
    return a["v"].reshape(-1, 3, 3).astype(float)

def izrisi(tri, pot_png, pogled, velikost=900):
    # pogled: smer gledanja (od kod gleda kamera) in "gor" vektor
    smer = np.array(pogled[0], float); smer /= np.linalg.norm(smer)
    gor = np.array(pogled[1], float)
    desno = np.cross(gor, smer); desno /= np.linalg.norm(desno)
    gor = np.cross(smer, desno)
    R = np.stack([desno, gor, smer])              # vrstice: x zaslona, y zaslona, globina proti kameri
    p = tri @ R.T
    n = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    dol = np.linalg.norm(n, axis=1); ok = dol > 1e-9
    p, n = p[ok], n[ok] / dol[ok][:, None]
    vidni = n[:, 2] > 0
    p, n = p[vidni], n[vidni]
    luc = np.array([0.35, 0.55, 0.76]); luc /= np.linalg.norm(luc)
    svet = np.clip(n @ luc, 0, 1) * 0.65 + 0.35
    mn, mx = p[:, :, :2].reshape(-1, 2).min(0), p[:, :, :2].reshape(-1, 2).max(0)
    merilo = (velikost * 0.86) / max(mx - mn)
    rob = (velikost - (mx - mn) * merilo) / 2
    vrstni_red = np.argsort(p[:, :, 2].mean(1))
    img = Image.new("RGB", (velikost, velikost), (236, 239, 243))
    d = ImageDraw.Draw(img)
    osnova = np.array([242, 204, 51])
    for i in vrstni_red:
        xy = [(float((q[0] - mn[0]) * merilo + rob[0]), float(velikost - ((q[1] - mn[1]) * merilo + rob[1]))) for q in p[i]]
        b = tuple(int(c) for c in osnova * svet[i])
        d.polygon(xy, fill=b, outline=b)
    img.save(pot_png)

if __name__ == "__main__":
    tri = beri_stl(sys.argv[1])
    pogledi = {"hrbet": ((0, -1, 0), (0, 0, 1)), "hrbet-izo": ((-0.6, -1, 0.45), (0, 0, 1)), "izo": ((0.7, 1, 0.5), (0, 0, 1))}
    izrisi(tri, sys.argv[2], pogledi[sys.argv[3]])
    print("ok", len(tri), "trikotnikov")
