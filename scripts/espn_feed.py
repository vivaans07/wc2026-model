#!/usr/bin/env python3
"""
espn_feed.py — pull LINEUPS + NEWS for a match from ESPN's public API (no key).

ESPN exposes a free, unauthenticated JSON API. The match "summary" endpoint
carries each team's roster with STARTER flags (the actual XI, posted ~1 hour
before kickoff), news headlines, and bookmaker odds.

  scoreboard : https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard
  summary    : https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/summary?event=ID

Usage:
  python espn_feed.py --home England --away Ghana      # finds event, prints XI + news
  python espn_feed.py --scoreboard                     # list today's events + ids

NOTE: ESPN gives the lineup/news. Turning "player X is out" into a probability
shift still needs PLAYER-VALUE ratings (Transfermarkt-style) which this project
lacks — so absences are surfaced as CAVEATS for manual shading, not auto-ingested.
"""
import sys, json, argparse, urllib.request

BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world"
ALIAS = {"DR Congo": "Congo DR", "South Korea": "Korea Republic", "Turkey": "Türkiye",
         "Czech Republic": "Czechia", "Ivory Coast": "Côte d'Ivoire", "United States": "USA"}

def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research)"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)

def scoreboard(date=None):
    url = f"{BASE}/scoreboard" + (f"?dates={date}" if date else "")
    return _get(url).get("events", [])

def _all_events():
    """default board + the next 3 dated boards (so upcoming fixtures are found)."""
    import datetime
    evs = {e["id"]: e for e in scoreboard()}
    for d in range(0, 3):
        day = (datetime.date(2026, 6, 23) + datetime.timedelta(days=d)).strftime("%Y%m%d")
        for e in scoreboard(day): evs[e["id"]] = e
    return list(evs.values())

def find_event(home, away):
    names = {home.lower(), away.lower(), ALIAS.get(home, "").lower(), ALIAS.get(away, "").lower()}
    for e in _all_events():
        nm = e["name"].lower()
        if sum(1 for n in names if n and n in nm) >= 2:
            return e["id"], e["name"], e["competitions"][0]["status"]["type"]["state"]
    return None, None, None

def match_feed(event_id):
    d = _get(f"{BASE}/summary?event={event_id}")
    out = {"lineups": {}, "news": [], "odds": None}
    for r in d.get("rosters", []):
        team = r.get("team", {}).get("displayName", "?")
        xi, bench = [], []
        for p in r.get("roster", []):
            nm = p.get("athlete", {}).get("displayName", "?")
            pos = p.get("position", {}).get("abbreviation", "")
            (xi if p.get("starter") else bench).append(f"{nm} ({pos})")
        out["lineups"][team] = {"starting_XI": xi, "bench": bench}
    out["news"] = [a.get("headline", "") for a in d.get("news", {}).get("articles", [])][:6]
    od = d.get("odds") or d.get("pickcenter")
    if od:
        o = od[0] if isinstance(od, list) else od
        out["odds"] = o.get("details") or o.get("summary")
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--home"); ap.add_argument("--away")
    ap.add_argument("--scoreboard", action="store_true")
    a = ap.parse_args()
    if a.scoreboard or not (a.home and a.away):
        print("World Cup events on ESPN right now:")
        for e in scoreboard():
            c = e["competitions"][0]
            print(f"  id={e['id']}  {e['date'][:16]}  {e['name']}  [{c['status']['type']['state']}]")
        return
    eid, name, state = find_event(a.home, a.away)
    if not eid:
        print(f"No ESPN event found for {a.home} vs {a.away} (may not be listed yet).")
        return
    print(f"\n{name}  (event {eid}, status: {state})")
    feed = match_feed(eid)
    if not any(v["starting_XI"] for v in feed["lineups"].values()):
        print("  Lineups not posted yet (they appear ~1 hour before kickoff).")
    for team, l in feed["lineups"].items():
        print(f"\n  {team} XI:")
        for p in l["starting_XI"]: print(f"     {p}")
    if feed["news"]:
        print("\n  News headlines (scan for injuries/suspensions):")
        for h in feed["news"]: print(f"     - {h}")
    if feed["odds"]: print(f"\n  ESPN odds line: {feed['odds']}")

if __name__ == "__main__":
    main()
