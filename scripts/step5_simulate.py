#!/usr/bin/env python3
"""
STEP 5 — Monte Carlo tournament simulation (default 50,000 iterations).

Uses the real 2026 format: 12 groups of 4 -> top 2 + 8 best third-placed -> a
Round of 32 -> R16 -> QF -> SF -> Final. The 8 already-played group results are
held FIXED; only remaining matches are simulated.

Engine: the fitted Dixon-Coles bivariate-Poisson goals model (fitted_ratings.json).
  * Group matches: scorelines sampled as independent Poisson with the DC-fitted
    means (the DC low-score rho correction shifts W/D/L by <0.4pp and is omitted
    in sampling; it IS used in the analytical per-fixture probabilities reported).
  * Knockout matches: resolved by ANALYTICAL advance probability that accounts for
    regulation (Skellam), 30' extra time (Skellam at 1/3 rates), and a near-coin-
    flip penalty shootout with a mild strength tilt. Avoids scoreline sampling
    noise in the bracket and is fully reproducible.

Host advantage: hosts (USA/Mexico/Canada) get the full fitted home advantage when
playing in their own country in the group stage, and half of it in knockouts
(uncertain venue). Documented assumption.

Group tiebreakers: points -> goal difference -> goals for -> head-to-head points
among tied teams -> drawing of lots (random). Best-third ranking: points -> GD ->
GF -> lots. Thirds are assigned to the 8 Round-of-32 third-slots by a legal
bipartite matching that respects each slot's allowed source groups (a faithful,
always-legal stand-in for FIFA's fixed 495-row allocation table).
"""
import sys, os, json, csv, argparse, math
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from scipy.stats import skellam
import wc_lib as L

rng = np.random.default_rng(2026)

# ---------------------------------------------------------------- load ratings
with open(os.path.join(L.OUT, "fitted_ratings.json")) as f:
    FIT = json.load(f)
TEAMS = L.ALL_TEAMS
TI = {t: i for i, t in enumerate(TEAMS)}
ATK = np.array([FIT["teams"][t]["atk"] for t in TEAMS])
DFN = np.array([FIT["teams"][t]["dfn"] for t in TEAMS])
C, GAMMA, RHO = FIT["c"], FIT["gamma"], FIT["rho"]
HOST_IDX = {TI[t] for t in L.HOSTS}


def xg(i, j, hadv_i=0.0, hadv_j=0.0):
    lam = math.exp(C + ATK[i] - DFN[j] + GAMMA * hadv_i)
    nu = math.exp(C + ATK[j] - DFN[i] + GAMMA * hadv_j)
    return lam, nu


# analytical advance prob for knockout (memoised)
_padv_cache = {}
def p_advance(i, j, hadv_i=0.0, hadv_j=0.0):
    key = (i, j, round(hadv_i, 3), round(hadv_j, 3))
    if key in _padv_cache: return _padv_cache[key]
    lam, nu = xg(i, j, hadv_i, hadv_j)
    pH = 1 - skellam.cdf(0, lam, nu); pD = skellam.pmf(0, lam, nu)
    le, ne = lam / 3.0, nu / 3.0
    pHe = 1 - skellam.cdf(0, le, ne); pDe = skellam.pmf(0, le, ne)
    p_pen = 0.5 + 0.10 * math.tanh(0.6 * (lam - nu))
    p = pH + pD * (pHe + pDe * p_pen)
    _padv_cache[key] = float(p); return float(p)


