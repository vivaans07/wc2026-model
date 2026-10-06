#!/usr/bin/env python3
"""
#3 CLV audit — re-grade EVERY ledger pick against the real (free) Kalshi close,
then do the statistics the single-bet tracker can't: mean CLV, hit rate vs the
close, t-stat, bootstrap CI, and an honest sample-size verdict.

Two numbers per pick:
  * clv_pct — expected ROI at your price if the close is the true probability:
      dec(price_taken) * close_prob - 1. The money metric. Your entry price
      already carries the book's vig, so this nets what you paid.
  * clv_pts — probability points: close_prob - implied(price_taken). Cleaner for
      comparing entries across different odds levels (a +31% CLV on a longshot
      and on a favorite are very different point moves).

The t-test runs on clv_pct with H0 = "no edge vs the close" (mean 0). With a
handful of picks the verdict SHOULD read "cannot reject luck" — the audit's job
is to say so and to estimate how many picks it would take at the current edge.

The ledger stays untouched (clv_tracker owns it); results go to
outputs/clv_audit.csv.

Usage:
  python clv_audit.py
"""
import sys, os, csv, math, random
sys.path.insert(0, os.path.dirname(__file__))
import wc_lib as L
import clv_tracker as T
import kalshi_client as K

AUDIT = os.path.join(L.OUT, "clv_audit.csv")
FIELDS = ["pick_id", "date", "match", "side", "price_taken", "implied_pct", "ticker",
          "close_prob", "close_american", "clv_pct", "clv_pts", "status"]

def _names(x):
    """Kalshi uses FIFA-style names ('Congo DR'); the ledger uses common ones
    ('DR Congo') — match on either, reusing the tracker's alias table."""
    return {n.lower() for n in (x, T.ALIAS.get(x, "")) if n}

def discover(home, away, team=None, draw=False, max_pages=10):
    """Like clv_tracker.discover_kalshi but PAGINATES (settled WC markets pile up
    fast and a single 200-row page misses early group-stage games) and matches
    team-name aliases."""
    hs, aws = _names(home), _names(away)
    wants = {"tie"} if draw else _names(team or home)
    for st in ("settled", "finalized", "closed", "active", None):
        cursor = None
        for _ in range(max_pages):
            d = K.markets(series_ticker="KXWCGAME", status=st, limit=200, cursor=cursor)
            if isinstance(d, dict) and d.get("error"): break
            for m in d.get("markets", []):
                t = m.get("title", "").lower()
                if any(h in t for h in hs) and any(a in t for a in aws) \
                        and any(w in m.get("yes_sub_title", "").lower() for w in wants):
                    return m["ticker"], m
            cursor = d.get("cursor")
            if not cursor: break
    return None, None

def grade_pick(r):
    """One ledger row -> one audit row, graded against the real Kalshi close."""
    home, away = [s.strip() for s in r["match"].split(" v ")]
    team = r["side"].replace(" ML", "").strip()
    draw = team.lower() in ("draw", "tie")
    price = int(r["price_taken"])
    row = {k: r[k] for k in ("pick_id", "date", "match", "side", "price_taken")}
    row["implied_pct"] = round(T.am2p(price) * 100, 1)
    tk, m = discover(home, away, team=None if draw else team, draw=draw)
    if not tk:
        return {**row, "status": "no Kalshi market found"}
    row["ticker"] = tk
    g = T.grade_kalshi(tk, T.kickoff_iso(r["date"], home, away), price)
    if g.get("error"):
        return {**row, "status": f"no close: {g['error']}"}
    q = g["close_prob"]
    return {**row, "close_prob": round(q, 3), "close_american": g["close_american"],
            "clv_pct": round((T.am2dec(price) * q - 1) * 100, 2),
            "clv_pts": round((q - T.am2p(price)) * 100, 2), "status": "graded"}

