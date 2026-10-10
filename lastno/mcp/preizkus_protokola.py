# -*- coding: utf-8 -*-
"""Preizkus mostu freecad_mcp.py po protokolu MCP (stdio), kot ga uporablja Claude Code.

    python lastno/mcp/preizkus_protokola.py            (spletni FreeCAD mora teči)

Zažene most kot podproces, pošlje initialize, tools/list, nekaj tools/call (stanje, drevo, slika), resources/list,
resources/read, prompts/list in prompts/get ter preveri obliko odgovorov. Ničesar ne spreminja v dokumentih.
Izhodna koda 0 = vse v redu.
"""
import json
import os
import subprocess
import sys
import threading

TU = os.path.dirname(os.path.abspath(__file__))


def main():
    p = subprocess.Popen([sys.executable, os.path.join(TU, "freecad_mcp.py")], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    threading.Thread(target=lambda: [None for _ in p.stderr], daemon=True).start()
    stevec = [0]
    napake = []

    def poslji(metoda, params=None, obvestilo=False):
        sporocilo = {"jsonrpc": "2.0", "method": metoda}
        if params is not None:
            sporocilo["params"] = params
        if not obvestilo:
            stevec[0] += 1
            sporocilo["id"] = stevec[0]
        p.stdin.write((json.dumps(sporocilo) + "\n").encode("utf-8"))
        p.stdin.flush()
        if obvestilo:
            return None
        while True:
            vrstica = p.stdout.readline()
            if not vrstica:
                raise RuntimeError("most se je končal")
            odgovor = json.loads(vrstica.decode("utf-8"))
            if odgovor.get("id") == stevec[0]:
                return odgovor
            print("  (obvestilo: %s)" % odgovor.get("method"))

    def preveri(pogoj, opis):
        print(("OK   " if pogoj else "NAPAKA ") + opis)
        if not pogoj:
            napake.append(opis)

    r = poslji("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                              "clientInfo": {"name": "preizkus", "version": "1"}})["result"]
    preveri(r.get("serverInfo", {}).get("name") == "freecad", "initialize: serverInfo")
    preveri(len(r.get("instructions", "")) > 200, "initialize: navodila (%d znakov)" % len(r.get("instructions", "")))
    preveri(r.get("capabilities", {}).get("tools", {}).get("listChanged") is True, "initialize: tools.listChanged")
    poslji("notifications/initialized", obvestilo=True)
    orodja = poslji("tools/list")["result"]["tools"]
    imena = [o["name"] for o in orodja]
    preveri("zazeni" in imena and "python" in imena and len(imena) >= 15, "tools/list: %d orodij" % len(imena))
    preveri(all(o.get("inputSchema", {}).get("type") == "object" for o in orodja), "tools/list: sheme")
    dolzina = len(json.dumps(orodja, ensure_ascii=False))
    print("     opisi orodij skupaj %d znakov (~%d žetonov)" % (dolzina, dolzina // 3))
    r = poslji("tools/call", {"name": "stanje", "arguments": {}})["result"]
    preveri(not r.get("isError") and "FreeCAD" in r["content"][0]["text"], "tools/call stanje")
    r = poslji("tools/call", {"name": "drevo", "arguments": {"globina": 2}})["result"]
    preveri(not r.get("isError") and r["content"][0]["type"] == "text", "tools/call drevo")
    r = poslji("tools/call", {"name": "slika", "arguments": {"velikost": 300}})["result"]
    slike = [c for c in r.get("content", []) if c["type"] == "image"]
    preveri(not r.get("isError") and slike and slike[0]["mimeType"].startswith("image/"), "tools/call slika (slika)")
    r = poslji("tools/call", {"name": "ne_obstaja", "arguments": {}})["result"]
    preveri(r.get("isError") is True, "tools/call neznano orodje -> isError")
    viri = poslji("resources/list")["result"]["resources"]
    preveri(any(v["uri"] == "freecad://pravila" for v in viri), "resources/list: %d virov" % len(viri))
    r = poslji("resources/read", {"uri": "freecad://pravila"})["result"]
    preveri("Skice" in r["contents"][0]["text"], "resources/read pravila")
    predloge = poslji("prompts/list")["result"]["prompts"]
    preveri(len(predloge) >= 4, "prompts/list: %d predlog" % len(predloge))
    r = poslji("prompts/get", {"name": "nov_kos", "arguments": {"opis": "kocka 10 mm"}})["result"]
    preveri("kocka 10 mm" in r["messages"][0]["content"]["text"], "prompts/get nov_kos")
    r = poslji("neznana/metoda")
    preveri(r.get("error", {}).get("code") == -32601, "neznana metoda -> -32601")
    p.stdin.close()
    p.wait(timeout=10)
    print("REZULTAT:", "OK" if not napake else "NAPAKE: " + "; ".join(napake))
    return 0 if not napake else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
