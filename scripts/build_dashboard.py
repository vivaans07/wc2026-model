"""Build the static results dashboard (docs/index.html) from the files in outputs/.

Run:  python scripts/build_dashboard.py
Serve: GitHub Pages -> Settings -> Pages -> Deploy from branch: main, folder: /docs
"""
import csv
import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"
DOCS = ROOT / "docs"


def rows(name):
    with open(OUT / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


teams = [
    {
        "team": r["country"], "group": r["group"], "conf": r["confederation"],
        "rank": int(num(r["fifa_rank"]) or 0),
        "adv": num(r["P_advance_group"]), "r16": num(r["P_reach_R16"]), "qf": num(r["P_reach_QF"]),
        "sf": num(r["P_reach_SF"]), "final": num(r["P_reach_final"]), "win": num(r["P_win_cup"]),
    }
    for r in rows("per_team_outcomes.csv")
]
teams.sort(key=lambda t: -t["win"])

clv = [
    {
        "date": r["date"], "match": r["match"], "pick": r["pick"],
        "model": num(r["model_prob"]), "open": num(r["open_prob"]), "close": num(r["close_prob"]),
        "clv": num(r["clv_pct"]),
    }
    for r in rows("clv_full_audit.csv") if num(r["clv_pct"]) is not None
]
clv.sort(key=lambda r: r["date"])

calib = [
    {"lo": num(r["bin_lo"]), "hi": num(r["bin_hi"]), "n": int(num(r["n"])),
     "conf": num(r["mean_confidence"]), "acc": num(r["empirical_accuracy"])}
    for r in rows("calibration_reliability.csv")
]

val = json.loads((OUT / "model_validation.json").read_text())
models = [{"name": "Dixon–Coles (this model)", **val["dixon_coles_best"]}]
labels = {"elo_logistic": "Elo + logistic", "gbm": "Gradient boosting", "nn_mlp": "Neural net (MLP)"}
for key, m in val.get("benchmarks", {}).items():
    models.append({"name": labels.get(key, key), **m})

vals = sorted(r["clv"] for r in clv)
beat = sum(v > 0 for v in vals)
median = vals[len(vals) // 2] if len(vals) % 2 else (vals[len(vals) // 2 - 1] + vals[len(vals) // 2]) / 2
dc = val["dixon_coles_best"]
summary = {
    "n_matches": len(clv), "beat": beat,
    "median_clv": float(Decimal(str(round(median, 2))).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)),
    "accuracy": dc["accuracy"], "brier": dc["brier"], "n_val": val["split"]["n_val_used"],
}

data = {"teams": teams, "clv": clv, "calib": calib, "models": models, "summary": summary}
html = (Path(__file__).with_name("dashboard_template.html").read_text(encoding="utf-8")
        .replace("/*__DATA__*/null", json.dumps(data, separators=(",", ":"))))
DOCS.mkdir(exist_ok=True)
(DOCS / "index.html").write_text(html, encoding="utf-8")
(DOCS / ".nojekyll").write_text("")
print(f"wrote docs/index.html  ({len(teams)} teams, {len(clv)} CLV picks, {len(calib)} calibration bins)")
