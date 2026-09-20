"""Transaction senders (tx.from), targets (tx.to) and gas of the arbitrage contracts' swaps, from Envio HyperSync.

The pool's Swap event only records `sender` — the contract that called the pool.  One operator may use several
contracts and several externally owned accounts (EOAs); the EOA that signed the transaction is tx.from.  This script
fetches, for every swap of the pool whose `sender` is one of the active arbitrage contracts (≥ --min-arbs strict
arbitrages in the fork window, from arb_response/<pool>/arbs.parquet), the transaction's from/to/index/gas, joins
them to the strict arbitrages on (block, log_index) and writes

    <out>/arb_response/operators/<pool>_arbs_tx.parquet     strict arbs + tx_from, tx_to, tx_index, gas_used, gas_price
    <out>/arb_response/operators/<pool>_contracts.csv       per sender contract: transactions, distinct EOAs, top EOA share
    <out>/arb_txfrom_<fork>.zip                             the folder above, for upload

HyperSync is queried with the Swap topic and the sender addresses as topic1 (indexed), so only the bots' swaps are
transferred (a few million logs per fork at most, minutes); transaction fields come from the default log→transaction
join.  Needs `pip install hypersync` and ENVIO_API_TOKEN (as run_pilot.py --hypersync).

    python fetch_tx_from.py --out full_fermi --fork Fermi
    python fetch_tx_from.py --out full_fermi --fork Fermi --pools WBNB-USDT-500 ETH-USDT-500 BTCB-USDT-500 WBNB-USDT-100
"""
from __future__ import annotations
import argparse, asyncio, glob, json, os, re, shutil, sys, time, zipfile
import numpy as np, pandas as pd
import config as CFG
import fetch_hypersync as HS


def log(m):
    print(time.strftime("%H:%M:%S"), m, file=sys.stderr, flush=True)


MAX_RECONNECTS = 30          # outer reconnect attempts per pool (on top of the client's own 8 retries per request)


def topic_of(addr: str) -> str:
    return "0x" + "0" * 24 + addr.lower()[2:]


