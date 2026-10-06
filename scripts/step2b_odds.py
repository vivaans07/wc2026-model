#!/usr/bin/env python3
"""
STEP 2 (optional) — market odds for benchmarking the model.

Scraped outright (to-win-tournament) American odds, June 14 2026, from CBS Sports
/ FanDuel aggregations (see SOURCE). These are *with* bookmaker margin (overround),
so raw implied probabilities sum to >100%; we also report a normalised version
(scaled so the listed teams' implied probabilities sum to the model's total over
the same teams) for a fairer comparison. Only headline teams are publicly listed
free of charge; the long tail of 48 teams is paywalled, so we skip those (as the
prompt permits) rather than fabricate.
"""
import sys, os, csv, json
sys.path.insert(0, os.path.dirname(__file__))
import wc_lib as L

SOURCE = "https://www.cbssports.com/betting/news/world-cup-odds/ (FanDuel, 2026-06-14)"
ODDS = {  # American odds to win the World Cup
    "Spain": 450, "France": 490, "England": 700, "Portugal": 800,
    "Brazil": 900, "Argentina": 900, "Germany": 1300, "Netherlands": 1700,
    "Norway": 3300, "Colombia": 4000, "United States": 5000, "Senegal": 12500,
}

def implied(american):
    return 100.0 / (american + 100.0) if american > 0 else (-american) / (-american + 100.0)

# model probabilities
model = {r["country"]: float(r["P_win_cup"])
         for r in csv.DictReader(open(os.path.join(L.OUT, "per_team_outcomes.csv")))}

raw = {t: implied(o) for t, o in ODDS.items()}
sum_raw = sum(raw.values())
sum_model_listed = sum(model[t] for t in ODDS)
# normalise market so listed-team implied probs sum to the model's listed total
norm = {t: raw[t] / sum_raw * sum_model_listed for t in ODDS}

rows = []
for t in sorted(ODDS, key=lambda x: -raw[x]):
    rows.append({
        "country": t, "american_odds": f"+{ODDS[t]}",
        "implied_prob_raw": round(raw[t], 4),
        "implied_prob_normalized": round(norm[t], 4),
        "model_P_win": round(model[t], 4),
        "model_minus_market": round(model[t] - norm[t], 4),
        "source": SOURCE,
    })
with open(os.path.join(L.OUT, "wc2026_market_odds.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

print(f"wc2026_market_odds.csv -> {len(rows)} teams")
print(f"  raw implied sum (12 favs) = {sum_raw:.2f} (overround; full 48-team book is larger)")
print("\n  team           market(norm)  model    model-market")
for r in rows:
    print(f"  {r['country']:<14} {r['implied_prob_normalized']*100:6.1f}%   "
          f"{r['model_P_win']*100:6.1f}%   {r['model_minus_market']*100:+6.1f}pp")
