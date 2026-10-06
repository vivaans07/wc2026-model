#!/usr/bin/env python3
"""
kalshi_client.py — direct client for Kalshi's public market-data API.

The win here: reading Kalshi market data (markets, events, candlesticks, trades)
needs NO authentication and is FREE. So for Kalshi closing lines we do NOT need
Oddpool's paid tier — we pull candlesticks straight from Kalshi. (Keep Oddpool for
Polymarket historical; use this for Kalshi.) A candlestick's last close before
kickoff IS the closing line for CLV.

Base: https://api.elections.kalshi.com/trade-api/v2  (the old trading-api host is
retired). Timestamps are UNIX SECONDS (not ms like Oddpool).

Endpoints wrapped:
  GET /markets?series_ticker=&event_ticker=&status=              -> find tickers
  GET /events?series_ticker=&status=                            -> discovery
  GET /series/{series}/markets/{ticker}/candlesticks?period_interval=&start_ts=&end_ts=
       period_interval: 1 (min) | 60 (hour) | 1440 (day); each candle carries
       yes_bid/yes_ask OHLC -> mid = (bid.close+ask.close)/2 = the price.
  Settled-before-cutoff markets: same under /historical/markets/{ticker}/candlesticks

Usage:
  python kalshi_client.py markets KXWCGOALLEADER          # list a series' markets
  python kalshi_client.py close <ticker> "2026-07-07T18:00:00Z"   # closing line
"""
import sys, os, json, time, argparse, datetime, urllib.request, urllib.parse, hashlib

BASE = "https://api.elections.kalshi.com/trade-api/v2"
CACHE = os.path.join(os.path.dirname(__file__), "..", "config", "_kalshi_cache")
os.makedirs(CACHE, exist_ok=True)
_last = [0.0]; _GAP = 0.3

def _to_ts(when):
    """ISO-8601 / datetime / epoch -> unix SECONDS."""
    if isinstance(when, (int, float)):
        return int(when if when < 1e12 else when / 1000)      # accept s or ms
    if isinstance(when, str):
        when = datetime.datetime.fromisoformat(when.replace("Z", "+00:00"))
    if when.tzinfo is None: when = when.replace(tzinfo=datetime.timezone.utc)
    return int(when.timestamp())

def _get(path, params=None, cache_min=60):
    qs = ("?" + urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})) if params else ""
    url = BASE + path + qs
    ck = os.path.join(CACHE, hashlib.md5(url.encode()).hexdigest() + ".json")
    if os.path.exists(ck) and time.time() - os.path.getmtime(ck) < cache_min * 60:
        return json.load(open(ck))
    gap = _GAP - (time.time() - _last[0])
    if gap > 0: time.sleep(gap)
    _last[0] = time.time()
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "wc2026/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
        json.dump(data, open(ck, "w")); return data
    except urllib.error.HTTPError as e:
        return {"error": e.code, "detail": e.read().decode()[:200], "url": url}
    except Exception as e:
        return {"error": str(e), "url": url}

# ---------------------------------------------------------------- discovery
def markets(series_ticker=None, event_ticker=None, status=None, limit=100, cursor=None):
    return _get("/markets", {"series_ticker": series_ticker, "event_ticker": event_ticker,
                             "status": status, "limit": limit, "cursor": cursor}, cache_min=10)

def events(series_ticker=None, status=None, limit=100, cursor=None):
    return _get("/events", {"series_ticker": series_ticker, "status": status,
                            "limit": limit, "cursor": cursor}, cache_min=30)

def series_of(ticker):
    """Kalshi market ticker 'KXWORLDCUPGAME-26JUL07COLSUI-...' -> series 'KXWORLDCUPGAME'."""
    return ticker.split("-")[0]

# ---------------------------------------------------------------- candlesticks (CLV)
def candlesticks(ticker, series_ticker=None, start_ts=None, end_ts=None, period_interval=60):
    s = series_ticker or series_of(ticker)
    return _get(f"/series/{s}/markets/{ticker}/candlesticks",
                {"start_ts": start_ts, "end_ts": end_ts, "period_interval": period_interval},
                cache_min=1440)

def _mid(c):
    """mid from a candle's yes_bid/yes_ask closes; fall back to last trade price."""
    def cl(side):
        v = c.get(side, {}).get("close_dollars"); return float(v) if v is not None else None
    b, a = cl("yes_bid"), cl("yes_ask")
    if b is not None and a is not None and 0 < a < 1:   # live two-sided book
        return round((b + a) / 2, 4)
    if b is not None and a is not None and (b > 0 or a < 1):
        return round((b + a) / 2, 4)
    p = c.get("price", {}).get("previous_dollars")       # fallback: last trade
    return round(float(p), 4) if p is not None else None

def closing_price(ticker, kickoff, series_ticker=None, window_min=240):
    """THE CLV anchor for Kalshi — the last candle's mid at-or-before kickoff."""
    k = _to_ts(kickoff)
    d = candlesticks(ticker, series_ticker, start_ts=k - window_min * 60, end_ts=k, period_interval=1)
    if isinstance(d, dict) and d.get("error"): return d
    cs = [c for c in d.get("candlesticks", []) if c.get("end_period_ts", 0) <= k]
    cs = [c for c in cs if _mid(c) is not None]
    if not cs:
        return {"error": "no candlesticks in window", "ticker": ticker}
    last = max(cs, key=lambda c: c["end_period_ts"])
    return {"ticker": ticker, "close": _mid(last), "ts": last["end_period_ts"],
            "yes_bid": last.get("yes_bid", {}).get("close_dollars"),
            "yes_ask": last.get("yes_ask", {}).get("close_dollars"), "n_candles": len(cs)}

def clv(price_taken_decimal, close_prob):
    if not close_prob: return None
    return round(price_taken_decimal * close_prob - 1, 4)


def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd")
    mk = sub.add_parser("markets"); mk.add_argument("series"); mk.add_argument("--status")
    cl = sub.add_parser("close"); cl.add_argument("ticker"); cl.add_argument("kickoff"); cl.add_argument("--series")
    a = ap.parse_args()
    if a.cmd == "markets":
        d = markets(series_ticker=a.series, status=a.status)
        if isinstance(d, dict) and d.get("error"): print("ERR", d); return
        for m in d.get("markets", [])[:20]:
            print(f"  {m.get('ticker')} | {m.get('title')} | {m.get('status')} | last {m.get('last_price')}")
    elif a.cmd == "close":
        print(json.dumps(closing_price(a.ticker, a.kickoff, series_ticker=a.series), indent=2))
    else:
        ap.print_help()

if __name__ == "__main__":
    main()
