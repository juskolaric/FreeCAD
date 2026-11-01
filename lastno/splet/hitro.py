# -*- coding: utf-8 -*-
"""Hitra sprememba modela, zgrajenega s skripto projekta, v enem klicu (brez okna, brez novega procesa FreeCAD-a).

    python lastno/splet/hitro.py <skripta.py> <dokument> [IME=vrednost ...]

1. V skripti prepiše številske konstante na ravni modula (`IME = 2.1  # opis` -> `IME = 2.3  # opis`; komentar ostane),
   skripta ostane vir resnice.
2. V tekočem spletnem FreeCAD-u (3020, prek izvedi.py) skripto naloži znova in pokliče `zgradi(doc)` v dokumentu
   <dokument> (ime ali oznaka; aktivni dokument v brskalniku se ne zamenja). Brskalnik dobi spremenjene objekte sam.
3. Izpiše čas gradnje in okvirje spremenjenih kosov; ne shranjuje, ne dela STL, ne riše slik.

Skripta mora imeti funkcijo `zgradi(doc)` (npr. Oblak/3D modeliranje/Bliskavična noga/Skripte/podaljsek.py).
"""
import os
import re
import subprocess
import sys

TU = os.path.dirname(os.path.abspath(__file__))


def prepisi(pot, pari):
    with open(pot, encoding="utf-8") as f:
        besedilo = f.read()
    for ime, vrednost in pari:
        float(vrednost)                                    # samo številke
        vzorec = re.compile(r"^(%s\s*=\s*)(-?[0-9.]+)(?=[ 	]*(?:#|$))" % re.escape(ime), re.M)   # samo čista številka
        besedilo, n = vzorec.subn(lambda m: m.group(1) + vrednost, besedilo, count=1)
        if not n:
            raise SystemExit("konstante %s (čista številka) ni v %s" % (ime, pot))
    tmp = pot + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(besedilo)
    os.replace(tmp, pot)


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    skripta, dokument = os.path.abspath(argv[0]), argv[1]
    pari = [a.split("=", 1) for a in argv[2:]]
    if pari:
        prepisi(skripta, pari)
    koda = '''
import importlib.util, time
t = time.perf_counter()
d = App.getDocument(%r) if %r in App.listDocuments() else next(x for x in App.listDocuments().values() if x.Label == %r)
spec = importlib.util.spec_from_file_location("hitro_skripta", %r)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
vrstice = m.zgradi(d)
rezultat = {"dokument": d.Label, "cas_s": round(time.perf_counter() - t, 2), "napake": [o.Name for o in d.Objects if "Invalid" in o.State]}
''' % (dokument, dokument, dokument, skripta)
    r = subprocess.run([sys.executable, os.path.join(TU, "izvedi.py"), "-"], input=koda.encode("utf-8"))
    return r.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
