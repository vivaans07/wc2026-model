#!/usr/bin/env python3
"""
live_winprob.py — LIVE (in-play) win/draw/loss probabilities that update with the
current score and minutes remaining. Turns the pre-game Dixon-Coles expected
goals into a fair PRICE you can compare to Polymarket's live price.

Idea: goals still arrive at the team's expected rate, but only the REMAINING
minutes are left to play. So remaining expected goals = pregame_xG * (mins_left/90).
Final score = current score + a fresh draw of remaining goals. From that we get
live P(home win / draw / away win), a fair price in cents (= probability), and an
EDGE vs whatever price the market is showing.

Usage:
  python live_winprob.py --home Canada --away Qatar --hs 0 --as 0 --minute 60
  optional: --redcard home|away   --market_home 0.72  (market YES price 0-1 for home)
"""
import sys, os, json, math, argparse
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np

FIT = json.load(open(os.path.join(os.path.dirname(__file__), "..", "outputs", "fitted_ratings.json")))
ATK = {t: FIT["teams"][t]["atk"] for t in FIT["teams"]}
DFN = {t: FIT["teams"][t]["dfn"] for t in FIT["teams"]}
C, GAMMA = FIT["c"], FIT["gamma"]
HOSTS = {"United States", "Mexico", "Canada"}

def pregame_xg(home, away, host_home=False, host_away=False):
    hi = GAMMA if host_home else 0.0; hj = GAMMA if host_away else 0.0
    lam = math.exp(C + ATK[home] - DFN[away] + hi)
    nu  = math.exp(C + ATK[away] - DFN[home] + hj)
    return lam, nu

def american(p):
    if p <= 0: return "n/a"
    return f"+{round((1/p-1)*100)}" if p < 0.5 else f"-{round(100/((1/p)-1))}"

def live_probs(home, away, hs, as_, minute, redcard=None,
               host_home=False, host_away=False, full=94):
    lam, nu = pregame_xg(home, away, host_home, host_away)
    frac = max(0.0, (full - minute) / 90.0)
    lam_r, nu_r = lam * frac, nu * frac
    # red-card effect (approximate): down a man -> score less, concede more
    if redcard == "home": lam_r *= 0.65; nu_r *= 1.25
    elif redcard == "away": nu_r *= 0.65; lam_r *= 1.25
    # distribution of ADDITIONAL goals for each side (Poisson), capped
    K = 12
    gx = np.arange(K + 1); fac = np.array([math.factorial(k) for k in gx])
    ph = np.exp(-lam_r) * lam_r**gx / fac
    pa = np.exp(-nu_r) * nu_r**gx / fac
    M = np.outer(ph, pa)  # P(home adds i, away adds j)
    pH = pD = pA = 0.0
    for i in range(K + 1):
        for j in range(K + 1):
            fh, fa = hs + i, as_ + j
            if fh > fa: pH += M[i, j]
            elif fh == fa: pD += M[i, j]
            else: pA += M[i, j]
    return pH, pD, pA, lam_r, nu_r

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", required=True); ap.add_argument("--away", required=True)
    ap.add_argument("--hs", type=int, default=0); ap.add_argument("--as", type=int, dest="as_", default=0)
    ap.add_argument("--minute", type=float, default=0)
    ap.add_argument("--redcard", choices=["home", "away"], default=None)
    ap.add_argument("--market_home", type=float, default=None, help="market YES price for home, 0-1")
    ap.add_argument("--market_draw", type=float, default=None)
    ap.add_argument("--market_away", type=float, default=None)
    a = ap.parse_args()
    hh = a.home in HOSTS; ha = a.away in HOSTS
    pH, pD, pA, lr, nr = live_probs(a.home, a.away, a.hs, a.as_, a.minute, a.redcard, hh, ha)

    print(f"\nLIVE  {a.home} {a.hs}-{a.as_} {a.away}  @ {a.minute:.0f}'"
          + (f"  (RED CARD: {a.redcard})" if a.redcard else ""))
    print(f"  remaining expected goals: {a.home} {lr:.2f} | {a.away} {nr:.2f}\n")
    print(f"  {'outcome':<22}{'fair prob':>10}{'fair price(¢)':>14}{'fair odds':>11}")
    for name, p in [(f"{a.home} win", pH), ("Draw", pD), (f"{a.away} win", pA)]:
        print(f"  {name:<22}{p*100:>9.1f}%{p*100:>13.0f}¢{american(p):>11}")

    mkt = {"home": a.market_home, "draw": a.market_draw, "away": a.market_away}
    fair = {"home": pH, "draw": pD, "away": pA}
    if any(v is not None for v in mkt.values()):
        print(f"\n  EDGE vs market (positive = potential value):")
        for k, lbl in [("home", f"{a.home}"), ("draw", "Draw"), ("away", f"{a.away}")]:
            if mkt[k] is None: continue
            edge = fair[k] - mkt[k]
            flag = "  <-- VALUE (buy)" if edge > 0.04 else ("  <-- overpriced (consider sell)" if edge < -0.04 else "")
            print(f"    {lbl:<16} fair {fair[k]*100:4.1f}¢  market {mkt[k]*100:4.1f}¢  "
                  f"edge {edge*100:+5.1f}¢{flag}")
        print("    (rule of thumb: need edge > ~4¢ to beat spread/fees/model error)")

if __name__ == "__main__":
    main()
