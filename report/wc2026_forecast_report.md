# 2026 FIFA World Cup — Predictive Model Report

**Author:** sports-data-science pipeline · **Date:** 14 June 2026 (3 days into the tournament)
**Method:** time-decayed Dixon-Coles bivariate-Poisson goals model → 50,000-iteration Monte Carlo bracket simulation
**Forecast horizon:** the 8 already-played group matches are held fixed; the remaining 96 matches are simulated.

> **This is a forecast from aggregate data, not a guarantee.** It is honestly calibrated (Brier 0.49 / 61.8 % out-of-sample 3-way accuracy on 1,315 recent internationals), but international football is high-variance and several documented limitations below mean real-world error bars are wide. Treat the percentages as well-reasoned estimates, not certainties.

---

## 0. The single most important finding — read this first

**The data folder `worldcup-1.1.0` is the Fjelstul World Cup Database (historical World Cup results, 1930–2022). It is NOT the Transfermarkt-style player dataset that the task's STEP 0–3 instructions assume.** None of the five files the prompt references exist here:

| Prompt-assumed file | Status | Capability lost |
|---|---|---|
| `player_national_performances.csv` | **absent** | per-player caps/goals → squad-experience features |
| `player_profiles.csv` | **absent** | citizenship / DOB / **market value** → team-id map, age & value features |
| `player_injuries.csv` | **absent** | injury days/games missed → availability features |
| `player_teammates_played_with.csv` | **absent** | minutes/goals together → squad-cohesion features |
| `team_competitions_seasons.csv` | **absent** | club league strength → club-pedigree weighting |

There are also **no Git-LFS stub files** — all 27 Fjelstul CSVs are real and complete. So the limitation is not "missing LFS blobs"; it is that **this dataset cannot support squad-value / age / injury / cohesion / club-pedigree features at all.** Rather than fabricate them, every such column in `team_features.csv` is emitted explicitly as `NA_no_source`.

**What I did instead (to maximize accuracy as requested):** I used the Fjelstul data for what it is genuinely good at (historical World Cup pedigree, host effects, format/structure), and I **augmented** it with a large, public, freely-licensed corpus of **49,477 international match results, 1872–2026** (martj42/international_results), which is what actually drives a modern strength model. Every external data point is scraped, cross-validated, and source-cited.

---

## 1. Top-10 title favourites

From 50,000 simulations (full file: `outputs/per_team_outcomes.csv`):

| # | Country | Group | **Win cup** | Reach final | Reach SF | Reach QF | Advance group |
|--:|---------|:---:|--:|--:|--:|--:|--:|
| 1 | **Brazil** | C | **14.6 %** | 23.2 % | 36.4 % | 52.7 % | 97.9 % |
| 2 | **Argentina** | J | **13.3 %** | 21.0 % | 32.9 % | 47.6 % | 97.0 % |
| 3 | **Spain** | H | **12.7 %** | 21.4 % | 33.5 % | 46.6 % | 97.4 % |
| 4 | **England** | L | **7.3 %** | 13.1 % | 22.9 % | 39.8 % | 94.8 % |
| 5 | **France** | I | **5.8 %** | 11.5 % | 21.5 % | 36.9 % | 91.8 % |
| 6 | **Portugal** | K | **5.7 %** | 11.2 % | 20.9 % | 37.0 % | 90.3 % |
| 7 | **Colombia** | K | **5.3 %** | 10.4 % | 19.5 % | 35.3 % | 89.2 % |
| 8 | **Germany** | E | **4.7 %** | 9.6 % | 19.5 % | 35.6 % | 95.3 % |
| 9 | **Belgium** | G | **3.7 %** | 8.1 % | 15.9 % | 33.1 % | 89.0 % |
| 10 | **Uruguay** | H | **3.4 %** | 7.3 % | 14.6 % | 26.8 % | 89.2 % |

**Highest group-advancement odds:** Mexico 98.7 % and USA 98.3 % (host advantage + favourable groups). **Lowest:** Haiti 7.2 % (drawn with Brazil), Curaçao 14.5 %, Cape Verde 26.8 %.

---

## 2. Method

### 2.1 Data sources (all cross-validated, source-cited)
- **Fjelstul World Cup Database** (`worldcup-1.1.0/data-csv`, 27 CSVs, 1930–2022): historical pedigree, host effects, format.
- **martj42/international_results** (49,477 matches, 1872–2026): the strength-model backbone; also contains the 72 scheduled 2026 group fixtures (8 already played).
- **Wikipedia / MLSSoccer / ESPN / CBS** (June 2026): official group draw (A–L), seeding pots, FIFA rankings, the exact Round-of-32→Final bracket, played results, and outright market odds.
- All 48 qualified nations join cleanly to the results corpus (≥ 53 matches since 2018; **zero unmatched**).

