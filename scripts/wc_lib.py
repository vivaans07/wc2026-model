#!/usr/bin/env python3
"""
wc_lib.py — Canonical 2026 FIFA World Cup data + shared loaders/helpers.

All 2026 facts below were scraped and CROSS-VALIDATED from multiple sources in
June 2026 (see SOURCES). Where two sources disagreed (e.g. a stale article put
"Costa Rica" in Group E while the official fixtures + draw pots have Ivory Coast),
the value consistent with the official fixtures AND the draw pots was used.

Naming convention: we use the martj42/international-results spelling as the
CANONICAL key (because the modeling backbone is that results corpus), and map it
to the official/FIFA spelling and to the Fjelstul team_id.

Author: Vivaan Sandwar. Pure stdlib + (optionally) pandas elsewhere.
"""
import csv, os, math, datetime

# ----------------------------------------------------------------------------
PROJ = "/Users/vivaansandwar/Downloads/wc2026_model"
FJELSTUL = "/Users/vivaansandwar/Downloads/worldcup-1.1.0/data-csv"
RESULTS_CSV = os.path.join(PROJ, "scraped", "intl_results.csv")
OUT = os.path.join(PROJ, "outputs")

SOURCES = {
    "results_corpus": "https://github.com/martj42/international_results (results.csv, 1872–2026)",
    "groups": "https://en.wikipedia.org/wiki/2026_FIFA_World_Cup + MLSSoccer draw recap (Dec 5 2025 draw)",
    "seeding_pots": "https://en.wikipedia.org/wiki/2026_FIFA_World_Cup (draw pots, Nov 2025 FIFA ranking)",
    "knockout_bracket": "https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_knockout_stage",
    "results_jun13": "https://www.espn.com/soccer/scoreboard + Yahoo/SBS recaps (June 13 2026)",
    "fifa_ranking_playoff": "ESPN FIFA Men's Top 50, June 2026 (for the 6 playoff winners)",
}

# ----------------------------------------------------------------------------
# 12 official groups A–L. Canonical (martj42) names.
GROUPS = {
    "A": ["Mexico", "South Africa", "South Korea", "Czech Republic"],
    "B": ["Canada", "Switzerland", "Qatar", "Bosnia and Herzegovina"],
    "C": ["Brazil", "Morocco", "Scotland", "Haiti"],
    "D": ["United States", "Paraguay", "Australia", "Turkey"],
    "E": ["Germany", "Curaçao", "Ivory Coast", "Ecuador"],   # NOT Costa Rica (failed to qualify)
    "F": ["Netherlands", "Japan", "Tunisia", "Sweden"],
    "G": ["Belgium", "Egypt", "Iran", "New Zealand"],
    "H": ["Spain", "Cape Verde", "Saudi Arabia", "Uruguay"],
    "I": ["France", "Senegal", "Norway", "Iraq"],
    "J": ["Argentina", "Algeria", "Austria", "Jordan"],
    "K": ["Portugal", "Colombia", "Uzbekistan", "DR Congo"],
    "L": ["England", "Croatia", "Ghana", "Panama"],
}

# Pot (from official draw) and FIFA ranking feature.
# Ranks for 42 named teams = Nov-2025 seeding snapshot; the 6 playoff winners
# (Turkey, Sweden, Czech Republic, DR Congo, Iraq, Bosnia) = June-2026 snapshot.
POT = {}  # filled below
FIFA_RANK = {
    # Pot 1
    "Spain":1,"Argentina":2,"France":3,"England":4,"Brazil":5,"Portugal":6,
    "Netherlands":7,"Belgium":8,"Germany":9,"United States":14,"Mexico":15,"Canada":27,
    # Pot 2
    "Croatia":10,"Morocco":11,"Colombia":13,"Uruguay":16,"Switzerland":17,"Japan":18,
    "Senegal":19,"Iran":20,"South Korea":22,"Ecuador":23,"Austria":24,"Australia":26,
    # Pot 3
    "Norway":29,"Panama":30,"Egypt":34,"Algeria":35,"Scotland":36,"Paraguay":39,
    "Tunisia":40,"Ivory Coast":42,"Uzbekistan":50,"Qatar":51,"Saudi Arabia":60,"South Africa":61,
    # Pot 4 (named)
    "Jordan":66,"Cape Verde":68,"Ghana":72,"Curaçao":82,"Haiti":84,"New Zealand":86,
    # Pot 4 (playoff winners — June 2026 ranks)
    "Turkey":27,"Sweden":38,"Czech Republic":40,"DR Congo":46,"Iraq":57,"Bosnia and Herzegovina":64,
}
_POT1 = {"Spain","Argentina","France","England","Brazil","Portugal","Netherlands","Belgium",
         "Germany","United States","Mexico","Canada"}
