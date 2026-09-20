"""Offline end-to-end test of the pipeline on SIMULATED data (no network needed).

Simulates a CEX price (GBM), a constant-product pool with fee, one arbitrageur acting once per
block (moving the pool price to the edge of the no-arbitrage band) and Poisson noise traders,
under two block-interval regimes (1.5s -> 0.75s).  Emits data in exactly the schema produced by
find_blocks.py / fetch_swaps.py / fetch_binance.py and runs analyze_pilot.run().

Expected pattern (Milionis et al. 2023 with fees; Fritsch & Canidio 2024): arbitrage loss per unit of
volume falls when blocks get faster, arbitrage trades become more frequent but smaller.

    python simulate_test.py --hours 6 --out results/sim
"""
from __future__ import annotations
import argparse, numpy as np, pandas as pd
import analyze_pilot as A

Q96 = 2 ** 96


def simulate(hours=6.0, sigma_annual=0.8, fee=0.0005, L=2_000_000.0, p0=600.0, seed=1,
             pre_ms=1500, post_ms=750, noise_per_sec=0.3, noise_size_q=3000.0):
    rng = np.random.default_rng(seed)
    total_ms = int(hours * 3600 * 1000)
    switch_ms = total_ms // 2
    # --- CEX price path at 100ms resolution
    dt = 0.1
    n = total_ms // 100 + 1
    sig = sigma_annual / np.sqrt(365 * 86400)
    logp = np.log(p0) + np.cumsum(rng.normal(0, sig * np.sqrt(dt), n))
    cex_path = np.exp(logp)
    t_ms = np.arange(n) * 100
    # 1s klines: open_time = start of the second, close = last 100ms tick of that second
    n_sec = (n - 1) // 10
    cex_1s = pd.DataFrame({"ts_ms": np.arange(n_sec) * 1000, "close": cex_path[9:9 + 10 * n_sec:10]})
    # --- blocks
    ts, cur, num = [], 0, 1_000_000
    blocks = []
    while cur < total_ms:
        blocks.append({"number": num, "timestamp": cur // 1000, "milli_ts": cur, "gas_used": 0,
                       "gas_limit": 0, "tx_count": 0, "miner": "0x0"})
        num += 1
        cur += pre_ms if cur < switch_ms else post_ms
    blocks = pd.DataFrame(blocks)
    blocks["interval"] = blocks["milli_ts"].diff() / 1000
    fork_block = int(blocks.loc[blocks["milli_ts"] >= switch_ms, "number"].min())
    # --- pool state (constant product with liquidity L; token0 = base, token1 = quote)
    p = p0
    swaps = []

    def do_swap(block, log_index, p_target):
        nonlocal p
        if abs(p_target / p - 1) < 1e-9:
            return
        dx = L * (1 / np.sqrt(p_target) - 1 / np.sqrt(p))   # base change for the pool
        dy = L * (np.sqrt(p_target) - np.sqrt(p))           # quote change for the pool
        if dy > 0:      # trader buys base with quote: fee on quote input
            a0, a1 = dx, dy / (1 - fee)
        else:           # trader sells base: fee on base input
            a0, a1 = dx / (1 - fee), dy
        p = p_target
        swaps.append({"block": block, "tx": f"0x{block:x}{log_index:x}", "log_index": log_index,
                      "sender": "0xarb" if log_index == 0 else "0xnoise", "recipient": "0x0",
                      "amount0": int(a0 * 1e18), "amount1": int(a1 * 1e18),
                      "sqrt_price_x96": int(np.sqrt(p) * Q96), "liquidity": int(L * 1e18), "tick": 0,
                      "protocol_fee0": 0, "protocol_fee1": 0})

    for _, b in blocks.iterrows():
        P = cex_path[min(int(b["milli_ts"] // 100), n - 1)]
        li = 0
        # arbitrageur: move pool price to the edge of the band if outside it
        if p > P * (1 + fee):
            do_swap(int(b["number"]), li, P * (1 + fee)); li += 1
        elif p < P * (1 - fee):
            do_swap(int(b["number"]), li, P * (1 - fee)); li += 1
        # noise traders
        k = rng.poisson(noise_per_sec * (pre_ms if b["milli_ts"] < switch_ms else post_ms) / 1000)
        for _ in range(k):
            q = rng.exponential(noise_size_q) * rng.choice([-1, 1])
            # quote-denominated market order of size q: solve new price from constant product
            sp = np.sqrt(p) + (q * (1 - fee) if q > 0 else q) / L
            sp = max(sp, np.sqrt(p) * 0.5)
            do_swap(int(b["number"]), li, sp ** 2); li += 1
    swaps = pd.DataFrame(swaps)
    for k, v in {"pool": "0xpool", "token0": "0xbase", "token1": "0xquote", "fee": 500,
                 "base_is_token0": True, "dec0": 18, "dec1": 18}.items():
        swaps[k] = v
    return blocks, swaps, cex_1s, fork_block


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--hours", type=float, default=6); ap.add_argument("--out", default="results/sim")
    a = ap.parse_args()
    blocks, swaps, cex, fb = simulate(hours=a.hours)
    print(f"simulated {len(blocks)} blocks, {len(swaps)} swaps, fork block {fb}")
    reg, day, n_swaps = A.run(blocks, swaps, cex, fb, a.out)