### 2.2 Strength model — Dixon-Coles bivariate Poisson (primary, generative)
Each team gets an **attack** and **defence** rating; globals are a baseline, a **home advantage** (applied only at non-neutral venues), and the Dixon-Coles low-score correlation ρ. Fit by **time-decayed, ridge-regularised weighted maximum likelihood** (half-life **5 years**, selected on validation) so recent and competitive matches count more (a friendly is weighted 0.4× a World Cup match). Expected goals for a fixture:

```
log λ_home = c + attack_home − defence_away + γ·(home advantage)
log λ_away = c + attack_away − defence_home
```

A complementary **World-Football-Elo** rating (margin-of-victory & importance aware) is computed as a feature and a baseline; DC-strength and Elo correlate **0.97**.

### 2.3 Why not the deep-learning / in-play model the prompt asked about
**Honest method-fit statement:** these inputs are career- and match-**aggregate** results. There are **no event timelines, no tracking/positional data, no possession/pass sequences.** A sequential or spatial deep-learning model (RNN/transformer for in-play or xG-from-tracking) **is not supported by this data and would be a fabrication of capability.** A feed-forward NN benchmark was built instead (below). *If* event/tracking data were added later, it would plug in at the per-match scoreline step — replacing the Poisson means λ with a learned sequence model — without changing the simulation layer.

### 2.4 Benchmarks (do they beat Dixon-Coles?)
Trained on the same DC-derived features, evaluated on the same held-out window:

| Model | Brier ↓ | Log-loss ↓ | Accuracy ↑ |
|---|--:|--:|--:|
| **Dixon-Coles (primary)** | 0.488 | 0.834 | 61.8 % |
| Elo → logistic | 0.496 | 0.842 | 60.5 % |
| Gradient-boosted (HistGBM) | 0.485 | 0.826 | 61.9 % |
| **Feed-forward NN (MLP)** | 0.484 | 0.824 | 62.0 % |

