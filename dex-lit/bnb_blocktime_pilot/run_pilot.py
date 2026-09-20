"""One-command pilot / full sample: fork block -> swaps -> block timestamps -> Binance -> metrics -> zip.

    # quick connectivity check (~10 min): 6 h before/after Maxwell, one pool
    python run_pilot.py --fork Maxwell --hours 6 --pools WBNB-USDT-500 --out pilot_quick

    # real pilot: 7 days before/after, three pools
    python run_pilot.py --fork Maxwell --hours 168 --pools WBNB-USDT-500 ETH-USDT-500 BTCB-USDT-500 --out pilot_maxwell

    # full sample, all pools, 4 parallel log/header fetchers
    python run_pilot.py --fork Maxwell --hours 720 --pools all --out full_maxwell --include-swaps \
        --logs-rpc "https://bsc-mainnet.nodereal.io/v1/<key>" --workers 4

    # offline integration test against mock_server.py
    python run_pilot.py --fork Maxwell --hours 3 --pools WBNB-USDT-500 --out /tmp/pilot_mock \
        --rpc http://127.0.0.1:8545 --binance-base http://127.0.0.1:8546/data/spot/daily

Every step is resumable: existing parquet files are reused (swap logs per 250k-block segment, headers,
the block-timestamp table, Binance days).  Pools are processed one at a time (fetch -> analyse -> free),
so memory stays bounded even for pools with tens of millions of swaps.  At the end, <out>/pilot_results.zip
contains regime/daily tables, summary.json and (if --include-swaps) the per-swap enriched data.

Block timestamps: instead of fetching a header for every block with a swap (millions of blocks on
public nodes), the run fetches anchor headers (2 consecutive blocks every 10 minutes, plus the fork window)
and reconstructs every other block's millisecond timestamp from BSC's fixed block period, verifying each
span end-to-end and bisecting the rare spans where the chain fell behind schedule
(find_blocks.fill_timestamps; ~10^4 headers instead of ~10^6, exact by construction).
"""
from __future__ import annotations
import argparse, datetime as dt, gc, glob, json, os, re, shutil, sys, time, zipfile
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pandas as pd
import pyarrow.compute as pc
import pyarrow.parquet as pq
from pandas.api.types import union_categoricals
import config as C
from rpc import Rpc, find_block_by_time, resolve_pool, verify_tokens, redact, clean_url
from find_blocks import dump_blocks, dump_block_list, with_intervals, detect_fork_block, parse_ts, block_row, fill_timestamps
from fetch_swaps import fetch_range, decode_swap
import fetch_binance as FB
import fetch_hypersync as HS
import analyze_pilot as A

SEGMENT = 250_000   # blocks per swap file (resume granularity)
PROBE_BLOCK = [0]   # block used to probe eth_getLogs capability (set to the fork block at run time)
WORKERS = {"logs": 1, "headers": 1}
HYPERSYNC = {"obj": None}   # HS.HyperSyncLogs when --hypersync is given: logs come from Envio HyperSync, not eth_getLogs
BIG_INT_COLS = ("amount0", "amount1", "sqrt_price_x96", "liquidity", "protocol_fee0", "protocol_fee1")


def peak_mem_gb() -> float:
    """Peak resident memory of this process (macOS reports bytes, Linux kilobytes)."""
    import resource
    v = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return v / 1e9 if sys.platform == "darwin" else v / 1e6