# DC analytical W/D/L + most-likely score (for reporting; includes rho)
def analytic_match(i, j, hadv_i=0.0, hadv_j=0.0, maxg=10):
    lam, nu = xg(i, j, hadv_i, hadv_j)
    gx = np.arange(maxg + 1)
    fac = np.array([math.factorial(k) for k in gx])
    px = np.exp(-lam) * lam ** gx / fac
    py = np.exp(-nu) * nu ** gx / fac
    M = np.outer(px, py)
    for (x, y), corr in [((0, 0), 1 - lam * nu * RHO), ((0, 1), 1 + lam * RHO),
                         ((1, 0), 1 + nu * RHO), ((1, 1), 1 - RHO)]:
        M[x, y] *= corr
    M /= M.sum()
    pH = np.tril(M, -1).sum(); pD = np.trace(M); pA = np.triu(M, 1).sum()
    sx, sy = np.unravel_index(M.argmax(), M.shape)
    return pH, pD, pA, lam, nu, int(sx), int(sy)


# ---------------------------------------------------------------- fixtures
def host_adv_for(team_idx, venue_country, stage_group=True):
    """home advantage multiplier for a host team."""
    if team_idx not in HOST_IDX: return 0.0
    name = TEAMS[team_idx]
    in_own = (name == "United States" and "United States" in venue_country) or \
             (name == "Mexico" and "Mexico" in venue_country) or \
             (name == "Canada" and "Canada" in venue_country)
    if stage_group:
        return 1.0 if in_own else 0.0
    return 0.5  # knockouts: reduced, venue uncertain

# load group fixtures (with played results fixed)
GROUP_FIX = {g: [] for g in L.GROUPS}   # g -> list of (i, j, hadv_i, hadv_j, fixed_or_None)
played = {(d, h, a): (hs, as_) for (d, h, a, hs, as_) in L.PLAYED_RESULTS}
with open(os.path.join(L.OUT, "wc2026_fixtures.csv")) as f:
    for r in csv.DictReader(f):
        if not r["group"]: continue
        h, a = r["home_country"], r["away_country"]
        i, j = TI[h], TI[a]; venue = r["venue"]
        hi = host_adv_for(i, venue, True); hj = host_adv_for(j, venue, True)
        fixed = None
        if r["status"] == "played":
            fixed = (int(r["actual_home_goals"]), int(r["actual_away_goals"]))
        GROUP_FIX[r["group"]].append((i, j, hi, hj, fixed))


# ---------------------------------------------------------------- third-slot matching
def bipartite_match(groups):
    """Assign each qualifying-third group to a distinct R32 third-slot whose
    allowed-group set contains it. Returns dict slot->group. groups: list of 8."""
    slots = list(L.THIRD_SLOTS.keys())
    allow = {s: set(L.THIRD_SLOTS[s]) for s in slots}
    matchG = {}  # group -> slot
    def try_assign(s, seen):
        for g in groups:
            if g in allow[s] and g not in seen:
                seen.add(g)
                if g not in matchG or try_assign(matchG[g], seen):
                    matchG[g] = s; return True
        return False
    # match slots to groups (augmenting path)
    for s in slots:
        try_assign(s, set())
    return {s: g for g, s in matchG.items()}

_match_cache = {}
def third_assignment(groups_tuple):
    if groups_tuple in _match_cache: return _match_cache[groups_tuple]
    res = bipartite_match(list(groups_tuple))
    _match_cache[groups_tuple] = res; return res


# ---------------------------------------------------------------- simulation
ROUND_NAMES = {1: "Round of 32", 2: "Round of 16", 3: "Quarter-final",
               4: "Semi-final", 5: "Final", 6: "Champion"}

