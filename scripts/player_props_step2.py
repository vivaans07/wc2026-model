#!/usr/bin/env python3
"""
PLAYER PROPS — Step 2: match-specific 'to score' probabilities for a given day.

Method (consistent with the team model):
  * Each team's MATCH xG comes from the Dixon-Coles model (already includes
    opponent defence, the goal-environment recalibration, and the market-value prior).
  * Distribute that team xG across its players by weight = goal_rate * expected_minutes,
    so the players' expected goals sum to the team's xG.
  * P(player scores >=1) = 1 - exp(-player_xG);  P(2+) = 1 - exp(-x)(1+x).

Expected minutes: real XIs post ~1h pre-kickoff (ESPN). Until then we PROXY likely
starters by squad market-value rank (high value -> starter). Re-run with --lineups
once ESPN posts them for sharp numbers. Goal rate naturally zeroes out non-scorers
(GK/defenders), so the minutes proxy mostly affects attackers.

Usage: python player_props_step2.py --date 2026-06-23
"""
import sys, os, csv, math, argparse
sys.path.insert(0, os.path.dirname(__file__))
import wc_lib as L
from predict_day import score_matrix

def exp_minutes_by_value(players):
    """proxy: rank squad by market value; top 11 ~start, next ~bench cameo."""
    ranked = sorted(players, key=lambda p: -(p["mv"] or 0))
    em = {}
    for i, p in enumerate(ranked):
        em[p["player"]] = 82 if i < 11 else (28 if i < 16 else 8)
    return em

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--date", default="2026-06-23"); a = ap.parse_args()
    # load rates + values, key by (country, player)
    rate = {}
    for r in csv.DictReader(open(os.path.join(L.OUT, "player_goal_rates.csv"))):
        rate[(r["country"], r["player"])] = (float(r["shrunk_rate"]), r["pos"], r["caps"])
    # position weight: goals come overwhelmingly from forwards/mids, rarely defenders
    POS_W = {"ATT": 1.0, "MID": 0.55, "DEF": 0.12, "GK": 0.01, "": 0.40}
    squad = {}
    for r in csv.DictReader(open(os.path.join(L.OUT, "wc2026_squad_values.csv"))):
        mv = float(r["market_value_eur"]) if r["market_value_eur"] not in ("", None) else 0.0
        pc = r.get("pos_cat", "")
        squad.setdefault(r["country_name"], []).append(
            {"player": r["player_name"], "mv": mv, "pos": pc, "posw": POS_W.get(pc, 0.40),
             "rate": rate.get((r["country_name"], r["player_name"]), (0.12, "", 0))[0]})

    games = [x for x in csv.DictReader(open(os.path.join(L.OUT, "wc2026_fixtures.csv")))
             if x["date"] == a.date and x["group"]]
    allrows = []
    for g in games:
        h, aw = g["home_country"], g["away_country"]
        M, lam, nu = score_matrix(h, aw, 0.0, 0.0)
        print(f"\n{'='*60}\n{h} vs {aw}   (team xG: {h} {lam:.2f}, {aw} {nu:.2f})\n{'='*60}")
        for team, txg in ((h, lam), (aw, nu)):
            ps = squad.get(team, [])
            em = exp_minutes_by_value(ps)
            for p in ps: p["w"] = p["rate"] * em[p["player"]] * p["posw"]
            W = sum(p["w"] for p in ps) or 1.0
            scored = []
            for p in ps:
                share = p["w"] / W
                pxg = txg * share
                p_any = 1 - math.exp(-pxg)
                p_2 = 1 - math.exp(-pxg) * (1 + pxg)
                scored.append((p["player"], em[p["player"]], pxg, p_any, p_2))
                allrows.append({"date": a.date, "match": f"{h} v {aw}", "team": team,
                                "player": p["player"], "exp_min": em[p["player"]],
                                "player_xG": round(pxg, 3), "P_to_score": round(p_any, 3),
                                "P_2plus": round(p_2, 3)})
            scored.sort(key=lambda x: -x[3])
            print(f"\n  {team} — top 'to score' candidates:")
            print(f"    {'player':<22}{'min':>4}{'xG':>7}{'P(score)':>10}{'P(2+)':>8}")
            for nm, mn, pxg, pa, p2 in scored[:5]:
                print(f"    {nm:<22}{mn:>4}{pxg:>7.2f}{pa*100:>9.0f}%{p2*100:>7.0f}%")
    out = os.path.join(L.OUT, f"player_props_{a.date}.csv")
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(allrows[0].keys())); w.writeheader(); w.writerows(allrows)
    print(f"\nsaved -> {out}")
    print("NOTE: minutes are a market-value proxy until ESPN posts real XIs; re-run then for sharp numbers.")

if __name__ == "__main__":
    main()
