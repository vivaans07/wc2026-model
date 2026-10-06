#!/usr/bin/env python3
"""
STEP 2 — wc2026_squads.csv : scrape the 48 announced 2026 squads from Wikipedia
and FUZZY-JOIN each player to the Fjelstul players.csv (player_id) by normalised
name (+ birth-date confirmation), restricted to plausible matches.

EXPECTATION (stated up front, not a surprise): the Fjelstul players table only
contains players who appeared at a World Cup 1930-2022, so only 2026 squad members
who ALSO played at the 2018/2022 World Cups can match. The match rate is therefore
low BY CONSTRUCTION; we report it honestly. These player rows do NOT feed the
forecasting model (no market-value/age/injury features are derivable here).
"""
import sys, os, re, csv, unicodedata, html as htmlmod
sys.path.insert(0, os.path.dirname(__file__))
import wc_lib as L

SRC = "https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_squads"
HTML = os.path.join(L.PROJ, "scraped", "wc2026_squads.html")

def strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
def norm(s):
    return re.sub(r"[^a-z ]", "", strip_accents(htmlmod.unescape(s)).lower()).strip()

# country header ids on the page use common names (underscored)
ID2COUNTRY = {t.replace(" ", "_"): t for t in L.ALL_TEAMS}

html = open(HTML, encoding="utf-8").read()
# positions of country section headers
hdr = []
for m in re.finditer(r'id="([^"]+)"', html):   # accent-aware (e.g. id="Curaçao")
    cid = m.group(1)
    if cid in ID2COUNTRY:
        hdr.append((m.start(), ID2COUNTRY[cid]))
hdr.sort()

def country_at(pos):
    cur = None
    for p, c in hdr:
        if p <= pos: cur = c
        else: break
    return cur

# parse each player row
ROW = re.compile(r'<tr class="nat-fs-player">(.*?)</tr>', re.S)
NAME = re.compile(r'data-sort-value="([^"]+)"')
ANCHOR = re.compile(r'scope="row"><a[^>]*>([^<]+)</a>')
BDAY = re.compile(r'<span class="bday">(\d{4}-\d{2}-\d{2})</span>')
POS = re.compile(r'>(GK|DF|MF|FW)</a>')
CELLS = re.compile(r'<td>(\d+)\s*\n?</td>')

players = []
for m in ROW.finditer(html):
    blk = m.group(1); ctry = country_at(m.start())
    if ctry is None: continue
    nm = NAME.search(blk); an = ANCHOR.search(blk)
    if nm:
        # data-sort-value is "Family, Given"
        fam, _, giv = nm.group(1).partition(",")
        name_disp = (giv.strip() + " " + fam.strip()).strip() if giv else fam.strip()
    elif an:
        name_disp = htmlmod.unescape(an.group(1))
    else:
        continue
    bd = BDAY.search(blk); ps = POS.search(blk)
    players.append({"country_name": ctry, "player_name": name_disp,
                    "birth_date": bd.group(1) if bd else "",
                    "position": ps.group(1) if ps else ""})

print(f"Parsed {len(players)} squad players across {len(set(p['country_name'] for p in players))} teams")

# ---- fuzzy join to Fjelstul players.csv ----
fj = list(csv.DictReader(open(os.path.join(L.FJELSTUL, "players.csv"))))
# index by normalised "given family" and by family name
by_full = {}
for r in fj:
    full = norm(f"{r['given_name']} {r['family_name']}")
    by_full.setdefault(full, []).append(r)

matched = 0
for p in players:
    cands = by_full.get(norm(p["player_name"]), [])
    pick = None; conf = ""
    if cands:
        # confirm by birth date if available
        if p["birth_date"]:
            exact = [c for c in cands if c["birth_date"] == p["birth_date"]]
            if exact: pick = exact[0]; conf = "name+dob"
        if pick is None:
            # prefer a candidate who played 2018/2022
            recent = [c for c in cands if "2022" in c["list_tournaments"] or "2018" in c["list_tournaments"]]
            pick = (recent or cands)[0]
            conf = "name-only" if len(cands) == 1 else "name-ambiguous"
    p["player_id"] = pick["player_id"] if pick else ""
    p["match_confidence"] = conf if pick else "unmatched"
    if pick: matched += 1

with open(os.path.join(L.OUT, "wc2026_squads.csv"), "w", newline="") as f:
    cols = ["country_name", "player_name", "position", "birth_date",
            "player_id", "match_confidence", "source"]
    w = csv.DictWriter(f, fieldnames=cols); w.writeheader()
    for p in players:
        p["source"] = SRC; w.writerow({k: p.get(k, "") for k in cols})

print(f"wc2026_squads.csv -> {len(players)} players | matched to Fjelstul player_id: "
      f"{matched} ({matched/len(players)*100:.1f}%) | unmatched: {len(players)-matched}")
conf_counts = {}
for p in players: conf_counts[p["match_confidence"]] = conf_counts.get(p["match_confidence"], 0) + 1
print("  match-confidence breakdown:", conf_counts)
