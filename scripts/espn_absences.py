#!/usr/bin/env python3
"""
espn_absences.py — free injury/absence DETECTOR from ESPN (no key).

For each team it collects the starting XI from every game, then flags players who
STARTED the previous game but are NOT starting the latest one (= injured /
suspended / rested). Also scans ESPN news headlines for injury keywords. This is
the free stand-in for an explicit injury feed (API-Football free has no 2026 data).

Honest label: a dropped starter could be injury, suspension OR rotation — the tool
flags the change; you (or I) confirm the reason from the news line.

Usage:
  python espn_absences.py                 # all teams: changes between their last 2 XIs
  python espn_absences.py --team England   # focus one team + news scan
"""
import sys, os, json, time, argparse, urllib.request, datetime
from collections import defaultdict

BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world"
CACHE = os.path.join(os.path.dirname(__file__), "..", "config", "_espn_cache")
os.makedirs(CACHE, exist_ok=True)
INJURY_KW = ("injur", "out", "doubt", "fitness", "knock", "strain", "suspend",
             "ban", "ruled out", "miss", "hamstring", "ankle", "groin")

def _get(url):
    ck = os.path.join(CACHE, str(abs(hash(url))) + ".json")
    if os.path.exists(ck) and time.time() - os.path.getmtime(ck) < 1800:
        return json.load(open(ck))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research)"})
    with urllib.request.urlopen(req, timeout=25) as r:
        d = json.load(r)
    json.dump(d, open(ck, "w")); return d

def collect():
    """team -> sorted list of (date, event_id, set(starting XI names))."""
    d0, d1 = datetime.date(2026, 6, 11), datetime.date(2026, 6, 26)
    team_games = defaultdict(list); day = d0; seen = set()
    while day <= d1:
        try: evs = _get(f"{BASE}/scoreboard?dates={day.strftime('%Y%m%d')}").get("events", [])
        except Exception: evs = []
        for e in evs:
            if e["id"] in seen: continue
            comp = e["competitions"][0]
            if comp["status"]["type"]["state"] != "post": continue
            seen.add(e["id"])
            d = _get(f"{BASE}/summary?event={e['id']}")
            for r in d.get("rosters", []):
                team = r.get("team", {}).get("displayName", "?")
                xi = {p.get("athlete", {}).get("displayName", "?")
                      for p in r.get("roster", []) if p.get("starter")}
                if xi: team_games[team].append((e["date"][:10], e["id"], xi))
        day += datetime.timedelta(days=1)
    for t in team_games: team_games[t].sort()
    return team_games

def news_injuries(team):
    """scan latest match news headlines mentioning this team + injury keywords."""
    hits = []
    try:
        for e in _get(f"{BASE}/scoreboard").get("events", []):
            if team.lower() in e["name"].lower():
                d = _get(f"{BASE}/summary?event={e['id']}")
                for a in d.get("news", {}).get("articles", []):
                    h = a.get("headline", "")
                    if any(k in h.lower() for k in INJURY_KW): hits.append(h)
    except Exception: pass
    return hits[:5]

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--team"); a = ap.parse_args()
    tg = collect()
    teams = [a.team] if a.team else sorted(tg)
    for team in teams:
        games = tg.get(team, [])
        if len(games) < 2:
            if a.team: print(f"{team}: <2 games with posted XIs yet.");
            continue
        (pd, _, prev), (ld, _, last) = games[-2], games[-1]
        dropped = sorted(prev - last); added = sorted(last - prev)
        if dropped or added or a.team:
            print(f"\n{team}  (XI change {pd} -> {ld}):")
            print(f"   OUT of XI (injury/susp/rotation?): {', '.join(dropped) if dropped else 'none'}")
            print(f"   NEW in XI:                         {', '.join(added) if added else 'none'}")
            if a.team:
                ni = news_injuries(team)
                print("   injury-related news:", "; ".join(ni) if ni else "none found")
    if not a.team:
        print("\n(Use --team NAME for a focused view with news scan. Flags include rotation,")
        print(" not only injuries — confirm the reason from the news line.)")

if __name__ == "__main__":
    main()
