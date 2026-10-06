#!/usr/bin/env python3
"""
possession_sim.py — agent-style POSSESSION-BY-POSSESSION match simulator.

  *** HONEST METHOD NOTE ***
  The provided datasets contain NO event/tracking data, so the per-possession
  event RATES below (passes per possession, foul/corner/throw-in/offside
  probabilities, shot-on-target %, etc.) are FOOTBALL DOMAIN BASE RATES from
  public match-stat averages — they are NOT estimated from the data. What IS
  data-driven is each team's expected goals (xG), taken from the validated
  Dixon-Coles model; the engine's shot-conversion is auto-calibrated so the
  simulated mean goals MATCH that xG. So: goals = data-driven & validated;
  the granular event breakdown = realistic but assumption-based colour.

Each match is simulated as a sequence of possessions until ~96 min of game time
is consumed. Every possession runs a small Markov chain of events:
  pass(es) -> {shot, foul-won->free-kick/penalty, out->throw-in, corner,
               offside, turnover} -> ball transitions to the next possession.

Outputs aggregate team stats over N matches + one fully-logged sample match.
Usage: python possession_sim.py --home Uzbekistan --away Colombia --n 10000
"""
import sys, os, json, math, argparse, random
from collections import defaultdict, Counter
sys.path.insert(0, os.path.dirname(__file__))
import wc_lib as L

FIT = json.load(open(os.path.join(L.OUT, "fitted_ratings.json")))
ATK = {t: FIT["teams"][t]["atk"] for t in L.ALL_TEAMS}
DFN = {t: FIT["teams"][t]["dfn"] for t in L.ALL_TEAMS}
C, GAMMA = FIT["c"], FIT["gamma"]

def model_xg(home, away, hadv_h=0.0, hadv_a=0.0):
    lam = math.exp(C + ATK[home] - DFN[away] + GAMMA*hadv_h)
    nu  = math.exp(C + ATK[away] - DFN[home] + GAMMA*hadv_a)
    return lam, nu

# ---- domain base rates (per-possession, tuned to public match-stat averages:
#      ~12-14 shots, ~5 corners, ~11-13 fouls, ~20 throw-ins, ~105 sequences/team) ----
MATCH_SECONDS   = 96*60          # incl. stoppage
PASS_TIME       = 4.5            # seconds per pass/touch
EVENT_TIME      = 9.0            # seconds for the terminating action
BASE = dict(shot=0.11, foul=0.10, corner=0.026, throwout=0.13, offside=0.016)
PEN_FRAC_OF_FOUL = 0.012         # fraction of won fouls that are penalties (in box)
PEN_CONVERSION   = 0.78          # penalty scoring rate
# non-goal shot resolution shares (sum to 1):
SHOT_SAVED      = 0.30           # on target, saved   -> corner 30% / goal kick 70%
SHOT_OFFTARGET  = 0.50           # off target         -> goal kick
SHOT_BLOCKED    = 0.20           # blocked            -> corner 50% / cleared 50%

def passes_mean(strength_factor):
    return max(2.2, 3.8 + 1.6*strength_factor)   # stronger team strings more passes

