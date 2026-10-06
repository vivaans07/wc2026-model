#!/usr/bin/env python3
"""
STEP 3 — feature engineering per national team (as of June 2026).

Builds outputs/team_features.csv for all 48 teams. Also fits the FINAL
Dixon-Coles + Elo ratings on the full results corpus (through 2026-06-13, with
the validation-selected hyperparameters) and saves them to
outputs/fitted_ratings.json for the Monte Carlo step to reuse.

IMPORTANT — features the prompt requested that this dataset CANNOT support are
emitted as explicit 'NA_no_source' columns (never imputed):
  squad_market_value_*, mean_age, pct_u23, pct_o30, injury_days_missed,
  squad_cohesion, club_league_strength.
These require the Transfermarkt-style files (player_profiles / injuries /
teammates / competitions) which are absent from the Fjelstul database.

Features that ARE built (from real data):
  * model ratings: DC attack / defence / overall strength, current Elo
  * external: FIFA rank, pot, confederation, host & playoff-winner flags
  * recent international form (last 24 months): matches, points-per-game,
    goals for/against per game, win/draw/loss %
  * historical WC pedigree (Fjelstul 1930-2022): titles, appearances, matches,
    win%, goals for/against per match, best finish, last appearance year
"""
import sys, os, csv, json, datetime, math
sys.path.insert(0, os.path.dirname(__file__))
import wc_lib as L, ratings as RT

HALF_LIFE, RIDGE = 5.0, 1.0           # validation-selected
REF = "2026-06-23"
NOW = datetime.date(2026, 6, 23)
GOAL_ENV_K = 40        # shrinkage prior strength for the goal-environment recalibration
VALUE_PRIOR_SCALE = 1.0  # validation-selected weight on the squad market-value prior

# ---------------------------------------------------------------- market-value prior
# Anchor each WC team toward the strength implied by its squad market value (Transfermarkt).
# This injects the talent signal the results-only model can't see (fixes France-underrating /
# CONMEBOL-overrating). Built as a standardized log-squad-value z-score; DC ridge shrinks
# attack/defence toward it. Validated to slightly improve out-of-sample logloss.
value_prior = {}
sv_path = os.path.join(L.OUT, "wc2026_squad_values.csv")
if os.path.exists(sv_path):
    vals = {}
    for r in csv.DictReader(open(sv_path)):
        if r["market_value_eur"] not in ("", None):
            vals[r["country_name"]] = vals.get(r["country_name"], 0.0) + float(r["market_value_eur"])
    logv = {t: math.log(v) for t, v in vals.items() if v > 0}
    if logv:
        mu = sum(logv.values()) / len(logv)
        sd = (sum((x - mu) ** 2 for x in logv.values()) / len(logv)) ** 0.5 or 1.0
        value_prior = {t: VALUE_PRIOR_SCALE * (logv[t] - mu) / sd for t in logv}

# ---------------------------------------------------------------- xG substitution (#1)
# Replace played WC-2026 games' raw goals with shot-based xG (deserved goals) so the
# in-tournament signal isn't distorted by finishing luck in a tiny sample. Scoped to
# WC games (only place we have shot data); historical corpus keeps goals (luck averages out).
rows_all = L.load_results(min_date="2006-01-01")
xg_path = os.path.join(L.OUT, "wc2026_xg.csv")
n_xg = 0
if os.path.exists(xg_path):
    pair_xg = {}
    for r in csv.DictReader(open(xg_path)):
        pair_xg.setdefault(frozenset((r["team"], r["opponent"])), {})[r["team"]] = float(r["xg"])
    for r in rows_all:
        if r["date"] >= "2026-06-11" and r["tournament"] == "FIFA World Cup":
            key = frozenset((r["home_team"], r["away_team"]))
            if key in pair_xg and r["home_team"] in pair_xg[key] and r["away_team"] in pair_xg[key]:
                r["hs"] = pair_xg[key][r["home_team"]]; r["as"] = pair_xg[key][r["away_team"]]; n_xg += 1

# ---------------------------------------------------------------- final ratings
print(f"Fitting FINAL Dixon-Coles + Elo (ref {REF}) | value-prior teams: {len(value_prior)} | xG-substituted WC games: {n_xg}...")
dc = RT.DixonColes(half_life_years=HALF_LIFE, ridge=RIDGE, ref_date=REF, prior=value_prior).fit(rows_all, L.canon)
elo, _ = RT.compute_elo(rows_all, L.canon)

# ---------------------------------------------------------------- favorite-strength recalibration (#trained)
# Validation showed the model was UNDER-confident on favorites (predicted 75% -> actual ~85%),
# and live results confirmed it (Portugal 5-0 vs a model that had them 65% / under-3.5 74%).
# Stretching the attack/defence spread away from the mean by STRETCH makes mismatches more
# decisive; STRETCH=1.2 was validation-selected (best OOS logloss + favorite-end calibration).
STRETCH = 1.20
_ma, _md = dc.atk.mean(), dc.dfn.mean()
dc.atk = _ma + STRETCH * (dc.atk - _ma)
dc.dfn = _md + STRETCH * (dc.dfn - _md)
print(f"  favorite-strength recalibration: rating spread x{STRETCH} (fixes favorite under-confidence)")

