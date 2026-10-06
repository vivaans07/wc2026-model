#!/usr/bin/env python3
"""
live_draw.py — LIVE probability of a DRAW (and win/loss), combining TWO sources:
  (1) the structural model  : teams + current score + minutes left (Dixon-Coles),
  (2) the Polymarket prices  : the crowd's live view (de-vigged to true probs).

Why blend? The market sees things the model can't (momentum, injuries, who's
pushing) and is usually sharp live; the model contributes correct structure
(how a draw's probability should move with score & time). The blend is better
than either alone, and shrinking toward the market guards against over-betting
on model disagreement.

Final fair = w_market * market_prob + (1-w_market) * model_prob  (renormalised).
Edge on an outcome = fair - price_you_pay. Positive => underpriced => buy.

Usage (prices are Polymarket YES prices, 0-1):
  python live_draw.py --home Mexico --away "South Korea" --hs 1 --as 0 --minute 55 \
      --p_home 0.62 --p_draw 0.27 --p_away 0.14 --w_market 0.6
"""
import argparse, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from live_winprob import live_probs, american
HOSTS = {"United States", "Mexico", "Canada"}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", required=True); ap.add_argument("--away", required=True)
    ap.add_argument("--hs", type=int, default=0); ap.add_argument("--as", type=int, dest="as_", default=0)
    ap.add_argument("--minute", type=float, default=0)
    ap.add_argument("--redcard", choices=["home", "away"], default=None)
    ap.add_argument("--p_home", type=float, required=True, help="Polymarket YES price home win, 0-1")
    ap.add_argument("--p_draw", type=float, required=True)
    ap.add_argument("--p_away", type=float, required=True)
    ap.add_argument("--w_market", type=float, default=0.6, help="blend weight on market (0-1)")
    a = ap.parse_args()

    hh, ha = a.home in HOSTS, a.away in HOSTS
    mH, mD, mA = live_probs(a.home, a.away, a.hs, a.as_, a.minute, a.redcard, hh, ha)[:3]

    # de-vig the market prices -> true implied probabilities
    over = a.p_home + a.p_draw + a.p_away
    iH, iD, iA = a.p_home/over, a.p_draw/over, a.p_away/over

    # blend, then renormalise
    w = a.w_market
    bH = w*iH + (1-w)*mH; bD = w*iD + (1-w)*mD; bA = w*iA + (1-w)*mA
    s = bH + bD + bA; bH, bD, bA = bH/s, bD/s, bA/s

    print(f"\nLIVE  {a.home} {a.hs}-{a.as_} {a.away}  @ {a.minute:.0f}'"
          + (f"  (RED {a.redcard})" if a.redcard else ""))
    print(f"  market overround (vig): {(over-1)*100:+.1f}%   blend weight on market: {w:.0%}\n")
    hdr = f"  {'outcome':<16}{'MODEL':>9}{'MARKET(devig)':>15}{'price paid':>12}{'BLEND fair':>12}{'edge':>9}"
    print(hdr); print("  " + "-"*(len(hdr)-2))
    for lbl, m, im, price, b in [(f"{a.home}", mH, iH, a.p_home, bH),
                                 ("DRAW", mD, iD, a.p_draw, bD),
                                 (f"{a.away}", mA, iA, a.p_away, bA)]:
        edge = b - price
        flag = "  BUY" if edge > 0.04 else ("  SELL/avoid" if edge < -0.04 else "")
        print(f"  {lbl:<16}{m*100:>8.1f}%{im*100:>14.1f}%{price*100:>11.0f}¢"
              f"{b*100:>11.1f}%{edge*100:>+8.1f}¢{flag}")

    print(f"\n  >>> PROBABILITY OF A DRAW (blended fair): {bD*100:.1f}%  "
          f"(fair price {bD*100:.0f}¢, fair odds {american(bD)})")
    print(f"      model alone {mD*100:.1f}% | market alone {iD*100:.1f}% | you pay {a.p_draw*100:.0f}¢")
    de = bD - a.p_draw
    print("      VERDICT: " + ("DRAW is underpriced -> value BUY" if de > 0.04 else
          "DRAW is overpriced -> don't buy / consider selling" if de < -0.04 else
          "DRAW fairly priced -> no clear edge"))

if __name__ == "__main__":
    main()
