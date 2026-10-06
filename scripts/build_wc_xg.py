#!/usr/bin/env python3
"""
#1 xG-based ratings (Step A): build a shot-based xG for every played WC-2026 game
from ESPN shots / shots-on-target, so the in-tournament games can feed the model as
xG (deserved goals) instead of raw goals (which carry finishing luck in a tiny sample).

No free xG exists for the 49k-match history, so this is scoped to the WC games where
ESPN gives shot data. We fit goals ~ a*SOT + b*off-target (non-negative least squares,
unbiased so mean xG == mean goals) — a standard shots-based xG proxy.

Output: outputs/wc2026_xg.csv  (date, team, opponent, actual_goals, xg)
"""
import sys, os, csv
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np, wc_lib as L

# ESPN display name -> our canonical (martj42) name
ESPN2CANON = {"USA": "United States", "Korea Republic": "South Korea", "Türkiye": "Turkey",
              "Czechia": "Czech Republic", "Côte d'Ivoire": "Ivory Coast", "Congo DR": "DR Congo",
              "IR Iran": "Iran", "Bosnia-Herzegovina": "Bosnia and Herzegovina"}
def canon(nm):
    if nm in ESPN2CANON: return ESPN2CANON[nm]
    if nm in L.ALL_TEAMS: return nm
    # reverse the official-name map
    for c, off in L.OFFICIAL_NAME.items():
        if off == nm: return c
    return nm

rows = list(csv.DictReader(open(os.path.join(L.OUT, "espn_match_stats.csv"))))
G, SOT, OFF = [], [], []
for r in rows:
    try:
        g = float(r["goals"]); sot = float(r["shotsOnTarget"]); sh = float(r["totalShots"])
    except (ValueError, KeyError):
        continue
    G.append(g); SOT.append(sot); OFF.append(max(sh - sot, 0))
G, SOT, OFF = np.array(G), np.array(SOT), np.array(OFF)
# non-negative least squares: goals ~ a*SOT + b*OFF
X = np.column_stack([SOT, OFF])
from scipy.optimize import nnls
coef, _ = nnls(X, G)
a, b = coef
xg_all = X @ coef
# unbiased rescale (so mean xG == mean goals exactly)
scale = G.mean() / xg_all.mean()
a, b = a * scale, b * scale
print(f"shot-based xG model: xG = {a:.3f}*SOT + {b:.3f}*off_target  (mean goals {G.mean():.2f})")
print(f"  fit quality: corr(xG, goals) = {np.corrcoef(X@np.array([a,b]), G)[0,1]:.3f}")

out = []
for r in rows:
    try:
        sot = float(r["shotsOnTarget"]); sh = float(r["totalShots"]); g = float(r["goals"])
    except (ValueError, KeyError):
        continue
    xg = a * sot + b * max(sh - sot, 0)
    out.append({"date": r["date"], "team": canon(r["team"]), "opponent": canon(r["opponent"]),
                "actual_goals": int(g), "xg": round(xg, 3)})
with open(os.path.join(L.OUT, "wc2026_xg.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)
print(f"saved outputs/wc2026_xg.csv ({len(out)} team-games)\n")

# biggest finishing luck (actual - xG), aggregated per team
from collections import defaultdict
agg = defaultdict(lambda: [0.0, 0.0, 0])
for r in out:
    agg[r["team"]][0] += r["actual_goals"]; agg[r["team"]][1] += r["xg"]; agg[r["team"]][2] += 1
luck = sorted(((t, (g - x), g, x, n) for t, (g, x, n) in agg.items()), key=lambda z: -z[1])
print("Most OVER-performing finishing (scored >> xG -> rating will shade DOWN):")
for t, d, g, x, n in luck[:5]:
    print(f"  {t:<16} {g} goals vs {x:.1f} xG  ({d:+.1f})  in {n} games")
print("Most UNDER-performing (scored << xG -> rating will shade UP):")
for t, d, g, x, n in luck[-5:]:
    print(f"  {t:<16} {g} goals vs {x:.1f} xG  ({d:+.1f})  in {n} games")
