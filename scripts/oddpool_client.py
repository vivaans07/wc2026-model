#!/usr/bin/env python3
"""
oddpool_client.py — client for the Oddpool API (api.oddpool.com): historical
Polymarket + Kalshi prediction-market data.

Why this matters for us: the `top-of-book` timeseries gives the **actual closing
line** of any market (the price right before settlement/kickoff) — which is exactly
what true CLV needs, and what we never had from ESPN/DraftKings. It also fixes
market discovery (search), and OHLCV history can be used to calibrate the model
toward sharp market-implied probabilities.

Auth: X-API-Key header (key in config/secrets.env as ODDPOOL_API_KEY). Historical
+ search are paid tiers — a 401 = bad key, 403 = plan doesn't cover that endpoint.

Endpoints wrapped:
  GET /search/markets?q=&exchange=&status=&sort_by=&limit=          -> find a market_id
  GET /historical/{venue}/top-of-book?market_id=&asset_id=&start_time=&end_time=&granularity=
  GET /historical/{venue}/trades?market_id=&start_time=&end_time=
  GET /markets/ohlcv?market_ids=&from=&to=&last=&interval=          -> probability bars
  GET /arbitrage/current                                            -> cross-venue arb

Usage:
  python oddpool_client.py search "England vs Ghana" --exchange polymarket
  python oddpool_client.py close <venue> <market_id> "2026-06-23T20:00:00Z"   # closing line
"""
import sys, os, json, time, argparse, datetime, urllib.request, urllib.parse, hashlib

BASE = "https://api.oddpool.com"
CFG = os.path.join(os.path.dirname(__file__), "..", "config")
CACHE = os.path.join(CFG, "_oddpool_cache"); os.makedirs(CACHE, exist_ok=True)
_MIN_GAP = 1.5            # seconds between live (uncached) requests -> avoid HTTP 429
_last_call = [0.0]

def _key():
    for line in open(os.path.join(CFG, "secrets.env")):
        if line.startswith("ODDPOOL_API_KEY"):
            return line.split("=", 1)[1].strip()
    raise SystemExit("ODDPOOL_API_KEY not in config/secrets.env — paste your Oddpool key first.")

def _to_ms(when):
    """ISO-8601 string or datetime -> unix ms."""
    if isinstance(when, (int, float)): return int(when)
    if isinstance(when, str):
        when = datetime.datetime.fromisoformat(when.replace("Z", "+00:00"))
    if when.tzinfo is None: when = when.replace(tzinfo=datetime.timezone.utc)
    return int(when.timestamp() * 1000)

def _get(path, params=None, cache_min=10):
    qs = ("?" + urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})) if params else ""
    url = BASE + path + qs
    ck = os.path.join(CACHE, hashlib.md5(url.encode()).hexdigest() + ".json")
    if os.path.exists(ck) and time.time() - os.path.getmtime(ck) < cache_min * 60:
        return json.load(open(ck))
    req = urllib.request.Request(url, headers={"X-API-Key": _key()})
    for attempt in range(4):
        gap = _MIN_GAP - (time.time() - _last_call[0])
        if gap > 0: time.sleep(gap)
        _last_call[0] = time.time()
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.load(r)
            json.dump(data, open(ck, "w")); return data
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 3:        # backoff + retry on rate limit
                time.sleep(2 ** attempt * 2); continue
            return {"error": e.code, "detail": e.read().decode()[:200], "url": url}
        except Exception as e:
            return {"error": str(e), "url": url}

# ---------------------------------------------------------------- search / discovery
def search_markets(q=None, series_id=None, exchange=None, status="active", sort_by="volume", limit=20):
    return _get("/search/markets", {"q": q, "series_id": series_id, "exchange": exchange,
                                    "status": status, "sort_by": sort_by, "limit": limit})

# ---------------------------------------------------------------- historical price (CLV)
def top_of_book(venue, market_id, asset_id=None, start_time=None, end_time=None,
                granularity="1m", limit=200, pagination_key=None):
    """venue: 'polymarket' or 'kalshi'. start/end in unix ms (or omit for latest).
    limit caps at 200 per call (API hard limit) — use top_of_book_all() to paginate."""
    return _get(f"/historical/{venue}/top-of-book",
                {"market_id": market_id, "asset_id": asset_id,
                 "start_time": start_time, "end_time": end_time,
                 "granularity": granularity, "limit": min(limit, 200),
                 "pagination_key": pagination_key}, cache_min=1440)