def sim_match(home, away, conv, log=False):
    """Simulate one match. conv = {team: per-shot goal prob}. Returns stats dict
    and (if log) an event list for the first part of the match."""
    lamh, lama = model_xg(home, away)
    # possession share from xG diff (mild)
    share_home = 0.5 + 0.12*math.tanh(lamh - lama)   # prob a neutral restart -> home
    # per-team attack scaling for shot prob (relative to a 'balanced' xG ~1.1)
    sf = {home: (lamh-1.1)/1.1, away: (lama-1.1)/1.1}
    stats = {t: Counter() for t in (home, away)}
    goals = {home: 0, away: 0}
    t_elapsed = 0.0
    # initial kickoff
    poss = home if random.random() < 0.5 else away
    events = []
    def other(x): return away if x == home else home
    def neutral_restart():
        return home if random.random() < share_home else away

    while t_elapsed < MATCH_SECONDS:
        atk = poss; dfn = other(poss); s = stats[atk]; s["possessions"] += 1
        # passes this possession
        npass = max(0, int(random.gauss(passes_mean(sf[atk]), 2.4)))
        s["passes"] += npass
        t_elapsed += npass*PASS_TIME + EVENT_TIME
        # terminating event probabilities (scale shot by attacking quality)
        p_shot = BASE["shot"] * (1 + 0.6*sf[atk])
        p = dict(shot=max(0.02, p_shot), foul=BASE["foul"], corner=BASE["corner"],
                 throwout=BASE["throwout"], offside=BASE["offside"])
        p["turnover"] = max(0.05, 1 - sum(p.values()))
        r = random.random(); cum = 0; ev = "turnover"
        for k, v in p.items():
            cum += v
            if r < cum: ev = k; break

        if ev == "shot":
            s["shots"] += 1
            if random.random() < conv[atk]:
                s["goals"] += 1; goals[atk] += 1; s["shots_on_target"] += 1
                if log and len(events) < 9999: events.append((round(t_elapsed/60,1), atk, f"GOAL ({npass} passes)"))
                poss = dfn  # kickoff to conceding team
            else:
                # non-goal shot resolution
                rr = random.random()
                if rr < SHOT_SAVED:                      # on target, saved
                    s["shots_on_target"] += 1; s["saved"] += 1
                    if random.random() < 0.30: s["corners"] += 1; poss = atk
                    else: poss = dfn                     # goalkeeper -> defending team
                elif rr < SHOT_SAVED + SHOT_OFFTARGET:   # off target -> goal kick
                    s["off_target"] += 1; poss = dfn
                else:                                    # blocked
                    s["blocked"] += 1
                    if random.random() < 0.50: s["corners"] += 1; poss = atk
                    else: poss = dfn
                if log and len(events) < 40: events.append((round(t_elapsed/60,1), atk, f"shot ({npass} passes)"))
        elif ev == "foul":
            # foul won by attacker -> free kick (or penalty)
            if random.random() < PEN_FRAC_OF_FOUL:
                s["penalties_won"] += 1
                stats[dfn]["fouls_conceded"] += 1
                if random.random() < PEN_CONVERSION:
                    s["goals"] += 1; goals[atk] += 1; s["penalties_scored"] += 1
                    if log and len(events) < 40: events.append((round(t_elapsed/60,1), atk, "PENALTY GOAL"))
                    poss = dfn
                else:
                    if log and len(events) < 40: events.append((round(t_elapsed/60,1), atk, "penalty MISS/SAVE"))
                    poss = dfn
            else:
                s["free_kicks_won"] += 1; stats[dfn]["fouls_conceded"] += 1
                poss = atk
                if log and len(events) < 40: events.append((round(t_elapsed/60,1), atk, "free kick won"))
        elif ev == "corner":
            s["corners"] += 1; poss = atk
            if log and len(events) < 40: events.append((round(t_elapsed/60,1), atk, "corner"))
        elif ev == "throwout":
            s["throwins_for_opp"] += 1; poss = neutral_restart()
            if log and len(events) < 40: events.append((round(t_elapsed/60,1), atk, "out of bounds -> throw-in"))
        elif ev == "offside":
            s["offside"] += 1; poss = dfn
            if log and len(events) < 40: events.append((round(t_elapsed/60,1), atk, "offside"))
        else:
            s["turnovers"] += 1; poss = dfn
            if log and len(events) < 40: events.append((round(t_elapsed/60,1), atk, f"turnover ({npass} passes)"))

    return goals, stats, events


