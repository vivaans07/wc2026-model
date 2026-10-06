#!/usr/bin/env python3
"""
#2 Closing Line Value (CLV) tracker — corrected to respect KICKOFF timing.

True CLV needs the CLOSING line (the price right before kickoff). So:
  * game status 'pre'  (not kicked off) -> the live line is NOT the close. We record
    it as 'current-line value' (a preview) and leave CLV PENDING.
  * game status 'in'/'post' -> the line at/after kickoff IS effectively the close,
    so we lock it as the closing line and compute TRUE CLV.

Every snapshot is timestamped + status-tagged so nothing pre-kickoff is mislabeled
as CLV. Run again near/after kickoff to capture the real close.

Market benchmark: ESPN pickcenter (a real book's de-vigged moneyline). Pinnacle /
your book / Polymarket can be dropped in for a sharper close.

Usage:
  python clv_tracker.py --demo     # log recent picks, fetch lines, show pending vs true CLV
  python clv_tracker.py            # re-check ledger, upgrade pending->CLV once games kick off
"""
import sys, os, csv, json, argparse, datetime, urllib.request
sys.path.insert(0, os.path.dirname(__file__))
import wc_lib as L
try:
    import oddpool_client as OP          # Polymarket closing lines (paid)
except Exception:
    OP = None
try:
    import kalshi_client as K            # Kalshi closing lines (free, no auth)
except Exception:
    K = None

LEDGER = os.path.join(L.OUT, "picks_ledger.csv")
FIELDS = ["pick_id", "date", "match", "side", "price_taken", "line_seen", "line_status",
          "line_time", "metric_type", "value_pct"]
ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world"
ALIAS = {"DR Congo": "Congo DR", "South Korea": "Korea Republic", "Turkey": "Türkiye",
         "Czech Republic": "Czechia", "Ivory Coast": "Côte d'Ivoire", "United States": "USA"}

def _get(u):
    return json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=25))
def am2dec(a): return 1 + (a/100 if a > 0 else 100/(-a))
def am2p(a): return 100/(a+100) if a > 0 else (-a)/(-a+100)
def p2am(p): return f"+{round((1/p-1)*100)}" if p < 0.5 else f"-{round(100/((1/p)-1))}"

def event_on(date, home, away):
    """find the ESPN event for a match on its date; return (eid, status)."""
    names = {home.lower(), away.lower(), ALIAS.get(home, "").lower(), ALIAS.get(away, "").lower()}
    try:
        evs = _get(f"{ESPN}/scoreboard?dates={date.replace('-','')}").get("events", [])
    except Exception:
        evs = []
    for e in evs:
        if sum(1 for n in names if n and n in e["name"].lower()) >= 2:
            return e["id"], e["competitions"][0]["status"]["type"]["state"]
    return None, None

def devig_ml(eid):
    d = _get(f"{ESPN}/summary?event={eid}")
    pc = d.get("pickcenter") or []
    if not pc: return None
    o = pc[0]
    try:
        mlH = float(o["homeTeamOdds"]["moneyLine"]); mlA = float(o["awayTeamOdds"]["moneyLine"]); mlD = float(o["drawOdds"]["moneyLine"])
    except (KeyError, TypeError): return None
    raw = {"home": am2p(mlH), "draw": am2p(mlD), "away": am2p(mlA)}; s = sum(raw.values())
    return {k: v/s for k, v in raw.items()}

def assess(date, home, away, side, price_taken):
    eid, status = event_on(date, home, away)
    now = datetime.datetime.now().isoformat(timespec="minutes")
    if not eid: return dict(line_seen="n/a", line_status="not found", line_time=now, metric_type="-", value_pct="")
    fair = devig_ml(eid)
    if not fair: return dict(line_seen="n/a", line_status=status, line_time=now, metric_type="-", value_pct="")
    team = side.split(" ML")[0]
    key = "home" if team == home else "away"
    cp = fair[key]
    # closed only if the game has kicked off
    closed = status in ("in", "post")
    val = (am2dec(price_taken) * cp - 1) * 100   # your decimal odds * line's fair prob - 1
    return dict(line_seen=f"{p2am(cp)} ({cp*100:.0f}%)",
                line_status=status, line_time=now,
                metric_type="TRUE CLV" if closed else "current-line value (PENDING close)",
                value_pct=round(val, 1))

def kickoff_iso(date, home, away):
    """Pull the real kickoff time from ESPN so the Polymarket close is anchored
    to the actual gun, not a guess. Falls back to 20:00 UTC on the date."""
    eid, _ = event_on(date, home, away)
    if eid:
        try:
            d = _get(f"{ESPN}/summary?event={eid}")
            t = d.get("header", {}).get("competitions", [{}])[0].get("date")
            if t: return t
        except Exception:
            pass
    return f"{date}T20:00:00Z"

