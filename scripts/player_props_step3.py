#!/usr/bin/env python3
"""
PLAYER PROPS — Step 3b: SHOTS / SHOTS-ON-TARGET from real club data (API-Football).

Constraints discovered on the FREE tier:
  * /players search REQUIRES a league (or team) id alongside the name + season.
  * 10 requests/minute, 100/day, seasons 2022-2024 only.
So a fully-automated all-players pipeline isn't feasible free; we fetch the marquee
big-5-league attackers (where shots props are actually offered) using a club->league
map, throttled, caching only SUCCESSFUL responses.

shots/90 & SOT/90 from the player's most recent covered club season -> scaled by
expected minutes -> Poisson over/under lines. Scales up trivially on a paid tier
(no rate limit, current season, all leagues).
"""
import sys, os, csv, json, math, time, urllib.request, urllib.parse, hashlib
sys.path.insert(0, os.path.dirname(__file__))
import wc_lib as L

CFG = os.path.join(L.PROJ, "config"); CACHE = os.path.join(CFG, "_apifootball_cache")
os.makedirs(CACHE, exist_ok=True)
KEY = next(l.split("=", 1)[1].strip() for l in open(os.path.join(CFG, "secrets.env")) if l.startswith("APIFOOTBALL_API_KEY"))
LEAGUE = {"EPL": 39, "LaLiga": 140, "SerieA": 135, "Bundesliga": 78, "Ligue1": 61}

# marquee June-23 attackers with their club's league (shots props are offered on these)
TARGETS = [
    ("Harry Kane", "England", 78), ("Bukayo Saka", "England", 39),
    ("Anthony Gordon", "England", 39), ("Jude Bellingham", "England", 140),
    ("Bruno Fernandes", "Portugal", 39), ("Goncalo Ramos", "Portugal", 61),
    ("Mario Pasalic", "Croatia", 135),
]

def af_get(params):
    url = "https://v3.football.api-sports.io/players?" + urllib.parse.urlencode(params)
    ck = os.path.join(CACHE, hashlib.md5(url.encode()).hexdigest() + ".json")
    if os.path.exists(ck):
        return json.load(open(ck))
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers={"x-apisports-key": KEY})
            with urllib.request.urlopen(req, timeout=25) as r:
                d = json.load(r)
        except Exception as e:
            return {"error": str(e)}
        if d.get("errors") and "rateLimit" in str(d["errors"]):
            time.sleep(62); continue            # wait out the per-minute limit, retry once
        if not d.get("errors") and "response" in d:
            json.dump(d, open(ck, "w"))          # cache ONLY clean responses
        return d
    return d

def rate_for(name, league, season=2024):
    for ssn in (season, 2023, 2022):
        d = af_get({"search": name.split()[-1], "league": league, "season": ssn})
        for p in d.get("response", []):
            if name.split()[-1].lower() in p["player"]["name"].lower():
                st = p["statistics"][0]
                mins = st.get("games", {}).get("minutes") or 0
                sh = st.get("shots", {}).get("total"); on = st.get("shots", {}).get("on")
                if mins >= 450 and sh:
                    return sh / (mins / 90), (on or 0) / (mins / 90), ssn, st.get("team", {}).get("name", ""), mins
        time.sleep(7)                            # throttle: stay under 10/min
    return None

def main():
    # expected minutes from the Step 2 props file
    em = {}
    try:
        for r in csv.DictReader(open(os.path.join(L.OUT, "player_props_2026-06-23.csv"))):
            em[r["player"]] = float(r["exp_min"])
    except FileNotFoundError:
        pass
    def over(lam, line): return 1 - sum(math.exp(-lam) * lam**k / math.factorial(k) for k in range(int(line) + 1))
    out = []
    print("Fetching real club shot rates (throttled ~7s/call, free-tier safe)...\n")
    print(f"  {'player':<18}{'team':<10}{'sh/90':>6}{'sot/90':>7}{'exp_sh':>7}{'o2.5sh':>8}{'o0.5sot':>9}{'o1.5sot':>9}")
    for name, team, lg in TARGETS:
        r = rate_for(name, lg)
        if not r:
            print(f"  {name:<18}{team:<10}  no data"); continue
        sh90, sot90, ssn, club, mins = r
        mn = em.get(name, 82); esh = sh90 * mn / 90; esot = sot90 * mn / 90
        row = {"player": name, "team": team, "src_season": ssn, "src_club": club,
               "shots90": round(sh90, 2), "sot90": round(sot90, 2),
               "exp_shots": round(esh, 2), "exp_sot": round(esot, 2),
               "P_shots_o2.5": round(over(esh, 2.5), 3), "P_shots_o1.5": round(over(esh, 1.5), 3),
               "P_sot_o0.5": round(over(esot, 0.5), 3), "P_sot_o1.5": round(over(esot, 1.5), 3)}
        out.append(row)
        print(f"  {name:<18}{team:<10}{sh90:>6.1f}{sot90:>7.1f}{esh:>7.1f}"
              f"{over(esh,2.5)*100:>7.0f}%{over(esot,0.5)*100:>8.0f}%{over(esot,1.5)*100:>8.0f}%")
    if out:
        fn = os.path.join(L.OUT, "player_shots_props_2026-06-23.csv")
        with open(fn, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)
        print(f"\nsaved -> {fn}")

if __name__ == "__main__":
    main()
