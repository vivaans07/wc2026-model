#!/usr/bin/env python3
"""
run_all.py — reproduce the entire 2026 World Cup forecast end to end.

Pipeline (each step writes to ../outputs/):
  step0_integrity.py   data-integrity audit of the Fjelstul CSVs
  step1_2_context.py   country_team_map / wc2026_groups / wc2026_fixtures
  step2b_odds.py       wc2026_market_odds  (benchmark)            [needs step5 first]
  step2c_squads.py     wc2026_squads       (scrape + fuzzy join)
  step3_features.py    team_features + fitted_ratings  (FINAL DC + Elo)
  step4_model.py       model validation + calibration + importances
  step5_simulate.py    per_team_outcomes + simulated_match_predictions

Prerequisites (already fetched into ../scraped/ by the original run; re-fetch if
missing): intl_results.csv (martj42), wc2026_squads.html (Wikipedia).

Usage:  python run_all.py [--n 50000]
"""
import subprocess, sys, os, argparse, time

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

def run(script, *args):
    print(f"\n{'='*70}\n>>> {script} {' '.join(args)}\n{'='*70}")
    t = time.time()
    r = subprocess.run([PY, os.path.join(HERE, script), *args])
    if r.returncode != 0:
        sys.exit(f"FAILED: {script}")
    print(f"<<< {script} done in {time.time()-t:.1f}s")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", default="50000", help="Monte Carlo iterations")
    args = ap.parse_args()
    # scraped inputs check
    scr = os.path.join(HERE, "..", "scraped")
    for f in ("intl_results.csv", "wc2026_squads.html"):
        if not os.path.exists(os.path.join(scr, f)):
            print(f"WARNING: scraped/{f} missing — re-fetch (see report data-sources).")

    run("step0_integrity.py")
    run("step1_2_context.py")
    run("step3_features.py")          # fits FINAL ratings -> needed by 4,5
    run("step4_model.py")             # validation/calibration
    run("step5_simulate.py", "--n", args.n)
    run("step2c_squads.py")
    run("step2b_odds.py")             # uses per_team_outcomes from step5
    print("\nALL STEPS COMPLETE. Outputs in ../outputs/")

if __name__ == "__main__":
    main()