_POT2 = {"Croatia","Morocco","Colombia","Uruguay","Switzerland","Japan","Senegal","Iran",
         "South Korea","Ecuador","Austria","Australia"}
_POT3 = {"Norway","Panama","Egypt","Algeria","Scotland","Paraguay","Tunisia","Ivory Coast",
         "Uzbekistan","Qatar","Saudi Arabia","South Africa"}
_POT4 = {"Jordan","Cape Verde","Ghana","Curaçao","Haiti","New Zealand","Turkey","Sweden",
         "Czech Republic","DR Congo","Iraq","Bosnia and Herzegovina"}
for _t in _POT1: POT[_t]=1
for _t in _POT2: POT[_t]=2
for _t in _POT3: POT[_t]=3
for _t in _POT4: POT[_t]=4

# 6 playoff winners (entered draw as placeholders; Pot 4)
PLAYOFF_WINNERS = {"Turkey","Sweden","Czech Republic","DR Congo","Iraq","Bosnia and Herzegovina"}

# Confederation per team.
CONFED = {
    # UEFA
    "Spain":"UEFA","France":"UEFA","England":"UEFA","Portugal":"UEFA","Netherlands":"UEFA",
    "Belgium":"UEFA","Germany":"UEFA","Croatia":"UEFA","Switzerland":"UEFA","Austria":"UEFA",
    "Norway":"UEFA","Scotland":"UEFA","Turkey":"UEFA","Sweden":"UEFA","Czech Republic":"UEFA",
    "Bosnia and Herzegovina":"UEFA",
    # CONMEBOL
    "Argentina":"CONMEBOL","Brazil":"CONMEBOL","Uruguay":"CONMEBOL","Colombia":"CONMEBOL",
    "Ecuador":"CONMEBOL","Paraguay":"CONMEBOL",
    # CONCACAF
    "United States":"CONCACAF","Mexico":"CONCACAF","Canada":"CONCACAF","Panama":"CONCACAF",
    "Haiti":"CONCACAF","Curaçao":"CONCACAF",
    # CAF
    "Morocco":"CAF","Senegal":"CAF","Egypt":"CAF","Algeria":"CAF","Tunisia":"CAF",
    "Ivory Coast":"CAF","Ghana":"CAF","South Africa":"CAF","Cape Verde":"CAF","DR Congo":"CAF",
    # AFC
    "Iran":"AFC","Japan":"AFC","South Korea":"AFC","Australia":"AFC","Saudi Arabia":"AFC",
    "Qatar":"AFC","Uzbekistan":"AFC","Jordan":"AFC","Iraq":"AFC",
    # OFC
    "New Zealand":"OFC",
}

# Map canonical (martj42) -> official/FIFA spelling, and -> Fjelstul team_id.
OFFICIAL_NAME = {
    "South Korea":"Korea Republic","Czech Republic":"Czechia","Ivory Coast":"Côte d'Ivoire",
    "Turkey":"Türkiye","DR Congo":"Congo DR","Iran":"IR Iran",
}
FJELSTUL_TEAM_ID = {
    "Algeria":"T-01","Argentina":"T-03","Australia":"T-04","Austria":"T-05","Belgium":"T-06",
    "Bosnia and Herzegovina":"T-08","Brazil":"T-09","Canada":"T-12","Colombia":"T-15",
    "Croatia":"T-17","Czech Republic":"T-19","Ecuador":"T-24","Egypt":"T-25","England":"T-27",
    "France":"T-28","Germany":"T-29","Ghana":"T-30","Haiti":"T-32","Iran":"T-36","Iraq":"T-37",
    "Ivory Coast":"T-40","Japan":"T-42","Mexico":"T-44","Morocco":"T-45","Netherlands":"T-46",
    "New Zealand":"T-47","Norway":"T-51","Panama":"T-52","Paraguay":"T-53","Portugal":"T-56",
    "Qatar":"T-57","Saudi Arabia":"T-61","Scotland":"T-62","Senegal":"T-63","South Africa":"T-68",
    "South Korea":"T-69","Spain":"T-71","Sweden":"T-72","Switzerland":"T-73","Tunisia":"T-76",
    "Turkey":"T-77","United States":"T-80","Uruguay":"T-81",
    "DR Congo":"T-85",  # Fjelstul lists this nation under its former name "Zaire"
    # Debutants with NO Fjelstul (World Cup) history:
    "Cape Verde":None,"Curaçao":None,"Jordan":None,"Uzbekistan":None,
}
# host nations (get partial home advantage at their venues)
HOSTS = {"United States","Mexico","Canada"}

