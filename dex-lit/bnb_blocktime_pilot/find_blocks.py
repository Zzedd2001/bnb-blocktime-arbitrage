"""Step 1: locate fork blocks and dump block timestamps around each fork.

Usage:
    python find_blocks.py --fork Maxwell --hours 24 --out data/blocks_Maxwell.parquet
    python find_blocks.py --start 2025-06-23T00:00:00Z --end 2025-07-07T00:00:00Z --out data/blocks.parquet

Output: one row per block (number, timestamp, milli_ts, interval, gas_used, gas_limit, tx_count, miner).
Headers are fetched in adaptive JSON-RPC batches (start 100, halved on rejection) using
eth_getHeaderByNumber where available (header only, ~1 KB) and eth_getBlockByNumber(false) otherwise.
`interval` is only defined between consecutive block numbers (NaN otherwise), so the same functions
work for sparse block sets (see run_pilot.py, which only fetches the blocks it needs).
"""
from __future__ import annotations
import argparse, datetime as dt, sys
import numpy as np
import pandas as pd
import config as C
from rpc import Rpc, find_block_by_time


def parse_ts(s: str) -> int:
    return int(dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())


def dump_blocks(rpc: Rpc, b0: int, b1: int) -> pd.DataFrame:
    """All headers in [b0, b1]."""
    return dump_block_list(rpc, list(range(b0, b1 + 1)))


def dump_block_list(rpc: Rpc, numbers: list[int], workers: int = 1, log=None) -> pd.DataFrame:
    """Headers for an arbitrary (sorted, unique) list of block numbers; interval only between consecutive numbers.
    workers > 1 fetches concurrently across endpoints (Rpc.headers_parallel)."""
    log = log or (lambda m: print(m, file=sys.stderr))
    numbers = sorted(set(int(n) for n in numbers))
    if not numbers:
        return pd.DataFrame(columns=["number", "timestamp", "milli_ts", "gas_used", "gas_limit", "tx_count", "miner", "interval"])
    rows = []
    if workers and workers > 1:
        for b in rpc.headers(numbers, workers=workers, log=log):
            rows.append(block_row(b))
        return with_intervals(pd.DataFrame(rows))
    step = 2000
    for i in range(0, len(numbers), step):
        for b in rpc.headers(numbers[i:i + step]):
            rows.append(block_row(b))
        log(f"  headers {numbers[i]}..{numbers[min(i + step - 1, len(numbers) - 1)]} ({min(i + step, len(numbers))}/{len(numbers)})")
    return with_intervals(pd.DataFrame(rows))


# ---------------------------------------------------------------- exact timestamps for every block from sparse headers
def nominal_elapsed_ms(a: int, c: int, fork_block: int, pre_ms: int, post_ms: int) -> int:
    """Sum of nominal block periods over the intervals a->a+1, ..., c-1->c.  The interval n->n+1 has the
    post-fork period iff n >= fork_block (the fork block is the first block whose following interval is short)."""
    pre = max(0, min(c, fork_block) - a)
    post = (c - a) - pre
    return pre * pre_ms + post * post_ms


