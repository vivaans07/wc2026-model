#!/usr/bin/env python3
"""
PLAYER PROPS — Step 1: build per-player international goal-rate baselines for the
2026 WC squads (the foundation for 'anytime goalscorer' / 'player to score' props).

Data: salimt/football-datasets player_national_performances.csv (caps + goals per
national team) joined to wc2026_squad_values.csv (which carries each squad player's
Transfermarkt player_id from the earlier profile match).

Per player we take their SENIOR national team row (the team_id with the most caps,
to avoid youth-team inflation), compute goals-per-cap with light shrinkage toward a
positional baseline, and convert to an anytime-scorer probability via Poisson.

This is the RATE baseline only. Step 2 adds: club form (per-season goals via the
club file), expected minutes (ESPN lineups), and opponent-defence adjustment.
"""
import sys, os, csv, math
sys.path.insert(0, os.path.dirname(__file__))
import wc_lib as L

SCR = os.path.join(L.PROJ, "scraped")
PRIOR_RATE, PRIOR_W = 0.12, 5.0   # shrink goals/cap toward 0.12 with weight ~5 caps

# aggregate national performances: per player, keep the senior team (max matches)
best = {}   # player_id -> (matches, goals, career_state)
for r in csv.DictReader(open(os.path.join(SCR, "tm_natl_perf.csv"))):
    try: m, g = int(r["matches"]), int(r["goals"])
    except ValueError: continue
    pid = r["player_id"]
    if pid not in best or m > best[pid][0]:
        best[pid] = (m, g, r.get("career_state", ""))

# join to WC squads (have tm_player_id)
squad = list(csv.DictReader(open(os.path.join(L.OUT, "wc2026_squad_values.csv"))))
rows = []
matched = current = 0
for s in squad:
    pid = s.get("tm_player_id", "")
    caps = goals = 0; cstate = ""
    if pid and pid in best:
        caps, goals, cstate = best[pid]; matched += 1
        if cstate == "CURRENT_NATIONAL_PLAYER": current += 1
    rate = (goals + PRIOR_RATE * PRIOR_W) / (caps + PRIOR_W) if caps else PRIOR_RATE
    p_score = 1 - math.exp(-rate)        # anytime-scorer prob over a full match (pre-adjustment)
    rows.append({"country": s["country_name"], "player": s["player_name"],
                 "pos": s.get("pos_cat", ""), "caps": caps, "intl_goals": goals,
                 "goals_per_cap": round(goals / caps, 3) if caps else "",
                 "shrunk_rate": round(rate, 3), "p_anytime_scorer_base": round(p_score, 3),
                 "career_state": cstate, "market_value_eur": s.get("market_value_eur", "")})
out = os.path.join(L.OUT, "player_goal_rates.csv")
with open(out, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

print(f"Squad players: {len(rows)} | matched to national-perf data: {matched} "
      f"({matched/len(rows)*100:.0f}%) | flagged CURRENT_NATIONAL_PLAYER: {current}")
print(f"saved -> {out}\n")
print("Top 20 anytime-scorer baselines (min 15 caps, full-match, pre-opponent/minutes):")
elig = [r for r in rows if r["caps"] >= 15]
elig.sort(key=lambda r: -r["p_anytime_scorer_base"])
print(f"  {'player':<22}{'country':<13}{'caps':>5}{'gls':>5}{'g/cap':>7}{'P(score)':>10}")
for r in elig[:20]:
    print(f"  {r['player']:<22}{r['country']:<13}{r['caps']:>5}{r['intl_goals']:>5}"
          f"{r['goals_per_cap']:>7}{r['p_anytime_scorer_base']*100:>9.0f}%")