def discover_polymarket(home, away, date=None, kind="moneyline", team=None):
    """Best-effort: find the Polymarket market_id + the asset_id of the side you bet.
    kind: 'moneyline' (titled "Will TEAM win on DATE?"), 'spread', 'total', 'btts'.

    Note Polymarket's title conventions: single-game MLs carry the DATE but NOT the
    opponent, while spread/total/btts carry BOTH teams but no date. So we query and
    date-filter per kind. Returns (market_id, yes_asset_id, market_obj). Always
    eyeball the returned question before trusting the grade."""
    if OP is None: return None, None, None
    kw = {"moneyline": ["win on", "to win"], "spread": ["spread"],
          "total": ["o/u", "over/under"], "btts": ["both teams"]}[kind]
    # moneyline: search by the team (+date); others: search by both teams.
    q = (f"{team or home} win {date or ''}").strip() if kind == "moneyline" else f"{home} {away}"
    for st in ("closed", "resolved", "active"):
        d = OP.search_markets(q=q, exchange="polymarket", status=st, limit=40)
        rows = d if isinstance(d, list) else d.get("data", [])
        if isinstance(d, dict) and d.get("error"): continue
        cand = [m for m in rows if any(k in m.get("question", "").lower() for k in kw)]
        if team:
            cand = [m for m in cand if team.lower() in m.get("question", "").lower()] or cand
        if date:                              # pin to the right game: date in title OR slug/event_id
            dated = [m for m in cand if date in m.get("question", "")
                     or date in (m.get("slug", "") + m.get("event_id", ""))]
            if dated: cand = dated
            elif kind == "moneyline":         # ML title MUST carry the date — don't grab another game
                cand = [m for m in cand if date in m.get("question", "")]
        if cand:
            m = max(cand, key=lambda x: x.get("volume", 0))
            yes = _yes_token(m["market_id"], m.get("last_yes_price"))
            return m["market_id"], yes, m
    return None, None, None

def _yes_token(market_id, last_yes_price=None, venue="polymarket"):
    """Identify the YES token (the named outcome: team-wins / spread-covers / over).
    The market's last_yes_price IS the YES side's price, so the YES token is the one
    whose latest book mid sits closest to it. Robust for active AND settled markets."""
    d = OP.top_of_book(venue, market_id, limit=8)
    snaps = d.get("snapshots", []) if isinstance(d, dict) else []
    if not snaps: return None
    latest = {}
    for s in sorted(snaps, key=lambda x: x.get("timestamp", 0)):
        latest[s["asset_id"]] = OP._mid(s)
    if last_yes_price is None:
        return next(iter(latest))
    target = float(last_yes_price)
    return min(latest, key=lambda aid: abs((latest[aid] if latest[aid] is not None else 9) - target))

def grade_polymarket(market_id, yes_asset_id, kickoff, price_taken_american, venue="polymarket"):
    """TRUE CLV against the real Polymarket/Kalshi close. price_taken_american is
    the odds YOU got (American). Returns close prob + CLV%."""
    if OP is None: return {"error": "oddpool_client unavailable"}
    r = OP.closing_price(venue, market_id, kickoff, asset_id=yes_asset_id)
    if r.get("error") or r.get("close") is None:
        return {"error": r.get("error", "no close"), "detail": r}
    close = r["close"]
    dec = am2dec(price_taken_american)
    return {"close_prob": close, "close_american": p2am(close),
            "price_taken": p2am(am2p(price_taken_american)),
            "clv_pct": round((dec * close - 1) * 100, 1),
            "close_source": r.get("close_source"), "venue": venue, "market_id": market_id}

# ---------------------------------------------------------------- Kalshi (free) path
# NOTE: we treat Polymarket and Kalshi as virtually the same market — their closes
# track each other, so either venue's close is a valid CLV benchmark for a bet placed
# on the other. Kalshi is free/no-auth, so prefer it when available.
def discover_kalshi(home, away, team=None, draw=False):
    """Find the Kalshi KXWCGAME (Reg-Time winner) ticker for a game + outcome.
    Match the game by title, the side by yes_sub_title ('Reg Time: {Team}'|'...: Tie').
    Returns (ticker, market_obj)."""
    if K is None: return None, None
    want = "tie" if draw else (team or home).lower()
    for st in ("settled", "finalized", "closed", "active", None):
        d = K.markets(series_ticker="KXWCGAME", status=st, limit=200)
        if isinstance(d, dict) and d.get("error"): continue
        game = [m for m in d.get("markets", [])
                if home.lower() in m.get("title", "").lower()
                and away.lower() in m.get("title", "").lower()]
        for m in game:
            if want in m.get("yes_sub_title", "").lower():
                return m["ticker"], m
    return None, None

def grade_kalshi(ticker, kickoff, price_american, series_ticker=None):
    """TRUE CLV against the real (free) Kalshi close."""
    if K is None: return {"error": "kalshi_client unavailable"}
    price_american = int(price_american)          # tolerate "+150"/"-223"/150
    r = K.closing_price(ticker, kickoff, series_ticker=series_ticker)
    if r.get("error") or r.get("close") is None:
        return {"error": r.get("error", "no close"), "detail": r}
    close = r["close"]; dec = am2dec(price_american)
    return {"close_prob": close, "close_american": p2am(close),
            "price_taken": p2am(am2p(price_american)),
            "clv_pct": round((dec * close - 1) * 100, 1), "venue": "kalshi", "ticker": ticker}

