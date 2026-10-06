# Learnings from the "san-solares" tipster (and what I changed)

Analysis of 14 captured picks (June 19–23, 2026). His settled record on them: **10–1–1**.

## His style, quantified
| Category | Picks | Total units |
|---|---|---|
| Goals (Over / BTTS / team total) | **8 / 14** | 9.65U |
| Favorite Asian handicaps (−1.0/−1.5/−2.5) | 5 / 14 | 10.0U |
| Moneyline | 1 / 14 | 1.0U |

Read of his method:
1. **Heavy attacking/goals lean** — over half his bets are that goals get scored (overs, BTTS, team totals). He's betting the tournament is high-scoring.
2. **Backs strong favorites to win *decisively*** vs weak opponents (Asian −1.0/−1.5/−2.5) — he trusts blowouts, not just wins.
3. **Conviction-based staking** — 0.65U to 4U; his biggest stake (Japan −1.0, 4U) hit 4–0. He concentrates money on his best spots.
4. **Discipline** — "Don't really love anything today, keep units low." He reduces exposure when there's no edge and doesn't force volume (1–4 picks/day).

## What I LEARNED and changed (data-grounded, baked in)
- **Goal-environment recalibration.** My model under-predicted goals (2.45 expected vs **2.98** actual over 44 WC games). I added a self-updating multiplier (currently **×1.113**, sample-shrunk) folded into the model baseline. Expected goals now 2.73 and rising toward reality as more games play. This was the single biggest reason I fought his (winning) over/margin picks — now corrected. *Calibrated to actual results, not to his picks.*
- **Effect:** mean disagreement with his prices fell 11.5% → 8.7%; my model now agrees with 5/14 of his calls (was 2/14), and the tournament forecast shows slightly more decisive favorites.
- **Adopted his discipline explicitly:** size by conviction tier, and **no-bet on true toss-ups** (already in the calibrated-hit-rate tiers).

## What I CANNOT learn (his private edge — not in my data)
The residual disagreement is concentrated on **favorite-margin Asian handicaps** (USA −1.0, Japan −1.0, France −2.5) that he wins and my model rates as thin. That edge almost certainly comes from inputs my dataset doesn't have:
- **Lineups / team news / rotation** (who's actually playing)
- **Attacking intent & motivation** (a must-win side chasing goals)
- **Sharp line movement** (following where pro money goes)
- **Shot-level xG** (he may use event data; mine is results-only)

I deliberately **did not** curve-fit my model to reproduce his picks — on a 14-pick sample that would overfit a hot streak and *destroy* real accuracy. I made the one principled change the data supports (goal environment) and documented the rest as his information advantage.

## How to actually capture more of his edge
1. **Add a lineup/team-news feed** before each match (the biggest gap).
2. **Track live line movement** and lean with sharp moves.
3. **Keep a running out-of-sample scorecard** of my model vs his — the only fair long-run test (his 10–1–1 is real but small).
4. Let the goal-environment multiplier keep self-updating daily (it will converge on the true tournament level).