def calibrate(home, away, trials=3000):
    """Set per-shot conversion so simulated mean goals == model xG for each team."""
    lamh, lama = model_xg(home, away)
    conv = {home: 0.10, away: 0.10}
    for _ in range(2):  # two refinement passes
        shots = {home: 0, away: 0}; gl = {home: 0, away: 0}
        for _ in range(trials):
            g, st, _ = sim_match(home, away, conv)
            for t in (home, away):
                shots[t] += st[t]["shots"]
        mean_shots = {t: shots[t]/trials for t in (home, away)}
        conv = {home: min(0.4, lamh/max(mean_shots[home],1e-6)),
                away: min(0.4, lama/max(mean_shots[away],1e-6))}
    return conv, (lamh, lama)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", default="Uzbekistan")
    ap.add_argument("--away", default="Colombia")
    ap.add_argument("--n", type=int, default=10000)
    args = ap.parse_args()
    home, away = args.home, args.away
    random.seed(2026)

    conv, (lamh, lama) = calibrate(home, away)
    print(f"\n{'='*74}\nPOSSESSION-LEVEL SIMULATION  —  {home} vs {away}\n{'='*74}")
    print(f"Calibration target (Dixon-Coles xG): {home} {lamh:.2f} | {away} {lama:.2f}")
    print(f"Auto-calibrated per-shot conversion : {home} {conv[home]*100:.1f}% | {away} {conv[away]*100:.1f}%")

    agg = {t: defaultdict(float) for t in (home, away)}
    score = Counter(); wdl = Counter(); gsum = {home:0, away:0}
    for i in range(args.n):
        g, st, _ = sim_match(home, away, conv)
        for t in (home, away):
            for k, v in st[t].items(): agg[t][k] += v
            gsum[t] += g[t]
        score[(g[home], g[away])] += 1
        wdl["H" if g[home] > g[away] else "D" if g[home] == g[away] else "A"] += 1

    n = args.n
    print(f"\n--- AGGREGATE over {n:,} simulated matches (per match averages) ---")
    print(f"{'stat':<22}{home:>14}{away:>14}   [source]")
    def row(label, key, src):
        print(f"{label:<22}{agg[home][key]/n:>14.2f}{agg[away][key]/n:>14.2f}   {src}")
    poss_tot = (agg[home]['possessions']+agg[away]['possessions'])/n
    print(f"{'possession %':<22}{agg[home]['possessions']/poss_tot/n*100:>13.1f}%"
          f"{agg[away]['possessions']/poss_tot/n*100:>13.1f}%   derived")
    row("goals (=xG, validated)", "goals", "DATA-DRIVEN")
    row("passes", "passes", "assumed")
    row("shots", "shots", "calibrated->xG")
    row("shots on target", "shots_on_target", "assumed")
    row("corners", "corners", "assumed")
    row("free kicks won", "free_kicks_won", "assumed")
    row("fouls conceded", "fouls_conceded", "assumed")
    row("penalties won", "penalties_won", "assumed")
    row("penalties scored", "penalties_scored", "assumed")
    row("throw-ins conceded", "throwins_for_opp", "assumed")
    row("offsides", "offside", "assumed")
    row("turnovers", "turnovers", "assumed")
    row("possessions", "possessions", "derived")

    print(f"\n--- RESULT distribution ---")
    print(f"  {home} win {wdl['H']/n*100:.1f}% | draw {wdl['D']/n*100:.1f}% | {away} win {wdl['A']/n*100:.1f}%")
    print(f"  mean score: {gsum[home]/n:.2f} - {gsum[away]/n:.2f}  (target xG {lamh:.2f}-{lama:.2f})")
    print("  most likely scorelines:")
    for (h, a), c in score.most_common(6):
        print(f"    {h}-{a}: {c/n*100:.1f}%")

    # one fully-logged sample match
    random.seed(7)
    g, st, events = sim_match(home, away, conv, log=True)
    print(f"\n--- SAMPLE single match, possession-by-possession (first ~30 events) ---")
    print(f"  Final score: {home} {g[home]} - {g[away]} {away}")
    for k, (mn, team, desc) in enumerate(events[:30]):
        print(f"   {mn:5.1f}'  {team:<11} {desc}")

    # save aggregate CSV
    import csv
    fn = os.path.join(L.OUT, f"possession_sim_{home}_vs_{away}.csv".replace(" ", "_"))
    with open(fn, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["stat", home, away, "source"])
        keys = [("goals","DATA-DRIVEN"),("passes","assumed"),("shots","calibrated"),
                ("shots_on_target","assumed"),("corners","assumed"),("free_kicks_won","assumed"),
                ("fouls_conceded","assumed"),("penalties_won","assumed"),("penalties_scored","assumed"),
                ("throwins_for_opp","assumed"),("offside","assumed"),("turnovers","assumed"),
                ("possessions","derived")]
        for k, src in keys:
            w.writerow([k, round(agg[home][k]/n,3), round(agg[away][k]/n,3), src])
    print(f"\nSaved {fn}")


if __name__ == "__main__":
    main()
