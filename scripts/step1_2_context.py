#!/usr/bin/env python3
"""
STEP 1 + STEP 2 — build canonical 2026 World Cup context CSVs.

  country_team_map.csv  (STEP 1, adapted): maps each of the 48 nations to its
      Fjelstul team_id + confederation + cross-naming, with a confidence flag.
      NOTE on STEP 1's original premise: it assumed mystery national team_ids in
      a Transfermarkt file 'player_national_performances.csv'. That file is NOT
      in this dataset; instead the Fjelstul 'teams.csv' already carries readable
      team names, so the id<->country resolution is direct (no scraping needed to
      RESOLVE ids — only to identify the 48 qualifiers). We cross-validate every
      mapping against the Fjelstul confederation code.

  wc2026_groups.csv     (STEP 2): group letter, country, FIFA rank, pot, confed.
  wc2026_fixtures.csv   (STEP 2): all 104 matches (72 group + 32 knockout slots),
      with played results filled and source citations.
"""
import csv, os, sys
sys.path.insert(0, os.path.dirname(__file__))
import wc_lib as L

OUT = L.OUT
os.makedirs(OUT, exist_ok=True)

# Load Fjelstul teams for confederation cross-validation.
fj_team = {}
with open(os.path.join(L.FJELSTUL, "teams.csv")) as f:
    for r in csv.DictReader(f):
        fj_team[r["team_id"]] = r
CF_CODE = {"CF-1":"AFC","CF-2":"CAF","CF-3":"CONCACAF","CF-4":"CONMEBOL","CF-5":"OFC","CF-6":"UEFA"}

# ---------------------------------------------------------------- country_team_map
rows = []
for t in sorted(L.ALL_TEAMS):
    tid = L.FJELSTUL_TEAM_ID[t]
    if tid is None:
        conf = L.CONFED[t]; src = "no Fjelstul WC history (debutant); confed hand-coded"
        confidence = "n/a-debutant"; xval = "—"
    else:
        fj = fj_team[tid]
        fj_conf = CF_CODE.get(fj["confederation_id"], "?")
        conf = L.CONFED[t]
        # cross-validate confederation
        if fj_conf == conf:
            xval = "confed-match"; confidence = "high"
        else:
            xval = f"confed-mismatch(Fjelstul={fj_conf})"; confidence = "medium"
        # name-change note
        if fj["team_name"] != t:
            src = f"Fjelstul team_name='{fj['team_name']}' (alias of {t})"
            if confidence == "high": confidence = "high-alias"
        else:
            src = "Fjelstul exact name match"
    rows.append({
        "team_id": tid or "",
        "country_name": t,
        "official_name": L.OFFICIAL_NAME.get(t, t),
        "fifa_confederation": conf,
        "source": src + " | " + L.SOURCES["groups"],
        "confidence": confidence,
        "confed_crossvalidation": xval,
    })
with open(os.path.join(OUT, "country_team_map.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
print(f"country_team_map.csv  -> {len(rows)} rows")
print("  confidence breakdown:",
      {k: sum(1 for r in rows if r['confidence']==k) for k in sorted(set(r['confidence'] for r in rows))})

# ---------------------------------------------------------------- wc2026_groups
grows = []
for letter, teams in L.GROUPS.items():
    for t in teams:
        grows.append({
            "group": letter, "country_name": t,
            "official_name": L.OFFICIAL_NAME.get(t, t),
            "fifa_rank": L.FIFA_RANK[t], "pot": L.POT[t],
            "confederation": L.CONFED[t],
            "is_host": int(t in L.HOSTS),
            "is_playoff_winner": int(t in L.PLAYOFF_WINNERS),
            "fifa_team_id": L.FJELSTUL_TEAM_ID[t] or "",
            "source": L.SOURCES["groups"],
        })
with open(os.path.join(OUT, "wc2026_groups.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(grows[0].keys())); w.writeheader(); w.writerows(grows)
print(f"wc2026_groups.csv     -> {len(grows)} rows ({len(L.GROUPS)} groups x 4)")

# ---------------------------------------------------------------- wc2026_fixtures
# 1) group-stage fixtures from martj42, with played results patched in.
played_lookup = {(d, h, a): (hs, as_) for (d, h, a, hs, as_) in L.PLAYED_RESULTS}
group_fix = []
_seen_fix = set()
with open(L.RESULTS_CSV) as f:
    for r in csv.DictReader(f):
        if r["date"].startswith("2026") and r["tournament"] == "FIFA World Cup":
            h, a = r["home_team"], r["away_team"]
            if (r["date"], h, a) in _seen_fix:
                continue                      # guard against duplicate corpus rows
            _seen_fix.add((r["date"], h, a))
            grp = L.TEAM_GROUP.get(h, "?")
            key = (r["date"], h, a)
            if key in played_lookup:
                hs, as_ = played_lookup[key]; status = "played"
            elif r["home_score"] not in ("", "NA"):
                hs, as_ = int(r["home_score"]), int(r["away_score"]); status = "played"
            else:
                hs, as_ = "", ""; status = "upcoming"
            group_fix.append({
                "match_id": "", "date": r["date"], "stage": f"Group {grp}",
                "group": grp, "home_country": h, "away_country": a,
                "venue": f"{r['city']}, {r['country']}",
                "actual_home_goals": hs, "actual_away_goals": as_, "status": status,
                "source": L.SOURCES["results_corpus"],
            })
group_fix.sort(key=lambda x: (x["date"], x["group"]))
for i, g in enumerate(group_fix, start=1):
    g["match_id"] = f"M{i:03d}"

# 2) knockout slots (matches 73–104) — teams TBD (depend on group outcomes).
ko_rows = []
STAGE = {**{m:"Round of 32" for m in range(73,89)}, **{m:"Round of 16" for m in range(89,97)},
         **{m:"Quarter-final" for m in range(97,101)}, 101:"Semi-final",102:"Semi-final",
         103:"Third place play-off",104:"Final"}
for m in range(73, 105):
    home, away = L.KNOCKOUT[m]
    ko_rows.append({
        "match_id": f"M{m:03d}", "date": "", "stage": STAGE[m], "group": "",
        "home_country": home, "away_country": away, "venue": "",
        "actual_home_goals": "", "actual_away_goals": "", "status": "upcoming",
        "source": L.SOURCES["knockout_bracket"],
    })
all_fix = group_fix + ko_rows
with open(os.path.join(OUT, "wc2026_fixtures.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(all_fix[0].keys())); w.writeheader(); w.writerows(all_fix)
n_play = sum(1 for g in group_fix if g["status"] == "played")
print(f"wc2026_fixtures.csv   -> {len(all_fix)} rows "
      f"({len(group_fix)} group [{n_play} played, {len(group_fix)-n_play} upcoming] "
      f"+ {len(ko_rows)} knockout slots)")
assert len(group_fix) == 72, "expected 72 group fixtures"
print("\nSTEP 1+2 context CSVs written OK.")
