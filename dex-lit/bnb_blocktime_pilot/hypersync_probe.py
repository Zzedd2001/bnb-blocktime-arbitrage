"""Validate HyperSync against an existing eth_getLogs segment before relying on it:

    export ENVIO_API_TOKEN=...
    python hypersync_probe.py --segment full_maxwell/swaps_WBNB-USDT-500_52109843_52359842.parquet

Fetches the same pool's Swap logs over a 20,000-block slice of that segment from HyperSync and compares
row counts, first/last (block, log_index, tx) and the block timestamps with the reconstructed table."""
from __future__ import annotations
import argparse, glob, os, re, sys
import pandas as pd
import config as C
import fetch_hypersync as HS
from fetch_swaps import decode_swap


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--segment", required=True, help="an existing swaps_<pool>_<b0>_<b1>.parquet file")
    ap.add_argument("--blocks", type=int, default=20_000)
    ap.add_argument("--url", default=HS.DEFAULT_URL)
    a = ap.parse_args()
    m = re.search(r"swaps_(.+)_(\d+)_(\d+)\.parquet$", os.path.basename(a.segment))
    pool_name, s0, s1 = m.group(1), int(m.group(2)), int(m.group(3))
    ref = pd.read_parquet(a.segment)
    pool = str(ref["pool"].iloc[0])
    b0 = s0 + (s1 - s0) // 3; b1 = min(b0 + a.blocks - 1, s1)
    ref = ref[(ref.block >= b0) & (ref.block <= b1)].sort_values(["block", "log_index"]).reset_index(drop=True)
    print(f"{pool_name} pool {pool}: reference slice blocks {b0:,}..{b1:,} has {len(ref):,} swaps", file=sys.stderr)
    hs = HS.HyperSyncLogs(a.url)
    print("chain / height:", hs.probe(), file=sys.stderr)
    rows = []
    hs.fetch_range(pool, C.TOPIC_SWAP_PCS_V3, b0, b1, lambda logs, x, y: rows.extend(decode_swap(l) for l in logs),
                   lambda msg: print(msg, file=sys.stderr))
    got = pd.DataFrame(rows).sort_values(["block", "log_index"]).reset_index(drop=True)
    print(f"hypersync: {len(got):,} swaps; block_ts present for {int((got.block_ts > 0).sum()):,}", file=sys.stderr)
    ok = len(got) == len(ref) and (got["tx"].values == ref["tx"].values).all() and (got["block"].values == ref["block"].values).all()
    same_vals = ok and all((got[c].astype(str).values == ref[c].astype(str).values).all()
                           for c in ("log_index", "sender", "recipient", "amount0", "amount1", "sqrt_price_x96", "liquidity", "tick"))
    print("IDENTICAL to the eth_getLogs data" if same_vals else "MISMATCH — send this output back", file=sys.stderr)
    if not same_vals and len(got) and len(ref):
        print(ref.head(3).to_string(), file=sys.stderr); print(got.head(3).to_string(), file=sys.stderr)
    # timestamps vs the reconstructed table, if present next to the segment
    tdir = os.path.dirname(a.segment)
    tabs = glob.glob(os.path.join(tdir, "timestamps_*.parquet"))
    if tabs and len(got):
        t = pd.read_parquet(tabs[0], columns=["number", "milli_ts"])
        tb0 = int(t["number"].iloc[0])
        recon = t["milli_ts"].to_numpy()[got["block"].to_numpy() - tb0] // 1000
        bad = int((recon != got["block_ts"].to_numpy()).sum())
        print(f"timestamps: {bad} of {len(got):,} differ from the reconstructed table" + (" (!)" if bad else " (all agree)"), file=sys.stderr)


if __name__ == "__main__":
    main()
