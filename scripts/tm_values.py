#!/usr/bin/env python3
"""
tm_values.py — join Transfermarkt market values to the 2026 WC squads, and turn a
list of ABSENT players into a model rating adjustment (so ESPN's absence flags can
be QUANTIFIED, not just noted).

Data: salimt/football-datasets (Transfermarkt) — player_profiles + latest market value.
Join: wc2026_squads (name+DOB+country) -> profiles (name[+DOB]) -> player_id -> value.

Outputs outputs/wc2026_squad_values.csv and a per-team value summary. Provides
absence_impact(country, [names]) used to shade the model when a key player is out.

HEURISTIC (documented, not fit): a player's importance ~ his share of squad market
value; losing him reduces the relevant rating (attack for FW/MF, defence for DF/GK)
by K_IMPACT * value_share. Calibrated so losing a ~20%-of-squad superstar ≈ -0.16
in rating (~0.18 xG). Can't be data-fit without historical absence/outcome data.
"""
import sys, os, csv, re, unicodedata, html as htmlmod
sys.path.insert(0, os.path.dirname(__file__))
import wc_lib as L

SCR = os.path.join(L.PROJ, "scraped")
K_IMPACT = 0.80

def norm(s):
    s = "".join(c for c in unicodedata.normalize("NFKD", htmlmod.unescape(s)) if not unicodedata.combining(c))
    return re.sub(r"[^a-z ]", "", s.lower()).strip()

# market values
mv = {}
for r in csv.DictReader(open(os.path.join(SCR, "tm_market_value.csv"))):
    try: mv[r["player_id"]] = float(r["value"])
    except ValueError: pass

# profiles -> index by normalized name (and name_in_home_country)
by_name = {}
for r in csv.DictReader(open(os.path.join(SCR, "tm_profiles.csv"))):
    for nm in {norm(r.get("player_name", "")), norm(r.get("name_in_home_country", ""))}:
        if nm: by_name.setdefault(nm, []).append(r)

def pos_cat(p):
    p = (p or "").lower()
    if "keeper" in p or p == "gk": return "GK"
    if "back" in p or "defend" in p or "centre-back" in p: return "DEF"
    if "midfield" in p: return "MID"
    if "wing" in p or "forward" in p or "striker" in p or "attack" in p: return "ATT"
    return "MID"

def main():
    squads = list(csv.DictReader(open(os.path.join(L.OUT, "wc2026_squads.csv"))))
    rows = []; matched = 0
    for s in squads:
        cands = by_name.get(norm(s["player_name"]), [])
        pick = None
        if cands:
            # confirm by birth date if available, else prefer citizenship == country
            exact = [c for c in cands if c.get("date_of_birth", "")[:10] == s.get("birth_date", "")] if s.get("birth_date") else []
            if exact: pick = exact[0]
            else:
                cc = [c for c in cands if s["country_name"].lower() in (c.get("citizenship", "") or "").lower()]
                pick = (cc or cands)[0]
        val = mv.get(pick["player_id"]) if pick else None
        if pick and val is not None: matched += 1
        rows.append({"country_name": s["country_name"], "player_name": s["player_name"],
                     "position": s.get("position", ""), "tm_player_id": pick["player_id"] if pick else "",
                     "main_position": pick.get("main_position", "") if pick else "",
                     "market_value_eur": int(val) if val else "",
                     "pos_cat": pos_cat(pick.get("main_position")) if pick else ""})
    # per-team totals + value share
    from collections import defaultdict
    tv = defaultdict(float)
    for r in rows:
        if r["market_value_eur"] != "": tv[r["country_name"]] += r["market_value_eur"]
    for r in rows:
        v = r["market_value_eur"]
        r["value_share"] = round(v / tv[r["country_name"]], 4) if (v != "" and tv[r["country_name"]]) else ""
    with open(os.path.join(L.OUT, "wc2026_squad_values.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

    print(f"Squad players: {len(rows)} | matched to a market value: {matched} ({matched/len(rows)*100:.0f}%)")
    print("\nSquad total market value (€m) — top 12:")
    for t, v in sorted(tv.items(), key=lambda x: -x[1])[:12]:
        top = max((r for r in rows if r["country_name"] == t and r["market_value_eur"] != ""),
                  key=lambda r: r["market_value_eur"], default=None)
        tn = f"{top['player_name']} €{top['market_value_eur']/1e6:.0f}m" if top else "?"
        print(f"  {t:<16} €{v/1e6:6.0f}m   most valuable: {tn}")
    return rows, tv

# ---- absence impact (callable by the prediction tools) ----
_rows = None; _tv = None
def _load():
    global _rows, _tv
    if _rows is None:
        _rows = list(csv.DictReader(open(os.path.join(L.OUT, "wc2026_squad_values.csv"))))
        from collections import defaultdict
        _tv = defaultdict(float)
        for r in _rows:
            if r["market_value_eur"] not in ("", None): _tv[r["country_name"]] += float(r["market_value_eur"])
    return _rows, _tv

def absence_impact(country, absent_names):
    """Return (datt, ddef) rating deltas (<=0) to apply to a team for absent players."""
    rows, tv = _load()
    nn = {norm(a) for a in absent_names}
    datt = ddef = 0.0; hit = []
    for r in rows:
        if r["country_name"] != country or r["market_value_eur"] in ("", None): continue
        if norm(r["player_name"]) in nn:
            share = float(r["value_share"]) if r["value_share"] not in ("", None) else 0.0
            d = K_IMPACT * share
            if r["pos_cat"] in ("GK", "DEF"): ddef -= d
            else: datt -= d
            hit.append((r["player_name"], share))
    return round(datt, 3), round(ddef, 3), hit

if __name__ == "__main__":
    main()