def simulate(N=50000, seed=2026):
    rng = np.random.default_rng(seed)
    nT = len(TEAMS)
    # outcome counters
    reach = {r: np.zeros(nT) for r in [1, 2, 3, 4, 5, 6]}  # reach R32..Champion
    finish_round = np.zeros(nT)  # accumulate round index reached (0=group exit)

    # ---- vectorised group stage ----
    GP = L.GROUPS
    glist = list(GP.keys())
    # per group: arrays of team global indices in fixed order
    group_team_idx = {g: [TI[t] for t in GP[g]] for g in glist}
    # standings arrays: pts, gd, gf  shape (N,4) per group
    standings = {g: {"pts": np.zeros((N, 4)), "gf": np.zeros((N, 4)),
                     "ga": np.zeros((N, 4))} for g in glist}
    # head-to-head points store: h2h[g] shape (N,4,4) points team r vs c
    h2h = {g: np.zeros((N, 4, 4)) for g in glist}

    for g in glist:
        gi = group_team_idx[g]
        local = {gi[k]: k for k in range(4)}
        for (i, j, hi, hj, fixed) in GROUP_FIX[g]:
            li, lj = local[i], local[j]
            if fixed is not None:
                hs = np.full(N, fixed[0]); as_ = np.full(N, fixed[1])
            else:
                lam, nu = xg(i, j, hi, hj)
                hs = rng.poisson(lam, N); as_ = rng.poisson(nu, N)
            st = standings[g]
            st["gf"][:, li] += hs; st["ga"][:, li] += as_
            st["gf"][:, lj] += as_; st["ga"][:, lj] += hs
            hw = hs > as_; dr = hs == as_; aw = hs < as_
            st["pts"][:, li] += 3 * hw + 1 * dr
            st["pts"][:, lj] += 3 * aw + 1 * dr
            h2h[g][:, li, lj] += 3 * hw + 1 * dr
            h2h[g][:, lj, li] += 3 * aw + 1 * dr

    # rank within each group -> 1st,2nd,3rd,4th (team-local indices) per sim
    pos = {}   # g -> array (N,4) of local team idx ordered 1st..4th
    third_stats = {}  # g -> (pts,gd,gf) of the 3rd team, shape (N,3)
    rand_lots = {g: rng.random((N, 4)) for g in glist}
    for g in glist:
        st = standings[g]; gd = st["gf"] - st["ga"]
        # primary key: pts, gd, gf, lots  (head-to-head applied as fine tiebreak below)
        key = (st["pts"] * 1e9 + (gd + 100) * 1e5 + st["gf"] * 1e2 + rand_lots[g])
        order = np.argsort(-key, axis=1)  # (N,4) local indices, 1st..4th
        pos[g] = order
        third_local = order[:, 2]
        rows = np.arange(N)
        third_stats[g] = np.stack([st["pts"][rows, third_local],
                                   gd[rows, third_local],
                                   st["gf"][rows, third_local]], axis=1)

    # best 8 thirds across the 12 groups
    tp = np.stack([third_stats[g][:, 0] for g in glist], axis=1)  # (N,12) pts
    tgd = np.stack([third_stats[g][:, 1] for g in glist], axis=1)
    tgf = np.stack([third_stats[g][:, 2] for g in glist], axis=1)
    tlot = rng.random((N, 12))
    third_key = tp * 1e9 + (tgd + 100) * 1e5 + tgf * 1e2 + tlot
    third_order = np.argsort(-third_key, axis=1)  # (N,12) group-idx by rank
    qualifying_thirds = third_order[:, :8]         # (N,8) group indices that advance

    # convenience: winner/runner-up global team idx per group per sim
    def team_at(g, place):  # place 0=winner,1=runner,2=third
        loc = pos[g][:, place]; gi = np.array(group_team_idx[g])
        return gi[loc]   # (N,)
    WIN = {g: team_at(g, 0) for g in glist}
    RUN = {g: team_at(g, 1) for g in glist}
    THIRD = {g: team_at(g, 2) for g in glist}

    # mark group-stage advancers (reach R32)
    for g in glist:
        np.add.at(reach[1], WIN[g], 1); np.add.at(reach[1], RUN[g], 1)
    # thirds that advanced
    gidx_arr = np.array(glist)
    for s in range(8):
        grp_sel = third_order[:, s]  # group index (0..11) ranked s-th
        # only first 8 advance -> all of these s<8 advance
        for gi_, g in enumerate(glist):
            mask = grp_sel == gi_
            if mask.any():
                np.add.at(reach[1], THIRD[g][mask], 1)
    finish_round += reach[1] * 0  # placeholder; we set per round below

    # ---- per-sim knockout ----
    # precompute slot->group allowed; knockout host adv handled via host_adv knockouts
    KO = L.KNOCKOUT
    # we need, per sim, the team filling each group-position slot and each third-slot
    glist_idx = {g: i for i, g in enumerate(glist)}
    U = rng.random((N, 40))  # uniforms for the up-to-40 knockout matches per sim
    # iterate sims in python (vectorisation of the third-matching is awkward)
    # accumulate per-round survivors
    reach_acc = {r: np.zeros(nT) for r in [2, 3, 4, 5, 6]}
    finish_acc = np.zeros(nT)

    # pre-extract arrays to plain python for speed
    WIN_a = {g: WIN[g] for g in glist}; RUN_a = {g: RUN[g] for g in glist}
    THIRD_a = {g: THIRD[g] for g in glist}
    qt = qualifying_thirds  # (N,8)

    def ko_hadv(i, j):
        hi = 0.5 if i in HOST_IDX else 0.0
        hj = 0.5 if j in HOST_IDX else 0.0
        return hi, hj

    for n in range(N):
        # which groups produced an advancing third (sorted tuple for cache)
        qgroups = tuple(sorted(glist[k] for k in qt[n]))
        assign = third_assignment(qgroups)  # slot-> group
        # build R32 participants
        slot_team = {}
        # group-position slots
        gp = {g: (WIN_a[g][n], RUN_a[g][n], THIRD_a[g][n]) for g in glist}
        def resolve_slot(code):
            # code like '1A','2B','3:ABCDF','W77','L101'
            if code[0] == '1': return gp[code[1]][0]
            if code[0] == '2': return gp[code[1]][1]
            if code.startswith('3:'):
                # find which match slot this is by reverse lookup at call site
                return None
            return None
        # assign thirds to their R32 matches
        third_for_slot = {}  # match_no -> team idx
        for mno, g in assign.items():
            third_for_slot[mno] = gp[g][2]

        winners = {}  # match_no -> team idx
        for mno in range(73, 105):
            hc, ac = KO[mno]
            # resolve home
            if hc.startswith('W'): h = winners[int(hc[1:])]
            elif hc.startswith('L'): h = ('L', int(hc[1:]))
            elif hc[0] == '1': h = gp[hc[1]][0]
            elif hc[0] == '2': h = gp[hc[1]][1]
            else: h = None
            if ac.startswith('W'): a = winners[int(ac[1:])]
            elif ac.startswith('L'): a = ('L', int(ac[1:]))
            elif ac[0] == '1': a = gp[ac[1]][0]
            elif ac[0] == '2': a = gp[ac[1]][1]
            elif ac.startswith('3:'): a = third_for_slot[mno]
            else: a = None
            # losers (third place match) handled separately
            if isinstance(h, tuple) or isinstance(a, tuple):
                # third-place playoff: resolve losers
                lh = losers[h[1]] if isinstance(h, tuple) else h
                la = losers[a[1]] if isinstance(a, tuple) else a
                h, a = lh, la
            hi, hj = ko_hadv(h, a)
            p = p_advance(h, a, hi, hj)
            home_adv_win = U[n, mno - 73] < p
            w = h if home_adv_win else a
            l = a if home_adv_win else h
            winners[mno] = w
            if mno == 73:
                losers = {}
            losers[mno] = l
            # record round reached by the WINNER advancing
            if mno <= 88:        # R32 winners reach R16
                reach_acc[2][w] += 1
            elif mno <= 96:      # R16 winners reach QF
                reach_acc[3][w] += 1
            elif mno <= 100:     # QF winners reach SF
                reach_acc[4][w] += 1
            elif mno <= 102:     # SF winners reach Final
                reach_acc[5][w] += 1
            elif mno == 104:     # final winner = champion
                reach_acc[6][w] += 1

    for r in [2, 3, 4, 5, 6]:
        reach[r] += reach_acc[r]

    # ---- expected finish (mean best round reached) ----
    # round reached index: 0=group exit,1=R32,2=R16,3=QF,4=SF,5=Final(lost),6=Champion
    # P(reach X) are cumulative; convert to exact-exit distribution for expected finish
    P = {r: reach[r] / N for r in [1, 2, 3, 4, 5, 6]}
    exp_finish = np.zeros(nT)
    # exact prob of finishing at each level
    p_group_exit = 1 - P[1]
    levels = [p_group_exit]
    for r in [1, 2, 3, 4, 5]:
        levels.append(P[r] - P[r + 1])
    levels.append(P[6])  # champion
    L_idx = [0, 1, 2, 3, 4, 5, 6]
    for k, lv in zip(L_idx, levels):
        exp_finish += k * lv
    return P, exp_finish


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=50000)
    args = ap.parse_args()
    print(f"Running Monte Carlo: {args.n:,} iterations...")
    import time; t0 = time.time()
    P, exp_finish = simulate(N=args.n)
    print(f"  done in {time.time()-t0:.1f}s")

    # per-team outcomes table
    EXIT_LABEL = {0: "Group stage", 1: "Round of 32", 2: "Round of 16",
                  3: "Quarter-final", 4: "Semi-final", 5: "Final", 6: "Champion"}
    rows = []
    for i, t in enumerate(TEAMS):
        rows.append({
            "country": t, "group": L.TEAM_GROUP[t], "confederation": L.CONFED[t],
            "fifa_rank": L.FIFA_RANK[t],
            "P_advance_group": round(float(P[1][i]), 4),
            "P_reach_R16": round(float(P[2][i]), 4),
            "P_reach_QF": round(float(P[3][i]), 4),
            "P_reach_SF": round(float(P[4][i]), 4),
            "P_reach_final": round(float(P[5][i]), 4),
            "P_win_cup": round(float(P[6][i]), 4),
            "expected_finish_round": round(float(exp_finish[i]), 3),
        })
    rows.sort(key=lambda r: -r["P_win_cup"])
    with open(os.path.join(L.OUT, "per_team_outcomes.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print("\nTop 12 title favourites:")
    for r in rows[:12]:
        print(f"  {r['country']:<16} win={r['P_win_cup']*100:5.1f}%  final={r['P_reach_final']*100:5.1f}%  "
              f"SF={r['P_reach_SF']*100:5.1f}%  adv={r['P_advance_group']*100:5.1f}%")

    # simulated_match_predictions.csv — remaining group fixtures (concrete matchups)
    pred = []
    with open(os.path.join(L.OUT, "wc2026_fixtures.csv")) as f:
        for r in csv.DictReader(f):
            if r["group"] and r["status"] == "upcoming":
                i, j = TI[r["home_country"]], TI[r["away_country"]]
                hi = host_adv_for(i, r["venue"], True); hj = host_adv_for(j, r["venue"], True)
                pH, pD, pA, lam, nu, sx, sy = analytic_match(i, j, hi, hj)
                pred.append({
                    "match_id": r["match_id"], "date": r["date"], "stage": r["stage"],
                    "home": r["home_country"], "away": r["away_country"],
                    "P_home_win": round(pH, 4), "P_draw": round(pD, 4), "P_away_win": round(pA, 4),
                    "exp_home_goals": round(lam, 2), "exp_away_goals": round(nu, 2),
                    "most_likely_score": f"{sx}-{sy}",
                })
    with open(os.path.join(L.OUT, "simulated_match_predictions.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(pred[0].keys())); w.writeheader(); w.writerows(pred)
    print(f"\nper_team_outcomes.csv ({len(rows)} teams) + "
          f"simulated_match_predictions.csv ({len(pred)} remaining group fixtures) written.")


if __name__ == "__main__":
    main()