def k_grade(home, away, date, price_american, team=None, draw=False):
    """Auto-discover the Kalshi market for a game + side and grade TRUE CLV against the
    free Kalshi close (≈ the Polymarket close, since we treat the venues as the same)."""
    tk, m = discover_kalshi(home, away, team=team, draw=draw)
    if not tk:
        print(f"  no Kalshi KXWCGAME market found for {home} v {away}"); return
    ko = kickoff_iso(date, home, away)
    print(f"  market: {tk}  \"{m.get('yes_sub_title')}\"  [{m.get('status')}]  kickoff {ko}")
    g = grade_kalshi(tk, ko, price_american)
    if g.get("error"): print("  ", g); return
    print(f"  took {g['price_taken']}  |  REAL Kalshi close {g['close_american']} "
          f"({g['close_prob']*100:.1f}%)  |  TRUE CLV {g['clv_pct']:+.1f}%  [free]")

def demo():
    picks = [
        ("2026-06-22", "Argentina", "Austria", "Argentina ML", -182),  # settled -> true CLV
        ("2026-06-22", "France", "Iraq", "France ML", -260),           # settled -> true CLV
        ("2026-06-23", "Portugal", "Uzbekistan", "Portugal ML", -200), # upcoming -> pending
        ("2026-06-23", "England", "Ghana", "England ML", -261),        # upcoming -> pending
        ("2026-06-23", "Colombia", "DR Congo", "Colombia ML", -201),   # upcoming -> pending
    ]
    rows = []
    for i, (date, h, aw, side, taken) in enumerate(picks, 1):
        a = assess(date, h, aw, side, taken)
        rows.append({"pick_id": i, "date": date, "match": f"{h} v {aw}", "side": side,
                     "price_taken": p2am(am2p(taken)), **a})
    with open(LEDGER, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader(); w.writerows(rows)
    report()

def report():
    rows = list(csv.DictReader(open(LEDGER)))
    print(f"\n{'match':<24}{'pick':<14}{'took':>6}{'line':>14}{'status':>6}  metric")
    for r in rows:
        v = f"{r['value_pct']}%" if r['value_pct'] != "" else "-"
        print(f"  {r['match']:<22}{r['side'].replace(' ML',''):<14}{r['price_taken']:>6}{r['line_seen']:>14}"
              f"{r['line_status']:>6}  {r['metric_type']}: {v}")
    true_clv = [float(r["value_pct"]) for r in rows if r["metric_type"] == "TRUE CLV" and r["value_pct"] != ""]
    pend = sum(1 for r in rows if "PENDING" in r["metric_type"])
    print(f"\n  TRUE CLV picks (kicked off): {len(true_clv)}" +
          (f" | mean {sum(true_clv)/len(true_clv):+.1f}% | beat close {sum(c>0 for c in true_clv)}/{len(true_clv)}" if true_clv else ""))
    print(f"  PENDING (not closed yet): {pend}  -> re-run near kickoff to lock the real close")

def pm_grade(home, away, date, price_american, kind="moneyline", team=None):
    """Auto-discover the Polymarket market for a game + side, then grade TRUE CLV
    against the real close. Eyeball the printed question to confirm the match."""
    mid, yes, m = discover_polymarket(home, away, date=date, kind=kind, team=team)
    if not mid:
        print(f"  no Polymarket {kind} market found for {home} v {away}"); return
    ko = kickoff_iso(date, home, away)
    print(f"  market: \"{m.get('question')}\"  [{m.get('status')}]  kickoff {ko}")
    g = grade_polymarket(mid, yes, ko, price_american)
    if g.get("error"): print("  ", g); return
    print(f"  took {g['price_taken']}  |  REAL Polymarket close {g['close_american']} "
          f"({g['close_prob']*100:.1f}%)  |  TRUE CLV {g['clv_pct']:+.1f}%  [{g['close_source']}]")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--pm", nargs="+", metavar="HOME AWAY DATE PRICE [KIND] [TEAM]",
                    help="grade one Polymarket bet, e.g. --pm England Ghana 2026-06-23 +110 spread England")
    ap.add_argument("--k", nargs="+", metavar="HOME AWAY DATE PRICE [TEAM|tie]",
                    help="grade one Kalshi moneyline bet (free), e.g. --k Argentina Switzerland 2026-07-11 +150 Argentina")
    a = ap.parse_args()
    if a.k:
        side = a.k[4] if len(a.k) > 4 else None
        draw = bool(side) and side.lower() in ("tie", "draw")
        k_grade(a.k[0], a.k[1], a.k[2], a.k[3], team=(None if draw else side), draw=draw)
    elif a.pm:
        pm_grade(*a.pm[:4], *( [a.pm[4]] if len(a.pm) > 4 else []), team=(a.pm[5] if len(a.pm) > 5 else None))
    elif a.demo:
        demo()
    else:
        report()
