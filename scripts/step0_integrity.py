#!/usr/bin/env python3
"""
STEP 0 - DATA INTEGRITY CHECK for the Fjelstul World Cup Database.

For every CSV: row count, columns, dtypes, null rates, 3-row sample.
Flags Git-LFS stub files. Checks for the Transfermarkt-style player tables
(player-level features) that are NOT part of this dataset, and reports the
modeling capability lost. Counts distinct national team_ids and 'current'
player states, mapped onto the columns that actually exist here.
"""
import os, json, datetime
import pandas as pd
import numpy as np

DATA_DIR = "/Users/vivaansandwar/Downloads/worldcup-1.1.0/data-csv"
OUT = "/Users/vivaansandwar/Downloads/wc2026_model/outputs/step0_integrity_summary.json"

# Player-level tables from a Transfermarkt-style dataset (not included in Fjelstul).
PLAYER_LEVEL_FILES = [
    "player_national_performances.csv", "player_profiles.csv",
    "player_injuries.csv", "player_teammates_played_with.csv",
    "team_competitions_seasons.csv",
]
LOST_CAPABILITY = {
    "player_national_performances.csv": "per-player national caps/goals -> squad experience features",
    "player_profiles.csv": "player citizenship/DOB/market value -> team_id map, age & value features",
    "player_injuries.csv": "injury days_missed/games_missed -> availability/injury-risk features",
    "player_teammates_played_with.csv": "minutes/goals together -> squad-cohesion features",
    "team_competitions_seasons.csv": "club league strength -> club-pedigree weighting",
}


def is_lfs_stub(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(120).startswith("version https://git-lfs")
    except Exception:
        return False


def analyze(path):
    fname = os.path.basename(path)
    df = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=["", "NA"])
    n = len(df)
    cols = []
    for c in df.columns:
        s = df[c]
        nn = s.dropna()
        # dtype inference
        dt = "str"
        if len(nn):
            if nn.str.fullmatch(r"-?\d+").all():
                dt = "int"
            elif nn.str.fullmatch(r"-?\d+(\.\d+)?").all():
                dt = "float"
            elif nn.str.fullmatch(r"\d{4}-\d{2}-\d{2}").all():
                dt = "date"
            elif set(nn.unique()) <= {"0", "1", "TRUE", "FALSE", "True", "False"}:
                dt = "bool/0-1"
        cols.append({
            "name": c, "dtype": dt,
            "null_rate": round(float(s.isna().mean()), 4),
            "n_unique": int(nn.nunique()),
        })
    sample = df.head(3).to_dict("records")
    return {"file": fname, "size_bytes": os.path.getsize(path),
            "is_lfs_stub": is_lfs_stub(path), "rows": n, "ncol": len(df.columns),
            "columns": cols, "sample3": sample, "_df": df}


def main():
    files = sorted(f for f in os.listdir(DATA_DIR) if f.endswith(".csv"))
    print("=" * 84)
    print("STEP 0 - DATA INTEGRITY CHECK | Fjelstul World Cup Database")
    print("dir:", DATA_DIR, "| files:", len(files),
          "| run:", datetime.datetime.now().isoformat(timespec="seconds"))
    print("=" * 84)

    summary, dfs = [], {}
    for fname in files:
        r = analyze(os.path.join(DATA_DIR, fname))
        dfs[fname] = r.pop("_df")
        summary.append(r)
        print(f"\n{'#'*82}\nFILE: {r['file']} | rows={r['rows']:,} cols={r['ncol']} "
              f"size={r['size_bytes']:,}B LFS_stub={r['is_lfs_stub']}\n{'-'*82}")
        for c in r["columns"]:
            flag = "  <== HIGH NULLS" if c["null_rate"] >= 0.30 else ""
            print(f"  {c['name']:<26} {c['dtype']:<9} null={c['null_rate']:6.1%} "
                  f"uniq={c['n_unique']:<6}{flag}")
        print("  sample(3):")
        for row in r["sample3"]:
            short = {k: (str(v)[:22] + "…" if len(str(v)) > 23 else v)
                     for k, v in list(row.items())[:8]}
            print("    ", short)

    # Player-level table check
    print("\n" + "=" * 84)
    print("PLAYER-LEVEL FILES (Transfermarkt-style) — needed for squad features")
    print("=" * 84)
    present = set(files)
    for f in PLAYER_LEVEL_FILES:
        st = "PRESENT" if f in present else "*** ABSENT ***"
        print(f"  {f:<42} {st}\n      lost: {LOST_CAPABILITY[f]}")

    # Entity counts, mapped to columns that DO exist:
    print("\n" + "=" * 84)
    print("STEP-0 ENTITY COUNTS (mapped to columns present in this dataset)")
    print("=" * 84)
    teams = dfs["teams.csv"]
    print(f"  distinct national team_ids (teams.csv):      {teams['team_id'].nunique()}")
    qt = dfs["qualified_teams.csv"]
    print(f"  distinct teams in qualified_teams.csv:       {qt['team_id'].nunique()}")
    players = dfs["players.csv"]
    print(f"  distinct players (players.csv):              {players['player_id'].nunique()}")
    print("  NOTE: there is NO career_state column / no CURRENT_NATIONAL_PLAYER flag here;")
    print("        this dataset is World-Cup-appearance based, not Transfermarkt career-state based.")
    # matches coverage
    m = dfs["matches.csv"]
    tr = dfs["tournaments.csv"]
    print(f"\n  matches.csv rows:                            {len(m):,}")
    if "year" in tr.columns:
        yrs = sorted(tr["year"].dropna().astype(int).tolist())
        print(f"  tournaments covered:                         {len(tr)} ({yrs[0]}–{yrs[-1]})")
    print(f"  date range of matches:                       "
          f"{m['match_date'].min()} .. {m['match_date'].max()}"
          if "match_date" in m.columns else "")

    with open(OUT, "w") as f:
        json.dump(summary, f, indent=2)
    print("\nSaved ->", OUT)


if __name__ == "__main__":
    main()
