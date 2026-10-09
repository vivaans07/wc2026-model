# 2026 FIFA World Cup — Predictive Model

A reproducible forecast of the 2026 FIFA World Cup (48 teams, 104 matches) built from
the **Fjelstul World Cup Database** (historical results 1930–2022) **augmented** with a
public corpus of 49,477 international results (1872–2026) and scraped, cross-validated
2026 context (groups, fixtures, bracket, rankings, odds).

**Engine:** time-decayed, ridge-regularised **Dixon-Coles bivariate-Poisson** goals
model (+ Elo, GBM, NN benchmarks) → **50,000-iteration Monte Carlo** of the real
12-group / best-thirds / R32→Final format, with the 8 already-played matches fixed.

➡️ **Read [`report/wc2026_forecast_report.md`](report/wc2026_forecast_report.md) first** —
it covers method, a critical data-mismatch finding, validation/calibration, top-10
favourites, and all limitations.

## Layout
```
scripts/   wc_lib.py (canonical 2026 data) · ratings.py (DC + Elo)
           step0_integrity · step1_2_context · step2b_odds · step2c_squads
           step3_features · step4_model · step5_simulate · run_all.py
scraped/   intl_results.csv (martj42) · wc2026_squads.html (Wikipedia)
outputs/   all 36 result CSV/JSON/XLSX deliverables
report/    wc2026_forecast_report.md
```

## Reproduce
```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python scripts/run_all.py --n 50000     # ~18s end-to-end
```

## Headline result (50k sims)
Brazil **14.6 %** · Argentina **13.3 %** · Spain **12.7 %** · England 7.3 % · France 5.8 %.
Out-of-sample accuracy 61.8 %, Brier 0.49, well-calibrated. *Forecast, not a guarantee.*

## Known limitations (see report §6)
No squad market-value / age / injury / cohesion / club data exist in this dataset
(those Transfermarkt-style files are absent), so the model is **results-only** — which
over-rates CONMEBOL and under-rates France vs. the market. Disclosed, not hidden.

## Project statistics

**Model & data**
- Engine: time-decayed (5-yr half-life), ridge-regularised **Dixon-Coles bivariate-Poisson** goals model, with an Elo cross-check and four recalibrations (goal-environment scaling, favorite-strength stretch = 1.20, market-value prior, xG substitution).
- Training corpus: **49,477** international results (1872–2026).
- Simulation: **50,000-iteration** Monte Carlo of the full 104-match bracket; **500,000 draws per match** for single-game scoreline distributions.
- Codebase: **33 Python modules, 4,712 lines**; 36 reproducible output files.

**Out-of-sample validation**
- 3-way (W/D/L) accuracy **61.8%**, Brier score **0.49**, log-loss and reliability curves confirm calibration.
- The favorite-strength stretch was selected by out-of-sample log-loss, correcting a systematic favorite-underrating bias.

**Market-efficiency / CLV layer**
- Integrated real prediction-market **closing lines** via the **Kalshi** candlestick API (free, no-auth) and **Polymarket** (Oddpool), plus **ESPN** and **API-Football** feeds.
- Full-tournament **Closing Line Value audit**: every pick graded under a pre-committed, no-cherry-pick rule across **92 matches** — beating the close on **64% (59/92)**, median **+4.5% CLV** (mean +18.2%, tail-inflated).
- CLV = `decimal(price_taken) × close_prob − 1`; beating the close measures forecast edge independent of any single result.

> Methodology demonstration, not a betting P&L — a 92-match sample is informative but not proof of a repeatable edge.

