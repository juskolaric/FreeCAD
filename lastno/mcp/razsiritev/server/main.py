# -*- coding: utf-8 -*-
"""Zaganjalnik razširitve »Spletni FreeCAD« za namizno aplikacijo Claude (MCPB).

Razširitev ne nosi kopije mostu: požene lastno/mcp/freecad_mcp.py iz repozitorija FreeCAD, zato popravki mostu in
kataloga orodij veljajo brez ponovne namestitve razširitve. Repozitorij išče na znanih mestih (pred in po selitvi v
skupino »3D tisk«) in v okoljski spremenljivki FREECAD_MCP_REPO.
"""
import os
import runpy
import sys

KANDIDATI = [
    os.environ.get("FREECAD_MCP_REPO", ""),
    r"C:\Users\Uporabnik\Desktop\Apps\FreeCAD",
    r"C:\Users\Uporabnik\Desktop\Apps\3D tisk\FreeCAD",
]

for repo in KANDIDATI:
    most = os.path.join(repo, "lastno", "mcp", "freecad_mcp.py") if repo else ""
    if most and os.path.isfile(most):
        sys.argv = [most] + sys.argv[1:]
        runpy.run_path(most, run_name="__main__")
        break
else:
    sys.stderr.write("[freecad-mcp] mostu freecad_mcp.py ni na nobenem znanem mestu: %s\n"
                     % "; ".join(k for k in KANDIDATI if k))
    sys.exit(1)
