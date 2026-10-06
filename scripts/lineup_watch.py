#!/usr/bin/env python3
"""Poll ESPN for the England–Ghana starting XI; exit as soon as it's posted,
reporting whether Harry Kane starts. Runs in the background until the lineup
drops (~1h before kickoff) or it times out."""
import urllib.request, json, time, sys
BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world"
def get(u): return json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=25))

eid = None
for d in ("20260623", "20260624"):
    try:
        for e in get(f"{BASE}/scoreboard?dates={d}").get("events", []):
            nm = e["name"].lower()
            if "england" in nm and "ghana" in nm:
                eid = e["id"]; break
    except Exception:
        pass
    if eid: break
if not eid:
    print("WATCH: England–Ghana event not found"); sys.exit(1)

print(f"WATCH: monitoring event {eid} for England XI (polling every 5 min)...", flush=True)
for i in range(72):                      # up to ~6 hours
    try:
        d = get(f"{BASE}/summary?event={eid}")
        state = d.get("header", {}).get("competitions", [{}])[0].get("status", {}).get("type", {}).get("state", "")
        for r in d.get("rosters", []):
            if "england" in r.get("team", {}).get("displayName", "").lower():
                xi = [p["athlete"]["displayName"] for p in r.get("roster", []) if p.get("starter")]
                if xi:
                    kane = any("kane" in n.lower() for n in xi)
                    print("=== ENGLAND XI POSTED ===")
                    print("XI:", ", ".join(xi))
                    print("HARRY_KANE_STARTS:", "YES" if kane else "NO")
                    sys.exit(0)
    except Exception:
        pass
    time.sleep(300)
print("WATCH: timed out before lineup posted"); sys.exit(2)
