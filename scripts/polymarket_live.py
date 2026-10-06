#!/usr/bin/env python3
"""
polymarket_live.py — pull LIVE market data from the polymarketdata.co API and
combine it with the structural live model to answer "what are the odds right now".

  * Reads the API key from config/secrets.env  (NOT hardcoded — rotate the key if
    it ever leaks; it grants read access to your account's data quota).
  * The key is RATE-LIMITED, so every response is cached to disk for CACHE_MIN
    minutes and calls retry once after a short sleep on a rate-limit error.

Endpoints learned:
  GET /v1/markets?search=<q>&limit=N        -> markets [{id, question, slug, tokens[{id,label}]}]
  GET /v1/markets/{id}/prices?start_ts&end_ts&resolution  -> price timeseries
        (latest point = current live price); params are unix seconds + resolution.
  GET /v1/events?search=<q>                  -> grouped events

Usage:
  python polymarket_live.py --home "Canada" --away "Qatar"        # list match markets + live prices
  python polymarket_live.py --odds --home Mexico --away "South Korea" --hs 1 --as 0 --minute 55
        # ^ fetch live result-market prices, blend with the model, print the draw/W/L odds
"""
import sys, os, json, time, argparse, urllib.request, urllib.parse, hashlib
sys.path.insert(0, os.path.dirname(__file__))

BASE = "https://api.polymarketdata.co/v1"
CFG = os.path.join(os.path.dirname(__file__), "..", "config", "secrets.env")
CACHE = os.path.join(os.path.dirname(__file__), "..", "config", "_pm_cache")
CACHE_MIN = 5
os.makedirs(CACHE, exist_ok=True)

def _key():
    for line in open(CFG):
        if line.startswith("POLYMARKETDATA_API_KEY"):
            return line.split("=", 1)[1].strip()
    raise SystemExit("API key not found in config/secrets.env")

def _get(path, params=None):
    """GET with on-disk cache + one rate-limit retry. Returns parsed JSON."""
    qs = ("?" + urllib.parse.urlencode(params)) if params else ""
    url = BASE + path + qs
    ck = os.path.join(CACHE, hashlib.md5(url.encode()).hexdigest() + ".json")
    if os.path.exists(ck) and time.time() - os.path.getmtime(ck) < CACHE_MIN * 60:
        return json.load(open(ck))
    for attempt in range(2):
        req = urllib.request.Request(url, headers={"x-api-key": _key()})
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                data = json.load(r)
            if isinstance(data, dict) and "Rate limit" in str(data.get("detail", "")):
                raise RuntimeError("rate-limited")
            json.dump(data, open(ck, "w"))
            return data
        except Exception as e:
            if attempt == 0:
                time.sleep(3); continue
            return {"error": str(e), "url": url}

def search_markets(query, limit=20):
    d = _get("/markets", {"search": query, "limit": limit})
    return d.get("data", []) if isinstance(d, dict) else []

def latest_prices(market_id, lookback_h=12, resolution="60"):
    """Return the most recent price(s) for a market's tokens. Defensive parser:
    finds the last timeseries record and extracts numeric price(s) in [0,1]."""
    now = int(time.time())
    d = _get(f"/markets/{market_id}/prices",
             {"start_ts": now - lookback_h * 3600, "end_ts": now, "resolution": resolution})
    if not isinstance(d, dict) or "data" not in d:
        return {"_raw": d}
    series = d["data"]
    if not series:
        return {"_empty": True}
    last = series[-1] if isinstance(series, list) else series
    # pull any float fields that look like probabilities
    prices = {}
    def walk(o, pfx=""):
        if isinstance(o, dict):
            for k, v in o.items(): walk(v, f"{pfx}{k}.")
        elif isinstance(o, list):
            for i, v in enumerate(o): walk(v, f"{pfx}{i}.")
        elif isinstance(o, (int, float)) and 0 <= o <= 1:
            prices[pfx.rstrip(".")] = o
    walk(last)
    return {"latest_record": last, "prices_found": prices}

