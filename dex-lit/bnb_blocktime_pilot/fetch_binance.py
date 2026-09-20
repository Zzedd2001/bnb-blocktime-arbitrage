"""Step 3: download Binance spot 1-second klines (or aggTrades) from the public bulk archive
https://data.binance.vision — no API key, no rate limit for bulk files.

Usage:
    python fetch_binance.py --symbols BNBUSDT ETHUSDT BTCUSDT CAKEUSDT --start 2025-06-23 --end 2025-07-07 --out data/
    python fetch_binance.py --symbols BNBUSDT --start ... --end ... --kind aggTrades --out data/

Output: data/binance_<SYMBOL>_1s.parquet with columns [ts_ms, open, high, low, close, volume, ...]
(or aggTrades with [ts_ms, price, qty, is_buyer_maker]).
"""
from __future__ import annotations
import argparse, io, os, sys, zipfile, datetime as dt
import pandas as pd, requests
import config as C

KLINE_COLS = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume",
              "n_trades", "taker_buy_base", "taker_buy_quote", "ignore"]
AGG_COLS = ["agg_id", "price", "qty", "first_id", "last_id", "ts_ms", "is_buyer_maker", "best_match"]


def daterange(s: str, e: str):
    d0, d1 = dt.date.fromisoformat(s), dt.date.fromisoformat(e)
    while d0 <= d1:
        yield d0.isoformat()
        d0 += dt.timedelta(days=1)


def _get_with_retries(url: str, attempts: int = 8, timeout: int = 120) -> requests.Response | None:
    """GET a bulk-data file, retrying transient failures (proxy tunnel errors, connection resets, time-outs,
    5xx/429) with exponential back-off.  Returns None for a 404 (file does not exist)."""
    import time
    last = None
    for i in range(attempts):
        try:
            r = requests.get(url, timeout=timeout)
            if r.status_code == 404:
                return None
            if r.status_code == 429 or r.status_code >= 500:
                raise requests.HTTPError(f"HTTP {r.status_code}", response=r)
            r.raise_for_status()
            return r
        except requests.RequestException as e:      # ProxyError / ConnectionError / Timeout / HTTPError
            last = e
            wait = min(2 ** i, 30)
            print(f"  {url.rsplit('/', 1)[-1]}: {str(e)[:90]} -> retry in {wait}s ({i + 1}/{attempts})", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"download failed after {attempts} attempts: {url} ({str(last)[:120]})")


def fetch_day(symbol: str, day: str, kind: str) -> pd.DataFrame | None:
    if kind == "klines":
        url = f"{C.BINANCE_VISION}/klines/{symbol}/1s/{symbol}-1s-{day}.zip"
    else:
        url = f"{C.BINANCE_VISION}/aggTrades/{symbol}/{symbol}-aggTrades-{day}.zip"
    r = _get_with_retries(url)
    if r is None:
        print(f"  missing {url}", file=sys.stderr)
        return None
    z = zipfile.ZipFile(io.BytesIO(r.content))
    name = z.namelist()[0]
    with z.open(name) as f:
        head = f.readline().decode()
    has_header = not head.split(",")[0].strip().isdigit()
    df = pd.read_csv(z.open(name), header=0 if has_header else None)
    df.columns = KLINE_COLS if kind == "klines" else AGG_COLS
    if kind == "klines":
        # Binance switched open_time to microseconds for some files in 2025: normalise to ms.
        df["ts_ms"] = df["open_time"].astype("int64")
        df.loc[df["ts_ms"] > 10**14, "ts_ms"] //= 1000
        df = df[["ts_ms", "open", "high", "low", "close", "volume", "n_trades", "taker_buy_base"]]
    else:
        df["ts_ms"] = df["ts_ms"].astype("int64")
        df.loc[df["ts_ms"] > 10**14, "ts_ms"] //= 1000
        df = df[["ts_ms", "price", "qty", "is_buyer_maker"]]
    return df


def agg_last_per_ms(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse a day of aggTrades to the last traded price of every millisecond (ts_ms, price), sorted.
    This is the tick-level reference series: ~1-3 M rows/day for BTCUSDT, a few MB as parquet."""
    d = df[["ts_ms", "price"]].astype({"ts_ms": "int64", "price": "float64"})
    d = d.groupby("ts_ms", sort=True)["price"].last().reset_index()
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="+", required=True)
    ap.add_argument("--start", required=True); ap.add_argument("--end", required=True)
    ap.add_argument("--kind", choices=["klines", "aggTrades"], default="klines")
    ap.add_argument("--out", default="data")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for s in a.symbols:
        parts = []
        for day in daterange(a.start, a.end):
            df = fetch_day(s, day, a.kind)
            if df is not None:
                parts.append(df)
                print(f"  {s} {day}: {len(df)} rows", file=sys.stderr)
        if parts:
            out = pd.concat(parts, ignore_index=True).sort_values("ts_ms")
            path = os.path.join(a.out, f"binance_{s}_{'1s' if a.kind == 'klines' else 'agg'}.parquet")
            out.to_parquet(path, index=False)
            print(f"-> {path} ({len(out)} rows)", file=sys.stderr)


if __name__ == "__main__":
    main()
