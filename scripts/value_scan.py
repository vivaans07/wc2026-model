#!/usr/bin/env python3
"""
value_scan.py — cross-match the Dixon-Coles model against EVERY Polymarket market
for a slate, surfacing the bets with the biggest model edge (model prob - price).

For each game it derives model probabilities for ML / draw / spreads / totals /
team totals / BTTS / exact scores from the full score matrix, pulls all live
Polymarket markets via Oddpool, joins them, and prints +EV bets ranked by ROI.
Edge is RAW (vs the price you actually pay); apply your own motivation overlay.

Usage: python value_scan.py 2026-06-25
"""
import sys, os, re, csv, math, argparse
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
import predict_day as P
import oddpool_client as OP

ALIAS = {"Turkey": "Türkiye", "Ivory Coast": "Côte d'Ivoire"}

def model_markets(h, a, venue):
    hi, hj = P.host_adv(h, venue), P.host_adv(a, venue)
    M, lam, nu = P.score_matrix(h, a, hi, hj)
    n = M.shape[0]; HH, AA = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")
    tot, diff = HH + AA, HH - AA
    pr = lambda mask: float(M[mask].sum())
    m = {"xg": (lam, nu)}
    m["h_win"], m["draw"], m["a_win"] = pr(diff > 0), pr(diff == 0), pr(diff < 0)
    for L in (0.5, 1.5, 2.5, 3.5, 4.5, 5.5): m[f"over{L}"] = pr(tot > L)
    m["btts"] = pr((HH >= 1) & (AA >= 1))
    for L in (0.5, 1.5, 2.5): m[f"h_tt_o{L}"] = pr(HH > L); m[f"a_tt_o{L}"] = pr(AA > L)
    for s in (1.5, 2.5, 3.5): m[f"h_-{s}"] = pr(diff > s); m[f"a_-{s}"] = pr(-diff > s)
    m["exact"] = {(int(i), int(j)): float(M[i, j]) for i in range(7) for j in range(7)}
    return m

def parse(q, h, a):
    """Map a Polymarket question -> (model_key, human_label). YES side only."""
    ql = q.lower(); hh = h.lower(); aa = ALIAS.get(h, h).lower(); ax = a.lower(); axx = ALIAS.get(a, a).lower()
    def is_h(s): return hh in s or aa in s
    def is_a(s): return ax in s or axx in s
    mm = re.search(r"o/u (\d+\.\d+)\s*$", ql) or re.search(r": o/u (\d+\.\d+)\?", ql)
    if "end in a draw" in ql: return "draw", "Draw"
    if ql.startswith("spread:"):
        line = re.search(r"\(-(\d+\.\d+)\)", ql)
        if line:
            s = line.group(1); who = "h" if is_h(ql) else "a"
            return f"{who}_-{s}", f"{(h if who=='h' else a)} -{s}"
    tt = re.search(r":\s*(.+?)\s+o/u (\d+\.\d+)", ql)
    if tt and "corner" not in ql and "half" not in ql:
        team, line = tt.group(1).strip(), tt.group(2)
        who = "h" if is_h(team) else ("a" if is_a(team) else None)
        if who: return f"{who}_tt_o{line}", f"{(h if who=='h' else a)} team Over {line}"
    if mm and "corner" not in ql and "half" not in ql:
        return f"over{mm.group(1)}", f"Over {mm.group(1)} goals"
    if "both teams to score" in ql and not re.search(r"half|1st|2nd|first|second", ql):
        return "btts", "Both Teams To Score"
    ex = re.search(r"exact score:\s*(.+?)\s+(\d+)\s*-\s*(\d+)\s+(.+?)\?", ql)
    if ex: return ("exact", int(ex.group(2)), int(ex.group(3))), f"Exact {ex.group(2)}-{ex.group(3)}"
    return None, None

def scan(date, games, motiv):
    print(f"\n{'='*86}\nVALUE SCAN {date} — model edge vs live Polymarket (RAW, pre-motivation)\n{'='*86}")
    for h, a, venue in games:
        m = model_markets(h, a, venue)
        rows, seen = [], set()
        for q in (f"{h} {a}", f"{ALIAS.get(a,a)} {h}", f"{a} {h}"):
            d = OP.search_markets(q=q, exchange="polymarket", status="active", limit=60)
            for mk in (d if isinstance(d, list) else d.get("data", [])):
                qq = mk.get("question", ""); pr = mk.get("last_yes_price")
                if qq in seen or pr in (None, "",): continue
                seen.add(qq); price = float(pr)
                key, label = parse(qq, h, a)
                if key is None: continue
                mp = m["exact"].get(key[1:]) if isinstance(key, tuple) and key[0] == "exact" else m.get(key)
                if mp is None: continue
                edge = mp - price; roi = (mp / price - 1) if price > 0 else 0
                rows.append((roi, edge, mp, price, label, mk.get("volume", 0)))
        # add ML (separate title convention)
        for who, team in (("h_win", h), ("a_win", a)):
            yp, _, _ = _winprice(team, date)
            if yp not in (None, ""):
                yp = float(yp); mp = m[who]; edge = mp - yp; roi = mp/yp - 1
                rows.append((roi, edge, mp, yp, f"{team} ML", 0))
        rows.sort(reverse=True)
        print(f"\n### {h} vs {a}  (xG {m['xg'][0]:.2f}-{m['xg'][1]:.2f})  — {motiv.get((h,a),'')}")
        print(f"  {'BET':<26}{'model':>7}{'mkt':>7}{'edge':>7}{'ROI':>8}")
        for roi, edge, mp, price, label, vol in rows:
            if roi > 0.05 and mp > 0.12:        # only show real, non-lottery edges
                print(f"  {label:<26}{mp*100:6.0f}%{price*100:6.0f}%{edge*100:+6.0f}{roi*100:+7.0f}%")

def _winprice(team, date):
    for st in ("active", "closed"):
        d = OP.search_markets(q=f"{team} win", exchange="polymarket", status=st, limit=40)
        for m in (d if isinstance(d, list) else d.get("data", [])):
            ql = m.get("question", "").lower()
            if "win on" in ql and (team.lower() in ql or ALIAS.get(team, team).lower() in ql) and date in m.get("question", ""):
                return m.get("last_yes_price"), m.get("question"), m.get("volume")
    return None, None, None

if __name__ == "__main__":
    GAMES = [("Curaçao", "Ivory Coast", "Philadelphia, United States"),
             ("Ecuador", "Germany", "East Rutherford, United States"),
             ("Japan", "Sweden", "Arlington, United States"),
             ("Tunisia", "Netherlands", "Kansas City, United States"),
             ("Paraguay", "Australia", "Santa Clara, United States"),
             ("United States", "Turkey", "Inglewood, United States")]
    MOTIV = {
        ("Curaçao", "Ivory Coast"): "CUR eliminated(GD-6) | CIV must-win -> favorite STRONGER than model",
        ("Ecuador", "Germany"): "GER qualified+winning grp -> rotation | ECU must-win -> dog edge may be REAL",
        ("Japan", "Sweden"): "JPN safe w/ draw | SWE must-win -> Sweden motivated",
        ("Tunisia", "Netherlands"): "TUN eliminated(GD-8) | NED wants top -> favorite STRONGER than model",
        ("Paraguay", "Australia"): "both advance w/ draw -> mutual-draw; model AUS naive",
        ("United States", "Turkey"): "USA through(rotation) | TUR must-win -> live underdog",
    }
    scan(sys.argv[1] if len(sys.argv) > 1 else "2026-06-25", GAMES, MOTIV)