def _short_err(e) -> str:
    """One line from a hypersync error: the leaf reasons of its 'Caused by' chains with counts (e.g. 'tls handshake eof x8;
    peer closed connection without sending TLS close_notify x1') instead of the 40-line message."""
    # numbered lines "<n>: <reason>" at the same indentation form one chain (each caused by the next); the leaf of a chain is
    # the last line before the indentation decreases (or the end of the message)
    num = [(len(l) - len(l.lstrip()), m.group(1).strip()) for l in str(e).splitlines() for m in [re.match(r"^\s*\d+: ?(.*)$", l)] if m]
    leaves = []
    for i, (ind, txt) in enumerate(num):
        if txt and (i + 1 >= len(num) or num[i + 1][0] < ind):
            leaves.append(txt.split(": http")[0].strip())
    if not leaves:
        return " ".join(str(e).split())[:120]
    counts = {}
    for l in leaves:
        counts[l] = counts.get(l, 0) + 1
    return "; ".join(f"{k} x{v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1]))[:160]


def wait_for_hypersync(hsl, need_height: int, log=log) -> tuple[int, int]:
    """Probe chain id / archive height; keep retrying (60s x attempts, at most 300s) while the endpoint is unreachable."""
    fails = 0
    while True:
        try:
            return hsl.probe(need_height=need_height)
        except Exception as e:  # noqa
            if "archive height" in str(e):
                raise
            fails += 1
            wait = min(60 * fails, 300)
            log(f"hypersync unreachable ({_short_err(e)}); waiting {wait}s (attempt {fails}/{MAX_RECONNECTS})")
            if fails > MAX_RECONNECTS:
                raise
            time.sleep(wait)


def _int(x):
    if x is None:
        return -1
    if isinstance(x, int):
        return x
    s = str(x)
    return int(s, 16) if s.startswith("0x") else int(s)


def _topic1(l):
    """The indexed `sender` topic of a Swap log.  The client returns `topics` as a 4-list with None for topics that were
    not requested, so it is taken by position; a bare list without topic0 (as in v2.14–2.14.2, which requested only
    TOPIC1) is handled by dropping the Swap topic0 if present and taking the remaining single value."""
    t = getattr(l, "topics", None)
    if isinstance(t, (list, tuple)):
        if len(t) >= 2 and t[1]:
            return str(t[1])
        vals = [str(x) for x in t if x and str(x).lower() != CFG.TOPIC_SWAP_PCS_V3.lower()]
        return vals[0] if len(vals) == 1 else None
    v = getattr(l, "topic1", None)
    return str(v) if v else None


def contracts_table(X: pd.DataFrame, strict_counts: pd.Series) -> pd.DataFrame:
    """Per sender contract: swaps, transactions, distinct EOAs (tx.from), top-EOA shares, strict arbs, share of txs sent
    straight to the contract."""
    X = X.dropna(subset=["sender"])
    g = X.groupby("sender")
    C = pd.DataFrame({"swaps": g.size(), "transactions": g["tx_hash"].nunique(), "distinct_eoas": g["tx_from"].nunique(),
                      "distinct_tx_to": g["tx_to"].nunique()})
    top = X.groupby(["sender", "tx_from"]).size().reset_index(name="n").sort_values(["sender", "n"], ascending=[True, False])
    C["top_eoa"] = top.groupby("sender").head(1).set_index("sender")["tx_from"]
    C["top_eoa_share"] = (top.groupby("sender").head(1).set_index("sender")["n"] / C["swaps"])
    C["top3_eoa_share"] = top.groupby("sender").head(3).groupby("sender")["n"].sum() / C["swaps"]
    C["strict_arbs"] = strict_counts.reindex(C.index).fillna(0).astype(int)
    C["tx_to_equals_sender_share"] = (X["tx_to"].str.lower() == X["sender"].str.lower()).groupby(X["sender"]).mean()
    return C.sort_values("strict_arbs", ascending=False)


def rebuild_contracts(out: str, pools: list[str], min_arbs: int, log=log):
    """Offline repair for runs of v2.14–2.14.2, whose <pool>_bot_swaps.parquet has an empty `sender` column: recover the
    sender of every bot swap from results_agg/<pool>/swaps_enriched.parquet (block, log_index) and rewrite
    <pool>_contracts.csv.  No network needed."""
    import pyarrow.parquet as pq
    odir = os.path.join(out, "arb_response", "operators")
    for pool in pools:
        fb = os.path.join(odir, f"{pool}_bot_swaps.parquet")
        fa = os.path.join(out, "arb_response", pool, "arbs.parquet")
        fe = os.path.join(out, "results_agg", pool, "swaps_enriched.parquet")
        if not (os.path.exists(fb) and os.path.exists(fa)):
            log(f"{pool}: bot swaps or arbs missing, skipped"); continue
        X = pd.read_parquet(fb)
        if X["sender"].isna().all():
            if not os.path.exists(fe):
                log(f"{pool}: sender missing and {fe} not found, skipped"); continue
            pf = pq.ParquetFile(fe)
            key = X[["block", "log_index"]].astype("int64")
            parts = []
            for batch in pf.iter_batches(batch_size=1_000_000, columns=["block", "log_index", "sender"]):
                d = batch.to_pandas(); d["block"] = d["block"].astype("int64"); d["log_index"] = d["log_index"].astype("int64")
                d["sender"] = d["sender"].astype(str)
                parts.append(d.merge(key, on=["block", "log_index"], how="inner"))
            S = pd.concat(parts, ignore_index=True).drop_duplicates(["block", "log_index"])
            X = X.drop(columns=["sender"]).merge(S, on=["block", "log_index"], how="left")
            X["sender"] = X["sender"].str.lower()
            X.to_parquet(fb, index=False)
            log(f"{pool}: sender recovered for {X['sender'].notna().mean():.1%} of {len(X):,} bot swaps")
        d = pd.read_parquet(fa, columns=["sender", "is_arb_strict"])
        cnt = d.loc[d["is_arb_strict"], "sender"].astype(str).str.lower().value_counts()
        C = contracts_table(X, cnt)
        C.to_csv(os.path.join(odir, f"{pool}_contracts.csv"))
        log(f"{pool}: {len(C)} contracts -> {pool}_contracts.csv ({int((C['distinct_eoas'] >= 30).sum())} with >= 30 EOAs)")


def fetch_pool(client_factory, pool_addr: str, senders: list[str], b0: int, b1: int, parts_dir: str, max_logs: int = 100_000, log=log):
    """All Swap logs of `pool_addr` whose sender is in `senders`, with the joined transactions.  Resumable: every page is
    written to parts_dir/<from>_<to>.parquet as it arrives, and a rerun continues after the last complete page.  Network
    errors (the client already retries 8 times) are retried again here with a fresh client and a longer wait."""
    import hypersync as hs
    fsel = hs.FieldSelection(log=[hs.LogField.BLOCK_NUMBER, hs.LogField.LOG_INDEX, hs.LogField.TRANSACTION_HASH, hs.LogField.TOPIC0, hs.LogField.TOPIC1],
                             transaction=[hs.TransactionField.HASH, hs.TransactionField.FROM, hs.TransactionField.TO, hs.TransactionField.BLOCK_NUMBER,
                                          hs.TransactionField.TRANSACTION_INDEX, hs.TransactionField.GAS_USED, hs.TransactionField.EFFECTIVE_GAS_PRICE,
                                          hs.TransactionField.GAS_PRICE, hs.TransactionField.STATUS])
    topics = [[CFG.TOPIC_SWAP_PCS_V3], [topic_of(s) for s in senders]]
    os.makedirs(parts_dir, exist_ok=True)
    done = []
    for f in glob.glob(os.path.join(parts_dir, "*.parquet")):
        m = re.match(r"^(\d{12})_(\d{12})\.parquet$", os.path.basename(f))
        if m:
            done.append((int(m.group(1)), int(m.group(2))))
    start = max(b for _, b in done) + 1 if done else b0
    if done:
        log(f"  resuming after block {start - 1:,} ({len(done)} pages already on disk)")

    def page_to_frame(res):
        rows, txs = [], {}
        for l in (res.data.logs or []):
            t1 = _topic1(l)
            rows.append((_int(l.block_number), _int(l.log_index), l.transaction_hash, "0x" + t1[-40:].lower() if t1 else None))
        for t in (res.data.transactions or []):
            txs[t.hash] = (t.from_, t.to, _int(t.transaction_index), _int(t.gas_used), _int(t.effective_gas_price if t.effective_gas_price is not None else t.gas_price), _int(t.status))
        L = pd.DataFrame(rows, columns=["block", "log_index", "tx_hash", "sender"])
        T = pd.DataFrame([(h,) + v for h, v in txs.items()], columns=["tx_hash", "tx_from", "tx_to", "tx_index", "gas_used", "gas_price_wei", "status"])
        return L.merge(T, on="tx_hash", how="left") if len(L) else L

    async def _run():
        c = None
        cur, pages, t0, fails, reconnects = start, 0, time.time(), 0, 0
        while cur <= b1:
            q = hs.Query(from_block=cur, to_block=b1 + 1, field_selection=fsel, logs=[hs.LogSelection(address=[pool_addr], topics=topics)], max_num_logs=max_logs)
            try:
                if c is None:
                    c = client_factory()
                res = await c.get(q)
            except Exception as e:  # noqa
                fails += 1; reconnects += 1
                wait = min(60 * fails, 300)
                log(f"  hypersync request failed ({_short_err(e)}); waiting {wait}s and reconnecting (attempt {fails}/{MAX_RECONNECTS}; "
                    f"progress so far is on disk, rerun the same command to resume)")
                if fails > MAX_RECONNECTS:
                    raise
                await asyncio.sleep(wait)
                c = None
                continue
            fails = 0
            nb = int(res.next_block)
            if nb <= cur:
                raise RuntimeError(f"HyperSync made no progress at block {cur:,}")
            hi = min(nb - 1, b1)
            df = page_to_frame(res)
            tmp = os.path.join(parts_dir, f"{cur:012d}_{hi:012d}.parquet.part")
            df.to_parquet(tmp, index=False); os.replace(tmp, tmp[:-5])
            pages += 1
            if pages % 5 == 1 or hi >= b1:
                log(f"  hypersync: blocks {cur:,}..{hi:,} -> {len(df):,} bot swaps in this page ({pages} pages this run, {time.time() - t0:.0f}s)")
            cur = nb
            await asyncio.sleep(0.05)
        if reconnects:
            log(f"  ({reconnects} reconnects were needed for this pool)")
    asyncio.run(_run())
    parts = sorted(glob.glob(os.path.join(parts_dir, "*.parquet")))
    frames = [pd.read_parquet(f) for f in parts]
    frames = [f for f in frames if len(f)]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["block", "log_index", "tx_hash", "sender", "tx_from", "tx_to", "tx_index", "gas_used", "gas_price_wei", "status"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True); ap.add_argument("--fork", required=True, choices=list(CFG.FORKS))
    ap.add_argument("--pools", nargs="+", default=["WBNB-USDT-500", "ETH-USDT-500", "BTCB-USDT-500", "WBNB-USDT-100"])
    ap.add_argument("--min-arbs", type=int, default=20, help="strict arbitrages in the window for a sender contract to be fetched")
    ap.add_argument("--hypersync", default=HS.DEFAULT_URL)
    ap.add_argument("--max-senders", type=int, default=400)
    ap.add_argument("--force", action="store_true", help="refetch pools whose output already exists")
    ap.add_argument("--max-logs", type=int, default=100_000, help="logs per HyperSync page (lower it, e.g. 30000, on a flaky connection)")
    ap.add_argument("--rebuild-contracts", action="store_true",
                    help="no network: recover the sender of the fetched bot swaps from results_agg/<pool>/swaps_enriched.parquet, rewrite <pool>_contracts.csv and the zip")
    a = ap.parse_args()
    if a.rebuild_contracts:
        rebuild_contracts(a.out, a.pools, a.min_arbs)
        write_zip(a.out, a.fork)
        return
    if not HS.available():
        raise SystemExit("pip install hypersync  (and export ENVIO_API_TOKEN)")
    if not os.environ.get("ENVIO_API_TOKEN"):
        log("WARNING: ENVIO_API_TOKEN is not set")
    S = json.load(open(os.path.join(a.out, "summary_agg.json")))
    b0, b1 = map(int, S["blocks"])
    hsl = HS.HyperSyncLogs(a.hypersync)
    cid, height = wait_for_hypersync(hsl, b1)
    log(f"hypersync OK: chain {cid}, height {height:,}; window {b0:,}..{b1:,}")
    odir = os.path.join(a.out, "arb_response", "operators"); os.makedirs(odir, exist_ok=True)
    keep_cols = ["block", "log_index", "sender", "ts_ms", "regime", "days_from_fork", "trigger", "tau_ms", "tau_lo_ms", "k_blocks",
                 "overshoot_bps", "jump_bps", "move_bps", "volume_q", "arb_loss", "dev_pre", "fee_rate"]
    for pool in a.pools:
        f = os.path.join(a.out, "arb_response", pool, "arbs.parquet")
        if not os.path.exists(f):
            log(f"{pool}: no arbs.parquet, skipped"); continue
        if os.path.exists(os.path.join(odir, f"{pool}_arbs_tx.parquet")) and not a.force:
            log(f"{pool}: already done (use --force to refetch)"); continue
        meta = S["pools"].get(pool, {}).get("meta", {})
        pool_addr = meta.get("pool")
        if not pool_addr:
            log(f"{pool}: pool address missing in summary_agg.json, skipped"); continue
        d = pd.read_parquet(f, columns=[c for c in keep_cols if c] + ["is_arb_strict"])
        d = d[d["is_arb_strict"]].drop(columns=["is_arb_strict"])
        d["sender"] = d["sender"].astype(str)
        cnt = d["sender"].value_counts()
        senders = list(cnt[cnt >= a.min_arbs].index[: a.max_senders])
        log(f"{pool}: {len(d):,} strict arbs by {len(cnt):,} contracts; fetching tx data for {len(senders)} contracts covering "
            f"{cnt[senders].sum() / cnt.sum():.1%} of them")
        t0 = time.time()
        parts_dir = os.path.join(odir, f"{pool}_bot_swaps.parts")
        X = fetch_pool(hsl.client, pool_addr, senders, b0, b1, parts_dir, max_logs=a.max_logs)
        log(f"{pool}: {len(X):,} swaps of these contracts, {X['tx_hash'].nunique():,} transactions, in {time.time() - t0:.0f}s")
        X.to_parquet(os.path.join(odir, f"{pool}_bot_swaps.parquet"), index=False)
        shutil.rmtree(parts_dir, ignore_errors=True)
        if X["sender"].isna().mean() > 0.01:
            log(f"{pool}: WARNING sender (topic1) missing for {X['sender'].isna().mean():.1%} of the bot swaps; "
                f"the contract table will be incomplete (rerun with --rebuild-contracts afterwards)")
        # per-contract summary (all their swaps, not only arbs)
        C = contracts_table(X, cnt)
        C.to_csv(os.path.join(odir, f"{pool}_contracts.csv"))
        # join to the strict arbs
        J = d.merge(X.drop(columns=["sender"]), on=["block", "log_index"], how="left")
        J.to_parquet(os.path.join(odir, f"{pool}_arbs_tx.parquet"), index=False)
        log(f"{pool}: tx data attached to {J['tx_from'].notna().mean():.1%} of strict arbs -> {odir}")
    write_zip(a.out, a.fork)


def write_zip(out: str, fork: str, log=log):
    odir = os.path.join(out, "arb_response", "operators")
    zpath = os.path.join(out, f"arb_txfrom_{fork}.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in glob.glob(os.path.join(odir, "*")):
            if f.endswith("_bot_swaps.parquet") or os.path.isdir(f):
                continue                       # kept locally (large); the joined arbs and contract tables are enough
            z.write(f, os.path.relpath(f, out))
    log(f"done -> {zpath}")


if __name__ == "__main__":
    main()