def log(msg):
    print(f"[{dt.datetime.now().strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


def coarse_fork_scan(rpc, ts_guess: int, before: float, after: float):
    """Sample 30 consecutive headers every FORK_SCAN_STEP_MIN minutes over FORK_SCAN_RANGE_H around the guess;
    return (block of last slow sample, block of first fast sample) bracketing the fork, or None."""
    thr = (before + after) / 2
    lo_h, hi_h = C.FORK_SCAN_RANGE_H
    t = ts_guess + int(lo_h * 3600)
    prev_slow = None
    b_hint = None
    while t <= ts_guess + int(hi_h * 3600):
        b = find_block_by_time(rpc, t, lo=b_hint)
        hdrs = rpc.headers(list(range(b, b + 30)))
        rows = [block_row(h) for h in hdrs if h]
        ints = [(rows[i + 1]["milli_ts"] - rows[i]["milli_ts"]) / 1000 for i in range(len(rows) - 1)]
        mean = sum(ints) / max(len(ints), 1)
        log(f"  scan {dt.datetime.fromtimestamp(t, dt.timezone.utc):%m-%d %H:%M} block {b}: mean interval {mean:.3f}s")
        if mean < thr and prev_slow is not None:
            return prev_slow, b + 30
        if mean >= thr:
            prev_slow = b
        b_hint = b
        t += C.FORK_SCAN_STEP_MIN * 60
    return None


def step_fork(rpc, fork, out):
    """Exact fork block: dense headers around the announced time; if the regime change is not inside that
    window, a coarse scan brackets it first (public announcements rarely give the exact hour)."""
    t, before, after = C.FORKS[fork]
    path = os.path.join(out, f"blocks_forkwindow_{fork}.parquet")
    ts = parse_ts(t)
    fb = None
    if os.path.exists(path):
        df = pd.read_parquet(path)
        fb = detect_fork_block(df, before, after)
        if fb is None:                      # stale cache from an earlier run that missed the fork: redo
            os.remove(path)
    if fb is None:
        f0 = find_block_by_time(rpc, ts - int(C.FORK_DETECT_HOURS * 3600))
        f1 = find_block_by_time(rpc, ts + int(C.FORK_DETECT_HOURS * 3600))
        log(f"fork window: blocks {f0}..{f1} ({f1 - f0 + 1} headers)")
        df = dump_blocks(rpc, f0, f1)
        fb = detect_fork_block(df, before, after)
        if fb is None:
            log("fork not inside the dense window — coarse scan for the regime change…")
            br = coarse_fork_scan(rpc, ts, before, after)
            if br is None:
                raise SystemExit("could not locate the block-interval change; adjust config.FORKS time / FORK_SCAN_RANGE_H")
            log(f"bracketed between blocks {br[0]} and {br[1]}; fetching dense headers")
            df = dump_blocks(rpc, br[0], br[1] + 400)      # +400 blocks so the post-fork side is long enough to detect
            fb = detect_fork_block(df, before, after)
        df.to_parquet(path, index=False)
    if fb is None:
        raise SystemExit("fork block not detected; inspect blocks_forkwindow parquet")
    pre, post = df[df.number < fb], df[df.number >= fb]
    log(f"fork block {fb} at {dt.datetime.fromtimestamp(int(df.loc[df.number == fb, 'timestamp'].iloc[0]), dt.timezone.utc):%Y-%m-%d %H:%M:%S} UTC; "
        f"mean interval pre {pre.interval.mean():.3f}s (n={len(pre)}), post {post.interval.mean():.3f}s (n={len(post)})")
    return df, fb


def step_blocks(rpc, fork, needed: set, out, cached: pd.DataFrame | None):
    """Headers for the needed block numbers (hourly sample runs + window edges + fork window), cached."""
    path = os.path.join(out, f"blocks_{fork}.parquet")
    have = pd.read_parquet(path) if os.path.exists(path) else (cached if cached is not None else pd.DataFrame())
    missing = sorted(needed - set(have["number"].tolist() if len(have) else []))
    log(f"headers: {len(needed)} needed, {len(missing)} to fetch")
    if missing:
        new = dump_block_list(rpc, missing, workers=WORKERS["headers"], log=log)
        have = pd.concat([have, new], ignore_index=True) if len(have) else new
    df = with_intervals(have)
    df.to_parquet(path, index=False)
    return df


def step_timestamps(rpc, fork, b0, b1, fork_block, before, after, hdr: pd.DataFrame, out):
    """Exact millisecond timestamp for every block in [b0, b1] (cached): sample-run headers + span checks +
    bisection of irregular spans (see find_blocks.fill_timestamps).  Extra headers fetched here are added to
    the header cache.  Returns (timestamp table, header table)."""
    path = os.path.join(out, f"timestamps_{fork}_{b0}_{b1}.parquet")
    cache = os.path.join(out, f"blocks_{fork}.parquet")
    if os.path.exists(path):
        t = pd.read_parquet(path)
        if len(t) == b1 - b0 + 1 and int(t["number"].iloc[0]) == b0:
            log(f"timestamps: cached table for blocks {b0}..{b1} ({len(t):,} blocks, {int(t['fetched'].sum()):,} fetched headers)")
            return t, hdr
    state = {"hdr": hdr}

    def fetch(nums):
        df = dump_block_list(rpc, nums, workers=WORKERS["headers"], log=log)
        state["hdr"] = with_intervals(pd.concat([state["hdr"], df], ignore_index=True))
        state["hdr"].to_parquet(cache, index=False)
        return df[["number", "milli_ts"]]

    known = dict(zip(hdr["number"].astype(int), hdr["milli_ts"].astype(np.int64)))
    t0 = time.time()
    t, n_fetched = fill_timestamps(b0, b1, fork_block, int(round(before * 1000)), int(round(after * 1000)), known, fetch, log)
    log(f"timestamps: {len(t):,} blocks, {int(t['fetched'].sum()):,} from headers ({n_fetched:,} fetched now), "
        f"{time.time() - t0:.0f}s")
    t.to_parquet(path, index=False)
    return t, state["hdr"]


def hourly_sample_blocks(b0: int, b1: int, blocks_per_hour_est: float, run: int, per_hour: int = 1) -> set:
    """`run` consecutive blocks at (approximately) every 1/per_hour hour between b0 and b1.  These headers anchor
    the block-timestamp reconstruction (fill_timestamps) and supply gas statistics; interval statistics come
    from the complete timestamp table."""
    step = max(int(blocks_per_hour_est / per_hour), run * 2)
    out = set()
    for start in range(b0, b1 + 1, step):
        out.update(range(start, min(start + run, b1 + 1)))
    return out


def step_swaps(rpc, pool_cfg, b0, b1, out):
    base, quote = C.TOKENS[pool_cfg["base"]], C.TOKENS[pool_cfg["quote"]]
    try:
        info = resolve_pool(rpc, base[0], quote[0], pool_cfg["fee"], fallback=C.KNOWN_POOLS.get(pool_cfg["name"]))
    except Exception as e:  # noqa
        log(f"skipping {pool_cfg['name']}: {str(e)[:120]}")
        return [], None
    b0_is_base = info["token0"].lower() == base[0].lower()
    meta = {"pool": info["pool"], "token0": info["token0"], "token1": info["token1"], "fee": info["fee"],
            "base_is_token0": b0_is_base, "dec0": base[1] if b0_is_base else quote[1], "dec1": quote[1] if b0_is_base else base[1]}
    log(f"swaps {pool_cfg['name']}: pool {info['pool']} (base_is_token0={b0_is_base})")
    if HYPERSYNC["obj"] is None and not getattr(rpc, "log_ok", None):
        log("probing which endpoints accept eth_getLogs…")
        ok = rpc.probe_logs(info["pool"], [C.TOPIC_SWAP_PCS_V3], PROBE_BLOCK[0], log)
        if not ok:
            raise SystemExit("No endpoint accepts eth_getLogs for a historical block. Free public BSC nodes prune or "
                             "refuse old logs: create a free key at Alchemy (bnb-mainnet) or NodeReal (bsc-mainnet) and rerun "
                             "with --logs-rpc https://<your-endpoint-with-key>  (the key stays on your machine).")
    files = []
    for s0 in range(b0, b1 + 1, SEGMENT):
        s1 = min(s0 + SEGMENT - 1, b1)
        path = os.path.join(out, f"swaps_{pool_cfg['name']}_{s0}_{s1}.parquet")
        if os.path.exists(path):
            try:
                pq.read_metadata(path)                # a file truncated by an interrupted run is refetched
                files.append(path); continue
            except Exception:  # noqa
                log(f"  {os.path.basename(path)}: unreadable (interrupted write?) -> refetching")
                os.remove(path)
        t0 = time.time()
        parts_dir = path + ".parts"
        os.makedirs(parts_dir, exist_ok=True)
        # parts of an interrupted fetch are kept: each is named by the block range it covers, so only the
        # uncovered ranges of the segment are fetched again (files from older versions are discarded)
        done_ranges = []
        for f in glob.glob(os.path.join(parts_dir, "*.parquet")):
            m = re.match(r"^(\d{12})_(\d{12})\.parquet$", os.path.basename(f))
            if m and int(m.group(1)) <= int(m.group(2)):
                try:
                    pq.read_metadata(f); done_ranges.append((int(m.group(1)), int(m.group(2))))
                    continue
                except Exception:  # noqa
                    pass
            os.remove(f)
        gaps = uncovered_ranges(s0, s1, done_ranges)
        if done_ranges:
            covered = sum(e - s + 1 for s, e in done_ranges)
            log(f"  {s0}..{s1}: resuming, {len(done_ranges)} parts covering {covered:,} of {s1 - s0 + 1:,} blocks already on disk")

        def on_chunk(logs, a, b):
            """Decode one eth_getLogs response and spill it to disk right away (called from worker threads):
            memory never holds more than one response, however many swaps a segment has.  Empty ranges are
            recorded too, so a resumed run knows they are done."""
            df = pd.DataFrame([decode_swap(l) for l in logs])
            if len(df):
                df = df.sort_values(["block", "log_index"], kind="stable")
            tmp = os.path.join(parts_dir, f"{a:012d}_{b:012d}.parquet.part")
            df.to_parquet(tmp, index=False); os.replace(tmp, tmp[:-5])
        for ga, gb in gaps:
            if HYPERSYNC["obj"] is not None:
                HYPERSYNC["obj"].fetch_range(info["pool"], C.TOPIC_SWAP_PCS_V3, ga, gb, on_chunk, log)
            else:
                fetch_range(rpc, info["pool"], [C.TOPIC_SWAP_PCS_V3], ga, gb, log=log, workers=WORKERS["logs"], on_chunk=on_chunk)
        n = merge_parts(sorted(glob.glob(os.path.join(parts_dir, "*.parquet"))), path, meta)
        shutil.rmtree(parts_dir, ignore_errors=True)
        files.append(path)
        log(f"  {s0}..{s1}: {n} swaps in {time.time() - t0:.0f}s (peak mem {peak_mem_gb():.1f} GB)")
    return files, meta


def uncovered_ranges(s0: int, s1: int, done: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Sub-ranges of [s0, s1] not covered by the (possibly overlapping, unsorted) ranges in `done`."""
    gaps, cur = [], s0
    for a, b in sorted(done):
        if b < cur:
            continue
        if a > cur:
            gaps.append((cur, min(a - 1, s1)))
        cur = max(cur, b + 1)
        if cur > s1:
            break
    if cur <= s1:
        gaps.append((cur, s1))
    return gaps


def merge_parts(parts: list[str], path: str, meta: dict) -> int:
    """Concatenate the per-response part files (sorted by first block; responses cover disjoint block ranges,
    so this is global block order) into one segment file, streaming one part at a time, and add the constant
    pool metadata columns.  Returns the row count."""
    import pyarrow as pa
    tmp = path + ".part"
    writer, schema, n = None, None, 0
    for f in parts:
        t = pq.read_table(f)
        if t.num_rows == 0 or t.num_columns == 0:
            continue
        for k, v in meta.items():
            t = t.append_column(k, pa.array([v] * t.num_rows))
        if writer is None:
            schema = t.schema.remove_metadata()
            writer = pq.ParquetWriter(tmp, schema)
        writer.write_table(t.cast(schema))
        n += t.num_rows
    if writer is None:                       # no swaps in this segment: keep an empty file with the metadata columns
        df = pd.DataFrame({k: pd.Series([], dtype=(object if isinstance(v, str) else type(v))) for k, v in meta.items()})
        df.to_parquet(tmp, index=False)
    else:
        writer.close()
    os.replace(tmp, path)
    return n


SWAP_COLS = ["block", "log_index", "sender", "recipient", "amount0", "amount1", "sqrt_price_x96", "liquidity", "tick", "block_ts"]
BATCH_ROWS = 300_000   # rows per in-memory batch when streaming segment files into the analysis


def _table_to_frame(tbl, meta: dict, cols: list[str]) -> pd.DataFrame:
    for c in BIG_INT_COLS:
        if c in tbl.column_names and str(tbl.schema.field(c).type) in ("string", "large_string", "string_view"):
            tbl = tbl.set_column(tbl.schema.get_field_index(c), c, pc.cast(tbl[c], "float64"))
    tbl = tbl.replace_schema_metadata(None)   # else to_pandas restores the stored (string) pandas dtypes
    d = tbl.to_pandas(categories=[c for c in ("sender", "recipient") if c in cols])
    for c in ("amount0", "amount1", "sqrt_price_x96", "liquidity"):
        if c in d and d[c].dtype == object:
            d[c] = d[c].to_numpy().astype(np.float64)
    for k, v in meta.items():
        if isinstance(v, str):
            d[k] = pd.Categorical.from_codes(np.zeros(len(d), dtype=np.int8), categories=[v])
        else:
            d[k] = v
    return d


def iter_swaps(files: list[str], meta: dict, batch_rows: int = BATCH_ROWS):
    """Stream the per-segment swap files as fixed-size row batches (in block order), each converted like
    load_swaps: only the needed columns, uint256 strings cast to float64 with pyarrow, addresses categorical.
    Memory is bounded by `batch_rows` regardless of how many swaps a segment holds."""
    import pyarrow as pa
    for f in files:
        pf = pq.ParquetFile(f)
        cols = [c for c in SWAP_COLS if c in pf.schema_arrow.names]
        if pf.metadata.num_rows == 0:
            continue
        for batch in pf.iter_batches(batch_size=batch_rows, columns=cols):
            if batch.num_rows == 0:
                continue
            yield _table_to_frame(pa.Table.from_batches([batch]), meta, cols)
        pa.default_memory_pool().release_unused()


def load_swaps(files: list[str], meta: dict) -> pd.DataFrame:
    """Memory-lean loader for the per-segment swap files: only the columns the analysis needs, uint256/int256
    decimal strings cast to float64 with pyarrow (exact to ~16 significant digits, ample for prices and amounts),
    addresses as categoricals, constant pool metadata as single-category columns."""
    frames = []
    for f in files:
        schema = pq.read_schema(f)
        cols = [c for c in SWAP_COLS if c in schema.names]
        tbl = pq.read_table(f, columns=cols)
        if tbl.num_rows == 0:
            continue
        frames.append(_table_to_frame(tbl, meta, cols))
    if not frames:
        return pd.DataFrame(columns=SWAP_COLS)
    # concatenate the address categoricals without materialising millions of Python strings
    cats = {c: union_categoricals([fr[c] for fr in frames]) for c in ("sender", "recipient")
            if c in frames[0] and all(isinstance(fr[c].dtype, pd.CategoricalDtype) for fr in frames)}
    meta_cols = [k for k, v in meta.items() if isinstance(v, str)]
    df = pd.concat([fr.drop(columns=list(cats) + meta_cols) for fr in frames], ignore_index=True)
    for c, v in cats.items():
        df[c] = v
    del frames, cats
    for k in meta_cols:
        df[k] = pd.Categorical.from_codes(np.zeros(len(df), dtype=np.int8), categories=[meta[k]])
    return df


def step_binance(symbol, d0, d1, out, workers: int = 1):
    """1-second close series for a Binance symbol, or for a cross-rate given as [base_symbol, quote_symbol]
    (e.g. CAKE/WBNB = CAKEUSDT / BNBUSDT).  Cached as parquet.  Days are downloaded concurrently."""
    if isinstance(symbol, (list, tuple)):
        a, b = step_binance(symbol[0], d0, d1, out, workers), step_binance(symbol[1], d0, d1, out, workers)
        path = os.path.join(out, f"binance_{symbol[0]}_over_{symbol[1]}_1s.parquet")
        if not os.path.exists(path):
            x = pd.read_parquet(a)[["ts_ms", "close"]].rename(columns={"close": "x"})
            y = pd.read_parquet(b)[["ts_ms", "close"]].rename(columns={"close": "y"})
            m = x.merge(y, on="ts_ms", how="outer").sort_values("ts_ms")
            m[["x", "y"]] = m[["x", "y"]].ffill()
            m = m.dropna()
            m["close"] = m["x"].astype(float) / m["y"].astype(float)
            m[["ts_ms", "close"]].to_parquet(path, index=False)
        return path
    path = os.path.join(out, f"binance_{symbol}_1s.parquet")
    if os.path.exists(path):
        return path

    def one(day):
        df = FB.fetch_day(symbol, day, "klines")
        if df is None:
            log(f"  {symbol} {day}: 1s klines missing, trying aggTrades")
            df = FB.fetch_day(symbol, day, "aggTrades")
            if df is not None:   # build 1s closes from aggTrades
                df = df.assign(sec=df.ts_ms // 1000 * 1000).groupby("sec")["price"].last().rename("close").reset_index().rename(columns={"sec": "ts_ms"})
        if df is not None:
            log(f"  {symbol} {day}: {len(df)} rows")
        return df

    days = list(FB.daterange(d0, d1))
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 2))) as ex:      # gentle on proxies / the CDN
        parts = [d for d in ex.map(one, days) if d is not None]
    if not parts:
        raise SystemExit(f"no Binance data for {symbol}")
    pd.concat(parts, ignore_index=True).sort_values("ts_ms").to_parquet(path, index=False)
    return path


def step_binance_agg(symbol, d0, d1, out, workers: int = 1):
    """Tick-level reference: Binance aggTrades collapsed to the last price of every millisecond, one parquet per
    day in <out>/binance_agg/<SYMBOL>/<day>.parquet (cached; missing days are downloaded, 2 at a time).
    A cross rate given as [base_symbol, quote_symbol] returns the two directories."""
    if isinstance(symbol, (list, tuple)):
        return [step_binance_agg(symbol[0], d0, d1, out, workers), step_binance_agg(symbol[1], d0, d1, out, workers)]
    ddir = os.path.join(out, "binance_agg", symbol)
    os.makedirs(ddir, exist_ok=True)
    days = list(FB.daterange(d0, d1))
    todo = [d for d in days if not os.path.exists(os.path.join(ddir, f"{d}.parquet"))]

    def one(day):
        df = FB.fetch_day(symbol, day, "aggTrades")
        if df is None:
            log(f"  {symbol} {day}: aggTrades missing")
            return day, 0
        last = FB.agg_last_per_ms(df)
        tmp = os.path.join(ddir, f"{day}.parquet.part")
        last.to_parquet(tmp, index=False); os.replace(tmp, os.path.join(ddir, f"{day}.parquet"))
        log(f"  {symbol} {day}: {len(df):,} aggTrades -> {len(last):,} ms prices")
        return day, len(last)

    if todo:
        log(f"{symbol}: downloading aggTrades for {len(todo)} of {len(days)} days (tick-level reference)")
        with ThreadPoolExecutor(max_workers=max(1, min(workers, 2))) as ex:
            list(ex.map(one, todo))
    have = [d for d in days if os.path.exists(os.path.join(ddir, f"{d}.parquet"))]
    if not have:
        raise SystemExit(f"no Binance aggTrades for {symbol}")
    return ddir


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fork", default="Maxwell", choices=list(C.FORKS))
    ap.add_argument("--hours", type=float, default=168)
    ap.add_argument("--pools", nargs="+", default=["WBNB-USDT-500", "ETH-USDT-500", "BTCB-USDT-500"],
                    help="pool names from config.PILOT_POOLS, or 'all'")
    ap.add_argument("--out", default="pilot_out")
    ap.add_argument("--rpc", nargs="*", help="override general RPC endpoint(s) (headers, eth_call)")
    ap.add_argument("--logs-rpc", nargs="*", help="endpoint(s) with full history used ONLY for eth_getLogs, e.g. a free "
                                                  "Alchemy/NodeReal key URL (or set env BSC_LOGS_RPC)")
    ap.add_argument("--binance-base", help="override Binance bulk-data base URL")
    ap.add_argument("--include-swaps", action="store_true", help="add per-swap enriched parquet to the zip")
    ap.add_argument("--hypersync", nargs="?", const=HS.DEFAULT_URL, default=None, metavar="URL",
                    help=f"fetch swap logs from Envio HyperSync instead of eth_getLogs (default URL {HS.DEFAULT_URL}; "
                         "token from env ENVIO_API_TOKEN; pip install hypersync)")
    ap.add_argument("--workers", type=int, default=1, help="parallel eth_getLogs requests (NodeReal free tier: 3-4 is safe)")
    ap.add_argument("--header-workers", type=int, default=None, help="parallel header batches across public nodes (default: --workers)")
    ap.add_argument("--reference", choices=["klines", "aggtrades"], default="klines",
                    help="swap-level reference price: close of the last completed 1s kline (default) or the last Binance "
                         "aggTrade at/before the block timestamp (tick level; results go to results_agg/ and summary_agg.json)")
    ap.add_argument("--ref-lag-ms", type=int, default=0, help="with --reference aggtrades: use the last trade at least this "
                                                                 "many ms before the block timestamp (0 = at block time)")
    a = ap.parse_args()
    # output directory / summary / zip names: results (klines), results_agg (aggTrades at block time),
    # results_agg_lag<N> (aggTrades N ms before block time) — so robustness runs never overwrite each other
    TAG = "" if a.reference == "klines" else ("_agg" if a.ref_lag_ms == 0 else f"_agg_lag{a.ref_lag_ms}")
    RES = "results" + TAG
    SUMMARY_NAME = f"summary{TAG}.json"
    os.makedirs(os.path.join(a.out, RES), exist_ok=True)
    WORKERS["logs"] = max(1, a.workers)
    WORKERS["headers"] = max(1, a.header_workers if a.header_workers is not None else a.workers)
    if a.rpc:
        C.RPC_ENDPOINTS[:] = [clean_url(u) for u in a.rpc]
    if a.binance_base:
        C.BINANCE_VISION = a.binance_base
    rpc = Rpc(endpoints=C.RPC_ENDPOINTS)
    rpc.logs_endpoints = [clean_url(u) for u in (a.logs_rpc or C.LOGS_RPC_ENDPOINTS or [u for u in os.environ.get("BSC_LOGS_RPC", "").split(",") if u])]
    if a.hypersync:
        if not HS.available():
            raise SystemExit("--hypersync needs the client library:  pip install hypersync   (then set ENVIO_API_TOKEN)")
        if not os.environ.get("ENVIO_API_TOKEN"):
            log("WARNING: ENVIO_API_TOKEN is not set — HyperSync rate-limits or rejects requests without a token "
                "(free token: https://envio.dev/app/api-tokens)")
        HYPERSYNC["obj"] = HS.HyperSyncLogs(a.hypersync)
        log(f"swap logs from HyperSync: {a.hypersync}")
    elif rpc.logs_endpoints:
        log(f"dedicated log endpoint(s): {', '.join(redact(u) for u in rpc.logs_endpoints)}")
    log("checking RPC endpoints (eth_chainId)…")
    rpc.check_endpoints(log)
    log(f"using {len(rpc.endpoints)} endpoint(s); workers: logs {WORKERS['logs']}, headers {WORKERS['headers']}")
    log("verifying token contracts (symbol/decimals)…")
    verify_tokens(rpc, C.TOKENS, log)

    # 1) exact fork block from a dense header window around the announced time
    fork_df, fork_block = step_fork(rpc, a.fork, a.out)
    PROBE_BLOCK[0] = fork_block
    # 2) study window [b0, b1] by timestamp
    t, before, after = C.FORKS[a.fork]
    ts_fork = int(fork_df.loc[fork_df.number == fork_block, "timestamp"].iloc[0])
    b0 = find_block_by_time(rpc, ts_fork - int(a.hours * 3600))
    b1 = find_block_by_time(rpc, ts_fork + int(a.hours * 3600))
    log(f"study window: blocks {b0}..{b1} ({b1 - b0 + 1} blocks, +/-{a.hours} h around block {fork_block})")
    if HYPERSYNC["obj"] is not None:
        cid, height = HYPERSYNC["obj"].probe(need_height=b1)
        if cid != C.CHAIN_ID:
            raise SystemExit(f"HyperSync endpoint serves chain {cid}, expected {C.CHAIN_ID}")
        log(f"hypersync OK: chain {cid}, archive height {height:,}")
    d0 = dt.datetime.fromtimestamp(ts_fork - int(a.hours * 3600), dt.timezone.utc).date().isoformat()
    d1 = dt.datetime.fromtimestamp(ts_fork + int(a.hours * 3600) + 60, dt.timezone.utc).date().isoformat()

    # 3) headers: hourly sample runs (interval statistics) + window edges + fork window; then the exact
    #    timestamp of EVERY block in the window by span verification / bisection (needs no per-swap headers)
    needed = {b0, b1, fork_block}
    needed |= hourly_sample_blocks(b0, fork_block - 1, 3600 / before, C.ANCHOR_RUN_BLOCKS, C.ANCHORS_PER_HOUR)
    needed |= hourly_sample_blocks(fork_block, b1, 3600 / after, C.ANCHOR_RUN_BLOCKS, C.ANCHORS_PER_HOUR)
    hdr = step_blocks(rpc, a.fork, needed, a.out, fork_df)
    tstab, hdr = step_timestamps(rpc, a.fork, b0, b1, fork_block, before, after, hdr, a.out)
    blocks = tstab[["number", "milli_ts"]].copy()
    blocks["interval"] = blocks["milli_ts"].diff() / 1000.0          # exact for every block (see fill_timestamps)
    # hourly block table (small): block counts / intervals from the full table, gas from the fetched headers
    hb = blocks.assign(hour=pd.to_datetime(blocks["milli_ts"], unit="ms", utc=True).dt.floor("h"))
    hourly = hb.groupby("hour").agg(n_blocks=("number", "size"), interval_ms=("interval", lambda x: 1000 * x.mean()),
                                    n_intervals=("interval", "count"))
    hg = hdr.assign(hour=pd.to_datetime(hdr["milli_ts"], unit="ms", utc=True).dt.floor("h"))
    hourly = hourly.join(hg.groupby("hour").agg(n_headers=("number", "size"), gas_used=("gas_used", "mean"),
                                                gas_limit=("gas_limit", "mean")), how="left")
    hourly.to_csv(os.path.join(a.out, RES, "blocks_hourly.csv"))
    del hb, hg

    # 4) per pool: swaps -> Binance -> metrics (one pool in memory at a time)
    pools = list(C.PILOT_POOLS) if a.pools == ["all"] else [p for p in C.PILOT_POOLS if p["name"] in a.pools]
    summary = {"fork": a.fork, "fork_block": fork_block, "fork_time_utc": dt.datetime.fromtimestamp(ts_fork, dt.timezone.utc).isoformat(),
               "block_interval_before": before, "block_interval_after": after, "hours": a.hours, "blocks": [b0, b1],
               "n_headers_fetched": int(len(hdr)), "n_blocks_timestamped": int(len(tstab)), "pools": {}}
    summary["reference"] = a.reference; summary["ref_lag_ms"] = a.ref_lag_ms
    spath = os.path.join(a.out, SUMMARY_NAME)
    for p in pools:
        files, meta = step_swaps(rpc, p, b0, b1, a.out)
        if meta is None:
            continue
        n_rows = sum(pq.read_metadata(f).num_rows for f in files)
        log(f"{p['name']}: {n_rows:,} swaps in {len(files)} segment files (peak mem so far {peak_mem_gb():.1f} GB)")
        if not p["binance"]:
            log(f"{p['name']}: no Binance reference, skipping metrics"); continue
        if n_rows == 0:
            log(f"{p['name']}: no swaps in window"); continue
        ts_ms = tstab["milli_ts"].to_numpy()
        chk = {"n": 0, "bad": 0}

        def chunks():
            """Fixed-size row batches in block order (memory stays bounded); provider timestamps are cross-checked."""
            done, k = 0, 0
            for d in iter_swaps(files, meta):
                if "block_ts" in d:
                    has = d["block_ts"].to_numpy() > 0
                    if has.any():
                        recon = ts_ms[d["block"].to_numpy()[has] - b0] // 1000
                        chk["n"] += int(has.sum()); chk["bad"] += int((recon != d["block_ts"].to_numpy()[has]).sum())
                done += len(d); k += 1
                if k % 5 == 1:
                    log(f"  metrics: batch {k}, {done:,}/{n_rows:,} swaps, blocks up to {int(d['block'].iloc[-1]):,}, peak mem {peak_mem_gb():.1f} GB")
                yield d
            if chk["n"]:
                log(f"  timestamp cross-check vs provider: {chk['bad']:,} of {chk['n']:,} swap blocks differ"
                    + (" (!)" if chk["bad"] else " (all agree)"))

        # Binance download / metrics: a failure here (proxy outage, memory) must not kill the run — the swap
        # logs are the expensive part and are already cached; rerunning the same command completes the rest.
        try:
            bpath = step_binance(p["binance"], d0, d1, a.out, workers=WORKERS["logs"])
            cex = pd.read_parquet(bpath, columns=["ts_ms", "close"])
            ref = None
            if a.reference == "aggtrades":
                ref = A.AggTradeRef(step_binance_agg(p["binance"], d0, d1, a.out, workers=WORKERS["logs"]), lag_ms=a.ref_lag_ms)
            res_dir = os.path.join(a.out, RES, p["name"])
            t0 = time.time()
            reg, day, n_sw = A.run_chunks(blocks, chunks(), cex, fork_block, res_dir, block_range=(b0, b1), log=log, ref=ref)
            summary["pools"][p["name"]] = {"meta": meta, "n_swaps": int(n_sw), "regime": json.loads(reg.to_json())}
            log(f"{p['name']}: metrics done in {time.time() - t0:.0f}s ({n_sw:,} swaps, peak mem {peak_mem_gb():.1f} GB) -> {res_dir}")
            if ref is not None and "ref_kline_vs_tick_rms_bps" in reg.index:
                log(f"  reference noise (1s kline vs tick): RMS {reg.loc['ref_kline_vs_tick_rms_bps', 'pre']:.2f} / "
                    f"{reg.loc['ref_kline_vs_tick_rms_bps', 'post']:.2f} bp (pre / post)")
            del cex, reg, day, ref
        except KeyboardInterrupt:
            raise
        except Exception as e:  # noqa
            log(f"{p['name']}: metrics FAILED ({str(e)[:160]}) -> continuing with the next pool; rerun the same command later to fill it in")
            summary.setdefault("errors", {})[p["name"]] = str(e)[:300]
        with open(spath, "w") as f:
            json.dump(summary, f, indent=1, default=str)
        gc.collect()
    with open(spath, "w") as f:
        json.dump(summary, f, indent=1, default=str)
    if summary.get("errors"):
        log(f"WARNING: metrics missing for {', '.join(summary['errors'])} — rerun the same command to complete them")
    zpath = os.path.join(a.out, f"pilot_results{TAG}.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(spath, SUMMARY_NAME)
        for f in glob.glob(os.path.join(a.out, RES, "**", "*"), recursive=True):
            if os.path.isdir(f) or (f.endswith(".parquet") and not a.include_swaps):
                continue
            z.write(f, os.path.relpath(f, a.out))
        if a.include_swaps:
            for bp in (os.path.join(a.out, f"blocks_{a.fork}.parquet"), os.path.join(a.out, f"blocks_forkwindow_{a.fork}.parquet")):
                z.write(bp, os.path.basename(bp))
    log(f"done -> {zpath}")


if __name__ == "__main__":
    main()
