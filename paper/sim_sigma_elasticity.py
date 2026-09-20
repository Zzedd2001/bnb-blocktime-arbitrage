#!/usr/bin/env python3
"""sim_sigma_elasticity.py — mechanical elasticities of the overshoot and its components to volatility in the
simulation of Appendix D (Table D1): three arbitrage bots with fixed latencies (250 / 500 / 900 ms) and no
behavioural response, reference volatility scaled by 0.5, 0.7, 1.0, 1.4 and 2.0.

For each scale the simulator of the pipeline (simulate_response_test.simulate) writes a synthetic fork
(1.5 s blocks for two days, then 0.75 s), arb_response.py reconstructs opening times and components, and the
number of arbitrages and the mean overshoot, jump J and movement M of the CEX-triggered arbitrages are recorded per regime.  The elasticity
is the log-log slope over the five runs.

    python3 sim_sigma_elasticity.py [--out <dir>] [--seed 3]

Writes sim_sigma_elasticity.md and sim_sigma_elasticity.json next to this script.
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("REPL_ROOT", os.path.abspath(os.path.join(HERE, "..")))
PIPE = os.path.join(ROOT, "dex-lit", "bnb_blocktime_pilot")
sys.path.insert(0, PIPE)
import simulate_response_test as S  # noqa: E402

SCALES = [0.5, 0.7, 1.0, 1.4, 2.0]
SIG_TICK = 1.2e-4  # the simulator's default per-tick volatility


def run(scale: float, out: str, seed: int, reuse: bool = False) -> dict:
    fn = os.path.join(out, "arb_response", "WBNB-USDT-500", "arbs.parquet")
    if not (reuse and os.path.exists(fn)):
        S.simulate(out, seed=seed, sig_tick=SIG_TICK * scale)
        subprocess.run([sys.executable, os.path.join(PIPE, "arb_response.py"), "--out", out, "--fork", "Maxwell",
                        "--pools", "WBNB-USDT-500", "--days", "3", "--min-arbs", "5", "--min-pair", "20"],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    a = pd.read_parquet(fn)
    cex = a[a["trigger"] == "cex"]          # J and M are defined for CEX-triggered arbitrages
    res = {}
    for reg in ("pre", "post"):
        c = cex[cex["regime"] == reg]
        res[reg] = {"n": int((a["regime"] == reg).sum()), "overshoot": float(c["overshoot_bps"].mean()),
                    "J": float(c["jump_bps"].mean()), "M": float(c["move_bps"].mean())}
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "sim_sigma"))
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--reuse", action="store_true", help="reuse simulated runs already in --out")
    a = ap.parse_args()
    rows = []
    for sc in SCALES:
        r = run(sc, os.path.join(a.out, f"scale_{sc}"), a.seed, a.reuse)
        for reg, dt in (("pre", 1.5), ("post", 0.75)):
            rows.append({"regime": reg, "block_s": dt, "scale": sc, **r[reg]})
    df = pd.DataFrame(rows)
    lines = ["# Mechanical σ-elasticities in the simulation (fixed latencies 250/500/900 ms, no behavioural response; "
             "σ scaled by 0.5–2.0)", "", "| regime | Δt | σ scale | n arbs | overshoot (bp) | J (bp) | M (bp) |",
             "|---|---|---|---|---|---|---|"]
    for _, r in df.iterrows():
        lines.append(f"| {r.regime} | {r.block_s} | ×{r.scale} | {int(r.n):,} | {r.overshoot:.2f} | {r.J:.2f} | {r.M:.2f} |")
    el, txt = {}, []
    for reg in ("pre", "post"):
        d = df[df.regime == reg]
        for k in ("overshoot", "J", "M", "n"):
            b = np.polyfit(np.log(d["scale"]), np.log(d[k].astype(float)), 1)[0]
            el[f"{reg} {k}"] = float(b); txt.append(f"{reg} {k}: {b:+.2f}")
    lines += ["", "Log-log slopes (elasticity to σ) over the five runs: " + "; ".join(txt)]
    open(os.path.join(HERE, "sim_sigma_elasticity.md"), "w").write("\n".join(lines) + "\n")
    json.dump(el, open(os.path.join(HERE, "sim_sigma_elasticity.json"), "w"), indent=1)
    print("\n".join(lines))


if __name__ == "__main__":
    main()