**Verdict:** the GBM and NN improve log-loss by barely ~1 % over Dixon-Coles, and only because they are fed DC features — i.e. **the extra complexity does not help meaningfully and risks overfitting the 16.5k-row training set.** Dixon-Coles is retained as the primary engine because it is generative (produces full scorelines for the simulation), interpretable, and statistically efficient. *(Note: sklearn's `MLPClassifier`/`HistGradientBoosting` stand in for Keras/PyTorch & XGBoost, which could not be installed under a hard disk-space constraint on this machine; they fill the identical feed-forward / boosted-tree benchmark roles.)*

### 2.5 Monte Carlo simulation (50,000 iterations)
- Real format: 12 groups → top 2 + 8 best thirds → R32 → R16 → QF → SF → Final.
- **Group matches:** scorelines sampled as independent Poisson with DC means (ρ correction shifts W/D/L by < 0.4 pp; used in the reported per-fixture probabilities but omitted in sampling).
- **Knockouts:** resolved by an **analytical** advance probability covering regulation (Skellam), 30′ extra time (Skellam at ⅓ rates) and a near-coin-flip shootout with a mild strength tilt.
- **Best-third allocation:** thirds are matched to the 8 R32 third-slots by a legal bipartite matching respecting each slot's allowed source groups — **verified to produce a legal assignment for all 495 possible combinations.**
- **Validated invariants** (exact): Σ P(advance)=32, Σ P(R16)=16, Σ P(QF)=8, Σ P(SF)=4, Σ P(final)=2, Σ P(win)=1.

---

## 3. Calibration (is the model honest?)

Out-of-sample on 1,315 internationals (Jan 2025 – Jun 2026). The model is **well-calibrated and, if anything, slightly under-confident** at the high end (`outputs/calibration_reliability.csv`):

| Predicted confidence | Empirical accuracy | n |
|---|---|---|
| 0.50–0.60 | 0.540 | 261 |
| 0.60–0.70 | 0.670 | 212 |
| 0.70–0.80 | 0.873 | 157 |
| 0.80–0.90 | 0.908 | 109 |
| 0.90–1.00 | 0.985 | 67 |

---

## 4. Model vs. the betting market (external sanity check)

Normalised to compare (`outputs/wc2026_market_odds.csv`):

| Team | Market | Model | Δ (model − market) |
|---|--:|--:|--:|
| Spain | 13.8 % | 12.7 % | −1.1 pp |
| **France** | 12.9 % | 5.8 % | **−7.0 pp** |
| England | 9.5 % | 7.3 % | −2.2 pp |
| **Brazil** | 7.6 % | 14.6 % | **+7.0 pp** |
| **Argentina** | 7.6 % | 13.3 % | **+5.7 pp** |
| Colombia | 1.8 % | 5.3 % | +3.5 pp |

The model agrees closely with the market on most teams but **systematically over-rates CONMEBOL (Brazil, Argentina, Colombia) and under-rates France.** This is the clearest signature of the missing data: France's value to the market comes largely from elite **squad market value / individual talent**, which a results-only model cannot see, while South American sides bank strong results in fiercely competitive qualifiers and Copa América. See §6.

---

## 5. Key assumptions
1. **Host advantage:** USA/Mexico/Canada receive the full fitted home advantage when playing in their own country (group stage) and half of it in knockouts (uncertain venue).
2. **Time decay:** 5-year half-life on match weights (validation-selected); competitive matches weighted above friendlies.
3. **Group E = Ivory Coast, not Costa Rica.** One stale article listed Costa Rica; the official fixtures *and* draw pots both have Ivory Coast (Costa Rica did not qualify). Resolved in favour of the two consistent sources.
4. **Penalty shootouts** are treated as ~50/50 with a small tilt toward the stronger side.
5. **Group tiebreakers:** points → GD → goals for → head-to-head → drawing of lots (random); a faithful, always-legal stand-in for FIFA's full procedure.

## 6. Data limitations & biggest uncertainties
- **No squad/market-value/age/injury/cohesion/club data** (files absent). This is the largest source of bias — most visibly the **France gap** and CONMEBOL over-rating in §4.
- **Confederation isolation:** results-based ratings can't fully separate "strong team" from "weak opponents." Teams that farm wins in weaker confederations (some AFC/CAF/CONMEBOL sides) may be mildly over-rated for cross-confederation knockouts. FIFA rank (which carries cross-confederation info) is reported alongside as a check but is **not** baked into the generative model, so the model stays purely results-driven and the bias is disclosed rather than hidden.
- **Squad join is low by construction:** of 1,248 scraped 2026 squad players, only **316 (25.3 %)** match a Fjelstul `player_id` (311 confirmed by name+DOB) — because Fjelstul only contains past-World-Cup players. The 932 unmatched are the new generation; this is expected, not an error, and these rows do not feed the model.
- **`country_team_map.csv` confidence:** 43/48 high-confidence exact matches, 1 alias (DR Congo ↔ Fjelstul "Zaire"), **4 debutants with no Fjelstul history** (Cape Verde, Curaçao, Jordan, Uzbekistan) — their strength comes entirely from the recent-results corpus.
- **Small played sample:** only 8 of 104 matches are fixed; nearly the whole tournament is still probabilistic, so early upsets can swing the bracket substantially.

## 7. Honest accuracy statement
Out-of-sample 3-way accuracy is **61.8 %** with **Brier 0.49 / log-loss 0.83**, competitive with public football models and well-calibrated. But a single World Cup is one noisy draw from this distribution: the eventual champion is most likely *not* the 14.6 % favourite — there is an **~85 % chance someone other than Brazil wins.** Use the probabilities comparatively (who is more likely than whom), not as predictions of certainty.

---

## 8. Deliverables & reproducibility

All in `outputs/`:

| File | Step | Contents |
|---|---|---|
| `step0_integrity_summary.json` | 0 | per-CSV rows/cols/dtypes/null-rates |
| `country_team_map.csv` | 1 | 48 nations → Fjelstul team_id, confederation, confidence |
| `wc2026_groups.csv` | 2 | groups A–L, FIFA rank, pot, confederation |
| `wc2026_fixtures.csv` | 2 | all 104 matches (72 group + 32 knockout slots), results filled |
| `wc2026_squads.csv` | 2 | 1,248 players, fuzzy-joined to `player_id` |
| `wc2026_market_odds.csv` | 2 | market odds + model comparison |
| `team_features.csv` | 3 | 48 teams × 33 columns (ratings, form, WC pedigree; unavailable cols flagged) |
| `fitted_ratings.json` | 3 | final DC + Elo parameters |
| `model_validation.json` · `calibration_reliability.csv` · `feature_importances.csv` | 4 | validation, calibration, importances |
| `per_team_outcomes.csv` | 5 | per-team P(advance/R16/QF/SF/final/win), expected finish |
| `simulated_match_predictions.csv` | 5 | 64 remaining group fixtures: P(H/D/A), expected & most-likely score |

> **Knockout fixtures:** `simulated_match_predictions.csv` covers the 64 concrete remaining **group** fixtures. Knockout matchups are not yet determined (they depend on group outcomes), so knockout predictions are expressed as the round-reach probabilities in `per_team_outcomes.csv` rather than fixed head-to-heads.

**Reproduce end-to-end:** `python scripts/run_all.py --n 50000` (≈ 18 s; requires `pip install -r requirements.txt` and the two scraped inputs in `scraped/`). Scripts: `wc_lib.py` (canonical data), `ratings.py` (DC + Elo), `step0`–`step5`, `step2b/2c`, `run_all.py`.