# ---------------------------------------------------------------- goal-environment recalibration
# The long-history fit can be mis-tuned to the CURRENT tournament's scoring level.
# We measure model-expected vs actual total goals over played WC-2026 games and fold a
# SAMPLE-SIZE-SHRUNK multiplier into the baseline c (lam,nu both scale by GOAL_ENV).
# This is calibration to ACTUAL RESULTS (not to any tipster's picks) and self-updates daily.
wc = [r for r in rows_all if r["date"].startswith("2026") and r["tournament"] == "FIFA World Cup"]
exp_tot = act_tot = n_env = 0.0
for r in wc:
    h, a = L.canon(r["home_team"]), L.canon(r["away_team"])
    if h not in dc.idx or a not in dc.idx:
        continue
    hi = dc.gamma if (h in L.HOSTS and r.get("country") == h) else 0.0
    aj = dc.gamma if (a in L.HOSTS and r.get("country") == a) else 0.0
    lam = math.exp(dc.c + dc.atk[dc.idx[h]] - dc.dfn[dc.idx[a]] + hi)
    nu  = math.exp(dc.c + dc.atk[dc.idx[a]] - dc.dfn[dc.idx[h]] + aj)
    exp_tot += lam + nu; act_tot += r["hs"] + r["as"]; n_env += 1
if n_env >= 5 and exp_tot > 0:
    ratio = act_tot / exp_tot
    shrink = n_env / (n_env + GOAL_ENV_K)          # grows toward 1 as more games play
    goal_env = 1.0 + shrink * (ratio - 1.0)
else:
    ratio, shrink, goal_env = 1.0, 0.0, 1.0
adj_c = dc.c + math.log(goal_env)                  # scaling lam,nu by goal_env == adding ln() to c
print(f"  goal-env recal: {int(n_env)} WC games | model {exp_tot/max(n_env,1):.2f} vs actual "
      f"{act_tot/max(n_env,1):.2f}/game | raw ratio {ratio:.3f} x shrink {shrink:.2f} "
      f"=> GOAL_ENV {goal_env:.3f} (c {dc.c:.3f} -> {adj_c:.3f})")

# save fitted ratings (with the recalibration BAKED INTO c, so every tool uses it automatically)
fit = {"half_life": HALF_LIFE, "ridge": RIDGE, "ref_date": REF,
       "c": adj_c, "c_raw": dc.c, "goal_env": goal_env, "goal_env_n": int(n_env),
       "value_prior_scale": VALUE_PRIOR_SCALE, "value_prior_teams": len(value_prior),
       "rating_stretch": STRETCH, "gamma": dc.gamma, "rho": dc.rho,
       "teams": {t: {"atk": float(dc.atk[dc.idx[t]]), "dfn": float(dc.dfn[dc.idx[t]]),
                     "elo": float(elo.get(t, 1500.0))} for t in L.ALL_TEAMS}}
with open(os.path.join(L.OUT, "fitted_ratings.json"), "w") as f:
    json.dump(fit, f, indent=2)
print("  saved fitted_ratings.json (goal-env recalibration baked into c)")

# ---------------------------------------------------------------- recent form (24m)
cut = (NOW - datetime.timedelta(days=730)).isoformat()
form = {t: {"m": 0, "pts": 0, "gf": 0, "ga": 0, "w": 0, "d": 0, "l": 0} for t in L.ALL_TEAMS}
for r in rows_all:
    if r["date"] < cut: continue
    for side, opp_side, gf_k, ga_k in [("home_team", "away_team", "hs", "as"),
                                       ("away_team", "home_team", "as", "hs")]:
        t = L.canon(r[side])
        if t not in form: continue
        gf, ga = r[gf_k], r[ga_k]
        f = form[t]; f["m"] += 1; f["gf"] += gf; f["ga"] += ga
        if gf > ga: f["w"] += 1; f["pts"] += 3
        elif gf == ga: f["d"] += 1; f["pts"] += 1
        else: f["l"] += 1

# ---------------------------------------------------------------- WC pedigree (Fjelstul)
FJ = L.FJELSTUL
winners = {}
host_won = {}
with open(os.path.join(FJ, "tournaments.csv")) as f:
    tour = list(csv.DictReader(f))
title_count = {}
TITLE_ALIAS = {"West Germany": "Germany"}  # merge predecessor states into modern nation
for tr in tour:
    wn = TITLE_ALIAS.get(tr["winner"], tr["winner"])
    title_count[wn] = title_count.get(wn, 0) + 1
# standings: best finish (min position) + podium counts
best_finish = {}; podiums = {}
with open(os.path.join(FJ, "tournament_standings.csv")) as f:
    for r in csv.DictReader(f):
        tid = r["team_id"]; pos = int(r["position"])
        best_finish[tid] = min(best_finish.get(tid, 99), pos)
        if pos <= 3: podiums[tid] = podiums.get(tid, 0) + 1
