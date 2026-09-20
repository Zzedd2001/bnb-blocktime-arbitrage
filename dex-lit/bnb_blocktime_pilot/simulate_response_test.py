"""Offline test of arb_response.py on SIMULATED data with a KNOWN latency distribution (no network needed).

Three arbitrage bots with fixed latencies (250 / 500 / 900 ms, ±30 ms noise, each attentive with prob. 0.7) race
for every opportunity opened by a simulated Binance tick series (random walk with occasional jumps) or by noise
trades that push the pool price out of the fee band.  The winner lands in the first block sealed after
t_open + ℓ.  Blocks: 1.5 s for two days, then 0.75 s for two days.  The script writes the files arb_response.py
expects (summary_agg.json, timestamps table, results_agg/<pool>/swaps_enriched.parquet, binance_agg/<SYMBOL>/<day>)
and runs it; the estimated latency distribution should reproduce the winner-latency distribution printed here.

    python simulate_response_test.py --out sim_response
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys
import numpy as np, pandas as pd

DAY_MS = 86_400_000


def simulate(out: str, seed: int = 3, days_pre: int = 2, days_post: int = 2, dt_pre: int = 1500, dt_post: int = 750,
             gamma: float = 5e-4, ticks_per_sec: float = 4.0, sig_tick: float = 1.2e-4, jump_prob: float = 0.002,
             noise_per_block: float = 0.03, post_scale: float = 1.0):
    rng = np.random.default_rng(seed)
    t_start = 1_750_000_000_000 // DAY_MS * DAY_MS          # a day boundary (ms)
    T = (days_pre + days_post) * DAY_MS
    fork_ms = t_start + days_pre * DAY_MS
    # --- blocks
    n_pre = days_pre * DAY_MS // dt_pre; n_post = days_post * DAY_MS // dt_post
    bt = np.concatenate([t_start + np.arange(n_pre) * dt_pre, fork_ms + np.arange(n_post) * dt_post]).astype(np.int64)
    b0 = 50_000_000; nums = b0 + np.arange(len(bt)); fork_block = int(b0 + n_pre)
    # --- ticks: Poisson arrivals, log random walk with jumps
    n_t = int(T / 1000 * ticks_per_sec)
    tt = np.sort(rng.integers(t_start, t_start + T, n_t)).astype(np.int64)
    inc = rng.normal(0, sig_tick, n_t)
    jumps = rng.random(n_t) < jump_prob
    inc[jumps] += rng.normal(0, 6 * gamma, jumps.sum())
    price = 600.0 * np.exp(np.cumsum(inc))
    # --- bots
    bots = [("0xbotA", 250.0), ("0xbotB", 500.0), ("0xbotC", 900.0)]

    def winner(t_now=None):
        sc = post_scale if (t_now is not None and t_now >= fork_ms) else 1.0
        cands = [(sc * l + rng.normal(0, 30), n) for n, l in bots if rng.random() < 0.7]
        if not cands:
            cands = [(bots[2][1] + rng.normal(0, 30), bots[2][0])]
        l, n = min(cands)
        return max(l, 1.0), n
    # --- noise trades at random blocks
    noise_blocks = np.where(rng.random(len(bt)) < noise_per_block)[0]
    # --- event loop over ticks and noise trades (time order)
    ev_t = np.concatenate([tt, bt[noise_blocks]]); ev_k = np.concatenate([np.zeros(n_t, np.int8), np.ones(len(noise_blocks), np.int8)])
    ev_i = np.concatenate([np.arange(n_t), noise_blocks])
    order = np.lexsort((ev_k, ev_t)); ev_t, ev_k, ev_i = ev_t[order], ev_k[order], ev_i[order]
    p = price[0] * (1 + 0.5 * gamma)
    open_since, arb_block, arb_who, lat_true = None, None, None, []
    swaps, log_index = [], {}
    last_price = price[0]
    r_asof_idx = 0

    def record(bn, tb, sender, p_pre, p_post, r):
        li = log_index.get(bn, 0); log_index[bn] = li + 1
        dev_pre, dev_post = p_pre / r - 1, p_post / r - 1
        toward = (np.sign(dev_post - dev_pre) == -np.sign(dev_pre)) and abs(dev_post) < abs(dev_pre)
        is_arb = abs(dev_pre) > gamma and toward
        vol = abs(rng.exponential(5000.0))
        swaps.append({"block": int(bn), "log_index": li, "sender": sender, "ts_ms": int(tb), "p_pre": p_pre, "p_post": p_post, "p_cex": r,
                      "dev_pre": dev_pre, "dev_post": dev_post, "is_arb": bool(is_arb), "is_arb_strict": bool(is_arb and abs(dev_post) <= gamma),
                      "volume_q": vol, "arb_loss": vol * abs(dev_pre) * 0.5 if is_arb else 0.0, "fee_rate": gamma})

    def maybe_execute(t_now):
        """The scheduled arb block has been sealed before t_now: execute at that block with the as-of reference."""
        nonlocal p, open_since, arb_block, arb_who
        if arb_block is not None and bt[arb_block] <= t_now:
            tb = bt[arb_block]
            j = np.searchsorted(tt, tb, side="right") - 1
            r = price[j]
            dev = p / r - 1
            if abs(dev) > gamma:                                   # still open at the block: arbitrage to 0.8γ inside
                p_new = r * (1 + 0.8 * gamma * np.sign(dev))
                record(nums[arb_block], tb, arb_who, p, p_new, r)
                p = p_new
            open_since, arb_block, arb_who = None, None, None

    for t, k, i in zip(ev_t, ev_k, ev_i):
        maybe_execute(t)
        if k == 1:                                                  # noise trade at block i (executed at its block time)
            tb = bt[i]; j = np.searchsorted(tt, tb, side="right") - 1; r = price[j]
            p_new = p * np.exp(rng.normal(0, 2.5 * gamma))
            record(nums[i], tb, "0xrouter", p, p_new, r); p = p_new
            if abs(p / r - 1) > gamma and open_since is None:
                open_since = tb; l, who = winner(tb); lat_true.append(l)
                arb_block = int(np.searchsorted(bt, tb + l, side="left")); arb_who = who
                if arb_block >= len(bt):
                    arb_block = None
            elif abs(p / r - 1) <= gamma:
                open_since, arb_block, arb_who = None, None, None
            continue
        r = price[i]
        inside = abs(p / r - 1) <= gamma
        if inside:
            open_since, arb_block, arb_who = None, None, None
        elif open_since is None:
            open_since = t; l, who = winner(t); lat_true.append(l)
            arb_block = int(np.searchsorted(bt, t + l, side="left")); arb_who = who
            if arb_block >= len(bt):
                arb_block = None
    maybe_execute(t_start + T)
    sw = pd.DataFrame(swaps).sort_values(["block", "log_index"]).reset_index(drop=True)
    # --- write the pipeline layout
    pool = "WBNB-USDT-500"
    os.makedirs(os.path.join(out, "results_agg", pool), exist_ok=True)
    sw.to_parquet(os.path.join(out, "results_agg", pool, "swaps_enriched.parquet"), index=False)
    pd.DataFrame({"number": nums, "milli_ts": bt, "fetched": False}).to_parquet(os.path.join(out, f"timestamps_Maxwell_{nums[0]}_{nums[-1]}.parquet"), index=False)
    ddir = os.path.join(out, "binance_agg", "BNBUSDT"); os.makedirs(ddir, exist_ok=True)
    tk = pd.DataFrame({"ts_ms": tt, "price": price}).groupby("ts_ms", sort=True)["price"].last().reset_index()
    for day, g in tk.groupby(tk["ts_ms"] // DAY_MS):
        g.to_parquet(os.path.join(ddir, pd.Timestamp(day * DAY_MS, unit="ms", tz="UTC").strftime("%Y-%m-%d") + ".parquet"), index=False)
    S = {"fork": "Maxwell", "fork_block": fork_block, "blocks": [int(nums[0]), int(nums[-1])], "reference": "aggtrades", "ref_lag_ms": 0,
         "block_interval_before": dt_pre / 1000, "block_interval_after": dt_post / 1000, "pools": {pool: {"meta": {"fee": 500}}}}
    json.dump(S, open(os.path.join(out, "summary_agg.json"), "w"), indent=1)
    lat = np.array(lat_true)
    print(f"simulated {len(bt):,} blocks, {len(sw):,} swaps ({int(sw['is_arb'].sum()):,} arbs, {int(sw['is_arb_strict'].sum()):,} strict); "
          f"{len(lat):,} openings; TRUE winner latency: p10 {np.quantile(lat, .1):.0f}, p25 {np.quantile(lat, .25):.0f}, "
          f"median {np.median(lat):.0f}, p75 {np.quantile(lat, .75):.0f}, mean {lat.mean():.0f} ms")
    for name, dt in (("pre", dt_pre), ("post", dt_post)):
        print(f"  model P(k=1) {name}: {np.maximum(0, 1 - lat / dt).mean():.3f};  E[√τ] with τ = ℓ + U(0,Δt): "
              f"{np.mean([np.sqrt((lat + u) / 1000).mean() for u in np.linspace(0, dt, 50)]):.3f}")
    return sw


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default="sim_response"); ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--post-scale", type=float, default=1.0, help="multiply the bots' latencies after the fork (1 = unchanged)")
    a = ap.parse_args()
    simulate(a.out, seed=a.seed, post_scale=a.post_scale)
    here = os.path.dirname(os.path.abspath(__file__))
    subprocess.run([sys.executable, os.path.join(here, "arb_response.py"), "--out", a.out, "--fork", "Maxwell", "--pools", "WBNB-USDT-500",
                    "--days", "3", "--min-arbs", "5", "--min-pair", "20"], check=True)