def summarize(graded):
    pcts = [r["clv_pct"] for r in graded]
    n = len(pcts); mean = sum(pcts) / n
    if n < 2:
        return dict(n=n, mean=mean)
    sd = math.sqrt(sum((x - mean) ** 2 for x in pcts) / (n - 1))
    se = sd / math.sqrt(n)
    t = mean / se if se else float("nan")
    try:
        from scipy import stats as S
        p = 2 * S.t.sf(abs(t), n - 1)
    except Exception:
        p = 2 * (1 - 0.5 * (1 + math.erf(abs(t) / math.sqrt(2))))   # normal fallback
    random.seed(2026)
    boots = sorted(sum(random.choices(pcts, k=n)) / n for _ in range(10000))
    return dict(n=n, mean=mean, sd=sd, se=se, t=t, p=p,
                ci=(boots[249], boots[9749]), n_need=n_needed(mean, sd),
                beat=sum(x > 0 for x in pcts),
                pts=sum(r["clv_pts"] for r in graded) / n)

def n_needed(mean, sd):
    """Smallest n where this mean/sd clears the t-distribution's 95% bar. At tiny
    n the bar is well above 1.96 (2.78 at 4 df), so the naive normal formula
    understates what's needed."""
    if not mean: return None
    try:
        from scipy import stats as S
        crit = lambda n: S.t.ppf(0.975, n - 1)
    except Exception:
        crit = lambda n: 1.96
    for n in range(2, 100001):
        if abs(mean) / (sd / math.sqrt(n)) >= crit(n):
            return n
    return None

def report(rows, s):
    print(f"\n{'match':<26}{'side':<14}{'took':>6}{'impl%':>7}{'close':>7}{'CLV%':>8}{'pts':>7}  status")
    for r in rows:
        cp = f"{r['close_prob']*100:.1f}" if r.get("close_prob") is not None else "-"
        cv = f"{r['clv_pct']:+.1f}" if r.get("clv_pct") is not None else "-"
        pt = f"{r['clv_pts']:+.1f}" if r.get("clv_pts") is not None else "-"
        print(f"  {r['match']:<24}{r['side']:<14}{r['price_taken']:>6}{r['implied_pct']:>7}{cp:>7}{cv:>8}{pt:>7}  {r['status']}")
    if s["n"] < 2:
        print(f"\n  graded {s['n']} pick(s) — not enough for statistics"); return
    lo, hi = s["ci"]
    print(f"\n  == CLV audit vs the real Kalshi close ==")
    print(f"  picks graded          {s['n']}")
    print(f"  beat the close        {s['beat']}/{s['n']}")
    print(f"  mean CLV              {s['mean']:+.1f}%   (per-bet expected ROI if the close is the true prob)")
    print(f"  mean CLV (prob pts)   {s['pts']:+.1f}")
    print(f"  sd / SE               {s['sd']:.1f}% / {s['se']:.1f}%")
    print(f"  t-stat (H0: no edge)  {s['t']:.2f}   p = {s['p']:.3f}  ({s['n']-1} df)")
    print(f"  bootstrap 95% CI      [{lo:+.1f}%, {hi:+.1f}%]")
    verdict = ("EDGE CONFIRMED at 95% — mean CLV is statistically distinguishable from luck."
               if s["p"] < 0.05 else
               "CANNOT REJECT LUCK yet — the point estimate is promising but the sample is thin.")
    print(f"\n  verdict: {verdict}")
    if s["n_need"] and s["p"] >= 0.05:
        print(f"  at this mean/sd you'd need ~{s['n_need']} graded picks for t >= 1.96 "
              f"(you have {s['n']}; keep logging every pick).")

def main():
    rows = [grade_pick(r) for r in csv.DictReader(open(T.LEDGER))]
    graded = [r for r in rows if r["status"] == "graded"]
    with open(AUDIT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader(); w.writerows(rows)
    report(rows, summarize(graded) if graded else dict(n=0, mean=0))
    print(f"\n  per-pick detail -> {AUDIT}")

if __name__ == "__main__":
    main()
