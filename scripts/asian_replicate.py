#!/usr/bin/env python3
"""
asian_replicate.py — build an "Asian" bet on a BINARY exchange (Polymarket/Kalshi)
by splitting your stake across the Yes/No contracts they actually list.

Binary markets can't natively do Asian handicaps (no push/refund, no quarter
lines). But two of the most useful Asian bets can be replicated EXACTLY:

  * Draw No Bet (Asian 0.0):  win -> win, draw -> stake refunded, lose -> lose.
        Recipe: spend C*(1 - draw_price) on TEAM-WIN, C*draw_price on DRAW.
  * Double chance (Asian +0.5): win OR draw -> win, lose -> lose.
        Recipe: spend C*tw/(tw+dr) on TEAM-WIN, C*dr/(tw+dr) on DRAW.

Half-line Asian bets need NO construction — just buy the binary directly:
  Asian -0.5  = "Team to win"            (moneyline Yes)
  Asian -1.5  = "Team wins by 2+"        (a -1.5 goal-spread market, if listed)
  Asian O/U (half line) = the binary Over/Under market
Whole-line (-1.0) push bets and quarter lines (-0.25/-0.75) can't be done cleanly
on a binary exchange — use a real Asian sportsbook (e.g. Pinnacle) for those.

Usage:
  python asian_replicate.py --bet dnb --team_price 0.55 --draw_price 0.27 --stake 20
  python asian_replicate.py --bet dc  --team_price 0.55 --draw_price 0.27 --stake 20
"""
import argparse

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bet", choices=["dnb", "dc"], required=True,
                    help="dnb = Draw No Bet (Asian 0.0); dc = double chance (Asian +0.5)")
    ap.add_argument("--team_price", type=float, required=True, help="binary YES price for the team to WIN (0-1)")
    ap.add_argument("--draw_price", type=float, required=True, help="binary YES price for the DRAW (0-1)")
    ap.add_argument("--stake", type=float, default=20.0)
    a = ap.parse_args()
    tw, dr, C = a.team_price, a.draw_price, a.stake

    print(f"\nReplicating an Asian bet on a binary exchange  (team-win {tw*100:.0f}¢, draw {dr*100:.0f}¢, stake ${C:.2f})")
    if a.bet == "dnb":
        c_team = C * (1 - dr); c_draw = C * dr
        win_payout = c_team / tw
        print("\n  ASIAN 0.0 / DRAW NO BET — recipe:")
        print(f"    • Buy ${c_team:.2f} of 'TEAM WINS'   ({c_team/tw:.2f} shares)")
        print(f"    • Buy ${c_draw:.2f} of 'DRAW'        ({c_draw/dr:.2f} shares)")
        print("\n  Outcomes:")
        print(f"    Team WINS  -> ${win_payout:.2f}   (profit +${win_payout - C:.2f})")
        print(f"    DRAW       -> ${C:.2f}   (refund / push — break even)")
        print(f"    Team LOSES -> $0.00  (lose ${C:.2f})")
        eff = tw / (tw + (1 - tw - dr) if (1-tw-dr)>0 else tw)  # rough
        impl = win_payout > 0 and C / win_payout
        print(f"\n  Effective DNB win-probability you're paying: ~{impl*100:.1f}%  (fair odds {('+'+str(round((win_payout/C-1)*100)))})")
    else:
        denom = tw + dr
        c_team = C * tw / denom; c_draw = C * dr / denom
        payout = C / denom
        print("\n  ASIAN +0.5 / DOUBLE CHANCE (team win OR draw) — recipe:")
        print(f"    • Buy ${c_team:.2f} of 'TEAM WINS'   ({c_team/tw:.2f} shares)")
        print(f"    • Buy ${c_draw:.2f} of 'DRAW'        ({c_draw/dr:.2f} shares)")
        print("\n  Outcomes:")
        print(f"    Team WINS or DRAW -> ${payout:.2f}   (profit +${payout - C:.2f})")
        print(f"    Team LOSES        -> $0.00  (lose ${C:.2f})")
        print(f"\n  Implied win-probability you're paying: {C/payout*100:.1f}%  (fair odds {('+'+str(round((payout/C-1)*100)) if payout/C-1<1 else '-'+str(round(100/(payout/C-1))))})")
    print("\n  NOTE: you must be able to buy BOTH the team-win and the draw as separate")
    print("        Yes/No contracts on the platform. If only a 2-way (no draw) market")
    print("        exists, true DNB/AH isn't constructible there.")

if __name__ == "__main__":
    main()