def top_of_book_all(venue, market_id, asset_id=None, start_time=None, end_time=None,
                    granularity="1m", max_pages=15):
    """Walk pagination_key forward, returning every snapshot in [start,end]
    (the book is dense near kickoff, so reaching the close needs several pages)."""
    out, pk = [], None
    for _ in range(max_pages):
        d = top_of_book(venue, market_id, asset_id, start_time, end_time, granularity, 200, pk)
        if isinstance(d, dict) and d.get("error"):
            return {"error": d["error"], "detail": d.get("detail"), "partial": out}
        out += d.get("snapshots", [])
        pg = d.get("pagination", {}) or {}
        pk = pg.get("pagination_key")
        if not pg.get("has_more") or not pk:
            break
    return out

def trades(venue, market_id, asset_id=None, start_time=None, end_time=None, limit=200):
    return _get(f"/historical/{venue}/trades",
                {"market_id": market_id, "asset_id": asset_id,
                 "start_time": start_time, "end_time": end_time, "limit": min(limit, 200)}, cache_min=1440)

def ohlcv(market_ids, frm=None, to=None, last=None, interval="1d"):
    ids = market_ids if isinstance(market_ids, str) else ",".join(market_ids)
    return _get("/markets/ohlcv", {"market_ids": ids, "from": frm, "to": to,
                                   "last": last, "interval": interval}, cache_min=1440)

def arbitrage(min_net_cents=0.5):
    return _get("/arbitrage/current", {"min_net_cents": min_net_cents}, cache_min=2)

# ---------------------------------------------------------------- the CLV helper
def _mid(s):
    b, a = s.get("best_bid"), s.get("best_ask")
    if b is not None and a is not None: return (b + a) / 2
    return b if b is not None else a            # one-sided book: use the live quote

def closing_price(venue, market_id, kickoff, asset_id=None, window_min=12):
    """THE CLV anchor. Returns the market's CLOSING price — the last top-of-book
    snapshot at-or-before kickoff — paginating through the dense pre-kickoff book.

    Polymarket binary markets have two complementary tokens (YES/NO, prices sum to
    ~1) and the live book often sits on only ONE of them. If you pass the asset_id
    of YOUR side and that token is quiet, the price is derived as 1 - (other side).

      asset_id=None -> returns every token's close (you label YES/NO yourself)
      asset_id=<tok> -> returns 'close' = the price of THAT side for CLV
    """
    k = _to_ms(kickoff)
    snaps = top_of_book_all(venue, market_id, start_time=k - window_min * 60_000, end_time=k)
    if isinstance(snaps, dict):                  # error
        return snaps
    snaps = [s for s in snaps if s.get("timestamp", 0) <= k and _mid(s) is not None]
    if not snaps:
        return {"error": "no top-of-book data in window", "venue": venue, "market_id": market_id}
    # last snapshot per token
    last_by = {}
    for s in sorted(snaps, key=lambda x: x["timestamp"]):
        last_by[s["asset_id"]] = s
    tokens = {aid: {"mid": round(_mid(s), 4), "ts": s["timestamp"],
                    "best_bid": s.get("best_bid"), "best_ask": s.get("best_ask")}
              for aid, s in last_by.items()}
    res = {"venue": venue, "market_id": market_id, "kickoff_ms": k, "tokens": tokens}
    if asset_id:
        if asset_id in tokens:
            res["close"] = tokens[asset_id]["mid"]; res["close_source"] = "direct"
        elif tokens:                              # derive from complementary token
            other = max(tokens.values(), key=lambda t: t["ts"])
            res["close"] = round(1 - other["mid"], 4); res["close_source"] = "1-complement"
    return res


def clv(price_taken_decimal, close_prob):
    """Closing Line Value. price_taken_decimal = decimal odds you got;
    close_prob = sharp closing probability of that outcome (0-1).
    CLV>0 means you beat the close (long-run +EV signal)."""
    if not close_prob: return None
    return round(price_taken_decimal * close_prob - 1, 4)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("search"); s.add_argument("q"); s.add_argument("--exchange")
    c = sub.add_parser("close"); c.add_argument("venue"); c.add_argument("market_id"); c.add_argument("kickoff")
    c.add_argument("--asset_id")
    a = ap.parse_args()
    if a.cmd == "search":
        d = search_markets(q=a.q, exchange=a.exchange)
        if isinstance(d, dict) and d.get("error"): print("ERROR:", d); return
        for m in (d if isinstance(d, list) else d.get("data", []))[:15]:
            print(f"  [{m.get('exchange')}] {m.get('market_id')} | {m.get('question')} "
                  f"| vol {m.get('volume')}")
    elif a.cmd == "close":
        print(json.dumps(closing_price(a.venue, a.market_id, a.kickoff, asset_id=a.asset_id), indent=2))
    else:
        ap.print_help()

if __name__ == "__main__":
    main()
