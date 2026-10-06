#!/usr/bin/env python3
"""
espn_stats.py — pull per-match TEAM STATS (possession, shots, passes, fouls,
corners, etc.) for every played 2026 World Cup game from ESPN's free API, then
aggregate a per-team profile (average possession & co.).

Outputs:
  outputs/espn_match_stats.csv  — one row per team per game (with possession etc.)
  outputs/espn_team_stats.csv   — per-team averages across all their games

No API key needed. Responses cached to config/_espn_cache to be polite.
"""
import sys, os, csv, json, time, urllib.request, datetime
from collections import defaultdict

BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world"
CACHE = os.path.join(os.path.dirname(__file__), "..", "config", "_espn_cache")
OUT = os.path.join(os.path.dirname(__file__), "..", "outputs")
os.makedirs(CACHE, exist_ok=True)
KEYSTATS = ["possessionPct", "totalShots", "shotsOnTarget", "wonCorners",
            "foulsCommitted", "offsides", "totalPasses", "accuratePasses",
            "yellowCards", "redCards", "saves", "totalTackles", "interceptions"]

def _get(url):
    ck = os.path.join(CACHE, str(abs(hash(url))) + ".json")
    if os.path.exists(ck) and time.time() - os.path.getmtime(ck) < 1800:
        return json.load(open(ck))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research)"})
    with urllib.request.urlopen(req, timeout=25) as r:
        d = json.load(r)
    json.dump(d, open(ck, "w")); return d

def events_for_date(yyyymmdd):
    try:
        return _get(f"{BASE}/scoreboard?dates={yyyymmdd}").get("events", [])
    except Exception:
        return []

def match_stats(event_id):
    d = _get(f"{BASE}/summary?event={event_id}")
    rows = {}
    for t in d.get("boxscore", {}).get("teams", []):
        nm = t.get("team", {}).get("displayName", "?")
        st = {s.get("name"): s.get("displayValue") for s in t.get("statistics", [])}
        rows[nm] = st
    return rows

def main():
    # iterate the group-stage date range
    d0 = datetime.date(2026, 6, 11); d1 = datetime.date(2026, 6, 23)
    match_rows = []
    seen = set()
    day = d0
    while day <= d1:
        for e in events_for_date(day.strftime("%Y%m%d")):
            if e["id"] in seen: continue
            comp = e["competitions"][0]
            if comp["status"]["type"]["state"] != "post":  # only finished games
                continue
            seen.add(e["id"])
            teams = {c["homeAway"]: (c["team"]["displayName"], c.get("score")) for c in comp["competitors"]}
            stats = match_stats(e["id"])
            for ha in ("home", "away"):
                nm, sc = teams[ha]
                opp = teams["away" if ha == "home" else "home"][0]
                st = stats.get(nm, {})
                row = {"date": e["date"][:10], "team": nm, "opponent": opp,
                       "home_away": ha, "goals": sc}
                for k in KEYSTATS: row[k] = st.get(k, "")
                match_rows.append(row)
        day += datetime.timedelta(days=1)

    if not match_rows:
        print("No finished ESPN games found."); return
    with open(os.path.join(OUT, "espn_match_stats.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(match_rows[0].keys())); w.writeheader(); w.writerows(match_rows)

    # aggregate per team
    agg = defaultdict(lambda: defaultdict(list))
    for r in match_rows:
        for k in KEYSTATS:
            v = r[k]
            if v not in ("", None):
                try: agg[r["team"]][k].append(float(str(v).replace("%", "")))
                except ValueError: pass
        agg[r["team"]]["_games"].append(1)
    team_rows = []
    for team, d in sorted(agg.items()):
        row = {"team": team, "games": len(d["_games"])}
        for k in KEYSTATS:
            vals = d[k]
            row["avg_" + k] = round(sum(vals) / len(vals), 1) if vals else ""
        team_rows.append(row)
    team_rows.sort(key=lambda r: -(r["avg_possessionPct"] or 0))
    with open(os.path.join(OUT, "espn_team_stats.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(team_rows[0].keys())); w.writeheader(); w.writerows(team_rows)

    print(f"Pulled {len(match_rows)//2} games | {len(team_rows)} teams")
    print(f"  -> outputs/espn_match_stats.csv (per game) + espn_team_stats.csv (per team)\n")
    print(f"{'team':<22}{'GP':>3}{'poss%':>7}{'shots':>7}{'SOT':>6}{'corners':>8}{'fouls':>7}")
    for r in team_rows:
        print(f"  {r['team']:<20}{r['games']:>3}{r['avg_possessionPct']:>7}{r['avg_totalShots']:>7}"
              f"{r['avg_shotsOnTarget']:>6}{r['avg_wonCorners']:>8}{r['avg_foulsCommitted']:>7}")

if __name__ == "__main__":
    main()