# keywords that mark a NOVELTY / prop / side market (not the match result)
_PROP = ("announcers say", "o/u", "over/under", "corner", "card", "booking",
         "first goal", "penalty shootout", "to score", "clean sheet", "halftime",
         "ronaldo", "messi", "anthem", "var ")

def _is_result_or_draw(q):
    ql = q.lower()
    if any(p in ql for p in _PROP):
        return False
    # moneyline / draw markets read like "... win ...", "... vs ... (winner)", "draw"
    return ("draw" in ql) or ("win" in ql) or ql.strip().endswith("?") and " vs" in ql

def find_result_market(home, away):
    """Find the match-result (moneyline / draw) market(s), filtering out the flood
    of novelty/prop markets. Tries several search phrasings."""
    cand = {}
    for q in (f"{home} vs {away} draw", f"{home} vs {away} win",
              f"{home} vs {away}", f"{home} {away}"):
        for m in search_markets(q, limit=25):
            ql = m["question"].lower()
            if home.lower() in ql and away.lower() in ql and _is_result_or_draw(m["question"]):
                cand[m["id"]] = m
    return list(cand.values())

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", required=True); ap.add_argument("--away", required=True)
    ap.add_argument("--odds", action="store_true", help="blend with model & print live odds")
    ap.add_argument("--hs", type=int, default=0); ap.add_argument("--as", dest="as_", type=int, default=0)
    ap.add_argument("--minute", type=float, default=0)
    ap.add_argument("--p_draw", type=float, default=None,
                    help="if the auto-fetch can't find the draw price, pass it manually (0-1)")
    a = ap.parse_args()

    print(f"\nSearching polymarketdata.co for: {a.home} vs {a.away} ...")
    mkts = find_result_market(a.home, a.away)
    if not mkts:
        print("  No exact match-market found via search. Try the broader listing:")
        for m in search_markets(f"{a.home}", limit=10):
            print(f"    {m['id']} | {m['question']} | {[t['label'] for t in m.get('tokens',[])]}")
        return
    print(f"  Found {len(mkts)} related market(s):")
    draw_price = a.p_draw
    for m in mkts[:12]:
        labels = [t["label"] for t in m.get("tokens", [])]
        lp = latest_prices(m["id"])
        pr = lp.get("prices_found", {})
        print(f"    [{m['id']}] {m['question']}  tokens={labels}")
        if pr: print(f"         latest prices: {pr}")
        if "draw" in m["question"].lower() and pr:
            draw_price = list(pr.values())[0]

    if a.odds:
        from live_winprob import live_probs, american
        HOSTS = {"United States", "Mexico", "Canada"}
        pH, pD, pA = live_probs(a.home, a.away, a.hs, a.as_, a.minute,
                                host_home=a.home in HOSTS, host_away=a.away in HOSTS)[:3]
        print(f"\n  MODEL (live, {a.home} {a.hs}-{a.as_} {a.away} @ {a.minute:.0f}'):")
        print(f"    {a.home} {pH*100:.1f}% | DRAW {pD*100:.1f}% | {a.away} {pA*100:.1f}%")
        if draw_price is not None:
            w = 0.6
            blend = w * draw_price + (1 - w) * pD
            edge = blend - draw_price
            print(f"\n  >>> DRAW: model {pD*100:.1f}% | market {draw_price*100:.0f}¢ | "
                  f"blended fair {blend*100:.1f}% ({american(blend)})")
            print("      " + ("UNDERPRICED -> value buy draw" if edge > 0.04 else
                  "OVERPRICED -> avoid/sell draw" if edge < -0.04 else "fairly priced"))
        else:
            print("\n  (No draw price auto-found. Read it off Polymarket and pass --p_draw 0.27,")
            print("   or use the Excel sheet / live_draw.py to blend manually.)")

if __name__ == "__main__":
    main()