def fill_timestamps(b0: int, b1: int, fork_block: int, pre_ms: int, post_ms: int, known: dict[int, int],
                    fetch, log=print, max_leaf: int = 48) -> tuple[pd.DataFrame, int]:
    """Millisecond timestamps for EVERY block in [b0, b1] from a sparse set of fetched headers.

    BSC's Parlia consensus sets block.time = parent.time + period (1.5 s / 0.75 s / 0.45 s ...) unless the
    chain has fallen behind wall-clock time, in which case the block is later — never earlier.  Hence over a
    span [a, c] whose two end headers are known, elapsed(a, c) >= nominal(a, c), with equality iff every
    block in between sits exactly at its nominal time.  Spans that pass this check are filled arithmetically;
    spans that fail are bisected (fetching the midpoint header) until they pass or are small enough
    (<= max_leaf blocks) to fetch whole.  On real data (Maxwell ±7 d) 99.94% of consecutive swap blocks are
    at their nominal time, so this needs O(10^4) header fetches instead of O(10^6).

    `known`: {number: milli_ts} for already fetched headers (must include b0 and b1 or they are fetched).
    `fetch(numbers) -> DataFrame with columns number, milli_ts` (also expected to cache what it fetched).
    Returns (DataFrame[number, milli_ts, fetched], number_of_headers_fetched_here)."""
    ts = {int(k): int(v) for k, v in known.items() if b0 <= int(k) <= b1}
    fetched = 0
    need = [n for n in (b0, b1, fork_block) if b0 <= n <= b1 and n not in ts]
    if need:
        df = fetch(need); fetched += len(df)
        ts.update({int(r.number): int(r.milli_ts) for r in df.itertuples()})
    keys = sorted(ts)
    bad = [(a, c) for a, c in zip(keys[:-1], keys[1:])
           if c - a > 1 and ts[c] - ts[a] != nominal_elapsed_ms(a, c, fork_block, pre_ms, post_ms)]
    neg = [(a, c) for a, c in zip(keys[:-1], keys[1:]) if ts[c] - ts[a] < nominal_elapsed_ms(a, c, fork_block, pre_ms, post_ms)]
    if neg:
        raise ValueError(f"block timestamps run faster than the nominal period near {neg[:3]}: wrong fork block or period?")
    log(f"timestamps: {len(keys):,} known headers, {len(bad):,} spans off the nominal schedule -> bisecting")
    rounds, unresolved = 0, 0
    while bad:
        rounds += 1
        want = set()
        for a, c in bad:
            if c - a - 1 <= max_leaf:
                want.update(range(a + 1, c))
            else:
                want.add((a + c) // 2)
        want = sorted(want - set(ts))
        got = np.array([], dtype=np.int64)
        if want:
            df = fetch(want); fetched += len(df)
            new = {int(r.number): int(r.milli_ts) for r in df.itertuples()}
            ts.update(new)
            got = np.array(sorted(new), dtype=np.int64)
        nxt = []
        for a, c in bad:
            inside = got[np.searchsorted(got, a, "right"):np.searchsorted(got, c, "left")] if len(got) else got
            if len(inside) == 0:            # cannot happen with a real fetch (it returns exactly what was asked)
                unresolved += 1
                continue
            pts = [a] + [int(x) for x in inside] + [c]
            for x, y in zip(pts[:-1], pts[1:]):
                if y - x > 1:
                    d = ts[y] - ts[x]
                    nom = nominal_elapsed_ms(x, y, fork_block, pre_ms, post_ms)
                    if d < nom:
                        raise ValueError(f"block timestamps run faster than the nominal period in {x}..{y}")
                    if d != nom:
                        nxt.append((x, y))
        bad = nxt
        log(f"  bisection round {rounds}: fetched {len(want):,} headers, {len(bad):,} spans still irregular")
    if unresolved:
        log(f"  WARNING: {unresolved} irregular spans could not be refined (fetch returned no headers inside them)")
    # vectorised fill: ts(n) = ts(a) + nominal(a, n) inside every verified span (a, c)
    keys = np.array(sorted(ts), dtype=np.int64)
    kts = np.array([ts[int(k)] for k in keys], dtype=np.int64)
    numbers = np.arange(b0, b1 + 1, dtype=np.int64)
    idx = np.searchsorted(keys, numbers, side="right") - 1          # index of the last known block <= n
    a = keys[idx]
    pre = np.maximum(0, np.minimum(numbers, fork_block) - a)
    post = (numbers - a) - pre
    milli = kts[idx] + pre * pre_ms + post * post_ms
    is_known = np.zeros(len(numbers), dtype=bool)
    is_known[keys - b0] = True
    out = pd.DataFrame({"number": numbers, "milli_ts": milli, "fetched": is_known})
    # sanity: the fill reproduces every fetched header exactly (by construction) and is monotone
    assert (out.loc[out.fetched, "milli_ts"].values == kts).all()
    assert (np.diff(milli) > 0).all()
    return out, fetched


def with_intervals(df: pd.DataFrame) -> pd.DataFrame:
    df = df.drop_duplicates("number").sort_values("number").reset_index(drop=True)
    consecutive = df["number"].diff() == 1
    df["interval"] = (df["milli_ts"].diff() / 1000.0).where(consecutive)
    return df


def block_row(b: dict) -> dict:
    """BEP-520: since Lorentz the millisecond part of the timestamp is stored in the LAST TWO BYTES
    of header.mixHash (MilliTimestamp = timestamp*1000 + ms).  Before Lorentz mixHash is zero."""
    ts = int(b["timestamp"], 16)
    ms = int(b.get("mixHash", "0x0")[-4:], 16)
    ms = ms if ms < 1000 else 0
    return {"number": int(b["number"], 16), "timestamp": ts, "milli_ts": ts * 1000 + ms,
            "gas_used": int(b["gasUsed"], 16), "gas_limit": int(b["gasLimit"], 16),
            "tx_count": len(b["transactions"]) if isinstance(b.get("transactions"), list) else -1,
            "miner": b.get("miner")}


def detect_fork_block(df: pd.DataFrame, before: float, after: float, window: int = 60) -> int | None:
    """First block from which the FORWARD-looking mean of the next `window` intervals (ms precision,
    see block_row) is below the midpoint between the pre- and post-fork block intervals."""
    thr = (before + after) / 2
    fwd = df["interval"].iloc[::-1].rolling(window).mean().iloc[::-1].shift(-1)   # mean of intervals i+1..i+window
    hit = df.index[fwd < thr]
    if len(hit) == 0:
        return None
    # refine: from the coarse hit, the fork block is the first block whose own following interval is short
    # and stays short (missed blocks only make intervals longer, so a single short interval is unambiguous)
    nxt = df["interval"].shift(-1)
    short10 = nxt.iloc[::-1].rolling(10).mean().iloc[::-1]
    j = df.index[(df.index >= hit[0]) & (nxt < thr) & (short10 < thr)]
    return int(df.loc[j[0] if len(j) else hit[0], "number"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fork", choices=list(C.FORKS))
    ap.add_argument("--hours", type=float, default=12, help="hours before and after the fork to dump")
    ap.add_argument("--start"); ap.add_argument("--end")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rpc = Rpc()
    if a.fork:
        t, before, after = C.FORKS[a.fork]
        ts = parse_ts(t)
        t0, t1 = ts - int(a.hours * 3600), ts + int(a.hours * 3600)
    else:
        t0, t1 = parse_ts(a.start), parse_ts(a.end)
        before = after = None
    b0 = find_block_by_time(rpc, t0)
    b1 = find_block_by_time(rpc, t1)
    print(f"blocks {b0}..{b1} ({b1 - b0 + 1} blocks)", file=sys.stderr)
    df = dump_blocks(rpc, b0, b1)
    df.to_parquet(a.out, index=False)
    if a.fork:
        fb = detect_fork_block(df, before, after)
        print(f"{a.fork}: detected fork block ≈ {fb}; mean interval before/after: "
              f"{df[df.number < fb].interval.mean():.3f}s / {df[df.number >= fb].interval.mean():.3f}s"
              if fb else f"{a.fork}: fork not detected in window")
    print(df.describe().to_string())


if __name__ == "__main__":
    main()
