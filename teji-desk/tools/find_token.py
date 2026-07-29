#!/usr/bin/env python3
"""Find the SmartAPI `symboltoken` for a tradingsymbol.

Angel One publishes a full scrip master as JSON. This downloads it and greps for
your symbol so you can fill `instrument.token` / `tradingsymbol` in config.yaml.

    python tools/find_token.py BANKNIFTY
    python tools/find_token.py "NIFTY 25 JUL FUT"

Needs outbound internet. Run it on the machine where the trader will run.
"""
import json
import sys
import urllib.request

URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: python tools/find_token.py <search text>")
    needle = " ".join(sys.argv[1:]).upper()
    print(f"Downloading scrip master and searching for: {needle}\n")
    with urllib.request.urlopen(URL, timeout=60) as r:
        data = json.load(r)

    hits = [row for row in data if needle in str(row.get("symbol", "")).upper()
            or needle in str(row.get("name", "")).upper()]
    hits = hits[:40]
    if not hits:
        print("No matches. Try a shorter query (e.g. just BANKNIFTY).")
        return
    print(f"{'token':>10}  {'exch':<6} {'lot':>5}  symbol")
    print("-" * 60)
    for row in hits:
        print(f"{row.get('token',''):>10}  {row.get('exch_seg',''):<6} "
              f"{row.get('lotsize',''):>5}  {row.get('symbol','')}")
    print("\nUse `token` + `symbol` (as tradingsymbol) + the right exchange_type:")
    print("  NSE_CM=1  NSE_FO=2  BSE_CM=3  NSE_CD=13  MCX_FO=5")


if __name__ == "__main__":
    main()