# appearances + last year
appearances = {}; last_year = {}
yr = {tr["tournament_id"]: int(tr["year"]) for tr in tour}
with open(os.path.join(FJ, "qualified_teams.csv")) as f:
    for r in csv.DictReader(f):
        tid = r["team_id"]
        appearances[tid] = appearances.get(tid, 0) + 1
        last_year[tid] = max(last_year.get(tid, 0), yr.get(r["tournament_id"], 0))
# WC match aggregates from team_appearances
wc = {}
with open(os.path.join(FJ, "team_appearances.csv")) as f:
    for r in csv.DictReader(f):
        tid = r["team_id"]; w = wc.setdefault(tid, {"m": 0, "w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0})
        w["m"] += 1; w["gf"] += int(r["goals_for"]); w["ga"] += int(r["goals_against"])
        if r["win"] == "1": w["w"] += 1
        elif r["draw"] == "1": w["d"] += 1
        else: w["l"] += 1

# ---------------------------------------------------------------- assemble rows
NA = "NA_no_source"
# predecessor Fjelstul ids to fold into a modern nation's WC pedigree
PREDECESSOR_IDS = {"Germany": ["T-83"], "Czech Republic": ["T-20"]}  # West Germany; Czechoslovakia

def agg_wc(t, tid):
    """Aggregate WC match stats across a team's Fjelstul id(s)."""
    ids = ([tid] if tid else []) + PREDECESSOR_IDS.get(t, [])
    tot = {"m": 0, "w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0}
    for x in ids:
        if x in wc:
            for k in tot: tot[k] += wc[x][k]
    return tot if tot["m"] else None

def agg_scalar(t, tid, table, reducer):
    ids = ([tid] if tid else []) + PREDECESSOR_IDS.get(t, [])
    vals = [table[x] for x in ids if x in table]
    return reducer(vals) if vals else None

out = []
for t in L.ALL_TEAMS:
    i = dc.idx[t]; tid = L.FJELSTUL_TEAM_ID[t]
    f = form[t]; m = max(f["m"], 1)
    w = agg_wc(t, tid)
    wm = max(w["m"], 1) if w else 1
    # title count: match by Fjelstul team_name (winners stored by name)
    fj_name = None
    if tid:
        # winner names use modern names; handle DR Congo->Zaire (never won) etc.
        fj_name = t if t in title_count else None
    row = {
        "country_name": t,
        "fifa_team_id": tid or "",
        "confederation": L.CONFED[t],
        "pot": L.POT[t],
        "fifa_rank": L.FIFA_RANK[t],
        "is_host": int(t in L.HOSTS),
        "is_playoff_winner": int(t in L.PLAYOFF_WINNERS),
        # ---- model ratings ----
        "dc_attack": round(float(dc.atk[i]), 4),
        "dc_defence": round(float(dc.dfn[i]), 4),
        "dc_strength": round(float(dc.atk[i] + dc.dfn[i]), 4),
        "elo": round(float(elo.get(t, 1500.0)), 1),
        # ---- recent form (24m) ----
        "form24_matches": f["m"],
        "form24_ppg": round(f["pts"] / m, 3),
        "form24_gf_per": round(f["gf"] / m, 3),
        "form24_ga_per": round(f["ga"] / m, 3),
        "form24_win_pct": round(f["w"] / m, 3),
        # ---- WC pedigree (Fjelstul) ----
        "wc_titles": title_count.get(t, 0),
        "wc_appearances": (agg_scalar(t, tid, appearances, sum) or 0),
        "wc_best_finish": (agg_scalar(t, tid, best_finish, min) or ""),
        "wc_podiums": (agg_scalar(t, tid, podiums, sum) or 0),
        "wc_matches": w["m"] if w else 0,
        "wc_win_pct": round(w["w"] / wm, 3) if w else "",
        "wc_gf_per": round(w["gf"] / wm, 3) if w else "",
        "wc_ga_per": round(w["ga"] / wm, 3) if w else "",
        "wc_last_appearance": (agg_scalar(t, tid, last_year, max) or ""),
        # ---- prompt-requested but UNAVAILABLE (no Transfermarkt source) ----
        "squad_market_value_total": NA, "squad_market_value_top5": NA,
        "mean_age": NA, "pct_u23": NA, "pct_o30": NA,
        "injury_days_missed_24m": NA, "squad_cohesion": NA, "club_league_strength": NA,
    }
    out.append(row)

out.sort(key=lambda r: -r["dc_strength"])
with open(os.path.join(L.OUT, "team_features.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)
print(f"team_features.csv -> {len(out)} teams, {len(out[0])} columns")
print("\nTop 10 by DC strength:")
for r in out[:10]:
    print(f"  {r['country_name']:<22} str={r['dc_strength']:+.2f} Elo={r['elo']:.0f} "
          f"FIFA#{r['fifa_rank']:<3} form_ppg={r['form24_ppg']} titles={r['wc_titles']}")
print("\nDebutants (no Fjelstul WC history):",
      [r['country_name'] for r in out if r['wc_appearances'] == 0])