# Played results — AUTO-DERIVED from the martj42 corpus (ground truth), not hand-typed,
# so it can never drift from the source (a hand-typed 0-0 once slipped in for
# Uzbekistan-Colombia, which was actually 1-3 — fixed by deriving from the corpus).
def _load_played_results():
    out = []
    try:
        with open(RESULTS_CSV) as f:
            for r in csv.DictReader(f):
                if (r["date"].startswith("2026") and r["tournament"] == "FIFA World Cup"
                        and r["home_score"] not in ("", "NA") and r["away_score"] not in ("", "NA")):
                    out.append((r["date"], r["home_team"], r["away_team"],
                                int(r["home_score"]), int(r["away_score"])))
    except FileNotFoundError:
        pass
    # de-dup (corpus can carry stray duplicate fixtures), keep first
    seen = set(); uniq = []
    for row in out:
        k = (row[0], row[1], row[2])
        if k not in seen: seen.add(k); uniq.append(row)
    return sorted(uniq)

PLAYED_RESULTS = _load_played_results()

# Knockout bracket (match 73–104). Slots use codes:
#   "1X"=winner group X, "2X"=runner-up group X, "3{ABC..}"=best-third from allowed groups,
#   "W##"=winner of match ##, "L##"=loser of match ##.
KNOCKOUT = {
    73:("2A","2B"), 74:("1E","3:ABCDF"), 75:("1F","2C"), 76:("1C","2F"),
    77:("1I","3:CDFGH"), 78:("2E","2I"), 79:("1A","3:CEFHI"), 80:("1L","3:EHIJK"),
    81:("1D","3:BEFIJ"), 82:("1G","3:AEHIJ"), 83:("2K","2L"), 84:("1H","2J"),
    85:("1B","3:EFGIJ"), 86:("1J","2H"), 87:("1K","3:DEIJL"), 88:("2D","2G"),
    89:("W74","W77"), 90:("W73","W75"), 91:("W76","W78"), 92:("W79","W80"),
    93:("W83","W84"), 94:("W81","W82"), 95:("W86","W88"), 96:("W85","W87"),
    97:("W89","W90"), 98:("W93","W94"), 99:("W91","W92"), 100:("W95","W96"),
    101:("W97","W98"), 102:("W99","W100"),
    103:("L101","L102"),  # third place
    104:("W101","W102"),  # final
}
# The 8 R32 matches that take a best-third, with the set of allowed source groups.
THIRD_SLOTS = {74:"ABCDF",77:"CDFGH",79:"CEFHI",80:"EHIJK",81:"BEFIJ",82:"AEHIJ",85:"EFGIJ",87:"DEIJL"}

ALL_TEAMS = [t for g in GROUPS.values() for t in g]
TEAM_GROUP = {t:g for g,ts in GROUPS.items() for t in ts}

# ----------------------------------------------------------------------------
def load_results(min_date="1990-01-01"):
    """Load the international results corpus as list of dicts (completed matches only)."""
    rows=[]
    with open(RESULTS_CSV) as f:
        for r in csv.DictReader(f):
            if r["home_score"] in ("","NA") or r["away_score"] in ("","NA"):
                continue
            if r["date"] < min_date:
                continue
            try:
                r["hs"]=int(r["home_score"]); r["as"]=int(r["away_score"])
            except ValueError:
                continue
            r["neutral"]=(r["neutral"].strip().upper()=="TRUE")
            rows.append(r)
    return rows

# Name reconciliation: martj42 already uses our canonical names, but guard a few
# historical aliases so older results join to the modern nation.
RESULT_ALIAS = {
    "Zaire":"DR Congo","Congo DR":"DR Congo","Czechoslovakia":"Czech Republic",
    "West Germany":"Germany","Yugoslavia":None,"Serbia and Montenegro":None,
    "Soviet Union":None,
}
def canon(name):
    return RESULT_ALIAS.get(name, name)

if __name__ == "__main__":
    print("Canonical 2026 WC data loaded.")
    print(f"  teams: {len(ALL_TEAMS)} | groups: {len(GROUPS)} | played: {len(PLAYED_RESULTS)}")
    assert len(ALL_TEAMS)==48, "expected 48 teams"
    assert all(t in FIFA_RANK for t in ALL_TEAMS), "missing FIFA rank"
    assert all(t in CONFED for t in ALL_TEAMS), "missing confederation"
    assert all(t in POT for t in ALL_TEAMS), "missing pot"
    assert all(t in FJELSTUL_TEAM_ID for t in ALL_TEAMS), "missing Fjelstul map"
    g=sum(h+a for *_,h,a in PLAYED_RESULTS)
    print(f"  played results: {len(PLAYED_RESULTS)} matches, {g} goals (auto-derived from corpus)")
    print("  ALL canonical-data integrity assertions PASSED.")
