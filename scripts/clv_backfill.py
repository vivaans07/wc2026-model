#!/usr/bin/env python3
"""
clv_backfill.py — systematic full-tournament CLV audit.

Rule (fixed in advance, no cherry-picking): for EVERY WC game, the model's
predicted reg-time outcome (argmax of home/draw/away) is 'bet' at the OPENING
Kalshi price; CLV = closing_price / opening_price - 1 for that outcome (how far
the line moved in our favor by kickoff). Uses only real Kalshi candlesticks.

Output: outputs/clv_full_audit.csv  (+ console summary)
"""
import sys, os, csv, json, time, urllib.request, datetime, unicodedata
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np, predict_day as PP, kalshi_client as K, wc_lib as L

ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world"
def _get(u): return json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent":"Mozilla/5.0"}), timeout=25))

def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii","ignore").decode().lower().strip()
    for a,b in [("turkiye","turkey"),("cote d'ivoire","ivory coast"),("ir iran","iran"),
                ("united states","usa"),("korea republic","south korea"),("czechia","czech republic"),
                ("congo dr","dr congo"),("congo","dr congo"),("bosnia-herzegovina","bosnia")]:
        s = s.replace(a,b)
    return s
# map normalized name -> model team name
MODEL_NAME = {norm(t): t for t in L.ALL_TEAMS}
for alias, team in [("turkey","Türkiye"),("ivory coast","Côte d'Ivoire"),("iran","Iran"),
                    ("usa","USA"),("south korea","Korea Republic"),("dr congo","DR Congo"),
                    ("bosnia","Bosnia and Herzegovina")]:
    if alias not in MODEL_NAME:
        cand=[t for t in L.ALL_TEAMS if norm(t)==alias or alias in norm(t)]
        if cand: MODEL_NAME[alias]=cand[0]

def kalshi_games():
    """{frozenset(norm teams): [(datecode, {outcome_norm: ticker})]} from settled markets.
    Keyed by team pair (unique per tournament); date kept only as a tiebreaker."""
    tmp={}; cursor=None
    for _ in range(20):
        d=K.markets(series_ticker="KXWCGAME", status="settled", limit=200, cursor=cursor)
        ms=d.get("markets",[]) if isinstance(d,dict) else []
        for m in ms:
            tk=m["ticker"]; dc=tk.split("-")[1][:7]                # 26JUN22
            title=m.get("title","").replace(" Winner?","")
            if " vs " not in title: continue
            t1,t2=[norm(x) for x in title.split(" vs ")]
            sub=m.get("yes_sub_title","").lower().replace("reg time:","").strip()  # 'argentina'|'tie'
            tmp.setdefault(frozenset([t1,t2]),{}).setdefault(dc,{})[sub]=tk
        cursor=d.get("cursor") if isinstance(d,dict) else None
        if not cursor or not ms: break
    return {k:list(v.items()) for k,v in tmp.items()}

def opening_mid(ticker):
    """First candle mid over the market's life (daily granularity)."""
    d=K.candlesticks(ticker, start_ts=1749600000, end_ts=int(time.time()), period_interval=1440)
    if isinstance(d,dict) and d.get("error"): return None
    cs=[c for c in d.get("candlesticks",[]) if K._mid(c) is not None]
    return K._mid(cs[0]) if cs else None

def datecode(iso):
    dt=datetime.datetime.fromisoformat(iso.replace("Z","+00:00"))
    return dt.strftime("%y%b%d").upper()   # 26JUN22

def run():
    kg=kalshi_games()
    rows=[]; missing=[]
    seen=set()
    for dd in [f"202606{d:02d}" for d in range(11,31)]+[f"202607{d:02d}" for d in range(1,20)]:
        try: sb=_get(f"{ESPN}/scoreboard?dates={dd}")
        except Exception: continue
        for e in sb.get("events",[]):
            c=e["competitions"][0]
            if c["status"]["type"]["state"]!="post": continue
            comp=c["competitors"]; h=[x for x in comp if x["homeAway"]=="home"][0]; a=[x for x in comp if x["homeAway"]=="away"][0]
            hn,an=h["team"]["displayName"], a["team"]["displayName"]
            pair=frozenset([norm(hn),norm(an)])
            if pair in seen: continue
            seen.add(pair)
            mh=MODEL_NAME.get(norm(hn)); ma=MODEL_NAME.get(norm(an))
            cand=kg.get(pair)
            markets=None
            if cand:
                dc=datecode(e["date"])
                markets=dict(cand)[dc] if dc in dict(cand) else cand[0][1]   # exact date, else the pairing
            if not mh or not ma or not markets:
                missing.append(f"{e['date'][:10]} {hn} v {an} (model={bool(mh and ma)}, kalshi={bool(markets)})"); continue
            # model reg W/D/L
            M,lam,nu=PP.score_matrix(mh,ma,0,0)
            pH=float(np.tril(M,-1).sum()); pD=float(np.trace(M)); pA=float(np.triu(M,1).sum())
            picks=[(pH,"home",norm(hn)),(pD,"draw","tie"),(pA,"away",norm(an))]
            mp,side,outkey=max(picks,key=lambda x:x[0])
            tk=markets.get(outkey)
            if not tk: missing.append(f"{e['date'][:10]} {hn} v {an} (no {outkey} ticker)"); continue
            op=opening_mid(tk); cl=K.closing_price(tk, e["date"])
            cm=cl.get("close") if isinstance(cl,dict) else None
            if op is None or cm is None or op<=0.01:
                missing.append(f"{e['date'][:10]} {hn} v {an} (no open/close: op={op} cm={cm})"); continue
            clv=cm/op-1
            label = hn if side=="home" else (an if side=="away" else "Draw")
            rows.append(dict(date=e["date"][:10], match=f"{hn} v {an}", pick=label, side=side,
                             model_prob=round(mp,3), open_prob=round(op,3), close_prob=round(cm,3),
                             clv_pct=round(clv*100,1), ticker=tk))
            time.sleep(0.05)
    rows.sort(key=lambda r:r["date"])
    out=os.path.join(L.OUT,"clv_full_audit.csv")
    with open(out,"w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    clvs=[r["clv_pct"] for r in rows]
    print(f"GRADED {len(rows)} games | missing/skipped {len(missing)}")
    print(f"  mean CLV {np.mean(clvs):+.2f}% | median {np.median(clvs):+.2f}% | beat close {sum(c>0 for c in clvs)}/{len(clvs)} ({sum(c>0 for c in clvs)/len(clvs)*100:.0f}%)")
    print(f"  saved -> {out}")
    if missing: print("  first few skipped:", "; ".join(missing[:5]))

if __name__=="__main__":
    run()
